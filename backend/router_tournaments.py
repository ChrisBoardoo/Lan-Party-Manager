from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
from typing import Optional
from datetime import datetime
import math, random

from database import get_db
from models import (
    User, Tournament, Team, TeamMember, Match, Game, EventRSVP, ScheduleBlock, UserGameLibrary,
)
from schemas import (
    TournamentCreate, TournamentOut, TournamentUpdate,
    TeamCreate, TeamOut, MatchUpdate, MatchOut, ReportScore,
    RoundRobinStanding, HallOfFameEntry,
    TournamentGameOut, GameStatsSummary, GameStatsLeader, GameStatsDetail,
    PlayerGameStatsLine, UnlinkedTournamentOut,
)
from auth import get_current_user, require_admin
from activity import add_activity, add_audit
from games_catalog import resolve_game
from router_settings import is_feature_enabled
from tournament_stats import (
    decided_matches, leaderboard_key, linked_tournaments, player_game_records,
    team_records, winning_user_ids,
)

router = APIRouter()

ROUNDS_MAP = {
    2: ["final"],
    4: ["semifinal", "final"],
    8: ["quarterfinal", "semifinal", "final"],
    16: ["round_of_16", "quarterfinal", "semifinal", "final"],
}


def _bracket_rounds(n: int) -> list[str]:
    size = 2 ** math.ceil(math.log2(max(n, 2)))
    return ROUNDS_MAP.get(size, ["final"])


def _advance_winner(match: Match, db: Session) -> None:
    all_matches = db.query(Match).filter(Match.tournament_id == match.tournament_id).all()
    max_round = max(m.round_number for m in all_matches)
    if match.round_number >= max_round:
        return
    next_rn = match.round_number + 1
    next_mn = (match.match_number + 1) // 2
    slot = "a" if match.match_number % 2 == 1 else "b"
    next_match = db.query(Match).filter(
        Match.tournament_id == match.tournament_id,
        Match.round_number == next_rn,
        Match.match_number == next_mn,
    ).first()
    if next_match and match.winner_id:
        if slot == "a":
            next_match.team_a_id = match.winner_id
        else:
            next_match.team_b_id = match.winner_id


def _finalize_match(db: Session, tid: int, t: Tournament, match: Match, actor_id: int) -> None:
    """Apply the completion side-effects for a match whose status is 'completed':
    resolve the winner, advance the bracket (or close the round robin), and log
    the activity. Shared by the organizer's direct update and the confirm-a-
    reported-score flow so both behave identically."""
    if t.bracket_type == "round_robin":
        if match.score_a > match.score_b:
            match.winner_id = match.team_a_id
        elif match.score_b > match.score_a:
            match.winner_id = match.team_b_id
        else:
            match.winner_id = None

        all_matches = db.query(Match).filter(Match.tournament_id == tid).all()
        if all(m.status == "completed" for m in all_matches):
            t.status = "completed"
    else:
        if match.winner_id:
            _advance_winner(match, db)

            round_matches = db.query(Match).filter(
                Match.tournament_id == tid,
                Match.round_number == match.round_number,
            ).all()
            if all(m.status == "completed" for m in round_matches):
                next_round = db.query(Match).filter(
                    Match.tournament_id == tid,
                    Match.round_number == match.round_number + 1,
                ).all()
                t.status = next_round[0].round if next_round else "completed"

    add_activity(
        db, actor_id, "match_completed",
        f"Match completed in {t.game_name}", "match", match.id
    )


def _user_in_match(db: Session, match: Match, user_id: int) -> bool:
    """True if the user is a member of either team in the match — the eligibility
    check for self-service score reporting."""
    team_ids = [tid for tid in (match.team_a_id, match.team_b_id) if tid is not None]
    if not team_ids:
        return False
    return (
        db.query(TeamMember)
        .filter(TeamMember.team_id.in_(team_ids), TeamMember.user_id == user_id)
        .first()
        is not None
    )


def _generate_round_robin(teams: list) -> list:
    """Return list of rounds; each round is a list of (team_a, team_b) pairs."""
    lst = list(teams)
    if len(lst) % 2 == 1:
        lst.append(None)  # bye
    n = len(lst)
    rounds = []
    for _ in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = lst[i], lst[n - 1 - i]
            if a is not None and b is not None:
                pairs.append((a, b))
        rounds.append(pairs)
        lst = [lst[0]] + [lst[-1]] + lst[1:-1]
    return rounds


def _tournament_options():
    return [
        selectinload(Tournament.organizer),
        selectinload(Tournament.teams).selectinload(Team.members),
        selectinload(Tournament.matches).selectinload(Match.team_a).selectinload(Team.members),
        selectinload(Tournament.matches).selectinload(Match.team_b).selectinload(Team.members),
    ]


# ── Hall of Fame ───────────────────────────────────────────────────────────────

@router.get("/hall-of-fame", response_model=list[HallOfFameEntry])
def hall_of_fame(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    completed = (
        db.query(Tournament)
        .filter(Tournament.status == "completed")
        .options(*_tournament_options())
        .all()
    )

    user_wins: dict[int, int] = {}
    user_participations: dict[int, int] = {}

    for t in completed:
        for uid in winning_user_ids(t):
            user_wins[uid] = user_wins.get(uid, 0) + 1

        for team in t.teams:
            for member in team.members:
                if member.user_id:
                    user_participations[member.user_id] = user_participations.get(member.user_id, 0) + 1

    all_ids = set(user_wins) | set(user_participations)
    result = []
    for uid in all_ids:
        u = db.query(User).filter(User.id == uid).first()
        if u:
            result.append(HallOfFameEntry(
                user_id=uid,
                username=u.username,
                avatar_url=u.avatar_url,
                wins=user_wins.get(uid, 0),
                participations=user_participations.get(uid, 0),
            ))

    result.sort(key=lambda x: (-x.wins, -x.participations))
    return result[:10]


# ── Game picker + per-game stats ──────────────────────────────────────────────
# Declared before the /{tid} routes: a path like /games would otherwise be
# captured by /{tid} and rejected as a non-integer id (422).

@router.get("/games", response_model=list[TournamentGameOut])
def tournament_games(
    event_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """The shared catalog for the tournament game picker, best candidates first:
    games already played in tournaments, then the ones most of the event's
    attendees own, then the ones on the event's planning, then A-Z.

    Deliberately NOT gated by the `games` feature (profile library/wishlist):
    the catalog itself is seeded by migration 0019 regardless, and tournaments
    need it either way. Ownership counts only use library data when that
    feature is on, since members only fill a library when they can see it."""
    games = db.query(Game).all()
    counts = dict(
        db.query(Tournament.game_id, func.count(Tournament.id))
        .filter(Tournament.game_id.isnot(None))
        .group_by(Tournament.game_id)
        .all()
    )

    owners: dict[int, int] = {}
    planned: set[int] = set()
    if event_id is not None:
        if is_feature_enabled(db, "games"):
            attendees = db.query(EventRSVP.user_id).filter(
                EventRSVP.event_id == event_id, EventRSVP.status == "in"
            )
            owners = dict(
                db.query(UserGameLibrary.game_id, func.count(func.distinct(UserGameLibrary.user_id)))
                .filter(UserGameLibrary.user_id.in_(attendees))
                .group_by(UserGameLibrary.game_id)
                .all()
            )
        if is_feature_enabled(db, "planning"):
            # ScheduleBlock.game is still free text: match it to the catalog by name.
            names = {
                (b.game or "").strip().lower()
                for b in db.query(ScheduleBlock).filter(ScheduleBlock.event_id == event_id).all()
            }
            planned = {g.id for g in games if g.name.strip().lower() in names}

    rows = [
        TournamentGameOut(
            id=g.id, name=g.name, genre=g.genre, default_max_players=g.default_max_players,
            is_custom=bool(g.is_custom), tournament_count=counts.get(g.id, 0),
            owner_count=owners.get(g.id, 0), planned=g.id in planned,
        )
        for g in games
    ]
    rows.sort(key=lambda r: (-r.tournament_count, -r.owner_count, not r.planned, r.name.lower()))
    return rows


def _users_by_id(db: Session, ids) -> dict[int, User]:
    ids = set(ids)
    if not ids:
        return {}
    return {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}


def _match_count(tournaments) -> int:
    return sum(len(decided_matches(t.matches)) for t in tournaments)


@router.get("/stats/games", response_model=list[GameStatsSummary])
def game_stats_overview(
    event_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """One line per game with at least one decided match (optionally within one
    event): tournaments, decided matches, distinct linked players, the leader.
    A game whose only tournament hasn't played a match yet has nothing to show.

    Tournaments only: League of Legends games captured during LANs have their
    own tab on the Games page (router_lol.py), not a line here."""
    tournaments = linked_tournaments(db, event_id=event_id)
    by_game: dict[int, list] = {}
    for t in tournaments:
        by_game.setdefault(t.game_id, []).append(t)
    records = player_game_records(tournaments)
    games = {g.id: g for g in db.query(Game).filter(Game.id.in_(by_game)).all()} if by_game else {}
    users = _users_by_id(db, (r.user_id for r in records))

    out = []
    for game_id, ts in by_game.items():
        game = games.get(game_id)
        matches = _match_count(ts)
        if not game or matches == 0:
            continue
        lines = sorted((r for r in records if r.game_id == game_id), key=leaderboard_key)
        leader = None
        if lines and lines[0].wins > 0 and lines[0].user_id in users:
            u = users[lines[0].user_id]
            leader = GameStatsLeader(user_id=u.id, username=u.username, avatar_url=u.avatar_url, wins=lines[0].wins)
        out.append(GameStatsSummary(
            game_id=game_id, name=game.name, genre=game.genre, tournaments=len(ts),
            matches=matches, players=len(lines), leader=leader,
        ))
    out.sort(key=lambda s: (-s.matches, -s.tournaments, s.name.lower()))
    return out


@router.get("/stats/games/{game_id}", response_model=GameStatsDetail)
def game_stats_detail(
    game_id: int,
    event_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """The per-player leaderboard for one game."""
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(404, "Game not found")
    tournaments = [t for t in linked_tournaments(db, event_id=event_id) if t.game_id == game_id]
    lines = sorted(player_game_records(tournaments), key=leaderboard_key)
    users = _users_by_id(db, (r.user_id for r in lines))
    players = [
        PlayerGameStatsLine(
            user_id=r.user_id, username=users[r.user_id].username, avatar_url=users[r.user_id].avatar_url,
            played=r.played, wins=r.wins, losses=r.losses, draws=r.draws, win_rate=r.win_rate,
            tournaments=r.tournaments, titles=r.titles,
        )
        for r in lines if r.user_id in users
    ]
    return GameStatsDetail(
        game_id=game.id, name=game.name, genre=game.genre, tournaments=len(tournaments),
        matches=_match_count(tournaments), players=players,
    )


@router.get("/stats/unlinked", response_model=list[UnlinkedTournamentOut])
def unlinked_tournaments(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Tournaments the 0028 backfill couldn't match to a catalog game (free-text
    names like "LoL"). Invisible to per-game stats until an admin attaches them
    via PUT /{tid} with a game_id."""
    return (
        db.query(Tournament)
        .filter(Tournament.game_id.is_(None))
        .order_by(Tournament.created_at.desc())
        .all()
    )


def _game_for(db: Session, game_id: Optional[int], game_name: Optional[str], user_id: int) -> Game:
    """The catalog game a tournament should point at: the explicit pick, or the
    typed name looked up / added as a custom game."""
    if game_id is not None:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            raise HTTPException(404, "Game not found")
        return game
    if not game_name or not game_name.strip():
        raise HTTPException(422, "A game is required")
    return resolve_game(db, game_name, user_id)


# ── Tournament CRUD ───────────────────────────────────────────────────────────

@router.get("/", response_model=list[TournamentOut])
def list_tournaments(
    event_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(Tournament).options(*_tournament_options())
    if event_id is not None:
        query = query.filter(Tournament.event_id == event_id)
    return query.all()


@router.post("/", response_model=TournamentOut, status_code=201)
def create_tournament(
    data: TournamentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_tournament_organizer and current_user.role not in ("admin", "treasurer"):
        raise HTTPException(403, "You must be a tournament organizer or admin")
    payload = data.model_dump()
    game = _game_for(db, payload.pop("game_id"), payload.pop("game_name"), current_user.id)
    t = Tournament(**payload, game_id=game.id, game_name=game.name, organizer_id=current_user.id)
    db.add(t)
    db.commit()
    db.refresh(t)
    add_activity(db, current_user.id, "tournament_created", f"Created tournament: {t.game_name}", "tournament", t.id)
    db.commit()
    return t


@router.get("/{tid}", response_model=TournamentOut)
def get_tournament(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    t = db.query(Tournament).options(*_tournament_options()).filter(Tournament.id == tid).first()
    if not t:
        raise HTTPException(404, "Tournament not found")
    return t


@router.put("/{tid}", response_model=TournamentOut)
def update_tournament(
    tid: int,
    data: TournamentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t = db.query(Tournament).filter(Tournament.id == tid).first()
    if not t:
        raise HTTPException(404, "Tournament not found")
    if t.organizer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")
    fields = data.model_dump(exclude_unset=True)
    game_id = fields.pop("game_id", None)
    game_name = fields.pop("game_name", None)
    if game_id is not None or (game_name and game_name.strip()):
        game = _game_for(db, game_id, game_name, current_user.id)
        t.game_id = game.id
        t.game_name = game.name
    for field, value in fields.items():
        setattr(t, field, value)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{tid}")
def delete_tournament(
    tid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t = db.query(Tournament).filter(Tournament.id == tid).first()
    if not t:
        raise HTTPException(404, "Tournament not found")
    if t.organizer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")
    add_audit(db, current_user.id, "tournament_deleted", f"Tournament: {t.game_name}")
    db.delete(t)
    db.commit()
    return {"ok": True}


# ── Standings (round-robin) ───────────────────────────────────────────────────

@router.get("/{tid}/standings", response_model=list[RoundRobinStanding])
def get_standings(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    t = db.query(Tournament).filter(Tournament.id == tid).first()
    if not t:
        raise HTTPException(404, "Tournament not found")
    if t.bracket_type != "round_robin":
        raise HTTPException(400, "Standings only available for round-robin tournaments")

    return [
        RoundRobinStanding(
            team_id=r.team_id,
            team_name=r.team_name,
            color=r.color,
            seed=r.seed,
            wins=r.wins,
            losses=r.losses,
            draws=r.draws,
            points=r.points,
            played=r.played,
        )
        for r in team_records(t)
    ]


# ── Teams ─────────────────────────────────────────────────────────────────────

def _editable_teams_tournament(db: Session, tid: int, user: User) -> Tournament:
    """The tournament whose teams `user` is about to change, or the reason they can't.

    Same rule as update_tournament/generate_brackets: its organizer or an admin —
    these four routes used to check only that the caller was signed in, so any
    member could rename, empty or delete any team. And only while the tournament is
    still `pending`: once brackets exist, matches point at teams by id, and deleting
    one nulls it out of finished matches, rewriting the bracket, the Hall of Fame
    and per-game stats after the fact. Tournaments.tsx already hides these buttons
    outside that window; this makes the API agree.
    """
    t = db.query(Tournament).filter(Tournament.id == tid).first()
    if not t:
        raise HTTPException(404, "Tournament not found")
    if t.organizer_id != user.id and user.role != "admin":
        raise HTTPException(403, "Only the tournament's organizer or an admin can change its teams")
    if t.status != "pending":
        raise HTTPException(409, "Teams are locked once the brackets are generated")
    return t


@router.post("/{tid}/teams", response_model=TeamOut, status_code=201)
def add_team(
    tid: int,
    data: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _editable_teams_tournament(db, tid, current_user)

    team = Team(tournament_id=tid, team_name=data.team_name, color=data.color, seed=data.seed)
    db.add(team)
    db.flush()

    for m in data.members:
        db.add(TeamMember(team_id=team.id, **m.model_dump()))

    db.commit()
    db.refresh(team)
    return team


@router.put("/{tid}/teams/{team_id}", response_model=TeamOut)
def update_team(
    tid: int,
    team_id: int,
    data: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _editable_teams_tournament(db, tid, current_user)
    team = db.query(Team).filter(Team.id == team_id, Team.tournament_id == tid).first()
    if not team:
        raise HTTPException(404, "Team not found")

    team.team_name = data.team_name
    if data.color is not None:
        team.color = data.color
    if data.seed is not None:
        team.seed = data.seed

    for member in team.members:
        db.delete(member)
    db.flush()

    for m in data.members:
        db.add(TeamMember(team_id=team.id, **m.model_dump()))

    db.commit()
    db.refresh(team)
    return team


@router.patch("/{tid}/teams/{team_id}/seed", response_model=TeamOut)
def set_team_seed(
    tid: int,
    team_id: int,
    seed: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _editable_teams_tournament(db, tid, current_user)
    team = db.query(Team).filter(Team.id == team_id, Team.tournament_id == tid).first()
    if not team:
        raise HTTPException(404, "Team not found")
    team.seed = seed
    db.commit()
    db.refresh(team)
    return team


@router.delete("/{tid}/teams/{team_id}")
def delete_team(
    tid: int,
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _editable_teams_tournament(db, tid, current_user)
    team = db.query(Team).filter(Team.id == team_id, Team.tournament_id == tid).first()
    if not team:
        raise HTTPException(404, "Team not found")
    db.delete(team)
    db.commit()
    return {"ok": True}


# ── Brackets ──────────────────────────────────────────────────────────────────

@router.post("/{tid}/generate-brackets")
def generate_brackets(
    tid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t = db.query(Tournament).filter(Tournament.id == tid).first()
    if not t:
        raise HTTPException(404, "Tournament not found")
    if t.organizer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")

    teams = db.query(Team).filter(Team.tournament_id == tid).all()
    if len(teams) < 2:
        raise HTTPException(400, "Need at least 2 teams to generate brackets")

    db.query(Match).filter(Match.tournament_id == tid).delete()
    db.flush()

    if t.bracket_type == "round_robin":
        seeded = sorted(teams, key=lambda x: (x.seed is None, x.seed or 0))
        rr_rounds = _generate_round_robin(seeded)

        for rn, pairs in enumerate(rr_rounds, start=1):
            for mn, (ta, tb) in enumerate(pairs, start=1):
                db.add(Match(
                    tournament_id=tid,
                    round=f"round_{rn}",
                    round_number=rn,
                    match_number=mn,
                    team_a_id=ta.id,
                    team_b_id=tb.id,
                    status="pending",
                ))

        t.status = "round_robin"
        db.commit()
        return {"ok": True, "type": "round_robin", "rounds": len(rr_rounds), "teams": len(teams)}

    # Single elimination
    rounds = _bracket_rounds(len(teams))
    bracket_size = 2 ** math.ceil(math.log2(len(teams)))

    seeded = sorted(teams, key=lambda x: (x.seed is None, x.seed or 0))
    if all(t.seed is None for t in teams):
        random.shuffle(seeded)
    while len(seeded) < bracket_size:
        seeded.append(None)

    first_round = rounds[0]
    match_count = bracket_size // 2

    for i in range(match_count):
        ta = seeded[i * 2]
        tb = seeded[i * 2 + 1]
        winner_id = None
        status = "pending"
        if ta is None and tb is not None:
            winner_id, status, ta, tb = tb.id, "completed", tb, None
        elif tb is None and ta is not None:
            winner_id, status = ta.id, "completed"

        db.add(Match(
            tournament_id=tid,
            round=first_round,
            round_number=1,
            match_number=i + 1,
            team_a_id=ta.id if ta else None,
            team_b_id=tb.id if tb else None,
            winner_id=winner_id,
            status=status,
        ))

    prev = match_count
    for rn, rname in enumerate(rounds[1:], start=2):
        this = prev // 2
        for i in range(this):
            db.add(Match(tournament_id=tid, round=rname, round_number=rn, match_number=i + 1, status="pending"))
        prev = this

    t.status = first_round
    db.commit()
    return {"ok": True, "type": "single_elimination", "rounds": rounds, "teams": len(teams)}


# ── Matches ───────────────────────────────────────────────────────────────────

@router.put("/{tid}/matches/{match_id}", response_model=MatchOut)
def update_match(
    tid: int,
    match_id: int,
    data: MatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    match = db.query(Match).filter(Match.id == match_id, Match.tournament_id == tid).first()
    if not match:
        raise HTTPException(404, "Match not found")

    t = db.query(Tournament).filter(Tournament.id == tid).first()
    if t.organizer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(match, field, value)

    if match.status == "completed":
        _finalize_match(db, tid, t, match, current_user.id)

    db.commit()
    db.refresh(match)
    return match


@router.post("/{tid}/matches/{match_id}/report", response_model=MatchOut)
def report_match_score(
    tid: int,
    match_id: int,
    data: ReportScore,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A participant submits a proposed score from their own device. Only the
    reported_* fields are written — the live score, winner and bracket are
    untouched until an organizer confirms it."""
    match = db.query(Match).filter(Match.id == match_id, Match.tournament_id == tid).first()
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status == "completed":
        raise HTTPException(400, "This match is already completed")
    if match.team_a_id is None or match.team_b_id is None:
        raise HTTPException(400, "Both teams must be set before reporting a score")

    t = db.query(Tournament).filter(Tournament.id == tid).first()
    is_staff = t.organizer_id == current_user.id or current_user.role == "admin"
    if not is_staff and not _user_in_match(db, match, current_user.id):
        raise HTTPException(403, "Only a player in this match can report its score")

    match.reported_score_a = data.score_a
    match.reported_score_b = data.score_b
    match.reported_by = current_user.id
    match.reported_at = datetime.utcnow()
    add_activity(
        db, current_user.id, "score_reported",
        f"Reported a score in {t.game_name}", "match", match.id
    )
    db.commit()
    db.refresh(match)
    return match


@router.post("/{tid}/matches/{match_id}/confirm", response_model=MatchOut)
def confirm_match_score(
    tid: int,
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Organizer/admin accepts a reported score: it becomes the live score and
    the bracket advances, exactly as a direct update would."""
    match = db.query(Match).filter(Match.id == match_id, Match.tournament_id == tid).first()
    if not match:
        raise HTTPException(404, "Match not found")
    t = db.query(Tournament).filter(Tournament.id == tid).first()
    if t.organizer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")
    if match.reported_at is None:
        raise HTTPException(400, "No reported score to confirm")

    ra, rb = match.reported_score_a, match.reported_score_b
    if ra == rb and t.bracket_type != "round_robin":
        raise HTTPException(400, "A knockout match can't end in a draw")

    match.score_a = ra
    match.score_b = rb
    if ra > rb:
        match.winner_id = match.team_a_id
    elif rb > ra:
        match.winner_id = match.team_b_id
    else:
        match.winner_id = None
    match.status = "completed"
    _finalize_match(db, tid, t, match, current_user.id)

    match.reported_score_a = None
    match.reported_score_b = None
    match.reported_by = None
    match.reported_at = None
    db.commit()
    db.refresh(match)
    return match


@router.delete("/{tid}/matches/{match_id}/report", response_model=MatchOut)
def reject_match_report(
    tid: int,
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clear a pending reported score. Allowed to the organizer/admin or the
    player who submitted it."""
    match = db.query(Match).filter(Match.id == match_id, Match.tournament_id == tid).first()
    if not match:
        raise HTTPException(404, "Match not found")
    t = db.query(Tournament).filter(Tournament.id == tid).first()
    is_staff = t.organizer_id == current_user.id or current_user.role == "admin"
    if not is_staff and match.reported_by != current_user.id:
        raise HTTPException(403, "Forbidden")

    match.reported_score_a = None
    match.reported_score_b = None
    match.reported_by = None
    match.reported_at = None
    db.commit()
    db.refresh(match)
    return match
