"""LAN countdown reminders — J-10, J-7 and J-1 before an event starts.

From an event's first day on, members can no longer change their own arrival
and departure (see event_utils.has_started): those dates decide how the costs
are split. These reminders give everyone three chances to check them first.

Each reminder is an in-app notification (a targeted activity entry, which the
desktop app also shows as a native toast) and, when SMTP is configured, an
e-mail. Sent to every active member who is coming or hasn't answered yet;
those who said they're not coming are left alone. `LanCountdownSent` makes
it at-most-once per member, event and day count, so a restart or a second run
on the same day never notifies anyone twice.

Runs from the daily 10:00 job (main.py), in the instance's timezone.
"""

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from activity import add_activity
from database import SessionLocal
from event_utils import local_today
from mailer import send_email
from models import EventRSVP, LanCountdownSent, LanEvent, User
from router_settings import get_setting

logger = logging.getLogger(__name__)

COUNTDOWN_DAYS = (10, 7, 1)
SUBJECT = "LAN PARTY MANAGER - Your next LAN is about to start"
# Placeholder addresses given to accounts without a real one (Discord sign-up
# without e-mail, deleted accounts) — never mailed.
_UNDELIVERABLE = ("@no-email.local", "@deleted.invalid")


def _when(days: int, lang: str) -> str:
    if days == 1:
        return "tomorrow" if lang == "en" else "demain"
    return f"in {days} days" if lang == "en" else f"dans {days} jours"


def _fr_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _description(event: LanEvent, days: int, rsvp) -> str:
    """The in-app line, read as "<organiser>: <description>" on the desktop."""
    if rsvp is not None and rsvp.status == "in":
        return (
            f"Your next LAN is about to start: {event.title} begins {_when(days, 'en')}. "
            f"Check your dates ({rsvp.arrival_date} → {rsvp.departure_date}): they lock on {event.start_date}."
        )
    return (
        f"Your next LAN is about to start: {event.title} begins {_when(days, 'en')}. "
        f"Tell the crew whether you're coming — attendance locks on {event.start_date}."
    )


def _email_body(user: User, event: LanEvent, days: int, rsvp, link: str) -> str:
    attending = rsvp is not None and rsvp.status == "in"
    where = f" ({event.location})" if event.location else ""
    en_status = (
        f"You're down from {rsvp.arrival_date} to {rsvp.departure_date}."
        if attending else "You haven't said yet whether you're coming."
    )
    fr_status = (
        f"Tu viens du {_fr_date(rsvp.arrival_date)} au {_fr_date(rsvp.departure_date)}."
        if attending else "Tu n'as pas encore dit si tu venais."
    )
    return "\n".join([
        f"Hi {user.username},",
        "",
        f"{event.title} starts {_when(days, 'en')}, on {event.start_date}{where}.",
        en_status,
        f"Check your arrival and departure now: from {event.start_date} they're locked, and only the",
        "treasurer or an admin can change them — they decide how the costs are split.",
        "",
        link,
        "",
        "—",
        "",
        f"Salut {user.username},",
        "",
        f"{event.title} commence {_when(days, 'fr')}, le {_fr_date(event.start_date)}{where}.",
        fr_status,
        f"Vérifie tes dates d'arrivée et de départ maintenant : à partir du {_fr_date(event.start_date)},",
        "elles sont verrouillées et seuls le trésorier ou un admin peuvent les changer —",
        "ce sont elles qui fixent la répartition des frais.",
        "",
        link,
        "",
    ])


def remind_event(db: Session, event: LanEvent, days: int) -> int:
    """Send the J-`days` reminder of `event` to whoever hasn't had it yet.
    Returns how many members were notified."""
    rsvps = {r.user_id: r for r in db.query(EventRSVP).filter(EventRSVP.event_id == event.id).all()}
    already = {
        uid for (uid,) in db.query(LanCountdownSent.user_id).filter(
            LanCountdownSent.event_id == event.id, LanCountdownSent.days_before == days
        )
    }
    members = (
        db.query(User)
        .filter(User.is_active == True, User.deleted_at.is_(None))  # noqa: E712
        .order_by(User.id)
        .all()
    )
    base_url = (get_setting(db, "app_base_url") or "").rstrip("/")
    link = f"{base_url}/events" if base_url else ""

    notified = 0
    for user in members:
        rsvp = rsvps.get(user.id)
        if user.id in already or (rsvp is not None and rsvp.status == "out"):
            continue
        add_activity(
            db, user_id=event.created_by, action="lan_countdown",
            description=_description(event, days, rsvp),
            entity_type="event", entity_id=event.id, recipient_user_id=user.id,
        )
        db.add(LanCountdownSent(event_id=event.id, user_id=user.id, days_before=days))
        # Recorded before the e-mail goes out: a crash mid-run may skip a mail,
        # never send one twice.
        db.commit()
        notified += 1
        if user.email and not user.email.endswith(_UNDELIVERABLE):
            send_email(db, user.email, SUBJECT, _email_body(user, event, days, rsvp, link))
    return notified


def send_lan_countdown_reminders() -> None:
    """Scheduled job body — opens its own DB session, like discord_notify's."""
    db = SessionLocal()
    try:
        today = local_today(db)
        for days in COUNTDOWN_DAYS:
            target = today + timedelta(days=days)
            for event in db.query(LanEvent).filter(LanEvent.start_date == target).all():
                try:
                    count = remind_event(db, event, days)
                    if count:
                        logger.info("LAN countdown J-%d for %r: %d member(s) notified", days, event.title, count)
                except Exception:
                    logger.exception("LAN countdown J-%d failed for event %s", days, event.id)
                    db.rollback()
    finally:
        db.close()
