"""Event checklist — /api/checklist

A member's **private** packing checklist for one event: 9 fixed pre-filled
items (Computer, Screen, Screen PSU, Keyboard & Mouse, Cables, MousePad,
Headset, Vanity, Backpack) plus up to 10 custom fields, mirroring the My Setup
split (fixed columns for the translated vocabulary, a capped custom-fields
table for whatever a member invents).

Gated by the `checklist` feature flag (opt-in, default off), mirroring Gear.

**Private, structurally.** Unlike Gear — a shared pledge board — nobody but
the owner ever sees a checklist row, not even an admin. Every route here
resolves "the caller's own checklist for this event"; there is no route that
can name another user's row, so there's no `if user.id != owner_id` check to
forget. For the same reason, checklist activity is deliberately NOT posted to
the shared activity feed (add_activity) — that feed is public-by-design, and
"ticked Cables for LANFest" is nobody else's business.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import EventChecklist, EventChecklistField, LanEvent, User
from schemas import (
    CHECKLIST_FIXED_FIELDS,
    MAX_CHECKLIST_CUSTOM_FIELDS,
    ChecklistFieldOut,
    ChecklistItems,
    ChecklistOut,
    ChecklistSuggestion,
    ChecklistUpdate,
)
from router_settings import require_feature

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _event_or_404(db: Session, event_id: int) -> LanEvent:
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


def _load(db: Session, event_id: int, user_id: int) -> Optional[EventChecklist]:
    return (
        db.query(EventChecklist)
        .options(selectinload(EventChecklist.fields))
        .filter(EventChecklist.event_id == event_id, EventChecklist.user_id == user_id)
        .first()
    )


def _get_or_create(db: Session, event_id: int, user_id: int) -> EventChecklist:
    checklist = _load(db, event_id, user_id)
    if not checklist:
        checklist = EventChecklist(event_id=event_id, user_id=user_id)
        db.add(checklist)
        db.commit()
        db.refresh(checklist)
    return checklist


def _items(checklist: Optional[EventChecklist]) -> ChecklistItems:
    if not checklist:
        return ChecklistItems()
    return ChecklistItems(**{name: bool(getattr(checklist, name)) for name in CHECKLIST_FIXED_FIELDS})


def _sorted_fields(checklist: EventChecklist) -> list[EventChecklistField]:
    return sorted(checklist.fields, key=lambda f: (f.sort_order, f.id))


def _serialize(event_id: int, checklist: Optional[EventChecklist]) -> ChecklistOut:
    items = _items(checklist)
    fields = [ChecklistFieldOut.model_validate(f) for f in (_sorted_fields(checklist) if checklist else [])]
    checked = sum(1 for name in CHECKLIST_FIXED_FIELDS if getattr(items, name)) + sum(1 for f in fields if f.checked)
    total = len(CHECKLIST_FIXED_FIELDS) + len(fields)
    return ChecklistOut(
        event_id=event_id,
        items=items,
        custom_fields=fields,
        started=checklist is not None,
        progress_checked=checked,
        progress_total=total,
    )


def _most_recent_other(db: Session, user_id: int, exclude_event_id: Optional[int]) -> Optional[EventChecklist]:
    """The user's most recently updated checklist that isn't (a) for the
    excluded event or (b) entirely empty — an all-unticked, field-less
    checklist has nothing worth carrying over."""
    query = (
        db.query(EventChecklist)
        .options(selectinload(EventChecklist.fields))
        .filter(EventChecklist.user_id == user_id)
    )
    if exclude_event_id is not None:
        query = query.filter(EventChecklist.event_id != exclude_event_id)
    candidates = query.order_by(EventChecklist.updated_at.desc()).all()
    for candidate in candidates:
        has_ticked_fixed = any(getattr(candidate, name) for name in CHECKLIST_FIXED_FIELDS)
        if has_ticked_fixed or candidate.fields:
            return candidate
    return None


# ── Read / write my checklist ────────────────────────────────────────────────

@router.get("/events/{event_id}", response_model=ChecklistOut)
def get_my_checklist(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("checklist")),
):
    """Returns an empty shape rather than 404 when nothing's been saved yet —
    same as My Setup's get_my_setup."""
    _event_or_404(db, event_id)
    return _serialize(event_id, _load(db, event_id, user.id))


@router.put("/events/{event_id}", response_model=ChecklistOut)
def update_my_checklist(
    event_id: int,
    data: ChecklistUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("checklist")),
):
    """Save the 9 fixed items and the whole custom-field list in one request.

    Custom fields are replace-all (delete then re-insert, re-enumerating
    sort_order) — the same <=10-list semantics as My Setup's update_my_setup.
    """
    if len(data.custom_fields) > MAX_CHECKLIST_CUSTOM_FIELDS:
        raise HTTPException(400, f"A checklist is limited to {MAX_CHECKLIST_CUSTOM_FIELDS} custom fields")

    _event_or_404(db, event_id)
    checklist = _get_or_create(db, event_id, user.id)

    for name, value in data.items.model_dump().items():
        setattr(checklist, name, bool(value))

    for existing in list(checklist.fields):
        db.delete(existing)
    db.flush()
    for i, field in enumerate(data.custom_fields):
        db.add(EventChecklistField(
            checklist_id=checklist.id, label=field.label.strip(),
            checked=field.checked, sort_order=i,
        ))

    db.commit()
    db.refresh(checklist)
    return _serialize(event_id, checklist)


# ── Carryover — "copy my usual list" ─────────────────────────────────────────

@router.get("/suggestions", response_model=Optional[ChecklistSuggestion])
def checklist_suggestion(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("checklist")),
):
    """The user's most recent non-empty checklist from another event — powers
    the "copy your usual list" banner. None if they've never filled one in."""
    source = _most_recent_other(db, user.id, exclude_event_id=None)
    if not source:
        return None
    event = db.query(LanEvent).filter(LanEvent.id == source.event_id).first()
    return ChecklistSuggestion(
        source_event_id=source.event_id,
        source_event_title=event.title if event else "",
        items=_items(source),
        custom_fields=[ChecklistFieldOut.model_validate(f) for f in _sorted_fields(source)],
    )


@router.post("/events/{event_id}/carryover", response_model=ChecklistOut)
def carryover(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("checklist")),
):
    """Merge the user's most recent other checklist into this event's: fixed
    items OR'd together, custom fields appended by case-insensitive label if
    not already present (capped). Safe to call more than once."""
    _event_or_404(db, event_id)
    source = _most_recent_other(db, user.id, exclude_event_id=event_id)
    checklist = _get_or_create(db, event_id, user.id)
    if not source:
        return _serialize(event_id, checklist)

    for name in CHECKLIST_FIXED_FIELDS:
        if getattr(source, name):
            setattr(checklist, name, True)

    existing_labels = {f.label.strip().lower() for f in checklist.fields}
    room = MAX_CHECKLIST_CUSTOM_FIELDS - len(checklist.fields)
    next_order = len(checklist.fields)
    for field in _sorted_fields(source):
        if room <= 0:
            break
        key = field.label.strip().lower()
        if key in existing_labels:
            continue
        db.add(EventChecklistField(
            checklist_id=checklist.id, label=field.label.strip(),
            checked=field.checked, sort_order=next_order,
        ))
        existing_labels.add(key)
        next_order += 1
        room -= 1

    db.commit()
    db.refresh(checklist)
    return _serialize(event_id, checklist)
