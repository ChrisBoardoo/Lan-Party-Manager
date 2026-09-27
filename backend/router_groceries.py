"""Groceries / courses — /api/groceries

The per-event food/drink shopping list ("Courses"). Any attendee can add an
item, pick who's responsible for buying it (a dropdown of event attendees,
built on the frontend from the event's own attendee list), and tick it off
once bought. No price field — actual cost splitting stays in Treasury,
entered by hand by the treasurer.

All endpoints are gated by the `groceries` feature flag (non-admins get 404
when it's off; admins always pass so they can configure it first), mirroring
Gear/Planning.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import GroceryItem, LanEvent, User
from schemas import (
    GroceryItemCreate, GroceryItemUpdate, GroceryItemOut, GroceryEventOut,
    GroceryImport, GroceryImportResult,
)
from router_settings import require_feature

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _event_or_404(db: Session, event_id: int) -> LanEvent:
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


def _item_or_404(db: Session, item_id: int) -> GroceryItem:
    item = db.query(GroceryItem).filter(GroceryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Grocery item not found")
    return item


def _serialize(item: GroceryItem) -> GroceryItemOut:
    return GroceryItemOut(
        id=item.id,
        event_id=item.event_id,
        category=item.category,
        name=item.name,
        quantity=item.quantity,
        assigned_to=item.assigned_to,
        assigned_username=item.assignee.username if item.assignee else None,
        assigned_avatar_url=item.assignee.avatar_url if item.assignee else None,
        is_bought=bool(item.is_bought),
        created_by=item.created_by,
        created_at=item.created_at,
    )


def _event_payload(db: Session, event_id: int) -> GroceryEventOut:
    items = (
        db.query(GroceryItem)
        .options(selectinload(GroceryItem.assignee))  # avoid an N+1 on the assignee per row
        .filter(GroceryItem.event_id == event_id)
        .order_by(GroceryItem.created_at)
        .all()
    )
    out = [_serialize(i) for i in items]
    bought = sum(1 for i in items if i.is_bought)
    return GroceryEventOut(event_id=event_id, items=out, bought_count=bought, total_count=len(items))


def _can_manage(item: GroceryItem, user: User) -> bool:
    return user.role == "admin" or item.created_by == user.id or item.assigned_to == user.id


# ── Read ────────────────────────────────────────────────────────────────────────

@router.get("/events/{event_id}", response_model=GroceryEventOut)
def get_groceries(
    event_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("groceries")),
):
    """The whole groceries list for one event in a single call."""
    _event_or_404(db, event_id)
    return _event_payload(db, event_id)


# ── Add / edit / delete ───────────────────────────────────────────────────────

@router.post("/events/{event_id}/items", response_model=GroceryItemOut, status_code=201)
def add_item(
    event_id: int,
    data: GroceryItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("groceries")),
):
    """Any attendee can add a grocery item, optionally assigning who's buying it."""
    _event_or_404(db, event_id)
    if data.assigned_to is not None:
        if not db.query(User).filter(User.id == data.assigned_to).first():
            raise HTTPException(400, "Unknown assigned_to user")
    item = GroceryItem(
        event_id=event_id,
        category=data.category,
        name=data.name.strip(),
        quantity=data.quantity,
        assigned_to=data.assigned_to,
        created_by=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.post("/events/{event_id}/import", response_model=GroceryImportResult)
def import_items(
    event_id: int,
    data: GroceryImport,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("groceries")),
):
    """Bulk-add items — the CSV-import counterpart to the one-at-a-time add
    form (frontend parses the CSV client-side and posts the parsed rows here,
    same shape the export produces, so export-then-reimport round-trips).

    A row whose `assigned_username` doesn't match any account still creates
    the item (unassigned) rather than failing the whole import — one typo'd
    name in a 50-row sheet shouldn't lose the other 49 rows. Unmatched names
    are collected and returned so the caller can show what was skipped."""
    _event_or_404(db, event_id)

    usernames = {row.assigned_username.strip().lower() for row in data.items if row.assigned_username}
    users_by_username = {
        u.username.lower(): u.id
        for u in db.query(User).filter(func.lower(User.username).in_(usernames)).all()
    } if usernames else {}

    unmatched: set[str] = set()
    imported = 0
    for row in data.items:
        assigned_to = None
        if row.assigned_username:
            key = row.assigned_username.strip().lower()
            assigned_to = users_by_username.get(key)
            if assigned_to is None:
                unmatched.add(row.assigned_username.strip())
        db.add(GroceryItem(
            event_id=event_id,
            category=row.category,
            name=row.name.strip(),
            quantity=row.quantity,
            assigned_to=assigned_to,
            is_bought=row.is_bought,
            created_by=user.id,
        ))
        imported += 1
    db.commit()
    return GroceryImportResult(imported=imported, unmatched_usernames=sorted(unmatched))


@router.put("/items/{item_id}", response_model=GroceryItemOut)
def update_item(
    item_id: int,
    data: GroceryItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("groceries")),
):
    """Edit an item — name/category/quantity/assignee, or tick it off as bought.
    Only the item's creator, its current assignee, or an admin may edit it."""
    item = _item_or_404(db, item_id)
    if not _can_manage(item, user):
        raise HTTPException(403, "Not allowed to edit this item")
    fields = data.model_dump(exclude_unset=True)
    if "assigned_to" in fields and fields["assigned_to"] is not None:
        if not db.query(User).filter(User.id == fields["assigned_to"]).first():
            raise HTTPException(400, "Unknown assigned_to user")
    for field, value in fields.items():
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
    user: User = Depends(require_feature("groceries")),
):
    item = _item_or_404(db, item_id)
    if not _can_manage(item, user):
        raise HTTPException(403, "Not allowed to delete this item")
    db.delete(item)
    db.commit()
    return {"ok": True}
