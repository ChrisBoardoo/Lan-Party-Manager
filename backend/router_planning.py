"""Planning "Calendar View" — /api/planning

Members propose games for an event, approval-vote on the *hours* they'd play each
(bounded by their own RSVP arrival/departure window — "honest slots"), and an
organizer locks a final pick that surfaces on the event card / kiosk.

Behaviour is governed by two independent per-event toggles (with a global
default): `can_propose` and `can_vote`. Both on = "Friends LAN", both off =
"Professional LAN", propose-off + vote-on = "admins propose, members vote".

All endpoints are gated by the `planning` feature flag (non-admins get 404 when
it's off; admins always pass so they can configure it first).
"""
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ScheduleBlock, BlockVote, LanEvent, EventRSVP, User
from schemas import (
    ScheduleBlockCreate, ScheduleBlockOut, BlockVoteSet, BlockLock,
    SlotTally, PlanningEventOut, ViewPreferenceSet,
)
from router_settings import require_feature, planning_defaults
from activity import add_activity

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _event_or_404(db: Session, event_id: int) -> LanEvent:
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


def _block_or_404(db: Session, block_id: int) -> ScheduleBlock:
    block = db.query(ScheduleBlock).filter(ScheduleBlock.id == block_id).first()
    if not block:
        raise HTTPException(404, "Schedule block not found")
    return block


def _effective_toggles(db: Session, event: LanEvent) -> tuple[bool, bool]:
    """Resolve (can_propose, can_vote): the per-event override if set, else the
    global default from app_settings."""
    default_propose, default_vote = planning_defaults(db)
    propose = event.planning_can_propose if event.planning_can_propose is not None else default_propose
    vote = event.planning_can_vote if event.planning_can_vote is not None else default_vote
    return bool(propose), bool(vote)


def _my_rsvp(db: Session, event_id: int, user_id: int) -> EventRSVP | None:
    return (
        db.query(EventRSVP)
        .filter(
            EventRSVP.event_id == event_id,
            EventRSVP.user_id == user_id,
            EventRSVP.status == "in",
        )
        .first()
    )


def _check_hour_in_window(dt: datetime, event: LanEvent) -> None:
    """A time must be top-of-the-hour and fall on a day within the event window."""
    if dt.minute or dt.second or dt.microsecond:
        raise HTTPException(400, "Times must be on the hour")
    if dt.date() < event.start_date or dt.date() > event.end_date:
        raise HTTPException(400, "Time is outside the event window")


def _check_vote_slot(slot: datetime, event: LanEvent, rsvp: EventRSVP) -> None:
    """A vote slot must be within the event window AND within the voter's own
    RSVP arrival/departure window (honest slots)."""
    _check_hour_in_window(slot, event)
    lo = rsvp.arrival_date or event.start_date
    hi = rsvp.departure_date or event.end_date
    if slot.date() < lo or slot.date() > hi:
        raise HTTPException(400, "Slot is outside your arrival/departure window")


def _serialize_block(block: ScheduleBlock, user_id: int) -> ScheduleBlock:
    """Monkey-patch the computed vote aggregates onto the ORM instance so
    ScheduleBlockOut can read them via getattr (the EventOut pattern)."""
    counter = Counter(v.slot_start for v in block.votes)
    block.tallies = [SlotTally(slot_start=s, count=c) for s, c in sorted(counter.items())]
    block.my_slots = sorted(v.slot_start for v in block.votes if v.user_id == user_id)
    return block


# ── Read ────────────────────────────────────────────────────────────────────────

@router.get("/events/{event_id}", response_model=PlanningEventOut)
def get_planning(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("planning")),
):
    """Everything the PLAN page needs for one event in a single call."""
    event = _event_or_404(db, event_id)
    can_propose, can_vote = _effective_toggles(db, event)
    rsvp = _my_rsvp(db, event_id, user.id)
    blocks = (
        db.query(ScheduleBlock)
        .filter(ScheduleBlock.event_id == event_id)
        .order_by(ScheduleBlock.id)
        .all()
    )
    for b in blocks:
        _serialize_block(b, user.id)
    return PlanningEventOut(
        event_id=event.id,
        event_start=event.start_date,
        event_end=event.end_date,
        can_propose=can_propose,
        can_vote=can_vote,
        my_arrival_date=rsvp.arrival_date if rsvp else None,
        my_departure_date=rsvp.departure_date if rsvp else None,
        is_attending=rsvp is not None,
        my_schedule_view=user.planning_schedule_view,
        blocks=blocks,
    )


@router.patch("/view-preference")
def set_view_preference(
    data: ViewPreferenceSet,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("planning")),
):
    """Save the current user's Schedule tab display preference (list/calendar)
    on their account — deliberately narrow (just this one field), not a
    general-purpose preferences endpoint."""
    user.planning_schedule_view = data.view
    db.commit()
    return {"ok": True}


# ── Propose / delete ──────────────────────────────────────────────────────────────

@router.post("/events/{event_id}/blocks", response_model=ScheduleBlockOut, status_code=201)
def propose_block(
    event_id: int,
    data: ScheduleBlockCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("planning")),
):
    event = _event_or_404(db, event_id)
    can_propose, _ = _effective_toggles(db, event)
    if user.role != "admin" and not can_propose:
        raise HTTPException(403, "Proposing games is disabled for this event")

    if data.proposed_start and data.proposed_end and data.proposed_end <= data.proposed_start:
        raise HTTPException(400, "proposed_end must be after proposed_start")
    for dt in (data.proposed_start, data.proposed_end):
        if dt is not None:
            _check_hour_in_window(dt, event)

    block = ScheduleBlock(
        event_id=event_id,
        game=data.game.strip(),
        proposed_start=data.proposed_start,
        proposed_end=data.proposed_end,
        created_by=user.id,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    add_activity(db, user.id, "block_proposed", f"Proposed {block.game}", "schedule_block", block.id)
    db.commit()
    return _serialize_block(block, user.id)


@router.delete("/blocks/{block_id}")
def delete_block(
    block_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("planning")),
):
    block = _block_or_404(db, block_id)
    if user.role != "admin" and block.created_by != user.id:
        raise HTTPException(403, "Only the proposer or an admin can delete this")
    db.delete(block)
    db.commit()
    return {"ok": True}


# ── Vote ──────────────────────────────────────────────────────────────────────────

@router.put("/blocks/{block_id}/votes", response_model=ScheduleBlockOut)
def set_votes(
    block_id: int,
    data: BlockVoteSet,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("planning")),
):
    """Replace the current user's approved hour-slots for this block."""
    block = _block_or_404(db, block_id)
    event = _event_or_404(db, block.event_id)
    _, can_vote = _effective_toggles(db, event)
    if user.role != "admin" and not can_vote:
        raise HTTPException(403, "Voting is disabled for this event")

    rsvp = _my_rsvp(db, event.id, user.id)
    if rsvp is None:
        raise HTTPException(400, "RSVP to the event before voting on slots")

    slots = sorted(set(data.slots))
    for slot in slots:
        _check_vote_slot(slot, event, rsvp)

    db.query(BlockVote).filter(
        BlockVote.block_id == block_id, BlockVote.user_id == user.id
    ).delete()
    for slot in slots:
        db.add(BlockVote(block_id=block_id, user_id=user.id, slot_start=slot))
    db.commit()
    db.refresh(block)
    return _serialize_block(block, user.id)


# ── Lock / unlock ─────────────────────────────────────────────────────────────────

@router.post("/blocks/{block_id}/lock", response_model=ScheduleBlockOut)
def lock_block(
    block_id: int,
    data: BlockLock,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("planning")),
):
    block = _block_or_404(db, block_id)
    event = _event_or_404(db, block.event_id)
    if user.role != "admin" and block.created_by != user.id:
        raise HTTPException(403, "Only the proposer or an admin can lock this")
    if data.locked_end <= data.locked_start:
        raise HTTPException(400, "locked_end must be after locked_start")
    for dt in (data.locked_start, data.locked_end):
        _check_hour_in_window(dt, event)

    block.status = "locked"
    block.locked_start = data.locked_start
    block.locked_end = data.locked_end
    block.color = data.color
    db.commit()
    db.refresh(block)
    add_activity(db, user.id, "block_locked", f"Locked {block.game}", "schedule_block", block.id)
    db.commit()
    return _serialize_block(block, user.id)


@router.post("/blocks/{block_id}/unlock", response_model=ScheduleBlockOut)
def unlock_block(
    block_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("planning")),
):
    block = _block_or_404(db, block_id)
    if user.role != "admin" and block.created_by != user.id:
        raise HTTPException(403, "Only the proposer or an admin can unlock this")
    block.status = "proposed"
    block.locked_start = None
    block.locked_end = None
    db.commit()
    db.refresh(block)
    return _serialize_block(block, user.id)
