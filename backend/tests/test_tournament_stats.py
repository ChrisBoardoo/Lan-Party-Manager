"""Unit tests for the shared tournament statistics (``tournament_stats``).

Like prorata, everything here except ``tournaments_for_event`` is pure and
duck-typed, so we feed lightweight namespaces rather than persisted rows.

These tests pin down the reconciliation this module exists for: the champion and
the top of the standings table are now the same thing by construction. They used
to be computed differently and could disagree.
"""

from datetime import datetime
from types import SimpleNamespace

from tournament_stats import (
    decided_at,
    team_records,
    winning_team_id,
    winning_user_ids,
)


def _team(tid, name=None, members=(), color=None, seed=None):
    return SimpleNamespace(
        id=tid,
        team_name=name or f"Team {tid}",
        color=color,
        seed=seed,
        members=[SimpleNamespace(player_name=f"p{u}", user_id=u) for u in members],
    )


def _match(a, b, score_a, score_b, *, status="completed", rn=1, winner_id=None, played_at=None):
    return SimpleNamespace(
        team_a_id=a,
        team_b_id=b,
        score_a=score_a,
        score_b=score_b,
        status=status,
        round_number=rn,
        winner_id=winner_id,
        played_at=played_at,
    )


def _rr(teams, matches):
    return SimpleNamespace(bracket_type="round_robin", teams=teams, matches=matches)


def _se(teams, matches):
    return SimpleNamespace(bracket_type="single_elimination", teams=teams, matches=matches)


# ── Records & ranking ─────────────────────────────────────────────────────────

def test_points_are_three_per_win_plus_one_per_draw():
    t = _rr(
        [_team(1), _team(2), _team(3)],
        [_match(1, 2, 5, 3), _match(1, 3, 2, 2), _match(2, 3, 0, 4)],
    )
    by_id = {r.team_id: r for r in team_records(t)}

    assert (by_id[1].wins, by_id[1].draws, by_id[1].losses) == (1, 1, 0)
    assert by_id[1].points == 4  # 3 + 1
    assert by_id[1].played == 2
    assert by_id[2].points == 0  # two losses
    assert by_id[3].points == 4  # a win and a draw


def test_records_are_ranked_best_first():
    t = _rr(
        [_team(1), _team(2), _team(3)],
        [_match(1, 2, 1, 0), _match(1, 3, 1, 0), _match(2, 3, 1, 0)],
    )
    assert [r.team_id for r in team_records(t)] == [1, 2, 3]


def test_full_tie_breaks_deterministically_on_team_id():
    # Nothing played: every record is identical, so only the team_id tiebreak
    # keeps this from depending on load order.
    t = _rr([_team(3), _team(1), _team(2)], [])
    assert [r.team_id for r in team_records(t)] == [1, 2, 3]


def test_pending_matches_do_not_count():
    t = _rr([_team(1), _team(2)], [_match(1, 2, 5, 0, status="pending")])
    assert all(r.played == 0 for r in team_records(t))


def test_match_referencing_a_removed_team_is_ignored():
    t = _rr([_team(1), _team(2)], [_match(1, 99, 5, 0)])
    assert all(r.played == 0 for r in team_records(t))


# ── The reconciliation ────────────────────────────────────────────────────────

def test_round_robin_champion_is_the_top_of_the_standings():
    # Team 1: 2W/0D = 6 pts. Team 2: 1W/2D = 5 pts but would tie on a raw win
    # count against nobody — the point is that champion follows the table.
    t = _rr(
        [_team(1), _team(2), _team(3)],
        [_match(1, 2, 3, 0), _match(1, 3, 3, 0), _match(2, 3, 1, 1)],
    )
    assert winning_team_id(t) == team_records(t)[0].team_id == 1


def test_points_beat_raw_win_count_for_the_champion():
    # The old code picked the champion by raw wins, which disagreed with the
    # table. Both teams win twice; team 2 draws twice (8 pts) to team 1's once
    # (7 pts), so team 2 tops the table and is therefore the champion. Under the
    # old max(wins) the tie broke on dict order instead.
    t = _rr(
        [_team(1), _team(2), _team(3), _team(4)],
        [
            _match(1, 3, 1, 0), _match(1, 4, 1, 0),  # team 1: 2W
            _match(2, 3, 1, 0), _match(2, 4, 1, 0),  # team 2: 2W
            _match(2, 1, 2, 2),                      # team 2: +1 draw
            _match(2, 3, 1, 1),                      # team 2: +1 draw
        ],
    )
    records = team_records(t)
    assert records[0].team_id == 2
    assert records[0].points > records[1].points
    assert winning_team_id(t) == 2


def test_all_draws_has_no_champion():
    # The guard: a team can top the table on draws alone, but crowning a team
    # that never won a match would be a regression on the old behaviour.
    t = _rr([_team(1), _team(2)], [_match(1, 2, 1, 1), _match(1, 2, 2, 2)])
    assert team_records(t)[0].wins == 0
    assert winning_team_id(t) is None


def test_round_robin_with_no_matches_has_no_champion():
    assert winning_team_id(_rr([_team(1), _team(2)], [])) is None


# ── Single elimination ────────────────────────────────────────────────────────

def test_single_elim_champion_is_the_final_winner():
    t = _se(
        [_team(1), _team(2), _team(3), _team(4)],
        [
            _match(1, 2, 1, 0, rn=1, winner_id=1),
            _match(3, 4, 0, 1, rn=1, winner_id=4),
            _match(1, 4, 2, 1, rn=2, winner_id=1),
        ],
    )
    assert winning_team_id(t) == 1


def test_single_elim_with_an_unfinished_final_has_no_champion():
    t = _se(
        [_team(1), _team(2)],
        [_match(1, 2, 0, 0, rn=2, status="in_progress", winner_id=None)],
    )
    assert winning_team_id(t) is None


# ── Winners → accounts ────────────────────────────────────────────────────────

def test_winning_user_ids_skips_players_with_no_account():
    t = _se(
        [_team(1, members=[7, 9]), _team(2, members=[3])],
        [_match(1, 2, 1, 0, rn=1, winner_id=1)],
    )
    t.teams[0].members.append(SimpleNamespace(player_name="guest", user_id=None))
    assert sorted(winning_user_ids(t)) == [7, 9]


def test_winning_user_ids_is_empty_without_a_champion():
    assert winning_user_ids(_rr([_team(1, members=[7])], [])) == []


# ── decided_at ────────────────────────────────────────────────────────────────

def test_decided_at_is_the_latest_played_match():
    early, late = datetime(2026, 7, 1, 20, 0), datetime(2026, 7, 1, 22, 0)
    t = _rr(
        [_team(1), _team(2)],
        [_match(1, 2, 1, 0, played_at=early), _match(1, 2, 0, 1, played_at=late)],
    )
    assert decided_at(t) == late


def test_decided_at_is_none_for_legacy_undated_matches():
    t = _rr([_team(1), _team(2)], [_match(1, 2, 1, 0, played_at=None)])
    assert decided_at(t) is None
