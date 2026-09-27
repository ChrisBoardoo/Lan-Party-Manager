import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from database import SessionLocal
from models import User, LanEvent, EventRSVP, EventReminderSent
from router_settings import get_setting
from mailer import render_template

logger = logging.getLogger(__name__)

DEFAULT_REMINDER_TEMPLATE = (
    "⏰ **Reminder:** {{event_title}} is coming up!\n"
    "📅 {{start_date}} → {{end_date}}\n"
    "📍 {{location}}"
)
DEFAULT_ANNOUNCEMENT_TEMPLATE = (
    "🎉 **New LAN party scheduled:** {{event_title}}\n"
    "📅 {{start_date}} → {{end_date}}\n"
    "📍 {{location}}\n"
    "RSVP here: {{app_base_url}}"
)


def send_discord_message(db: Session, content: str) -> bool:
    webhook_url = get_setting(db, "discord_webhook_url")
    if not webhook_url:
        logger.info("Discord webhook not configured, skipping notification")
        return False

    try:
        resp = httpx.post(webhook_url, json={"content": content}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to post Discord notification")
        return False


def _resolve_timezone(db: Session) -> ZoneInfo:
    tz_name = get_setting(db, "app_timezone") or "UTC"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        logger.warning("Invalid app_timezone %r, falling back to UTC", tz_name)
        return ZoneInfo("UTC")


def send_event_reminders() -> None:
    """Scheduled job body — opens its own DB session since it runs outside any HTTP request.
    Posts one Discord message per due event (not per attendee), since a channel post is
    inherently broadcast — EventReminderSent still records one row per attendee so the
    idempotency gate (and any future per-user reporting) stays meaningful."""
    db = SessionLocal()
    try:
        today = datetime.now(_resolve_timezone(db)).date()
        days_before = int(get_setting(db, "reminder_days_before") or 3)
        target_date = today + timedelta(days=days_before)

        tpl = get_setting(db, "discord_tpl_reminder") or DEFAULT_REMINDER_TEMPLATE

        events = db.query(LanEvent).filter(LanEvent.start_date == target_date).all()
        for event in events:
            already_sent = db.query(EventReminderSent).filter(
                EventReminderSent.event_id == event.id
            ).first()
            if already_sent:
                continue

            attendees = (
                db.query(EventRSVP)
                .join(User, EventRSVP.user_id == User.id)
                .filter(EventRSVP.event_id == event.id, EventRSVP.status == "in", User.is_active == True)  # noqa: E712
                .all()
            )
            if not attendees:
                continue

            context = {
                "event_title": event.title,
                "start_date": event.start_date.isoformat(),
                "end_date": event.end_date.isoformat(),
                "location": event.location or "",
            }
            send_discord_message(db, render_template(tpl, **context))

            for rsvp in attendees:
                db.add(EventReminderSent(event_id=event.id, user_id=rsvp.user_id))
            try:
                db.commit()
            except Exception:
                logger.exception("Failed to record reminder-sent for event %s", event.id)
                db.rollback()
    finally:
        db.close()


def send_event_announcement(event_id: int) -> None:
    """Background-task body — takes just the event id and opens its own session,
    since a request-scoped session isn't safe to reuse once the response has been sent."""
    db = SessionLocal()
    try:
        event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
        if not event:
            return

        tpl = get_setting(db, "discord_tpl_announcement") or DEFAULT_ANNOUNCEMENT_TEMPLATE
        base_url = get_setting(db, "app_base_url") or ""

        context = {
            "event_title": event.title,
            "start_date": event.start_date.isoformat(),
            "end_date": event.end_date.isoformat(),
            "location": event.location or "",
            "app_base_url": base_url,
        }
        send_discord_message(db, render_template(tpl, **context))
    finally:
        db.close()
