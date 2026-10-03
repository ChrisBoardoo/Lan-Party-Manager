import logging
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from models import AppSetting, Expense, EventRSVP, LanEvent, SettlementPayment, User

logger = logging.getLogger(__name__)


def local_today(db: Session) -> date:
    """Today in the instance's own timezone (Settings → app_timezone), not the
    server's: Docker runs in UTC, so date.today() turns over at 02:00 in
    Paris. Reads the setting directly — router_settings imports this module."""
    tz_name = db.query(AppSetting.value).filter(AppSetting.key == "app_timezone").scalar() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning("Invalid app_timezone %r, falling back to UTC", tz_name)
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


# How long after a LAN the treasury keeps showing it by default: the week or
# two in which the crew actually settles up.
SETTLING_DAYS = 14


def treasury_default_event(db: Session) -> Optional[LanEvent]:
    """The event the treasury opens on: one in progress, else one that ended
    less than SETTLING_DAYS ago (its receipts are still coming in), else the
    usual current_event. Without the middle case, the Monday after a LAN
    showed — and filed new receipts under — next year's edition."""
    today = local_today(db)
    running = (
        db.query(LanEvent)
        .filter(LanEvent.start_date <= today, LanEvent.end_date >= today)
        .order_by(LanEvent.start_date)
        .first()
    )
    if running:
        return running
    just_ended = (
        db.query(LanEvent)
        .filter(LanEvent.end_date < today, LanEvent.end_date >= today - timedelta(days=SETTLING_DAYS))
        .order_by(LanEvent.end_date.desc())
        .first()
    )
    return just_ended or current_event(db)


def has_started(event: LanEvent, today: date) -> bool:
    """From its first day on, an event's attendance is locked: members can no
    longer change their own arrival/departure or leave, since that would move
    everyone else's share — only a treasurer or an admin can (and it's logged)."""
    return today >= event.start_date


def current_event(db: Session) -> Optional[LanEvent]:
    """The event to treat as 'now' when a page isn't tied to a specific event
    (e.g. the Tournaments list, a player profile). The soonest event still
    running or upcoming, falling back to the most recent past one. The
    treasury uses treasury_default_event instead, which keeps a LAN that just
    ended in view while the crew settles up."""
    today = local_today(db)
    event = (
        db.query(LanEvent)
        .filter(LanEvent.end_date >= today)
        .order_by(LanEvent.start_date)
        .first()
    )
    if not event:
        event = db.query(LanEvent).order_by(LanEvent.end_date.desc()).first()
    return event


def event_prorata_inputs(
    db: Session, event: LanEvent
) -> Tuple[List[EventRSVP], List[Expense], List[SettlementPayment]]:
    """The RSVPs, expenses and recorded payments for one event — the single
    scoped input set for ``prorata.calculate_prorata``.

    Expenses are scoped strictly by ``event_id``: an expense belongs to exactly
    one event's split. This used to be an unfiltered ``query(Expense).all()``,
    which meant every event's split silently included every other event's
    spending. Do not loosen this to also sweep in ``event_id IS NULL`` rows —
    that is what reintroduces the cross-event double-count. Untagged expenses
    are surfaced to the user for assignment instead (see
    ``router_expenses.unassigned_count``).

    Lives here rather than in prorata.py so that module stays pure and
    session-free.

    **Deactivated/deleted members and past events.** A deactivated or deleted
    member is excluded from the split for an event that hasn't concluded yet
    (``end_date >= today``) — same principle as the attendee list
    (``router_events._enrich``): they're gone, so they shouldn't owe or be
    owed anything for a LAN that hasn't happened. A *past* event's split is
    settled history, though — silently excluding them would retroactively
    reshuffle everyone else's already-agreed shares for money that's likely
    already been paid. Past events are deliberately left unfiltered here.
    """
    # Same boundary as the attendance lock (has_started): before the LAN, a
    # deactivated member is out of it and owes nothing; once it has started,
    # the attendance is frozen and they stay in the split. It used to switch
    # at the end date instead, so the amounts settled on the last evening
    # changed overnight.
    is_current = not has_started(event, local_today(db))

    rsvp_query = db.query(EventRSVP).filter(
        EventRSVP.event_id == event.id,
        EventRSVP.status == "in",
        EventRSVP.arrival_date.isnot(None),
        EventRSVP.departure_date.isnot(None),
    )
    if is_current:
        rsvp_query = rsvp_query.join(User, EventRSVP.user_id == User.id).filter(
            User.is_active == True  # noqa: E712
        )
    rsvps = rsvp_query.all()

    expenses = db.query(Expense).filter(Expense.event_id == event.id).all()

    payments = (
        db.query(SettlementPayment)
        .filter(SettlementPayment.event_id == event.id)
        .order_by(SettlementPayment.id)
        .all()
    )

    return rsvps, expenses, payments
