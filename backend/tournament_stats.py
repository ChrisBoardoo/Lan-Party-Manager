"""Shared tournament statistics — one definition of standings and "who won".

This logic used to exist in three places: the kiosk's `_winning_team_id` /
`_standings_for`, and an inline copy inside the Hall of Fame. They had drifted
apart in a way that mattered — the champion was picked by raw win count while
the standings table ranked by points (wins*3 + draws), so a 2W/2D team could
top the table while a 3W/0D team was announced as champion. Here the ranking is
the single source of truth and the champion is, by definition, whoever sits at
the top of it: that table is the one on the projector.

Everything except `tournaments_for_event` takes a duck-typed tournament —
anything with `.bracket_type`, `.teams` and `.matches` — so it unit-tests
without a database session, the same way prorata.py does.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Sequence

from sqlalchemy.orm import Session, selectinload

from models import Team, TeamMember, Tournament


@dataclass(frozen=True)
class TeamRecord:
    team_id: int
    team_name: str
    color: Optional[str]
    seed: Optional[int]
    wins: int
    losses: int
    draws: int
    points: int
    played: int


def decided_matches(matches: Sequence[Any]) -> List[Any]:
    """Completed matches with both sides set — the only ones that count."""
    return [m for m in matches if m.status == "completed" and m.team_a_id and m.team_b_id]


def match_result(m: Any) -> tuple[Optional[int], Optional[int]]:
    """(winner_team_id, loser_team_id) of a decided match, or (None, None) for a
    draw — the one definition of "who won a match", shared by the standings table
    and the per-game player stats.

    An explicit `winner_id` wins over the score: in a bracket the organizer
    *clicks* the winner, and the score may well have been left at 0-0 — that is
    not a draw (a knockout match can't end in one). Round-robin sets winner_id
    from the score itself, and None on a draw, so both agree there."""
    if m.winner_id is not None and m.winner_id in (m.team_a_id, m.team_b_id):
        loser = m.team_b_id if m.winner_id == m.team_a_id else m.team_a_id
        return m.winner_id, loser
    if m.score_a > m.score_b:
        return m.team_a_id, m.team_b_id
    if m.score_b > m.score_a:
        return m.team_b_id, m.team_a_id
    return None, None


def team_records(t: Any) -> List[TeamRecord]:
    """Every team's record, ranked best-first.

    Order is (points desc, wins desc, losses asc, team_id asc). The trailing
    team_id is what keeps a full tie deterministic — without it the order fell
    out of however the teams happened to be loaded.
    """
    tally: dict[int, dict] = {tm.id: {"wins": 0, "losses": 0, "draws": 0} for tm in t.teams}

    for m in decided_matches(t.matches):
        if m.team_a_id not in tally or m.team_b_id not in tally:
            continue  # match points at a team that's since been removed
        winner, loser = match_result(m)
        if winner is None:
            tally[m.team_a_id]["draws"] += 1
            tally[m.team_b_id]["draws"] += 1
        else:
            tally[winner]["wins"] += 1
            tally[loser]["losses"] += 1

    records = []
    for tm in t.teams:
        s = tally[tm.id]
        records.append(TeamRecord(
            team_id=tm.id,
            team_name=tm.team_name,
            color=tm.color,
            seed=tm.seed,
            wins=s["wins"],
            losses=s["losses"],
            draws=s["draws"],
            points=s["wins"] * 3 + s["draws"],
            played=s["wins"] + s["losses"] + s["draws"],
        ))

    records.sort(key=lambda r: (-r.points, -r.wins, r.losses, r.team_id))
    return records


def winning_team_id(t: Any) -> Optional[int]:
    """The champion's team id, or None if the tournament hasn't produced one.

    Round-robin: the top of the standings table. A table topped by a team with
    no wins at all — every match drawn — has no champion; that preserves the old
    behaviour, where an empty win tally returned None rather than crowning a
    team that never won anything.

    Single-elimination: the winner of the completed final.
    """
    if t.bracket_type == "round_robin":
        records = team_records(t)
        if not records or records[0].wins < 1:
            return None
        return records[0].team_id

    max_rn = max((m.round_number for m in t.matches), default=0)
    finals = [m for m in t.matches if m.round_number == max_rn and m.status == "completed"]
    return finals[0].winner_id if finals else None


def decided_at(t: Any) -> Optional[datetime]:
    """When the tournament was settled — its latest played match. None for
    legacy tournaments whose matches predate played_at being recorded."""
    stamps = [m.played_at for m in t.matches if m.played_at]
    return max(stamps) if stamps else None


def winning_user_ids(t: Any) -> List[int]:
    """Account ids on the winning team. Team members are free-text names with an
    optional account link, so players who were never linked contribute nothing."""
    wid = winning_team_id(t)
    if not wid:
        return []
    team = next((tm for tm in t.teams if tm.id == wid), None)
    if not team:
        return []
    return [m.user_id for m in team.members if m.user_id]


# A win rate over one or two matches is noise, not a ranking — below this the
# rate isn't reported and the leaderboard falls back to raw wins.
MIN_MATCHES_FOR_RATE = 3


@dataclass(frozen=True)
class PlayerGameRecord:
    """One player's record on one catalog game, across the tournaments given."""
    game_id: int
    user_id: int
    played: int
    wins: int
    losses: int
    draws: int
    tournaments: int
    titles: int

    @property
    def win_rate(self) -> Optional[float]:
        if self.played < MIN_MATCHES_FOR_RATE:
            return None
        return self.wins / self.played


def player_game_records(tournaments: Sequence[Any]) -> List[PlayerGameRecord]:
    """Per-(game, player) win/loss/draw records, derived on read like every other
    stat here — there is no stats table to drift out of sync.

    - Only tournaments linked to a catalog game (`game_id`) count.
    - Only account-linked team members count: a free-text player name has no
      identity to accumulate stats against (same rule as the Hall of Fame).
    - Every linked member of a team is credited with the team's result — five
      lines for one 5v5 match.
    - A match counts once it's decided, even if its tournament never finished;
      a title needs a completed tournament.
    - Byes don't count (a bye has no opponent — see `decided_matches`).
    """
    tally: dict[tuple[int, int], dict] = {}

    def rec(game_id: int, user_id: int) -> dict:
        return tally.setdefault(
            (game_id, user_id),
            {"played": 0, "wins": 0, "losses": 0, "draws": 0, "tournaments": 0, "titles": 0},
        )

    for t in tournaments:
        game_id = getattr(t, "game_id", None)
        if game_id is None:
            continue
        roster = {tm.id: {m.user_id for m in tm.members if m.user_id} for tm in t.teams}
        for uid in set().union(*roster.values()):
            rec(game_id, uid)["tournaments"] += 1

        for m in decided_matches(t.matches):
            if m.team_a_id not in roster or m.team_b_id not in roster:
                continue
            winner, _loser = match_result(m)
            for side in (m.team_a_id, m.team_b_id):
                for uid in roster[side]:
                    r = rec(game_id, uid)
                    r["played"] += 1
                    if winner is None:
                        r["draws"] += 1
                    elif side == winner:
                        r["wins"] += 1
                    else:
                        r["losses"] += 1

        if t.status == "completed":
            for uid in winning_user_ids(t):
                rec(game_id, uid)["titles"] += 1

    return [PlayerGameRecord(game_id=g, user_id=u, **v) for (g, u), v in tally.items()]


def leaderboard_key(r: PlayerGameRecord) -> tuple:
    """Best first: most wins, then the better rate (unrated last), then titles,
    then fewer matches for the same wins; user_id keeps full ties deterministic."""
    rate = r.win_rate
    return (-r.wins, rate is None, -(rate or 0.0), -r.titles, r.played, r.user_id)


def linked_tournaments(
    db: Session, *, event_id: Optional[int] = None, user_id: Optional[int] = None
) -> List[Tournament]:
    """Tournaments linked to a catalog game, loaded with what the per-game stats
    read (teams → members, matches). Optionally only one event's, and/or only
    the ones a given account played in."""
    q = (
        db.query(Tournament)
        .filter(Tournament.game_id.isnot(None))
        .options(selectinload(Tournament.teams).selectinload(Team.members), selectinload(Tournament.matches))
    )
    if event_id is not None:
        q = q.filter(Tournament.event_id == event_id)
    if user_id is not None:
        played_in = (
            db.query(Team.tournament_id)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .filter(TeamMember.user_id == user_id)
        )
        q = q.filter(Tournament.id.in_(played_in))
    return q.all()


def tournaments_for_event(db: Session, event_id: int, *, options: Sequence = ()) -> List[Tournament]:
    """Tournaments belonging to one event, strictly.

    Note the kiosk deliberately casts a wider net, also picking up tournaments
    tied to no event at all so a quick pickup bracket still reaches the
    projector. That's an ambient-display affordance; a recap is a record of what
    happened at *this* event, so it doesn't inherit it.
    """
    q = db.query(Tournament).filter(Tournament.event_id == event_id)
    if options:
        q = q.options(*options)
    return q.all()
