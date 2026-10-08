"""Crew XP endpoints. Read-only: XP is derived on read (see xp.py), so there is
nothing to write and nothing to audit. Gated by the `xp` feature; admins pass
the gate, as everywhere, so they can check the numbers before switching it on."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User
from router_settings import require_feature
from schemas import XpCrewEntry, XpLineOut, XpOut
from xp import crew_xp, user_xp

router = APIRouter()


@router.get("/crew", response_model=list[XpCrewEntry])
def get_crew_xp(db: Session = Depends(get_db), _: User = Depends(require_feature("xp"))):
    """Every active member's XP and level, best first — the Hub's leaderboard and
    the level shown on each roster card. Deleted and deactivated accounts are left
    out: a leaderboard is for the crew as it is now."""
    users = (
        db.query(User)
        .filter(User.deleted_at.is_(None), User.is_active == True)  # noqa: E712
        .order_by(User.created_at)
        .all()
    )
    by_id = {u.id: u for u in users}
    return [
        XpCrewEntry(
            user_id=s.user_id, username=by_id[s.user_id].username,
            avatar_url=by_id[s.user_id].avatar_url, total=s.total, level=s.level, title=s.title,
        )
        for s in crew_xp(db, users)
    ]


@router.get("/users/{user_id}", response_model=XpOut)
def get_user_xp(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_feature("xp"))):
    """One member's XP with its breakdown, for their profile."""
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(404, "User not found")
    s = user_xp(db, user_id)
    return XpOut(
        user_id=s.user_id, total=s.total, level=s.level, level_floor=s.level_floor,
        next_level_at=s.next_level_at, title=s.title,
        breakdown=[XpLineOut(code=line.code, count=line.count, xp=line.xp) for line in s.breakdown],
    )
