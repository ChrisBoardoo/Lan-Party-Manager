"""Gear / BYO — /api/gear

The per-event "who's bringing what" list. Members **pledge** kit they're hauling
to the LAN; admins post **requests** ("we need a 4th monitor") that a member can
**claim**. A personal **gear locker** (a user's past pledges, deduped) powers
one-tap carryover into a new event — because at a friends LAN everyone brings the
same car-boot of kit every time.

All endpoints are gated by the `gear` feature flag (non-admins get 404 when it's
off; admins always pass so they can configure it first), mirroring Planning.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import GearItem, LanEvent, User
from schemas import (
    GearItemCreate, GearItemUpdate, GearItemOut, GearEventOut,
    GearSuggestion, GearCarryover,
)
from router_settings import require_feature, is_feature_enabled
from auth import require_admin
from activity import add_activity

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _event_or_404(db: Session, event_id: int) -> LanEvent:
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


def _item_or_404(db: Session, item_id: int) -> GearItem:
    item = db.query(GearItem).filter(GearItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Gear item not found")
    return item


def _serialize(item: GearItem) -> GearItemOut:
    """Build the Out with the pledger's display fields read from the relationship."""
    return GearItemOut(
        id=item.id,
        event_id=item.event_id,
        name=item.name,
        category=item.category,
        quantity=item.quantity or 1,
        note=item.note,
        is_request=bool(item.is_request),
        pledged_by=item.pledged_by,
        pledged_username=item.pledger.username if item.pledger else None,
        pledged_avatar_url=item.pledger.avatar_url if item.pledger else None,
        created_by=item.created_by,
        created_at=item.created_at,
    )


def _event_payload(db: Session, event_id: int) -> GearEventOut:
    items = (
        db.query(GearItem)
        .options(selectinload(GearItem.pledger))  # avoid an N+1 on the pledger per row
        .filter(GearItem.event_id == event_id)
        .order_by(GearItem.is_request.desc(), GearItem.created_at)
        .all()
    )
    out = [_serialize(i) for i in items]
    pledged = sum(1 for i in items if i.pledged_by is not None)
    open_reqs = sum(1 for i in items if i.is_request and i.pledged_by is None)
    return GearEventOut(
        event_id=event_id, items=out, pledged_count=pledged, open_request_count=open_reqs
    )


def _can_manage(item: GearItem, user: User) -> bool:
    return user.role == "admin" or item.created_by == user.id or item.pledged_by == user.id


# ── Read ────────────────────────────────────────────────────────────────────────

@router.get("/events/{event_id}", response_model=GearEventOut)
def get_gear(
    event_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("gear")),
):
    """The whole gear list for one event in a single call."""
    _event_or_404(db, event_id)
    return _event_payload(db, event_id)


@router.get("/suggestions", response_model=list[GearSuggestion])
def gear_locker(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("gear")),
):
    """The current user's personal gear locker: everything they've pledged before,
    de-duplicated by name (case-insensitive), most-recent first. Drives the
    pre-ticked carryover panel on a new event."""
    past = (
        db.query(GearItem)
        .options(selectinload(GearItem.event))  # avoid an N+1 on event.title per row
        .filter(GearItem.pledged_by == user.id, GearItem.is_request.is_(False))
        .order_by(GearItem.created_at.desc())
        .all()
    )
    locker: dict[str, GearSuggestion] = {}
    counts: dict[str, int] = {}
    for it in past:
        key = it.name.strip().lower()
        counts[key] = counts.get(key, 0) + 1
        if key not in locker:
            # First (most recent) occurrence seeds the display fields.
            locker[key] = GearSuggestion(
                name=it.name.strip(),
                category=it.category,
                quantity=it.quantity or 1,
                times_brought=0,
                last_event_title=it.event.title if it.event else None,
            )
    result = []
    for key, s in locker.items():
        s.times_brought = counts[key]
        result.append(s)
    # Most brought, then most recent (insertion order already recency-desc).
    result.sort(key=lambda s: -s.times_brought)
    return result[:40]


# ── Pledge / request / carryover ──────────────────────────────────────────────

@router.post("/events/{event_id}/items", response_model=GearItemOut, status_code=201)
def pledge_item(
    event_id: int,
    data: GearItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("gear")),
):
    """A member pledges kit they're bringing."""
    _event_or_404(db, event_id)
    item = GearItem(
        event_id=event_id,
        name=data.name.strip(),
        category=data.category,
        quantity=data.quantity,
        note=data.note,
        pledged_by=user.id,
        is_request=False,
        created_by=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    add_activity(db, user.id, "gear_pledged", f"Bringing {item.name}", "gear_item", item.id)
    db.commit()
    return _serialize(item)


@router.post("/events/{event_id}/requests", response_model=GearItemOut, status_code=201)
def request_item(
    event_id: int,
    data: GearItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """An admin posts a need ("we need a 4th monitor") a member can claim. Requires
    the gear feature enabled: there's no point posting a request members can't see
    (mirrors the read endpoint's gate, applied to admins here too)."""
    if not is_feature_enabled(db, "gear"):
        raise HTTPException(404, "This feature is not enabled")
    _event_or_404(db, event_id)
    item = GearItem(
        event_id=event_id,
        name=data.name.strip(),
        category=data.category,
        quantity=data.quantity,
        note=data.note,
        pledged_by=None,
        is_request=True,
        created_by=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.post("/events/{event_id}/carryover", response_model=GearEventOut)
def carryover(
    event_id: int,
    data: GearCarryover,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("gear")),
):
    """Bulk-pledge the confirmed set from the user's gear locker. Skips any item
    the user has already pledged for this event (idempotent re-runs)."""
    _event_or_404(db, event_id)
    existing = {
        i.name.strip().lower()
        for i in db.query(GearItem).filter(
            GearItem.event_id == event_id, GearItem.pledged_by == user.id
        ).all()
    }
    added = 0
    for entry in data.items:
        if entry.name.strip().lower() in existing:
            continue
        db.add(GearItem(
            event_id=event_id,
            name=entry.name.strip(),
            category=entry.category,
            quantity=entry.quantity,
            pledged_by=user.id,
            is_request=False,
            created_by=user.id,
        ))
        existing.add(entry.name.strip().lower())
        added += 1
    if added:
        db.commit()
        add_activity(db, user.id, "gear_carryover", f"Brought {added} usual item(s)", "lan_event", event_id)
        db.commit()
    return _event_payload(db, event_id)


# ── Claim / release / edit / delete ───────────────────────────────────────────

@router.post("/items/{item_id}/claim", response_model=GearItemOut)
def claim_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("gear")),
):
    """Claim an open request — 'I'll bring that.'"""
    item = _item_or_404(db, item_id)
    if not item.is_request:
        raise HTTPException(400, "This item isn't an open request")
    if item.pledged_by is not None:
        raise HTTPException(409, "Already claimed")
    item.pledged_by = user.id
    db.commit()
    db.refresh(item)
    add_activity(db, user.id, "gear_claimed", f"Claimed {item.name}", "gear_item", item.id)
    db.commit()
    return _serialize(item)


@router.post("/items/{item_id}/unclaim", response_model=GearItemOut)
def unclaim_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("gear")),
):
    """Release a request you'd claimed (keeps the request open for someone else)."""
    item = _item_or_404(db, item_id)
    if not item.is_request:
        raise HTTPException(400, "This item isn't a request")
    if item.pledged_by != user.id and user.role != "admin":
        raise HTTPException(403, "Only the claimer or an admin can release this")
    item.pledged_by = None
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.put("/items/{item_id}", response_model=GearItemOut)
def update_item(
    item_id: int,
    data: GearItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("gear")),
):
    item = _item_or_404(db, item_id)
    if not _can_manage(item, user):
        raise HTTPException(403, "Not allowed to edit this item")
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "name":
            # name is NOT NULL — ignore an explicit null/blank rather than 500 on commit.
            if not value or not value.strip():
                continue
            value = value.strip()
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("gear")),
):
    item = _item_or_404(db, item_id)
    if not _can_manage(item, user):
        raise HTTPException(403, "Not allowed to delete this item")
    db.delete(item)
    db.commit()
    return {"ok": True}
