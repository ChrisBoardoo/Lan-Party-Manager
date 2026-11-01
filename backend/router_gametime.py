"""Game time — /api/gametime

What the crew played during a LAN, and for how long, as the members' desktop
apps see it: the app looks at the running processes, recognises a game (its
launcher's manifests, or the list served by GET /catalog), and sends a
heartbeat every minute while the game runs. Only "I'm playing X" leaves the
machine — never the process list.

Heartbeat rules (POST /heartbeat):
- time is the server's clock: a heartbeat extends the member's open session of
  that game (last one seen less than SESSION_GAP ago, same LAN) to now, or opens
  a new one. A session lasts last_seen_at − started_at, so a forged or doubled
  heartbeat can't add time that didn't pass — at worst, a member who sends
  heartbeats for a game they don't play is a member leaving a game open;
- heartbeats closer than MIN_WRITE apart for the same session aren't written
  (an app restarting in a loop costs nothing);
- a heartbeat sent while a LAN the member RSVP'd "in" to runs is filed under it
  (event_utils.lan_in_progress, same rule as the LoL capture); any other is kept
  with no event. Whether the app counts outside a LAN at all is the member's
  choice, made in the desktop app (GET /status tells it whether a LAN is on);
- at most 3 games per heartbeat, names cut to 80 characters, keys checked.
- no XP: game time pays nothing, or leaving a game open overnight would.

Stats are derived on read (GET /events/{id}); "now playing" lists only the
sessions whose member left "show what I'm playing" on.

Gated by the `gametime` feature flag (default OFF, see router_settings).
"""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from event_utils import _instance_tz, lan_in_progress
from models import Game, GameSession, LanEvent, User
from router_settings import is_feature_enabled, require_feature
from schemas import (
    GametimeBeatIn, GametimeBeatOut, GametimeCatalogOut, GametimeEventOut, GametimeGameLine,
    GametimeHeatCell, GametimeLongest, GametimeMemberGame, GametimeMemberLine, GametimeNowPlaying,
    GametimeStatusOut,
)

router = APIRouter()

# The desktop app sends one heartbeat a minute; a session survives a few
# missed ones (a slow network, the app restarting) before a new one starts.
SESSION_GAP = timedelta(minutes=3)
MIN_WRITE = timedelta(seconds=20)

CATALOG_PATH = Path(__file__).resolve().parent / "gametime_catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _catalog_names() -> Dict[str, str]:
    """game key → the shared catalog's name for it, from the served list."""
    return {g["key"]: g.get("catalog") or g["name"] for g in load_catalog()["games"]}


def _clean_name(name: str) -> str:
    name = "".join(ch for ch in name if ch.isprintable())
    return " ".join(name.split())[:80]


def _catalog_game_id(db: Session, key: str, name: str) -> Optional[int]:
    """The shared catalog's row for this game — looked up, never created:
    detection must not fill the catalog with whatever happens to run."""
    lookup = _catalog_names().get(key, name)
    row = db.query(Game.id).filter(func.lower(Game.name) == lookup.lower()).first()
    return row[0] if row else None


# ── What the desktop app asks and sends ──────────────────────────────────────

@router.get("/status", response_model=GametimeStatusOut)
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Asked by a member's desktop app every few minutes, like the LoL
    capture's /capture-status: is the feature on, and is a LAN they attend
    running. Plain auth rather than require_feature: an admin's app must also
    see `enabled: false`."""
    return GametimeStatusOut(
        enabled=is_feature_enabled(db, "gametime"),
        lan_in_progress=lan_in_progress(db, user) is not None,
    )


@router.get("/catalog", response_model=GametimeCatalogOut)
def catalog(_: User = Depends(get_current_user)):
    """The games the app recognises by executable name, and what it must
    ignore. Served rather than built into the app, so the list grows with a
    server update instead of a new MSI."""
    data = load_catalog()
    return GametimeCatalogOut(
        games=data["games"], ignore_exes=data["ignore_exes"], ignore_steam_apps=data["ignore_steam_apps"],
    )


@router.post("/heartbeat", response_model=GametimeBeatOut)
def heartbeat(data: GametimeBeatIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Not require_feature: an admin's app must not count with the feature off
    # either (it isn't sent then, see /status — this is the server's own check).
    if not is_feature_enabled(db, "gametime"):
        raise HTTPException(404, "This feature is not enabled")

    event = lan_in_progress(db, user)
    event_id = event.id if event else None
    now = datetime.utcnow()
    counted = 0
    seen = set()
    for game in data.games:
        if game.key in seen:
            continue
        seen.add(game.key)
        name = _clean_name(game.name)
        if not name:
            continue
        counted += 1
        open_session = (
            db.query(GameSession)
            .filter(
                GameSession.user_id == user.id,
                GameSession.game_key == game.key,
                GameSession.last_seen_at >= now - SESSION_GAP,
            )
            .order_by(GameSession.last_seen_at.desc())
            .first()
        )
        # A LAN that starts (or ends) mid-game starts a new session, so a
        # session's time is always counted for one LAN or for none.
        if open_session and open_session.event_id == event_id:
            if now - open_session.last_seen_at >= MIN_WRITE:
                open_session.last_seen_at = now
            open_session.visible = data.visible
            continue
        db.add(GameSession(
            user_id=user.id, event_id=event_id, game_id=_catalog_game_id(db, game.key, name),
            game_key=game.key, game_name=name, visible=data.visible,
            started_at=now, last_seen_at=now,
        ))
    db.commit()
    return GametimeBeatOut(counted=counted, event_id=event_id)


# ── Stats ────────────────────────────────────────────────────────────────────

def _seconds(s: GameSession) -> int:
    return max(0, int((s.last_seen_at - s.started_at).total_seconds()))


def _heatmap(sessions: List[GameSession], tz) -> List[GametimeHeatCell]:
    """Seconds played per local day and hour: each session is cut at the hour
    boundaries of the instance's timezone."""
    cells: Dict[Tuple, int] = defaultdict(int)
    for s in sessions:
        cur = s.started_at.replace(tzinfo=timezone.utc)
        end = s.last_seen_at.replace(tzinfo=timezone.utc)
        while cur < end:
            local = cur.astimezone(tz)
            hour_start = local.replace(minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            nxt = min(hour_start + timedelta(hours=1), end)
            cells[(local.date(), local.hour)] += int((nxt - cur).total_seconds())
            cur = nxt
    return [
        GametimeHeatCell(day=day, hour=hour, seconds=secs)
        for (day, hour), secs in sorted(cells.items()) if secs > 0
    ]


@router.get("/events/{event_id}", response_model=GametimeEventOut)
def event_gametime(
    event_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("gametime")),
):
    if not db.query(LanEvent.id).filter(LanEvent.id == event_id).first():
        raise HTTPException(404, "Event not found")
    sessions = db.query(GameSession).filter(GameSession.event_id == event_id).all()
    users = {
        u.id: u for u in db.query(User).filter(User.id.in_({s.user_id for s in sessions})).all()
    } if sessions else {}

    by_game: Dict[str, dict] = {}
    by_member: Dict[int, Dict[str, list]] = defaultdict(dict)
    longest: Optional[GameSession] = None
    for s in sessions:
        secs = _seconds(s)
        g = by_game.setdefault(s.game_key, {"name": s.game_name, "game_id": s.game_id, "seconds": 0, "players": set()})
        g["seconds"] += secs
        g["players"].add(s.user_id)
        m = by_member[s.user_id].setdefault(s.game_key, [s.game_name, 0])
        m[1] += secs
        if longest is None or secs > _seconds(longest):
            longest = s

    games = sorted(
        (GametimeGameLine(game_key=k, game_name=g["name"], game_id=g["game_id"], seconds=g["seconds"],
                          players=len(g["players"])) for k, g in by_game.items()),
        key=lambda line: (-line.seconds, line.game_name.lower()),
    )
    members = []
    for user_id, played in by_member.items():
        u = users.get(user_id)
        if not u:
            continue
        lines = sorted(
            (GametimeMemberGame(game_key=k, game_name=name, seconds=secs) for k, (name, secs) in played.items()),
            key=lambda line: -line.seconds,
        )
        members.append(GametimeMemberLine(
            user_id=u.id, username=u.username, avatar_url=u.avatar_url,
            seconds=sum(line.seconds for line in lines), games=lines,
        ))
    members.sort(key=lambda m: (-m.seconds, m.username.lower()))

    cutoff = datetime.utcnow() - SESSION_GAP
    now_playing = []
    for s in sorted(sessions, key=lambda s: s.started_at):
        u = users.get(s.user_id)
        if s.last_seen_at >= cutoff and s.visible and u and u.is_active:
            now_playing.append(GametimeNowPlaying(
                user_id=u.id, username=u.username, avatar_url=u.avatar_url,
                game_name=s.game_name, since=s.started_at,
            ))

    longest_out = None
    if longest and _seconds(longest) > 0 and longest.user_id in users:
        u = users[longest.user_id]
        longest_out = GametimeLongest(
            user_id=u.id, username=u.username, game_name=longest.game_name, seconds=_seconds(longest),
        )

    return GametimeEventOut(
        event_id=event_id,
        total_seconds=sum(g.seconds for g in games),
        games=games,
        members=members,
        heatmap=_heatmap(sessions, _instance_tz(db)),
        now_playing=now_playing,
        longest=longest_out,
    )
