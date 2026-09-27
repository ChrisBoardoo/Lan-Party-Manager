"""Announcements / PA — /api/announcements

An admin posts a short message that shows as a dismissible banner across the app
(and optionally fans out to the Discord webhook). Reads are open to any logged-in
user; writes are admin-only. Expired announcements are filtered out at read time.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Announcement, User
from schemas import AnnouncementCreate, AnnouncementOut
from auth import get_current_user, require_admin
from activity import add_activity, add_audit

router = APIRouter()

LEVELS = {"info", "alert"}


@router.get("/", response_model=list[AnnouncementOut])
def list_active(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Active (non-expired) announcements, newest first."""
    now = datetime.utcnow()
    return (
        db.query(Announcement)
        .filter((Announcement.expires_at.is_(None)) | (Announcement.expires_at > now))
        .order_by(Announcement.created_at.desc())
        .all()
    )


@router.post("/", response_model=AnnouncementOut)
def create_announcement(
    data: AnnouncementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if data.level not in LEVELS:
        raise HTTPException(400, f"Invalid level: {data.level}")

    ann = Announcement(
        message=data.message.strip(),
        level=data.level,
        event_id=data.event_id,
        created_by=current_user.id,
        expires_at=data.expires_at,
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    add_audit(db, current_user.id, "announcement_posted", ann.message[:120])
    add_activity(db, current_user.id, "announcement_posted", ann.message[:120], "announcement", ann.id)
    db.commit()

    if data.post_to_discord:
        # Imported here to avoid a circular import at module load.
        from discord_notify import send_discord_message
        prefix = "🚨 " if data.level == "alert" else "📣 "
        send_discord_message(db, prefix + ann.message)

    return ann


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    ann = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not ann:
        raise HTTPException(404, "Announcement not found")
    db.delete(ann)
    db.commit()
    return {"ok": True}
