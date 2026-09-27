"""lol_stats — per-player aggregates and records over captured lines (pure)."""
from types import SimpleNamespace

from lol_stats import category_of, game_records, player_records


def _line(user_id, *, match_id=1, win=False, kills=0, deaths=0, assists=0, damage=0, champion="Ahri"):
    return SimpleNamespace(
        user_id=user_id, match_id=match_id, win=win, kills=kills, deaths=deaths,
        assists=assists, damage=damage, champion=champion,
    )


def test_aggregates_every_game_of_a_player():
    recs = {r.user_id: r for r in player_records([
        _line(1, match_id=1, win=True, kills=10, deaths=2, assists=4, damage=30000),
        _line(1, match_id=2, win=False, kills=2, deaths=6, assists=8, damage=12000),
        _line(2, match_id=1, kills=1, deaths=5, assists=1, damage=8000),
    ])}
    one = recs[1]
    assert (one.games, one.wins, one.losses) == (2, 1, 1)
    assert (one.kills, one.deaths, one.assists, one.damage) == (12, 8, 12, 42000)
    assert one.kda == 3.0  # (12 + 12) / 8


def test_unclaimed_lines_are_left_out():
    assert [r.user_id for r in player_records([_line(None, kills=20), _line(3)])] == [3]


def test_deathless_kda_divides_by_one():
    (rec,) = player_records([_line(1, kills=10, deaths=0, assists=5)])
    assert rec.kda == 15.0


def test_win_rate_needs_three_games():
    two = player_records([_line(1, match_id=i, win=True) for i in range(2)])[0]
    three = player_records([_line(1, match_id=i, win=i < 2) for i in range(3)])[0]
    assert two.win_rate is None
    assert three.win_rate == 2 / 3


def test_best_kda_first_then_most_games():
    recs = player_records([
        _line(1, kills=1, deaths=1),                       # KDA 1
        _line(2, kills=5, deaths=1),                       # KDA 5
        _line(3, match_id=1, kills=5, deaths=1),           # KDA 5, but two games
        _line(3, match_id=2, kills=5, deaths=1),
    ])
    assert [r.user_id for r in recs] == [3, 2, 1]


def test_records_pick_the_best_single_game_per_kind():
    best = game_records([
        _line(1, match_id=1, kills=12, assists=3, damage=20000),
        _line(2, match_id=1, kills=4, assists=25, damage=45000, champion="Brand"),
        _line(1, match_id=2, kills=7, assists=9, damage=21000),
    ])
    assert (best["kills"].user_id, best["kills"].kills) == (1, 12)
    assert (best["assists"].user_id, best["assists"].assists) == (2, 25)
    assert (best["damage"].user_id, best["damage"].champion) == (2, "Brand")


def test_a_tied_record_stays_with_whoever_set_it_first():
    best = game_records([_line(2, match_id=5, kills=9), _line(1, match_id=3, kills=9)])
    assert best["kills"].user_id == 1


def test_no_record_for_a_kind_nobody_scored_in():
    assert "kills" not in game_records([_line(1, kills=0, assists=2)])


def test_records_ignore_unclaimed_lines():
    assert game_records([_line(None, kills=30)]) == {}


def test_categories():
    assert category_of(SimpleNamespace(is_custom=True, game_mode="ARAM")) == "custom"
    assert category_of(SimpleNamespace(is_custom=False, game_mode="ARAM")) == "aram"
    assert category_of(SimpleNamespace(is_custom=False, game_mode="CLASSIC")) == "matchmade"
    assert category_of(SimpleNamespace(is_custom=False, game_mode=None)) == "matchmade"
