import secrets
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from database import get_db
from models import LanEvent, EventRSVP, EventInvite, Expense, SettlementPayment
from schemas import (
    EventCreate, EventUpdate, EventOut, EventRSVPIn, EventRSVPAdjust, EventInviteOut, EventInviteValidate,
)
from auth import get_current_user, require_admin, require_treasurer
from activity import add_activity, add_audit
from event_utils import has_started, local_today
from limiter import limiter
from discord_notify import send_event_announcement
from uploads import rotate_image_file, save_image_upload
import models

router = APIRouter()

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L — hand-typed by guests
# 10 characters out of 32 = 50 bits: out of reach of guessing through the
# (rate-limited) validate route. Codes generated before 1.3.4 had 6.
INVITE_CODE_LENGTH = 10


def _generate_invite_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
        if not db.query(EventInvite).filter(EventInvite.code == code).first():
            return code


def _seats_left(event: LanEvent, rsvp_count: int) -> int | None:
    return None if event.capacity is None else max(0, event.capacity - rsvp_count)


def _rsvp_in(
    db: Session, event: LanEvent, user_id: int, arrival_date: date, departure_date: date
) -> EventRSVP:
    if arrival_date > departure_date:
        raise HTTPException(400, "Arrival date must be on or before departure date")
    if arrival_date < event.start_date or departure_date > event.end_date:
        raise HTTPException(
            400, f"Dates must fall within the event window ({event.start_date} — {event.end_date})"
        )

    if event.capacity:
        in_count = (
            db.query(func.count(EventRSVP.id))
            .join(models.User, EventRSVP.user_id == models.User.id)
            .filter(EventRSVP.event_id == event.id, EventRSVP.status == "in", models.User.is_active == True)  # noqa: E712
            .scalar() or 0
        )
        existing = db.query(EventRSVP).filter(
            EventRSVP.event_id == event.id, EventRSVP.user_id == user_id
        ).first()
        if in_count >= event.capacity and (not existing or existing.status != "in"):
            raise HTTPException(400, f"Event is at full capacity ({event.capacity})")

    rsvp = db.query(EventRSVP).filter(
        EventRSVP.event_id == event.id, EventRSVP.user_id == user_id
    ).first()
    if rsvp:
        rsvp.status = "in"
        rsvp.arrival_date = arrival_date
        rsvp.departure_date = departure_date
    else:
        rsvp = EventRSVP(
            event_id=event.id,
            user_id=user_id,
            status="in",
            arrival_date=arrival_date,
            departure_date=departure_date,
        )
        db.add(rsvp)
    return rsvp


def _enrich(event: LanEvent, db: Session, user_id: int) -> LanEvent:
    in_rsvps = (
        db.query(EventRSVP)
        .join(models.User, EventRSVP.user_id == models.User.id)
        .options(joinedload(EventRSVP.user))
        .filter(EventRSVP.event_id == event.id, EventRSVP.status == "in", models.User.is_active == True)  # noqa: E712
        .all()
    )
    event.rsvp_count = len(in_rsvps)
    event.attendees = [
        {
            "user_id": r.user_id,
            "username": r.user.username,
            "avatar_url": r.user.avatar_url,
            "arrival_date": r.arrival_date,
            "departure_date": r.departure_date,
        }
        for r in sorted(in_rsvps, key=lambda r: r.arrival_date or date.max)
    ]

    rsvp = db.query(EventRSVP).filter(
        EventRSVP.event_id == event.id, EventRSVP.user_id == user_id
    ).first()
    event.my_rsvp = rsvp.status if rsvp else None
    event.my_arrival_date = rsvp.arrival_date if rsvp else None
    event.my_departure_date = rsvp.departure_date if rsvp else None
    event.attendance_locked = has_started(event, local_today(db))
    return event


@router.get("/", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    events = db.query(LanEvent).order_by(LanEvent.start_date).all()
    return [_enrich(e, db, current_user.id) for e in events]


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return _enrich(event, db, current_user.id)


@router.post("/", response_model=EventOut, status_code=201)
def create_event(
    data: EventCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    if data.end_date < data.start_date:
        raise HTTPException(400, "End date must be on or after start date")
    event = LanEvent(
        title=data.title,
        description=data.description,
        location=data.location,
        start_date=data.start_date,
        end_date=data.end_date,
        capacity=data.capacity,
        planning_can_propose=data.planning_can_propose,
        planning_can_vote=data.planning_can_vote,
        created_by=current_user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    add_audit(db, current_user.id, "event_created", f"Event: {event.title}")
    db.commit()
    background_tasks.add_task(send_event_announcement, event.id)
    return _enrich(event, db, current_user.id)


@router.put("/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    data: EventUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    changes = data.model_dump(exclude_unset=True)
    old_start, old_end = event.start_date, event.end_date
    new_start = changes.get("start_date") or old_start
    new_end = changes.get("end_date") or old_end
    if new_end < new_start:
        raise HTTPException(400, "End date must be on or after start date")
    for field, value in changes.items():
        setattr(event, field, value)
    event.start_date, event.end_date = new_start, new_end

    if (new_start, new_end) != (old_start, old_end):
        # Postponing the LAN as a whole moves everyone's stay with it —
        # otherwise every RSVP falls outside the new window, everyone counts 0
        # nights and the treasury reads "all settled". A resize leaves the
        # RSVPs alone: the split clamps them to the new window.
        shift = new_start - old_start
        if shift and new_end - old_end == shift:
            for rsvp in db.query(EventRSVP).filter(EventRSVP.event_id == event.id).all():
                if rsvp.arrival_date:
                    rsvp.arrival_date += shift
                if rsvp.departure_date:
                    rsvp.departure_date += shift
        add_audit(
            db, current_user.id, "event_dates_changed",
            f"Event: {event.title} — {old_start}→{old_end} became {new_start}→{new_end}",
        )
    db.commit()
    db.refresh(event)
    return _enrich(event, db, current_user.id)


@router.post("/{event_id}/cover", response_model=EventOut)
async def upload_event_cover(
    event_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    if current_user.id != event.created_by and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")

    event.cover_image_url = await save_image_upload(
        file, subdir="covers", prefix=f"event_cover_{event_id}", box=(1200, 675),
        replaces=event.cover_image_url,
    )
    db.commit()
    db.refresh(event)
    return _enrich(event, db, current_user.id)


@router.post("/{event_id}/cover/rotate", response_model=EventOut)
def rotate_event_cover(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    if current_user.id != event.created_by and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")
    if not event.cover_image_url:
        raise HTTPException(400, "No cover image to rotate")

    event.cover_image_url = rotate_image_file(
        event.cover_image_url, subdir="covers", prefix=f"event_cover_{event_id}",
    )
    db.commit()
    db.refresh(event)
    return _enrich(event, db, current_user.id)


@router.delete("/{event_id}")
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    add_audit(db, current_user.id, "event_deleted", f"Event: {event.title}")
    # Its expenses don't vanish with it: detached, they show up again in the
    # treasury's "unassigned" banner for the treasurer to re-file. Its paid
    # markers, on the other hand, mean nothing without the event.
    db.query(Expense).filter(Expense.event_id == event.id).update(
        {Expense.event_id: None}, synchronize_session=False
    )
    db.query(SettlementPayment).filter(SettlementPayment.event_id == event.id).delete(
        synchronize_session=False
    )
    db.delete(event)
    db.commit()
    return {"ok": True}


# ── RSVP ──────────────────────────────────────────────────────────────────────

@router.post("/{event_id}/rsvp")
def rsvp_in(
    event_id: int,
    data: EventRSVPIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    _refuse_if_locked(db, event)

    _rsvp_in(db, event, current_user.id, data.arrival_date, data.departure_date)
    db.commit()
    return {"status": "in", "arrival_date": data.arrival_date, "departure_date": data.departure_date}


@router.delete("/{event_id}/rsvp")
def rsvp_out(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if event:
        _refuse_if_locked(db, event)
    rsvp = db.query(EventRSVP).filter(
        EventRSVP.event_id == event_id, EventRSVP.user_id == current_user.id
    ).first()
    if rsvp:
        rsvp.status = "out"
        db.commit()
    return {"status": "out"}


def _refuse_if_locked(db: Session, event: LanEvent) -> None:
    # Once the LAN has started, a member changing their own nights (or
    # leaving) moves everyone else's share: that goes through a treasurer.
    if has_started(event, local_today(db)):
        raise HTTPException(
            409, "The LAN has started: arrival and departure are locked. Ask the treasurer or an admin."
        )


def _describe_rsvp(rsvp) -> str:
    if rsvp is None or rsvp.status != "in":
        return "not attending"
    return f"{rsvp.arrival_date} → {rsvp.departure_date}"


@router.put("/{event_id}/rsvps/{user_id}")
def adjust_rsvp(
    event_id: int,
    user_id: int,
    data: EventRSVPAdjust,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_treasurer),
):
    """A treasurer or an admin sets a member's attendance — the only way to
    change it once the LAN has started (someone stays a night more or less,
    a latecomer). Logged in the audit trail, and the member is notified,
    since it moves everyone's share."""
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    member = db.query(models.User).filter(models.User.id == user_id).first()
    if not member or member.deleted_at is not None:
        raise HTTPException(404, "User not found")

    rsvp = db.query(EventRSVP).filter(EventRSVP.event_id == event_id, EventRSVP.user_id == user_id).first()
    before = _describe_rsvp(rsvp)
    if data.status == "in":
        if not data.arrival_date or not data.departure_date:
            raise HTTPException(400, "Arrival and departure dates are required")
        rsvp = _rsvp_in(db, event, user_id, data.arrival_date, data.departure_date)
    elif rsvp:
        rsvp.status = "out"
    after = _describe_rsvp(rsvp)
    if after == before:
        return {"status": data.status, "changed": False}

    add_audit(
        db, current_user.id, "rsvp_adjusted",
        f"{member.username} @ {event.title}: {before} became {after}",
    )
    if member.id != current_user.id:
        add_activity(
            db, user_id=current_user.id, action="rsvp_adjusted",
            description=(
                f"set your stay at {event.title} to {after}"
                if data.status == "in" else f"marked you as not attending {event.title}"
            ),
            entity_type="event", entity_id=event.id, recipient_user_id=member.id,
        )
    db.commit()
    return {"status": data.status, "changed": True}


# ── Invite codes ──────────────────────────────────────────────────────────────

def _invite_out(invite: EventInvite, event: LanEvent, db: Session) -> dict:
    rsvp_count = (
        db.query(func.count(EventRSVP.id))
        .filter(EventRSVP.event_id == event.id, EventRSVP.status == "in")
        .scalar() or 0
    )
    return {
        "id": invite.id,
        "event_id": event.id,
        "code": invite.code,
        "event_title": event.title,
        "capacity": event.capacity,
        "rsvp_count": rsvp_count,
        "seats_left": _seats_left(event, rsvp_count),
        "created_by": invite.created_by,
        "created_at": invite.created_at,
    }


@router.get("/{event_id}/invite", response_model=EventInviteOut | None)
def get_event_invite(
    event_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    invite = db.query(EventInvite).filter(EventInvite.event_id == event_id).first()
    return _invite_out(invite, event, db) if invite else None


@router.post("/{event_id}/invite", response_model=EventInviteOut, status_code=201)
def create_event_invite(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    invite = db.query(EventInvite).filter(EventInvite.event_id == event_id).first()
    code = _generate_invite_code(db)
    if invite:
        invite.code = code
    else:
        invite = EventInvite(event_id=event_id, code=code, created_by=current_user.id)
        db.add(invite)
    db.commit()
    db.refresh(invite)
    add_audit(db, current_user.id, "event_invite_created", f"Event: {event.title}, code: {code}")
    db.commit()
    return _invite_out(invite, event, db)


@router.delete("/{event_id}/invite")
def revoke_event_invite(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    invite = db.query(EventInvite).filter(EventInvite.event_id == event_id).first()
    if not invite:
        raise HTTPException(404, "No invite code for this event")
    add_audit(db, current_user.id, "event_invite_revoked", f"Event: {event.title if event else event_id}")
    db.delete(invite)
    db.commit()
    return {"ok": True}


def lookup_event_invite(db: Session, code: str) -> tuple[LanEvent, bool] | tuple[None, None]:
    """Resolve an invite code to (event, is_full), or (None, None) if unknown —
    or if its event is over: a code shared in a group chat months ago must not
    keep creating accounts."""
    invite = db.query(EventInvite).filter(EventInvite.code == code.upper()).first()
    if not invite:
        return None, None
    event = db.query(LanEvent).filter(LanEvent.id == invite.event_id).first()
    if not event or event.end_date < local_today(db):
        return None, None
    rsvp_count = (
        db.query(func.count(EventRSVP.id))
        .filter(EventRSVP.event_id == event.id, EventRSVP.status == "in")
        .scalar() or 0
    )
    full = event.capacity is not None and rsvp_count >= event.capacity
    return event, full


@router.get("/invite/validate/{code}", response_model=EventInviteValidate)
@limiter.limit("20/minute")
def validate_event_invite(request: Request, code: str, db: Session = Depends(get_db)):
    event, full = lookup_event_invite(db, code)
    if not event:
        return EventInviteValidate(valid=False)
    return EventInviteValidate(
        valid=True,
        full=full,
        event_id=event.id,
        event_title=event.title,
        event_start=event.start_date,
        event_end=event.end_date,
    )
