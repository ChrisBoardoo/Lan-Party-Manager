"""Crew XP — computed on read, never stored.

Same principle as badges.py: every point comes from a fact another feature
already owns (a LAN attended, a match won, a trophy revealed, a photo in Media,
chat messages, an avatar), so there is no XP table to drift from the truth. An organizer who
corrects a score moves the XP to the right team on the next read, and XP is
retroactive: matches played before the feature was switched on count too.

The breakdown carries codes, not labels — the strings live in the frontend's
i18n bundles as `xp.source.<code>`, same as `badges.<code>.label`.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from event_utils import local_day_start_utc, local_today
from models import (
    ChatMessage, EventRSVP, EventTrophy, EventTrophyWinner, LanEvent, MediaItem, Team, Tournament, User,
)
from router_settings import is_feature_enabled
from tournament_stats import decided_at, decided_matches, match_result, winning_user_ids

# ── Rules: the one place to tune the scale ───────────────────────────────────

# Per linked player of the winning side, by bracket stage (Match.round).
MATCH_WIN_XP = {"final": 100, "semifinal": 60, "quarterfinal": 40, "round_of_16": 25}
# Round-robin rounds ("round_N") and any stage not listed above.
OTHER_MATCH_WIN_XP = 15
# On top of the final, for every linked player of the champion team.
TOURNAMENT_WIN_XP = 50
# Per LAN attended ("in" RSVP), from the day after it ends — a reason to come
# back to LPM the week after. Decided 2026-10-19: showing up is what the crew
# wants most, and winning was nearly the only way to earn XP at a LAN.
ATTENDANCE_XP = 100
# Per monthly contract met (quests.py): two of its objectives in the month.
# Between two LANs, the way to earn a booster a month without a fake tournament.
QUEST_XP = 100
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
# Anti-farming (decided 2026-10-18): XP is earned at a LAN, not in a fake
# tournament or a spam burst between two of them.
# A tournament match counts when it was decided during a LAN: from its first day
# through the day after its last (a final that ends at 2 a.m., the morning after).
TOURNAMENT_DAYS_AFTER_END = 1
# A photo counts when it's attached to a LAN and was uploaded during it or in the
# week after (the camera rolls come in over the following days).
PHOTO_DAYS_AFTER_END = 7
# A chat message shorter than this, or identical to its author's previous one,
# isn't counted.
CHAT_MIN_CHARS = 3
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
    "attendance",
    "quest",
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


Window = Tuple[datetime, datetime]


def lan_windows(db: Session, days_after_end: int) -> Dict[int, Window]:
    """Every LAN as [its first day, the end of `days_after_end` days after its
    last) — local days, as the naive UTC instants the app stores."""
    return {
        e.id: (
            local_day_start_utc(db, e.start_date),
            local_day_start_utc(db, e.end_date + timedelta(days=days_after_end + 1)),
        )
        for e in db.query(LanEvent).all()
    }


def decided_at_a_lan(event_id: Optional[int], when: Optional[datetime], windows: Dict[int, Window]) -> bool:
    """Whether a match decided at `when` happened at a LAN: its tournament's own
    LAN when it has one, any LAN otherwise (plenty of real LAN tournaments were
    created without picking the event). A match decided before matches were
    timestamped (and not recoverable from the activity log, see migration 0036)
    gets the benefit of the doubt only when its tournament belongs to a LAN."""
    if when is None:
        return event_id is not None
    if event_id is not None:
        window = windows.get(event_id)
        return window is not None and window[0] <= when < window[1]
    return any(start <= when < end for start, end in windows.values())


def add_tournament_xp(ledger: _Ledger, tournaments: Sequence[Any], windows: Dict[int, Window]) -> None:
    """Match wins by stage, plus the champion bonus. Duck-typed like
    tournament_stats, so it unit-tests without a session.

    Counts what `decided_matches` counts: no byes (no opponent), no draws, nothing
    still waiting for an organizer. Players never linked to an account earn
    nothing — there is nobody to credit. Only what was decided at a LAN counts
    (`decided_at_a_lan`): a tournament made up between two LANs earns nothing.
    An account on both sides of a match (teams edited before the one-team rule)
    earns nothing from it either."""
    for t in tournaments:
        event_id = getattr(t, "event_id", None)
        roster = {tm.id: list(dict.fromkeys(m.user_id for m in tm.members if m.user_id)) for tm in t.teams}
        for m in decided_matches(t.matches):
            if not decided_at_a_lan(event_id, m.played_at, windows):
                continue
            winner, loser = match_result(m)
            if winner is None:
                continue
            both_sides = set(roster.get(winner, [])) & set(roster.get(loser, []))
            stage = m.round if m.round in MATCH_WIN_XP else "other"
            xp = MATCH_WIN_XP.get(m.round, OTHER_MATCH_WIN_XP)
            for uid in roster.get(winner, []):
                if uid not in both_sides:
                    ledger.add(uid, f"match_{stage}", xp)
        if t.status == "completed" and decided_at_a_lan(event_id, decided_at(t), windows):
            for uid in dict.fromkeys(winning_user_ids(t)):
                ledger.add(uid, "tournament_win", TOURNAMENT_WIN_XP)


def counted_chat_messages(rows: Sequence[Tuple[int, datetime, str]]) -> Dict[int, int]:
    """Chat messages that count, per author: `rows` are (user_id, created_at,
    content) in posting order. A message shorter than CHAT_MIN_CHARS, or the
    same as the author's previous one, doesn't count; then at most
    CHAT_MESSAGES_PER_DAY_CAP a day."""
    per_day: Counter = Counter()
    previous: Dict[int, str] = {}
    for uid, at, content in rows:
        text = " ".join((content or "").split()).casefold()
        repeated = previous.get(uid) == text
        previous[uid] = text
        if len(text) < CHAT_MIN_CHARS or repeated:
            continue
        per_day[(uid, at.date())] += 1
    counted: Dict[int, int] = defaultdict(int)
    for (uid, _day), n in per_day.items():
        counted[uid] += min(n, CHAT_MESSAGES_PER_DAY_CAP)
    return counted


def _build_ledger(db: Session) -> _Ledger:
    ledger = _Ledger()

    tournaments = (
        db.query(Tournament)
        .options(selectinload(Tournament.teams).selectinload(Team.members), selectinload(Tournament.matches))
        .all()
    )
    add_tournament_xp(ledger, tournaments, lan_windows(db, TOURNAMENT_DAYS_AFTER_END))

    # Attendance: every LAN over (as of yesterday) the member was "in" at. An
    # RSVP is one row per member and LAN, so going out and back in can't stack.
    attended = (
        db.query(EventRSVP.user_id, func.count())
        .join(LanEvent, LanEvent.id == EventRSVP.event_id)
        .filter(EventRSVP.status == "in", LanEvent.end_date < local_today(db))
        .group_by(EventRSVP.user_id)
        .all()
    )
    for uid, n in attended:
        ledger.add(uid, "attendance", n * ATTENDANCE_XP, n)

    # Monthly contracts met. Imported here: quests.py reads this module's chat rules.
    if is_feature_enabled(db, "quests"):
        from quests import contracts_met

        for uid, n in contracts_met(db).items():
            ledger.add(uid, "quest", n * QUEST_XP, n)

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

    # Photos: attached to a LAN, uploaded during it or in the week after.
    photo_windows = lan_windows(db, PHOTO_DAYS_AFTER_END)
    photos: Counter = Counter()
    rows = (
        db.query(MediaItem.uploaded_by, MediaItem.event_id, MediaItem.created_at)
        .filter(MediaItem.file_type == "image", MediaItem.event_id.isnot(None))
        .all()
    )
    for uid, event_id, at in rows:
        window = photo_windows.get(event_id)
        if window and at and window[0] <= at < window[1]:
            photos[(uid, event_id)] += 1
    for (uid, _event_id), n in photos.items():
        counted = min(n, PHOTOS_PER_EVENT_CAP)
        ledger.add(uid, "photo", counted * PHOTO_XP, counted)

    chat_rows = (
        db.query(ChatMessage.user_id, ChatMessage.created_at, ChatMessage.content)
        .order_by(ChatMessage.user_id, ChatMessage.created_at, ChatMessage.id)
        .all()
    )
    for uid, counted in counted_chat_messages(chat_rows).items():
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
