"""The post-event recap — the auto-generated page everyone screenshots.

Aggregates a finished event into one payload: who won, who showed up, how many
nights, the crew's best photos, what it cost, and who earned what badge. Nothing
here is stored; it's all derived on read from tables other features already own.

Gated by the `recap` feature flag (opt-in, default off). Reading is open to every
member — a recap the crew can't see is pointless — while minting or revoking the
public share link is admin-only.

**The money rule.** An authenticated recap includes spend aggregates when the
treasury is on. A recap fetched with a share token NEVER does, and never carries
the financial badge either: a public URL is the internet. This mirrors the
kiosk's rule that usernames and avatars are already projector-visible but money
is not.
"""
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session, selectinload

import badges as badges_mod
from auth import require_admin
from database import get_db
from event_utils import event_prorata_inputs
from models import EventRSVP, LanEvent, MediaItem, RecapShare, Team, Tournament, User
from prorata import calculate_prorata
from router_media import best_media_query, hydrate_reactions
from router_settings import (
    DEFAULT_CURRENCY,
    get_setting,
    is_feature_enabled,
    require_feature,
)
from schemas import (
    BadgeOut,
    MediaItemOut,
    RecapAttendance,
    RecapChampion,
    RecapEvent,
    RecapMedia,
    RecapMoney,
    RecapOut,
    RecapPlayer,
    RecapShareOut,
    RecapTournament,
    RecapTrophy,
    RecapTrophyWinner,
    TrophyBrief,
)
from router_trophies import revealed_editions
from tournament_stats import tournaments_for_event, winning_team_id, winning_user_ids

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event_or_404(db: Session, event_id: int) -> LanEvent:
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


def _require_recap_enabled(db: Session) -> None:
    """Explicit flag check for admin-only endpoints.

    require_feature lets admins through by design, so admin routes that must
    still respect the flag have to ask again — the same pattern router_gear uses
    for admin-posted requests.
    """
    if not is_feature_enabled(db, "recap"):
        raise HTTPException(404, "This feature is not enabled")


def require_recap_token(
    x_recap_token: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> LanEvent:
    """Authorize a public recap view by share token alone — no user session.

    Mirrors router_kiosk.require_kiosk: 404 when the feature is off (the surface
    stays invisible), 401 when the token is missing or wrong, and a constant-time
    compare on *bytes* — secrets.compare_digest raises TypeError on non-ASCII
    str, which would surface as a 500 rather than a clean 401.

    Header-only, deliberately: a token in a query string ends up in access logs,
    browser history and Referer headers.
    """
    if not is_feature_enabled(db, "recap"):
        raise HTTPException(404, "This feature is not enabled")
    if not x_recap_token:
        raise HTTPException(401, "Invalid recap token")

    provided = x_recap_token.encode("utf-8")
    for share in db.query(RecapShare).all():
        if secrets.compare_digest(provided, share.token.encode("utf-8")):
            return _event_or_404(db, share.event_id)
    raise HTTPException(401, "Invalid recap token")


def _tournaments_with_relations(db: Session, event_id: int) -> List[Tournament]:
    return tournaments_for_event(
        db,
        event_id,
        options=(
            selectinload(Tournament.teams).selectinload(Team.members),
            selectinload(Tournament.matches),
        ),
    )


def _attendance(db: Session, event: LanEvent) -> RecapAttendance:
    rsvps = (
        db.query(EventRSVP)
        .filter(EventRSVP.event_id == event.id, EventRSVP.status == "in")
        .all()
    )
    dated = [r for r in rsvps if r.arrival_date and r.departure_date]

    stays = []
    for r in dated:
        # Clamp to the event window, exactly as the pro-rata split does.
        arrival = max(r.arrival_date, event.start_date)
        departure = min(r.departure_date, event.end_date)
        stays.append(max(0, (departure - arrival).days))

    return RecapAttendance(
        attendee_count=len(rsvps),
        total_person_nights=sum(stays),
        longest_stay=max(stays) if stays else 0,
        first_arrival=min((r.arrival_date for r in dated), default=None),
        last_departure=max((r.departure_date for r in dated), default=None),
    )


def _tournaments(db: Session, event_id: int) -> List[RecapTournament]:
    out: List[RecapTournament] = []
    for t in _tournaments_with_relations(db, event_id):
        champion = None
        wt_id = winning_team_id(t)
        if wt_id:
            team = next((tm for tm in t.teams if tm.id == wt_id), None)
            if team:
                champion = RecapChampion(
                    team_name=team.team_name,
                    color=team.color,
                    members=[m.player_name for m in team.members],
                )
        out.append(RecapTournament(
            tournament_id=t.id,
            game_name=t.game_name,
            bracket_type=t.bracket_type,
            match_count=sum(1 for m in t.matches if m.status == "completed"),
            champion=champion,
        ))
    return out


def _mvp(db: Session, event_id: int) -> Optional[RecapPlayer]:
    """Most bracket wins at this event.

    Ties break on lowest user_id — arbitrary, but deterministic, which matters
    more than which of two equally-deserving people is named.
    """
    wins: dict[int, int] = {}
    for t in _tournaments_with_relations(db, event_id):
        if t.status != "completed":
            continue
        for uid in winning_user_ids(t):
            wins[uid] = wins.get(uid, 0) + 1
    if not wins:
        return None

    best = max(wins.values())
    winner_id = min(uid for uid, n in wins.items() if n == best)
    user = db.query(User).filter(User.id == winner_id).first()
    if not user:
        return None
    return RecapPlayer(
        user_id=user.id, username=user.username, avatar_url=user.avatar_url, wins=best
    )


def _media(db: Session, event_id: int, viewer_id: Optional[int]) -> RecapMedia:
    items = db.query(MediaItem).filter(MediaItem.event_id == event_id).all()
    top = best_media_query(db, event_id=event_id).limit(6).all()
    return RecapMedia(
        total=len(items),
        photo_count=sum(1 for i in items if i.file_type == "image"),
        video_count=sum(1 for i in items if i.file_type == "video"),
        top=[MediaItemOut.model_validate(i) for i in hydrate_reactions(db, top, viewer_id)],
    )


def _money(db: Session, event: LanEvent) -> Optional[RecapMoney]:
    if not is_feature_enabled(db, "treasury"):
        return None

    rsvps, expenses, payments = event_prorata_inputs(db, event)
    # viewer_id=None: aggregates only, and it also guarantees calculate_prorata
    # never populates a creditor's phone number.
    result = calculate_prorata(event, rsvps, expenses, payments, viewer_id=None)
    lines = result["settlements"]
    shares = result["shares"]

    return RecapMoney(
        total_expenses=result["total_expenses"],
        currency=get_setting(db, "currency") or DEFAULT_CURRENCY,
        per_person_avg=round(result["total_expenses"] / len(shares), 2) if shares else 0.0,
        settled_lines=sum(1 for l in lines if l["paid"]),
        total_lines=len(lines),
    )


def _trophies(db: Session, event: LanEvent) -> List[RecapTrophy]:
    """Revealed trophies of this edition. Stored decisions, not derived — but
    they carry no money, so the public share link shows them too."""
    if not is_feature_enabled(db, "trophies"):
        return []
    return [
        RecapTrophy(
            trophy=TrophyBrief(
                id=e.trophy.id, name=e.trophy.name, emoji=e.trophy.emoji,
                image_url=e.trophy.image_url, description=e.trophy.description,
            ),
            winners=[
                RecapTrophyWinner(
                    user_id=w.user_id, username=w.user.username, avatar_url=w.user.avatar_url, citation=w.citation,
                )
                for w in e.winners if w.user
            ],
        )
        for e in revealed_editions(db, event.id)
    ]


def _build_recap(db: Session, event: LanEvent, *, viewer_id: Optional[int], shared: bool) -> RecapOut:
    include_financial = not shared
    return RecapOut(
        event=RecapEvent(
            id=event.id,
            title=event.title,
            start_date=event.start_date,
            end_date=event.end_date,
            cover_image_url=event.cover_image_url,
            nights=max(0, (event.end_date - event.start_date).days),
        ),
        attendance=_attendance(db, event),
        tournaments=_tournaments(db, event.id),
        mvp=_mvp(db, event.id),
        media=_media(db, event.id, viewer_id),
        money=None if shared else _money(db, event),
        badges=[
            BadgeOut(
                code=a.code,
                user_id=a.user_id,
                username=a.username,
                avatar_url=a.avatar_url,
                value=a.value,
            )
            for a in badges_mod.event_badges(db, event, include_financial=include_financial)
        ],
        trophies=_trophies(db, event),
        generated_at=datetime.utcnow(),
        shared=shared,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/shared", response_model=RecapOut)
def get_shared_recap(
    event: LanEvent = Depends(require_recap_token),
    db: Session = Depends(get_db),
):
    """A recap fetched with a share token — no login.

    Declared before /{event_id} so "shared" is never parsed as an id.
    """
    return _build_recap(db, event, viewer_id=None, shared=True)


@router.get("/{event_id}", response_model=RecapOut)
def get_recap(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("recap")),
):
    """The full recap for a member of the crew."""
    event = _event_or_404(db, event_id)
    return _build_recap(db, event, viewer_id=user.id, shared=False)


@router.get("/{event_id}/share", response_model=RecapShareOut)
def get_share(
    event_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _require_recap_enabled(db)
    _event_or_404(db, event_id)
    share = db.query(RecapShare).filter(RecapShare.event_id == event_id).first()
    return RecapShareOut(event_id=event_id, token=share.token if share else None)


@router.post("/{event_id}/share", response_model=RecapShareOut)
def mint_share(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Mint or rotate this event's public link. Rotating invalidates the old URL
    immediately — that's also how you revoke a link that got out."""
    _require_recap_enabled(db)
    _event_or_404(db, event_id)

    token = secrets.token_urlsafe(24)
    share = db.query(RecapShare).filter(RecapShare.event_id == event_id).first()
    if share:
        share.token = token
        share.created_by = current_user.id
    else:
        db.add(RecapShare(event_id=event_id, token=token, created_by=current_user.id))
    db.commit()
    return RecapShareOut(event_id=event_id, token=token)


@router.delete("/{event_id}/share", response_model=RecapShareOut)
def revoke_share(
    event_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _require_recap_enabled(db)
    _event_or_404(db, event_id)
    share = db.query(RecapShare).filter(RecapShare.event_id == event_id).first()
    if share:
        db.delete(share)
        db.commit()
    return RecapShareOut(event_id=event_id, token=None)
