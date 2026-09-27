"""League of Legends stats — /api/lol

Every LoL game a member finishes is sent by their desktop app (the
end-of-game block of the League Client, parsed by lol_capture.py) and kept
once per Riot game id. Stats are then derived on read (lol_stats.py) and
shown on the Games page's League of Legends tracker tab: global by default,
or one LAN's games.

Capture rules (POST /matches):
- the sender must have a Riot ID on their profile, and that Riot ID must be
  one of the game's players — a member can only send games they played;
- a game that ends while a LAN the sender RSVP'd "in" to is running (event
  dates, in the app's timezone) is filed under that event; any other game is
  kept with no event and counts in the global stats only. Whether a member's
  app sends games outside a LAN at all is their own choice, made in the
  desktop app (GET /capture-status tells it whether a LAN is on);
- the same game sent again (every player's app sends it) is not an error:
  it answers 200 with the existing match, `created: false`;
- a remake (early surrender vote) is refused — nobody played that game;
- players are matched to members by Riot ID. In a custom game every player is
  kept, so someone who sets their Riot ID later still gets their games; in a
  matchmade game (ARAM, normals) only members are kept — strangers met in
  matchmaking are never stored.

Gated by the `lol_stats` feature flag (default OFF, see router_settings).
"""
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from activity import add_audit
from auth import get_current_user, require_admin
from database import get_db
from games_catalog import resolve_game
from lol_capture import CaptureError, parse_end_of_game
from lol_stats import (
    LOL_CATALOG_NAME, all_lines, captured_matches, category_of, game_records,
    lol_catalog_game, player_records,
)
from models import EventRSVP, LanEvent, LolMatch, LolMatchPlayer, User
from router_settings import get_setting, is_feature_enabled, require_feature
from schemas import (
    LolCaptureIn, LolCaptureResultOut, LolCaptureStatusOut, LolCategory, LolMatchOut,
    LolMatchPlayerOut, LolPlayerLine, LolRecordOut, LolStatsOut,
)

router = APIRouter()


def _today(db: Session) -> date:
    """Today in the app's timezone — a game at 00:30 on a LAN's first night
    must not land on the day before just because the server runs in UTC."""
    try:
        tz = ZoneInfo(get_setting(db, "app_timezone") or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


def _lan_in_progress(db: Session, user: User) -> Optional[LanEvent]:
    today = _today(db)
    return (
        db.query(LanEvent)
        .join(EventRSVP, EventRSVP.event_id == LanEvent.id)
        .filter(
            EventRSVP.user_id == user.id,
            EventRSVP.status == "in",
            LanEvent.start_date <= today,
            LanEvent.end_date >= today,
        )
        .order_by(LanEvent.start_date.desc(), LanEvent.id.desc())
        .first()
    )


def link_captured_players(db: Session, user: User) -> None:
    """Hand a member the unclaimed custom-game lines carrying their Riot ID —
    called when they set it (router_users.update_user). Lines already linked
    to someone are left alone: those games were played by whoever held that
    Riot ID at the time."""
    if not user.riot_id_key:
        return
    db.query(LolMatchPlayer).filter(
        LolMatchPlayer.riot_id_key == user.riot_id_key,
        LolMatchPlayer.user_id.is_(None),
    ).update({LolMatchPlayer.user_id: user.id}, synchronize_session=False)


# ── Capture ──────────────────────────────────────────────────────────────────

@router.post("/matches", response_model=LolCaptureResultOut, status_code=201)
def submit_match(
    data: LolCaptureIn,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("lol_stats")),
):
    try:
        game = parse_end_of_game(data.eog, data.session)
    except CaptureError as e:
        raise HTTPException(422, str(e))
    if game.is_remake:
        raise HTTPException(422, "Remakes are not counted")

    if not user.riot_id_key:
        raise HTTPException(400, "Set your Riot ID on your profile first")
    if user.riot_id_key not in {p.riot_id_key for p in game.players}:
        raise HTTPException(403, "Your Riot ID is not in this game")

    # Before looking up the LAN on purpose: a game is filed once, under the
    # LAN of whoever sent it first — a retry reaching us after the LAN ended
    # must not re-file it.
    existing = db.query(LolMatch).filter(LolMatch.riot_game_id == game.riot_game_id).first()
    if existing:
        response.status_code = 200
        return LolCaptureResultOut(match_id=existing.id, created=False)

    # No LAN on for the sender: kept all the same, for the global stats only.
    event = _lan_in_progress(db, user)

    members = {
        u.riot_id_key: u.id
        for u in db.query(User).filter(User.riot_id_key.in_([p.riot_id_key for p in game.players])).all()
    }
    match = LolMatch(
        event_id=event.id if event else None,
        riot_game_id=game.riot_game_id,
        game_mode=game.game_mode,
        queue_type=game.queue_type,
        is_custom=game.is_custom,
        duration_s=game.duration_s,
        submitted_by=user.id,
    )
    for p in game.players:
        user_id = members.get(p.riot_id_key)
        if user_id is None and not game.is_custom:
            continue
        match.players.append(LolMatchPlayer(
            user_id=user_id, riot_id=p.riot_id, riot_id_key=p.riot_id_key, champion=p.champion,
            team_id=p.team_id, win=p.win, kills=p.kills, deaths=p.deaths, assists=p.assists,
            damage=p.damage,
        ))
    # So the game shows up under League of Legends even on an install whose
    # catalog lost the seeded row.
    resolve_game(db, LOL_CATALOG_NAME, user.id)
    db.add(match)
    try:
        db.commit()
    except IntegrityError:
        # Every player's app sends the game at the same moment — another one
        # got it in between our check and our insert. Same answer as above.
        db.rollback()
        existing = db.query(LolMatch).filter(LolMatch.riot_game_id == game.riot_game_id).first()
        if not existing:
            raise
        response.status_code = 200
        return LolCaptureResultOut(match_id=existing.id, created=False)
    return LolCaptureResultOut(match_id=match.id, created=True)


@router.get("/capture-status", response_model=LolCaptureStatusOut)
def capture_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """What a member's desktop app asks (every few minutes) to decide whether
    to watch the League client: is the feature on, and is a LAN they attend
    running right now — the same rule, dates and timezone as POST /matches,
    so the app never does its own date arithmetic. Plain auth rather than
    require_feature: an admin's app must also see `enabled: false`."""
    return LolCaptureStatusOut(
        enabled=is_feature_enabled(db, "lol_stats"),
        lan_in_progress=_lan_in_progress(db, user) is not None,
    )


# ── Stats ────────────────────────────────────────────────────────────────────

def _users_by_id(db: Session, ids) -> dict[int, User]:
    ids = set(ids)
    if not ids:
        return {}
    return {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}


@router.get("/stats", response_model=LolStatsOut)
def lol_stats(
    event_id: Optional[int] = Query(None),
    category: Optional[LolCategory] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("lol_stats")),
):
    matches = captured_matches(db, event_id=event_id, category=category)
    lines = all_lines(matches)
    records = player_records(lines)
    best = game_records(lines)
    users = _users_by_id(db, [r.user_id for r in records])

    players = []
    for r in records:
        u = users.get(r.user_id)
        if not u:
            continue
        players.append(LolPlayerLine(
            user_id=u.id, username=u.username, avatar_url=u.avatar_url,
            games=r.games, wins=r.wins, losses=r.losses, win_rate=r.win_rate,
            kills=r.kills, deaths=r.deaths, assists=r.assists, damage=r.damage, kda=r.kda,
            avg_kills=r.kills / r.games, avg_deaths=r.deaths / r.games,
            avg_assists=r.assists / r.games, avg_damage=r.damage / r.games,
        ))

    out_records = []
    for kind, line in best.items():
        u = users.get(line.user_id)
        if not u:
            continue
        out_records.append(LolRecordOut(
            kind=kind, value=getattr(line, kind), user_id=u.id, username=u.username,
            avatar_url=u.avatar_url, champion=line.champion, match_id=line.match_id,
        ))

    game = lol_catalog_game(db)
    return LolStatsOut(
        game_id=game.id if game else None, matches=len(matches), players=players, records=out_records,
    )


# ── Match history (admin clean-up) ───────────────────────────────────────────

@router.get("/matches", response_model=list[LolMatchOut])
def list_matches(
    event_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("lol_stats")),
):
    matches = captured_matches(db, event_id=event_id)
    users = _users_by_id(
        db,
        [line.user_id for m in matches for line in m.players if line.user_id]
        + [m.submitted_by for m in matches if m.submitted_by],
    )
    out = []
    for m in matches:
        submitter = users.get(m.submitted_by)
        out.append(LolMatchOut(
            id=m.id, event_id=m.event_id, category=category_of(m), game_mode=m.game_mode,
            duration_s=m.duration_s, played_at=m.created_at,
            submitted_by=submitter.username if submitter else None,
            players=[
                LolMatchPlayerOut(
                    user_id=line.user_id,
                    username=users[line.user_id].username if line.user_id in users else None,
                    riot_id=line.riot_id, champion=line.champion, team_id=line.team_id, win=line.win,
                    kills=line.kills, deaths=line.deaths, assists=line.assists, damage=line.damage,
                )
                for line in sorted(m.players, key=lambda ln: (ln.team_id or 0, ln.id))
            ],
        ))
    return out


@router.delete("/matches/{match_id}")
def delete_match(
    match_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Removes a game that shouldn't count (a test, a remake, a joke run)."""
    match = db.query(LolMatch).filter(LolMatch.id == match_id).first()
    if not match:
        raise HTTPException(404, "Match not found")
    add_audit(db, admin.id, "lol_match_deleted", f"LoL game {match.riot_game_id}")
    db.delete(match)
    db.commit()
    return {"ok": True}

