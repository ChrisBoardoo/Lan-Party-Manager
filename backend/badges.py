"""Derived achievements — computed on read, never stored.

There is no achievements table on purpose. Every badge here is a fact already
implied by other data (who won, who stayed longest, who uploaded what), so
storing it would only create a second copy that can drift from the truth when the
underlying rows change.

Badges carry a `code`, not a label: the human strings live in the frontend's
i18n bundles as `badges.<code>.label` / `.desc`, which keeps English out of the
API and keeps the EN/FR parity check meaningful.

Ties award everyone tied — a LAN badge is bragging rights, not a prize.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from models import (
    EventRSVP,
    Expense,
    GearItem,
    LanEvent,
    MediaItem,
    MediaReaction,
    MiniGameScore,
    Team,
    TeamMember,
    Tournament,
    User,
)
from minigames_registry import GAMES
from router_settings import is_feature_enabled
from tournament_stats import team_records, tournaments_for_event, winning_user_ids


@dataclass(frozen=True)
class BadgeAward:
    code: str
    user_id: int
    username: str
    avatar_url: Optional[str]
    value: Optional[int] = None


def _users(db: Session, user_ids: Sequence[int]) -> Dict[int, User]:
    if not user_ids:
        return {}
    return {u.id: u for u in db.query(User).filter(User.id.in_(set(user_ids))).all()}


def _award(code: str, user: User, value: Optional[int] = None) -> BadgeAward:
    return BadgeAward(
        code=code, user_id=user.id, username=user.username, avatar_url=user.avatar_url, value=value
    )


def _top_scorers(scores: Dict[int, float]) -> tuple[List[int], float]:
    """Everyone tied at the maximum, and that maximum. Empty when nobody scored."""
    positive = {uid: v for uid, v in scores.items() if v > 0}
    if not positive:
        return [], 0
    best = max(positive.values())
    return [uid for uid, v in positive.items() if v == best], best


def _minigame_titles_held(db: Session, user_id: int) -> int:
    """How many mini-games this user currently tops.

    Derived on read like every other badge — the leaderboard already knows who is
    first, so storing a title would just be a second copy that goes stale the moment
    somebody beats it. Sort direction comes from the registry rather than being
    assumed: a future speedrun-shaped game ranks ascending.
    """
    titles = 0
    for slug, spec in GAMES.items():
        order = MiniGameScore.score.desc() if spec.higher_is_better else MiniGameScore.score.asc()
        leader = (
            db.query(MiniGameScore.user_id)
            .filter(MiniGameScore.game == slug)
            .order_by(order, MiniGameScore.created_at.asc())
            .first()
        )
        if leader and leader[0] == user_id:
            titles += 1
    return titles


def _event_tournaments(db: Session, event_id: int) -> List[Tournament]:
    return tournaments_for_event(
        db,
        event_id,
        options=(
            selectinload(Tournament.teams).selectinload(Team.members),
            selectinload(Tournament.matches),
        ),
    )


def event_badges(db: Session, event: LanEvent, *, include_financial: bool) -> List[BadgeAward]:
    """Badges earned at one event.

    `include_financial` is a hard gate, not a hint: the recap's public share link
    passes False so that who-fronted-the-money never leaves the crew.
    """
    awards: List[BadgeAward] = []
    tournaments = [t for t in _event_tournaments(db, event.id) if t.status == "completed"]

    # ── champion: won a bracket at this event ────────────────────────────────
    champion_wins: Dict[int, int] = {}
    for t in tournaments:
        for uid in winning_user_ids(t):
            champion_wins[uid] = champion_wins.get(uid, 0) + 1

    # ── undefeated: played at least twice and never lost ─────────────────────
    undefeated_ids: List[int] = []
    for t in tournaments:
        for record in team_records(t):
            if record.losses == 0 and record.played >= 2:
                team = next((tm for tm in t.teams if tm.id == record.team_id), None)
                if team:
                    undefeated_ids += [m.user_id for m in team.members if m.user_id]

    # ── first_blood: won the earliest match played at the event ──────────────
    first_blood_ids: List[int] = []
    played = [
        m
        for t in _event_tournaments(db, event.id)
        for m in t.matches
        if m.status == "completed" and m.played_at and m.winner_id
    ]
    if played:
        earliest = min(played, key=lambda m: m.played_at)
        winning_team = (
            db.query(Team)
            .options(selectinload(Team.members))
            .filter(Team.id == earliest.winner_id)
            .first()
        )
        if winning_team:
            first_blood_ids = [m.user_id for m in winning_team.members if m.user_id]

    # ── night_owl: stayed the most nights ────────────────────────────────────
    # NOTE: the roadmap's "Night Owl" meant whoever fell asleep last. We have no
    # such data — presence is a heartbeat that overwrites last_seen, not a sleep
    # log — so this is honestly "stayed the longest", and the i18n description
    # says exactly that rather than implying we track anyone's sleep.
    nights: Dict[int, float] = {}
    rsvps = (
        db.query(EventRSVP)
        .filter(
            EventRSVP.event_id == event.id,
            EventRSVP.status == "in",
            EventRSVP.arrival_date.isnot(None),
            EventRSVP.departure_date.isnot(None),
        )
        .all()
    )
    for r in rsvps:
        # Clamp to the event window, exactly as the pro-rata split does.
        arrival = max(r.arrival_date, event.start_date)
        departure = min(r.departure_date, event.end_date)
        nights[r.user_id] = max(0, (departure - arrival).days)

    # ── shutterbug: uploaded the most media ──────────────────────────────────
    uploads: Dict[int, float] = {
        uid: n
        for uid, n in db.query(MediaItem.uploaded_by, func.count())
        .filter(MediaItem.event_id == event.id)
        .group_by(MediaItem.uploaded_by)
        .all()
    }

    # ── crowd_pleaser: uploaded the single most-reacted item ─────────────────
    crowd_pleaser_ids: List[int] = []
    top_media = (
        db.query(MediaItem.uploaded_by, func.count(MediaReaction.id).label("n"))
        .join(MediaReaction, MediaReaction.media_id == MediaItem.id)
        .filter(MediaItem.event_id == event.id)
        .group_by(MediaItem.id)
        .order_by(func.count(MediaReaction.id).desc())
        .first()
    )
    if top_media and top_media[1] > 0:
        crowd_pleaser_ids = [top_media[0]]

    # ── quartermaster: pledged the most gear (only if gear is on) ────────────
    pledges: Dict[int, float] = {}
    if is_feature_enabled(db, "gear"):
        pledges = {
            uid: n
            for uid, n in db.query(GearItem.pledged_by, func.count())
            .filter(GearItem.event_id == event.id, GearItem.pledged_by.isnot(None))
            .group_by(GearItem.pledged_by)
            .all()
        }

    # ── snack_sponsor: fronted the most money (gated twice) ──────────────────
    spend: Dict[int, float] = {}
    if include_financial and is_feature_enabled(db, "treasury"):
        for e in db.query(Expense).filter(Expense.event_id == event.id).all():
            payer_id = e.paid_by or e.created_by
            if payer_id:
                spend[payer_id] = spend.get(payer_id, 0.0) + e.amount

    night_ids, night_best = _top_scorers(nights)
    upload_ids, upload_best = _top_scorers(uploads)
    pledge_ids, pledge_best = _top_scorers(pledges)
    spend_ids, spend_best = _top_scorers(spend)

    users = _users(
        db,
        list(champion_wins)
        + undefeated_ids
        + first_blood_ids
        + night_ids
        + upload_ids
        + crowd_pleaser_ids
        + pledge_ids
        + spend_ids,
    )

    for uid, wins in champion_wins.items():
        if uid in users:
            awards.append(_award("champion", users[uid], wins))
    for uid in dict.fromkeys(undefeated_ids):
        if uid in users:
            awards.append(_award("undefeated", users[uid]))
    for uid in dict.fromkeys(first_blood_ids):
        if uid in users:
            awards.append(_award("first_blood", users[uid]))
    for uid in night_ids:
        if uid in users:
            awards.append(_award("night_owl", users[uid], int(night_best)))
    for uid in upload_ids:
        if uid in users:
            awards.append(_award("shutterbug", users[uid], int(upload_best)))
    for uid in crowd_pleaser_ids:
        if uid in users:
            awards.append(_award("crowd_pleaser", users[uid]))
    for uid in pledge_ids:
        if uid in users:
            awards.append(_award("quartermaster", users[uid], int(pledge_best)))
    for uid in spend_ids:
        if uid in users:
            awards.append(_award("snack_sponsor", users[uid], round(spend_best)))

    return awards


def user_badges(db: Session, user_id: int) -> List[BadgeAward]:
    """A member's all-time badges, for their profile.

    Deliberately a different — and much cheaper — set than `event_badges`:
    unioning that across every event would run N event-sized queries on a profile
    page load. These are lifetime thresholds, and `value` carries the count so
    the UI can show a tier.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []

    awards: List[BadgeAward] = []

    wins = 0
    completed = (
        db.query(Tournament)
        .filter(Tournament.status == "completed")
        .options(
            selectinload(Tournament.teams).selectinload(Team.members),
            selectinload(Tournament.matches),
        )
        .all()
    )
    for t in completed:
        if user_id in winning_user_ids(t):
            wins += 1
    if wins >= 1:
        awards.append(_award("champion", user, wins))

    attended = (
        db.query(EventRSVP)
        .filter(EventRSVP.user_id == user_id, EventRSVP.status == "in")
        .count()
    )
    if attended >= 3:
        awards.append(_award("veteran", user, attended))

    uploads = db.query(MediaItem).filter(MediaItem.uploaded_by == user_id).count()
    if uploads >= 25:
        awards.append(_award("shutterbug", user, uploads))

    if is_feature_enabled(db, "gear"):
        pledged = db.query(GearItem).filter(GearItem.pledged_by == user_id).count()
        if pledged >= 10:
            awards.append(_award("quartermaster", user, pledged))

    if is_feature_enabled(db, "minigames"):
        titles = _minigame_titles_held(db, user_id)
        if titles >= 1:
            awards.append(_award("arcade_champion", user, titles))

    return awards
