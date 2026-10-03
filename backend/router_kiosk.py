"""Kiosk / Big Screen — /api/kiosk

An ambient, read-only projector display that runs unattended all weekend. It is
deliberately NOT gated by a normal user session: an admin mints a long-lived,
revocable kiosk token in Settings and opens `/kiosk?token=...` on the projector
machine. Every `/api/kiosk/*` read is authorized *only* by that token (compared
in constant time), so no personal JWT ever lives on the shared screen and only
non-sensitive ambient data is exposed — no emails, no financials.

Token minting/revoking and reading the current token are admin-only (normal
JWT). The `kiosk_enabled` flag and `kiosk_token` live in `app_settings`;
`kiosk_enabled` is in `router_settings.ALLOWED_KEYS` (toggled via the generic
settings PUT), while `kiosk_token` is managed only through the endpoints here so
it's always a strong random value.
"""
import secrets
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import (
    AppSetting, LanEvent, EventRSVP, User, Tournament, Team, Match,
    ScheduleBlock, MediaItem, MediaReaction, Announcement, GearItem,
)
from auth import require_admin
from router_settings import get_setting, is_feature_enabled, wifi_config
from router_presence import is_user_online
from event_utils import current_event
from tournament_stats import decided_at, team_records, winning_team_id
from router_trophies import revealed_editions
from router_media import best_media_query, hydrate_reactions

router = APIRouter()

KIOSK_TOKEN_KEY = "kiosk_token"
KIOSK_ENABLED_KEY = "kiosk_enabled"
# The #LoveWall "drop": a full-screen reveal of each photo posted while the
# display runs. Default ON (opt-out) — the point of the wall is that a post
# from your phone lands on the big screen.
KIOSK_LIVE_DROP_KEY = "kiosk_live_drop_enabled"

# How many recent media the #LoveWall rotates through.
WALL_SIZE = 24
# Videos a browser can play inline in a <video>. AVI, the other accepted upload
# type, plays nowhere, so it stays in the gallery and off the projector.
WALL_VIDEO_MIME = ("video/mp4", "video/webm", "video/quicktime")


# ── Settings plumbing ─────────────────────────────────────────────────────────

def _set_setting(db: Session, key: str, value: Optional[str]) -> None:
    s = db.query(AppSetting).filter(AppSetting.key == key).first()
    if s:
        s.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def _kiosk_enabled(db: Session) -> bool:
    return get_setting(db, KIOSK_ENABLED_KEY) == "true"


# ── Auth: token-only, for the unattended display ──────────────────────────────

def require_kiosk(
    x_kiosk_token: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> None:
    """Authorize an ambient display by its kiosk token alone — no user session.

    Rejects with 404 when the feature is off (so the surface is invisible unless
    an admin turned it on) and 401 when the token is missing or wrong. The
    compare is constant-time to avoid leaking the token via timing.

    Header-only, like the recap and setup shares: a `?token=` query string
    lands in access logs (it used to be accepted here too)."""
    if not _kiosk_enabled(db):
        raise HTTPException(404, "Kiosk is not enabled")
    stored = get_setting(db, KIOSK_TOKEN_KEY)
    provided = x_kiosk_token
    # Compare bytes: secrets.compare_digest raises TypeError on non-ASCII str
    # input, which would surface as a 500 instead of a clean 401.
    if not stored or not provided or not secrets.compare_digest(
        provided.encode("utf-8"), stored.encode("utf-8")
    ):
        raise HTTPException(401, "Invalid kiosk token")


# ── Admin: mint / revoke / read the token ─────────────────────────────────────

class KioskAdminOut(BaseModel):
    enabled: bool
    token: Optional[str]


@router.get("/admin", response_model=KioskAdminOut)
def get_kiosk_admin(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Current kiosk state for the Settings panel (admin-only)."""
    return KioskAdminOut(enabled=_kiosk_enabled(db), token=get_setting(db, KIOSK_TOKEN_KEY))


@router.post("/admin/token", response_model=KioskAdminOut)
def mint_kiosk_token(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Generate (or rotate) the kiosk token. Any previously-shared URL stops
    working immediately — this is also how you revoke a leaked link."""
    token = secrets.token_urlsafe(24)
    _set_setting(db, KIOSK_TOKEN_KEY, token)
    return KioskAdminOut(enabled=_kiosk_enabled(db), token=token)


@router.delete("/admin/token", response_model=KioskAdminOut)
def revoke_kiosk_token(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Clear the token so no kiosk URL is valid until a new one is minted."""
    _set_setting(db, KIOSK_TOKEN_KEY, None)
    return KioskAdminOut(enabled=_kiosk_enabled(db), token=None)


# ── Summary payload models ────────────────────────────────────────────────────

class KioskEvent(BaseModel):
    id: int
    title: str
    location: Optional[str]
    start_date: date
    end_date: date
    cover_image_url: Optional[str]


class KioskCountdown(BaseModel):
    label: str
    target: datetime


class KioskTeamSide(BaseModel):
    name: Optional[str]
    color: Optional[str]
    score: int


class KioskMatch(BaseModel):
    tournament: str
    round: str
    status: str
    team_a: KioskTeamSide
    team_b: KioskTeamSide


class KioskStanding(BaseModel):
    rank: int
    team_name: str
    color: Optional[str]
    wins: int
    losses: int
    draws: int
    points: int
    played: int


class KioskAttendee(BaseModel):
    username: str
    avatar_url: Optional[str]
    online: bool


class KioskArrivals(BaseModel):
    expected: int
    online: int
    attendees: list[KioskAttendee]


class KioskUpNext(BaseModel):
    game: str
    locked_start: datetime
    locked_end: datetime


class KioskReaction(BaseModel):
    """Counts only — who reacted stays off the shared screen, same rule as the
    public recap (hydrate_reactions with viewer_id=None)."""
    emoji: str
    count: int


class KioskMedia(BaseModel):
    id: int
    url: str
    caption: Optional[str]
    file_type: str
    thumbnail_url: Optional[str] = None
    uploader: Optional[str] = None
    uploader_avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    reactions: list[KioskReaction] = []
    reaction_total: int = 0
    # The in-scope item the room reacted to most — the wall's "coup de cœur".
    love_pick: bool = False


class KioskAnnouncement(BaseModel):
    id: int
    message: str
    level: str
    created_at: datetime


class KioskGearItem(BaseModel):
    name: str
    by: Optional[str]


class KioskGear(BaseModel):
    pledged_count: int
    open_request_count: int
    bringing: list[KioskGearItem]
    needs: list[str]


class KioskChampion(BaseModel):
    tournament_id: int
    game_name: str
    team_name: str
    color: Optional[str]
    members: list[str]
    decided_at: Optional[datetime]


class KioskTrophyWinner(BaseModel):
    username: str
    avatar_url: Optional[str]
    citation: Optional[str]


class KioskTrophy(BaseModel):
    edition_id: int
    name: str
    emoji: Optional[str]
    image_url: Optional[str]
    winners: list[KioskTrophyWinner]
    revealed_at: Optional[datetime]


class KioskWifi(BaseModel):
    ssid: str
    password: Optional[str]
    security: str
    hidden: bool


class KioskSummary(BaseModel):
    server_time: datetime
    event: Optional[KioskEvent]
    countdown: Optional[KioskCountdown]
    matches: list[KioskMatch]
    standings: list[KioskStanding]
    arrivals: KioskArrivals
    up_next: list[KioskUpNext]
    media: list[KioskMedia]
    announcements: list[KioskAnnouncement]
    gear: Optional[KioskGear]
    champion: Optional[KioskChampion]
    # "Join the LAN" scene. The kiosk is physically in the room, so it may show
    # the guest WiFi password — that's the point. join_url is app_base_url (the
    # frontend falls back to its own origin when unset).
    wifi: Optional[KioskWifi] = None
    join_url: Optional[str] = None
    # Revealed trophies of the current event, in reveal order. The display
    # celebrates any edition id it hasn't seen before — that's the ceremony:
    # an admin reveals from their phone, the projector plays it.
    trophies: list[KioskTrophy] = []
    # #LoveWall counters (the whole scope, not just the WALL_SIZE shown) and
    # whether a new post interrupts the rotation with a full-screen drop.
    media_total: int = 0
    media_reactions_total: int = 0
    live_drop: bool = True


# ── Helpers for the summary ───────────────────────────────────────────────────

def _team_side(team: Optional[Team], score: int) -> KioskTeamSide:
    if team is None:
        return KioskTeamSide(name=None, color=None, score=score)
    return KioskTeamSide(name=team.team_name, color=team.color, score=score)


def _standings_for(t: Tournament) -> list[KioskStanding]:
    return [
        KioskStanding(
            rank=i + 1,
            team_name=r.team_name,
            color=r.color,
            wins=r.wins,
            losses=r.losses,
            draws=r.draws,
            points=r.points,
            played=r.played,
        )
        for i, r in enumerate(team_records(t))
    ]


@router.get("/summary", response_model=KioskSummary)
def kiosk_summary(
    _auth: None = Depends(require_kiosk),
    db: Session = Depends(get_db),
):
    """Everything the projector display rotates through, in one poll. Scenes with
    no data are simply empty here and self-skip on the frontend."""
    now = datetime.utcnow()
    event = current_event(db)

    event_out = None
    if event:
        event_out = KioskEvent(
            id=event.id,
            title=event.title,
            location=event.location,
            start_date=event.start_date,
            end_date=event.end_date,
            cover_image_url=event.cover_image_url,
        )

    # Tournaments in scope: those tied to the current event, plus any that aren't
    # tied to an event at all (a quick pickup bracket) so they still show.
    tournaments: list[Tournament] = []
    if event:
        tournaments = (
            db.query(Tournament)
            .filter((Tournament.event_id == event.id) | (Tournament.event_id.is_(None)))
            .all()
        )
    else:
        tournaments = db.query(Tournament).all()

    # Matches: live ones first, then the next pending matches with both teams set.
    live: list[KioskMatch] = []
    upcoming: list[KioskMatch] = []
    for t in tournaments:
        for m in t.matches:
            if m.status == "in_progress":
                live.append(KioskMatch(
                    tournament=t.game_name, round=m.round, status="in_progress",
                    team_a=_team_side(m.team_a, m.score_a),
                    team_b=_team_side(m.team_b, m.score_b),
                ))
            elif m.status == "pending" and m.team_a_id and m.team_b_id:
                upcoming.append(KioskMatch(
                    tournament=t.game_name, round=m.round, status="pending",
                    team_a=_team_side(m.team_a, m.score_a),
                    team_b=_team_side(m.team_b, m.score_b),
                ))
    matches = (live + upcoming)[:6]

    # Standings: the round-robin tournament with the most completed matches.
    standings: list[KioskStanding] = []
    rr = [t for t in tournaments if t.bracket_type == "round_robin"]
    if rr:
        best = max(rr, key=lambda t: sum(1 for m in t.matches if m.status == "completed"))
        if any(m.status == "completed" for m in best.matches):
            standings = _standings_for(best)[:8]

    # Arrivals + who's-here (only for the current event).
    attendees: list[KioskAttendee] = []
    online_count = 0
    if event:
        rsvps = (
            db.query(EventRSVP)
            .join(User, EventRSVP.user_id == User.id)
            .filter(EventRSVP.event_id == event.id, EventRSVP.status == "in", User.is_active == True)  # noqa: E712
            .all()
        )
        for r in rsvps:
            u = r.user
            if not u:
                continue
            online = is_user_online(u)
            if online:
                online_count += 1
            attendees.append(KioskAttendee(username=u.username, avatar_url=u.avatar_url, online=online))
        # Online first, then alphabetical — keeps the "who's in the room" up top.
        attendees.sort(key=lambda a: (not a.online, a.username.lower()))
    arrivals = KioskArrivals(expected=len(attendees), online=online_count, attendees=attendees[:24])

    # Up next: locked schedule blocks for the current event, ending in the future.
    up_next: list[KioskUpNext] = []
    if event:
        blocks = (
            db.query(ScheduleBlock)
            .filter(
                ScheduleBlock.event_id == event.id,
                ScheduleBlock.status == "locked",
                ScheduleBlock.locked_end > now,
            )
            .order_by(ScheduleBlock.locked_start)
            .all()
        )
        up_next = [
            KioskUpNext(game=b.game, locked_start=b.locked_start, locked_end=b.locked_end)
            for b in blocks[:5]
        ]

    # Countdown target: the next locked block starting in the future, else the
    # event start if it hasn't begun yet.
    countdown = None
    future_blocks = [b for b in up_next if b.locked_start > now]
    if future_blocks:
        nxt = future_blocks[0]
        countdown = KioskCountdown(label=nxt.game, target=nxt.locked_start)
    elif event and datetime.combine(event.start_date, datetime.min.time()) > now:
        countdown = KioskCountdown(
            label=event.title,
            target=datetime.combine(event.start_date, datetime.min.time()),
        )

    # #LoveWall: the most recent photos and playable videos, scoped to the event
    # in scope — this used to query every image in the database, so last year's
    # LAN turned up on this year's projector.
    #
    # Lenient in the same way as the tournaments query above, and for a concrete
    # reason: MediaItem.event_id is nullable and the gallery tags an upload with
    # whatever filter happened to be selected, so a lot of photos are tied to no
    # event at all. Filtering strictly would leave the photo wall empty for any
    # crew that doesn't tag. An untagged photo is merely "not known to belong
    # elsewhere"; a photo explicitly tagged to a *different* event is definitely
    # not this one's, and that's what we exclude.
    def wall_scope(q):
        q = q.filter(
            (MediaItem.file_type == "image")
            | ((MediaItem.file_type == "video") & MediaItem.mime_type.in_(WALL_VIDEO_MIME))
        )
        if event:
            q = q.filter((MediaItem.event_id == event.id) | (MediaItem.event_id.is_(None)))
        return q

    media_rows = (
        wall_scope(db.query(MediaItem))
        .options(selectinload(MediaItem.uploader))
        # created_at has one-second resolution; a bulk upload shares it, so the
        # id keeps the newest-first order stable between polls.
        .order_by(MediaItem.created_at.desc(), MediaItem.id.desc())
        .limit(WALL_SIZE)
        .all()
    )
    # The coup de cœur can be older than the WALL_SIZE newest — then it rides
    # along at the end, so the wall can still pin it.
    love = wall_scope(best_media_query(db)).first()
    if love and all(m.id != love.id for m in media_rows):
        media_rows.append(love)
    hydrate_reactions(db, media_rows, viewer_id=None)
    media = [
        KioskMedia(
            id=m.id,
            url=m.url,
            caption=m.caption,
            file_type=m.file_type,
            thumbnail_url=m.thumbnail_url,
            uploader=m.uploader.username if m.uploader else None,
            uploader_avatar_url=m.uploader.avatar_url if m.uploader else None,
            created_at=m.created_at,
            reactions=[KioskReaction(emoji=r.emoji, count=r.count) for r in m.reactions],
            reaction_total=m.reaction_total,
            love_pick=love is not None and m.id == love.id,
        )
        for m in media_rows
    ]
    media_total = wall_scope(db.query(func.count(MediaItem.id))).scalar() or 0
    media_reactions_total = (
        wall_scope(db.query(func.count(MediaReaction.id)).join(MediaItem, MediaItem.id == MediaReaction.media_id))
        .scalar()
    ) or 0

    # Active announcements for the flash overlay.
    ann_rows = (
        db.query(Announcement)
        .filter((Announcement.expires_at.is_(None)) | (Announcement.expires_at > now))
        .order_by(Announcement.created_at.desc())
        .all()
    )
    announcements = [
        KioskAnnouncement(id=a.id, message=a.message, level=a.level, created_at=a.created_at)
        for a in ann_rows
    ]

    # Gear ("bringing to the LAN") — only for the current event, when enabled.
    gear = None
    if event and is_feature_enabled(db, "gear"):
        gear_rows = db.query(GearItem).filter(GearItem.event_id == event.id).all()
        bringing = [
            KioskGearItem(name=g.name, by=g.pledger.username if g.pledger else None)
            for g in gear_rows if g.pledged_by is not None
        ]
        needs = [g.name for g in gear_rows if g.is_request and g.pledged_by is None]
        if gear_rows:
            gear = KioskGear(
                pledged_count=len(bringing),
                open_request_count=len(needs),
                bringing=bringing[:12],
                needs=needs[:8],
            )

    # Champion: the most-recently-decided completed tournament with a winner.
    # Scoped to the tournaments already in scope for this event — querying every
    # completed tournament would put a champion from a *different* event on this
    # event's projector.
    champion = None
    completed = [t for t in tournaments if t.status == "completed"]
    best_decided: Optional[datetime] = None
    for t in completed:
        wt_id = winning_team_id(t)
        if not wt_id:
            continue
        decided = decided_at(t)
        # Prefer the most recently decided; undated (legacy) tournaments rank last.
        key = decided or datetime.min
        if best_decided is None or key > best_decided:
            wt = next((tm for tm in t.teams if tm.id == wt_id), None)
            if wt:
                best_decided = key
                champion = KioskChampion(
                    tournament_id=t.id,
                    game_name=t.game_name,
                    team_name=wt.team_name,
                    color=wt.color,
                    members=[mem.player_name for mem in wt.members],
                    decided_at=decided,
                )

    wifi = wifi_config(db)

    trophies: list[KioskTrophy] = []
    if event and is_feature_enabled(db, "trophies"):
        trophies = [
            KioskTrophy(
                edition_id=e.id,
                name=e.trophy.name,
                emoji=e.trophy.emoji,
                image_url=e.trophy.image_url,
                winners=[
                    KioskTrophyWinner(username=w.user.username, avatar_url=w.user.avatar_url, citation=w.citation)
                    for w in e.winners if w.user
                ],
                revealed_at=e.revealed_at,
            )
            for e in revealed_editions(db, event.id)
        ]

    return KioskSummary(
        server_time=now,
        event=event_out,
        countdown=countdown,
        matches=matches,
        standings=standings,
        arrivals=arrivals,
        up_next=up_next,
        media=media,
        announcements=announcements,
        gear=gear,
        champion=champion,
        wifi=KioskWifi(**wifi) if wifi else None,
        join_url=(get_setting(db, "app_base_url") or "").rstrip("/") or None,
        trophies=trophies,
        media_total=media_total,
        media_reactions_total=media_reactions_total,
        live_drop=get_setting(db, KIOSK_LIVE_DROP_KEY) != "false",
    )
