from datetime import date
from typing import List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from models import Expense, EventRSVP, LanEvent, SettlementPayment, User


def current_event(db: Session) -> Optional[LanEvent]:
    """The event to treat as 'now' when a page isn't tied to a specific event
    (e.g. the Tournaments list, a player profile). The soonest event still
    running or upcoming, falling back to the most recent past one. Mirrors the
    default used by the pro-rata split in router_expenses.py."""
    today = date.today()
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
) -> Tuple[List[EventRSVP], List[Expense], Set[Tuple[int, int]]]:
    """The RSVPs, expenses and settlement markers for one event — the single
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
    is_current = event.end_date >= date.today()

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

    paid_pairs = {
        (p.from_user_id, p.to_user_id)
        for p in db.query(SettlementPayment).filter(SettlementPayment.event_id == event.id).all()
    }

    return rsvps, expenses, paid_pairs
