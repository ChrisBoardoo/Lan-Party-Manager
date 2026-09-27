"""Presence — /api/presence

A lightweight browser heartbeat so the HUB roster can show who's currently
online. LAN-first: no external service, just a per-user last_seen timestamp.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from auth import get_current_user

router = APIRouter()

# A user counts as "online" if their last heartbeat is within this window.
# The frontend pings every ~45s, so 2 minutes tolerates a missed beat.
ONLINE_WINDOW_SECONDS = 120


def is_user_online(user: User) -> bool:
    if not user.last_seen:
        return False
    return datetime.utcnow() - user.last_seen < timedelta(seconds=ONLINE_WINDOW_SECONDS)


@router.post("/ping")
def ping(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Mark the current user active now. Called on a timer by the SPA while the
    tab is open/visible."""
    current_user.last_seen = datetime.utcnow()
    db.commit()
    return {"ok": True}
