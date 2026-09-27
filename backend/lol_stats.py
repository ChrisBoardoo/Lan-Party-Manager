"""League of Legends LAN stats — per-player aggregates and single-game records
over captured games (models.LolMatch / LolMatchPlayer).

Derived on read, like tournament_stats: the captured lines are the facts,
everything shown is recomputed from them. Pure functions over duck-typed rows
(`.user_id`, `.win`, `.kills`, ...) so they unit-test without a database,
plus the one query that loads a scope's matches.
"""
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from models import Game, LolMatch
from tournament_stats import MIN_MATCHES_FOR_RATE

LOL_CATALOG_NAME = "League of Legends"

# How a captured game is filed for the stats filter. Riot's own game_mode is
# too fine-grained to show (CLASSIC, ARAM, CHERRY, URF...): a crew mostly wants
# "our customs" vs "the rest", with ARAM apart as the other common LAN mode.
CATEGORIES = ("custom", "aram", "matchmade")
RECORD_KINDS = ("kills", "assists", "damage")


def category_of(match: Any) -> str:
    if match.is_custom:
        return "custom"
    if (match.game_mode or "").upper() == "ARAM":
        return "aram"
    return "matchmade"


@dataclass(frozen=True)
class LolPlayerRecord:
    user_id: int
    games: int
    wins: int
    kills: int
    deaths: int
    assists: int
    damage: int

    @property
    def losses(self) -> int:
        return self.games - self.wins

    @property
    def win_rate(self) -> Optional[float]:
        # Same rule as tournament stats: a rate over one or two games is noise.
        if self.games < MIN_MATCHES_FOR_RATE:
            return None
        return self.wins / self.games

    @property
    def kda(self) -> float:
        """(K + A) / D, with a deathless run divided by 1 — the usual LoL
        convention, so a 10/0/5 reads 15.0 rather than infinity."""
        return (self.kills + self.assists) / max(self.deaths, 1)


def player_records(lines: Iterable[Any]) -> List[LolPlayerRecord]:
    """One record per linked player, best KDA first (then most games, then
    user_id so full ties stay deterministic). Unclaimed lines (user_id None)
    are left out — they have no one to belong to yet."""
    tally: dict[int, dict] = {}
    for line in lines:
        if line.user_id is None:
            continue
        t = tally.setdefault(line.user_id, {"games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0, "damage": 0})
        t["games"] += 1
        t["wins"] += 1 if line.win else 0
        t["kills"] += line.kills
        t["deaths"] += line.deaths
        t["assists"] += line.assists
        t["damage"] += line.damage
    records = [LolPlayerRecord(user_id=uid, **t) for uid, t in tally.items()]
    records.sort(key=lambda r: (-r.kda, -r.games, r.user_id))
    return records


def game_records(lines: Iterable[Any]) -> dict[str, Any]:
    """The best single-game line per kind (most kills, assists, damage), among
    linked players. A tie keeps the earliest game — whoever set it first."""
    best: dict[str, Any] = {}
    for line in sorted((ln for ln in lines if ln.user_id is not None), key=lambda ln: ln.match_id):
        for kind in RECORD_KINDS:
            value = getattr(line, kind)
            if value > 0 and (kind not in best or value > getattr(best[kind], kind)):
                best[kind] = line
    return best


def lol_catalog_game(db: Session) -> Optional[Game]:
    return db.query(Game).filter(func.lower(Game.name) == LOL_CATALOG_NAME.lower()).first()


def captured_matches(
    db: Session, *, event_id: Optional[int] = None, category: Optional[str] = None
) -> List[LolMatch]:
    """Captured games with their player lines, newest first, optionally one
    event's and/or one category's (filtered in Python — a LAN is a few dozen
    games, and category_of stays the single definition of a category)."""
    q = db.query(LolMatch).options(selectinload(LolMatch.players))
    if event_id is not None:
        q = q.filter(LolMatch.event_id == event_id)
    matches = q.order_by(LolMatch.created_at.desc(), LolMatch.id.desc()).all()
    if category is not None:
        matches = [m for m in matches if category_of(m) == category]
    return matches


def all_lines(matches: Sequence[LolMatch]) -> List[Any]:
    return [line for m in matches for line in m.players]

