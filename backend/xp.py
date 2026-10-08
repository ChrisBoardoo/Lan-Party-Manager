"""Crew XP — computed on read, never stored.

Same principle as badges.py: every point comes from a fact another feature
already owns (a match won, a trophy revealed, a photo in Media, chat messages,
an avatar), so there is no XP table to drift from the truth. An organizer who
corrects a score moves the XP to the right team on the next read, and XP is
retroactive: matches played before the feature was switched on count too.

The breakdown carries codes, not labels — the strings live in the frontend's
i18n bundles as `xp.source.<code>`, same as `badges.<code>.label`.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from models import ChatMessage, EventTrophy, EventTrophyWinner, MediaItem, Team, Tournament, User
from router_settings import is_feature_enabled
from tournament_stats import decided_matches, match_result, winning_user_ids

# ── Rules: the one place to tune the scale ───────────────────────────────────

# Per linked player of the winning side, by bracket stage (Match.round).
MATCH_WIN_XP = {"final": 100, "semifinal": 60, "quarterfinal": 40, "round_of_16": 25}
# Round-robin rounds ("round_N") and any stage not listed above.
OTHER_MATCH_WIN_XP = 15
# On top of the final, for every linked player of the champion team.
TOURNAMENT_WIN_XP = 50
# Per revealed trophy edition won (co-winners each get it).
TROPHY_XP = 50
# Per photo uploaded to Media; videos don't count. Capped per event so a phone
# dump of 400 burst shots doesn't outweigh winning a final.
PHOTO_XP = 2
PHOTOS_PER_EVENT_CAP = 50
# Per full step of chat messages, counting at most a daily cap per person.
CHAT_XP = 5
CHAT_MESSAGES_PER_STEP = 30
CHAT_MESSAGES_PER_DAY_CAP = 60
# Having a profile picture at all. "Once a year" would need the avatar's upload
# date, which isn't stored; that's a migration left for after the LAN.
AVATAR_XP = 10

# Total XP at which each level starts: level 1 at 0, level 10 at 3000, then one
# level every LEVEL_STEP_AFTER. Early levels come fast (the first evening), later
# ones take a few LANs.
LEVEL_THRESHOLDS = (0, 50, 150, 300, 500, 800, 1200, 1700, 2300, 3000)
LEVEL_STEP_AFTER = 800
# (first level of the band, title code) — i18n `xp.title.<code>`.
LEVEL_TITLES = ((1, "recruit"), (3, "regular"), (5, "pillar"), (7, "veteran"), (10, "legend"))

# Display order of the breakdown, best-paying sources first.
SOURCE_ORDER = (
    "match_final",
    "match_semifinal",
    "match_quarterfinal",
    "match_round_of_16",
    "match_other",
    "tournament_win",
    "trophy",
    "photo",
    "chat",
    "avatar",
)


@dataclass(frozen=True)
class XpLine:
    code: str
    count: int
    xp: int


@dataclass(frozen=True)
class XpSummary:
    user_id: int
    total: int
    level: int
    level_floor: int
    next_level_at: int
    title: str
    breakdown: List[XpLine]


def level_progress(total: int) -> tuple[int, int, int]:
    """(level, XP where that level starts, XP where the next one starts)."""
    total = max(total, 0)
    level, floor = 1, 0
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if total >= threshold:
            level, floor = i + 1, threshold
    if level == len(LEVEL_THRESHOLDS):
        extra = (total - LEVEL_THRESHOLDS[-1]) // LEVEL_STEP_AFTER
        level += extra
        floor = LEVEL_THRESHOLDS[-1] + extra * LEVEL_STEP_AFTER
        return level, floor, floor + LEVEL_STEP_AFTER
    return level, floor, LEVEL_THRESHOLDS[level]


def title_for(level: int) -> str:
    code = LEVEL_TITLES[0][1]
    for first_level, band in LEVEL_TITLES:
        if level >= first_level:
            code = band
    return code


class _Ledger:
    """Per-user, per-source running (count, xp)."""

    def __init__(self) -> None:
        self.rows: Dict[int, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    def add(self, user_id: int, code: str, xp: int, count: int = 1) -> None:
        line = self.rows[user_id][code]
        line[0] += count
        line[1] += xp

    def summary(self, user_id: int) -> XpSummary:
        lines = self.rows.get(user_id, {})
        breakdown = [
            XpLine(code=code, count=lines[code][0], xp=lines[code][1])
            for code in SOURCE_ORDER
            if code in lines and lines[code][1] > 0
        ]
        total = sum(line.xp for line in breakdown)
        level, floor, next_at = level_progress(total)
        return XpSummary(
            user_id=user_id, total=total, level=level, level_floor=floor,
            next_level_at=next_at, title=title_for(level), breakdown=breakdown,
        )


def add_tournament_xp(ledger: _Ledger, tournaments: Sequence[Any]) -> None:
    """Match wins by stage, plus the champion bonus. Duck-typed like
    tournament_stats, so it unit-tests without a session.

    Counts what `decided_matches` counts: no byes (no opponent), no draws, nothing
    still waiting for an organizer. Players never linked to an account earn
    nothing — there is nobody to credit."""
    for t in tournaments:
        roster = {tm.id: list(dict.fromkeys(m.user_id for m in tm.members if m.user_id)) for tm in t.teams}
        for m in decided_matches(t.matches):
            winner, _loser = match_result(m)
            if winner is None:
                continue
            stage = m.round if m.round in MATCH_WIN_XP else "other"
            xp = MATCH_WIN_XP.get(m.round, OTHER_MATCH_WIN_XP)
            for uid in roster.get(winner, []):
                ledger.add(uid, f"match_{stage}", xp)
        if t.status == "completed":
            for uid in dict.fromkeys(winning_user_ids(t)):
                ledger.add(uid, "tournament_win", TOURNAMENT_WIN_XP)


def _build_ledger(db: Session) -> _Ledger:
    ledger = _Ledger()

    tournaments = (
        db.query(Tournament)
        .options(selectinload(Tournament.teams).selectinload(Team.members), selectinload(Tournament.matches))
        .all()
    )
    add_tournament_xp(ledger, tournaments)

    # Trophies: revealed editions only — a closed one is still a secret. Gated
    # like the rest of the trophy feature, so a hidden cabinet leaks nothing.
    if is_feature_enabled(db, "trophies"):
        won = (
            db.query(EventTrophyWinner.user_id, func.count())
            .join(EventTrophy, EventTrophy.id == EventTrophyWinner.event_trophy_id)
            .filter(EventTrophy.status == "revealed")
            .group_by(EventTrophyWinner.user_id)
            .all()
        )
        for uid, n in won:
            ledger.add(uid, "trophy", n * TROPHY_XP, n)

    photos = (
        db.query(MediaItem.uploaded_by, MediaItem.event_id, func.count())
        .filter(MediaItem.file_type == "image")
        .group_by(MediaItem.uploaded_by, MediaItem.event_id)
        .all()
    )
    for uid, _event_id, n in photos:
        counted = min(n, PHOTOS_PER_EVENT_CAP)
        ledger.add(uid, "photo", counted * PHOTO_XP, counted)

    day = func.date(ChatMessage.created_at)
    chat_counted: Dict[int, int] = defaultdict(int)
    for uid, _day, n in db.query(ChatMessage.user_id, day, func.count()).group_by(ChatMessage.user_id, day).all():
        chat_counted[uid] += min(n, CHAT_MESSAGES_PER_DAY_CAP)
    for uid, counted in chat_counted.items():
        steps = counted // CHAT_MESSAGES_PER_STEP
        if steps:
            ledger.add(uid, "chat", steps * CHAT_XP, counted)

    for (uid,) in db.query(User.id).filter(User.avatar_url.isnot(None), User.avatar_url != "").all():
        ledger.add(uid, "avatar", AVATAR_XP)

    return ledger


def user_xp(db: Session, user_id: int) -> XpSummary:
    """One member's XP with its breakdown, for their profile."""
    return _build_ledger(db).summary(user_id)


def crew_xp(db: Session, users: Sequence[User]) -> List[XpSummary]:
    """Everyone's XP in one pass (one query per source, not one per member),
    best first. Ties keep the order of `users`."""
    ledger = _build_ledger(db)
    summaries = [ledger.summary(u.id) for u in users]
    summaries.sort(key=lambda s: -s.total)
    return summaries
