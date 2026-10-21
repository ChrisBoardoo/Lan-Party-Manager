"""lol_capture.parse_end_of_game — reading the League Client's end-of-game block."""
import pytest

from lol_capture import MAX_DAMAGE, MAX_DURATION_S, MAX_KDA, CaptureError, parse_end_of_game
from lol_payloads import eog, player, session
from riot_id import riot_id_key


def _by_id(game):
    return {p.riot_id: p for p in game.players}


def test_reads_the_game_and_every_player():
    game = parse_end_of_game(
        eog(7001, [player("Cross", kills=10, deaths=2, assists=7, damage=31000, champion="Jinx")],
            [player("Bob", tag="FR1", kills=1, deaths=9, assists=3, damage=9000)],
            game_mode="CLASSIC", game_length=1934),
        session(is_custom=True),
    )
    assert game.riot_game_id == "7001"
    assert game.game_mode == "CLASSIC"
    assert game.duration_s == 1934
    assert game.is_custom is True

    players = _by_id(game)
    cross, bob = players["Cross#EUW"], players["Bob#FR1"]
    assert (cross.kills, cross.deaths, cross.assists, cross.damage) == (10, 2, 7, 31000)
    assert cross.champion == "Jinx"
    assert cross.win is True and cross.team_id == 100
    assert bob.win is False and bob.team_id == 200
    assert bob.riot_id_key == "bob#fr1"


def test_4v4_teams_are_fine():
    game = parse_end_of_game(eog(1, [player(f"W{i}xx") for i in range(4)], [player(f"L{i}xx") for i in range(4)]))
    assert len(game.players) == 8
    assert sum(p.win for p in game.players) == 4


def test_custom_flag_comes_from_the_session():
    block = eog(1, [player("Cross")], [player("Bob")])
    assert parse_end_of_game(block, session(is_custom=True)).is_custom is True
    assert parse_end_of_game(block, session(is_custom=False)).is_custom is False


def test_custom_flag_falls_back_to_the_game_type_without_a_session():
    assert parse_end_of_game(eog(1, [player("Cross")], [], gameType="CUSTOM_GAME")).is_custom is True
    assert parse_end_of_game(eog(1, [player("Cross")], [], gameType="MATCHED_GAME")).is_custom is False
    assert parse_end_of_game(eog(1, [player("Cross")], [])).is_custom is False


def test_bots_and_players_without_a_riot_id_are_skipped():
    bot = {"summonerName": "Annie Bot", "championName": "Annie", "stats": {"CHAMPIONS_KILLED": 3}}
    game = parse_end_of_game(eog(1, [player("Cross")], [bot]))
    assert [p.riot_id for p in game.players] == ["Cross#EUW"]


def test_legacy_summoner_name_carrying_the_tag_still_matches():
    legacy = {"summonerName": "OldTimer#EUW", "stats": {"CHAMPIONS_KILLED": 2}}
    game = parse_end_of_game(eog(1, [legacy], []))
    assert game.players[0].riot_id == "OldTimer#EUW"
    assert game.players[0].kills == 2


def test_alternate_name_fields_are_understood():
    alt = {"gameName": "Cross", "tagLine": "EUW", "skinName": "Jinx", "stats": {}}
    game = parse_end_of_game(eog(1, [alt], []))
    assert game.players[0].riot_id == "Cross#EUW"
    assert game.players[0].champion == "Jinx"


def test_missing_or_garbage_stats_count_as_zero():
    odd = player("Cross")
    odd["stats"] = {"CHAMPIONS_KILLED": "lots", "NUM_DEATHS": -4, "ASSISTS": None}
    p = parse_end_of_game(eog(1, [odd], [])).players[0]
    assert (p.kills, p.deaths, p.assists, p.damage) == (0, 0, 0, 0)


def test_a_player_listed_twice_is_kept_once():
    game = parse_end_of_game(eog(1, [player("Cross", kills=5)], [player("cross", kills=9)]))
    assert len(game.players) == 1
    assert game.players[0].kills == 5


@pytest.mark.parametrize("bad", [
    None,
    [],
    {"teams": []},                                        # no gameId
    {"gameId": 0, "teams": [{"players": []}]},            # nonsense id
    {"gameId": 12},                                       # no teams
    {"gameId": 12, "teams": "nope"},
    {"gameId": 12, "teams": [{"players": [{"summonerName": "Bot"}]}]},  # nobody identifiable
])
def test_unreadable_blocks_are_rejected(bad):
    with pytest.raises(CaptureError):
        parse_end_of_game(bad)


def test_bots_are_skipped_by_their_flag_even_with_a_name():
    bot = player("Annie Bot", tag="BOT", botPlayer=True, kills=4)
    game = parse_end_of_game(eog(1, [player("Cross")], [bot]))
    assert [p.riot_id for p in game.players] == ["Cross#EUW"]


def test_remakes_are_flagged():
    block = eog(1, [player("Cross")], [player("Bob")])
    assert parse_end_of_game(block).is_remake is False
    assert parse_end_of_game({**block, "gameEndedInEarlySurrender": True}).is_remake is True


# ── Bounds (D-3 of the 2026-10-20 review) ─────────────────────────────────────

def test_absurd_stats_are_clamped_not_stored():
    game = parse_end_of_game(
        eog(1, [player("Cross", kills=10**30, deaths=-5, assists=250, damage=10**12)], [player("Bob")],
            game_length=10**9),
    )
    cross = _by_id(game)["Cross#EUW"]
    assert (cross.kills, cross.deaths, cross.assists, cross.damage) == (MAX_KDA, 0, MAX_KDA, MAX_DAMAGE)
    assert game.duration_s == MAX_DURATION_S


def test_long_names_are_cut_and_still_match():
    game = parse_end_of_game(eog(1, [player("x" * 300, tag="y" * 40, champion="z" * 300)], [player("Bob")]))
    p = next(q for q in game.players if q.riot_id != "Bob#EUW")
    assert p.riot_id == "x" * 64 + "#" + "y" * 16 and p.champion == "z" * 64
    assert p.riot_id_key == riot_id_key("x" * 64, "y" * 16)


def test_more_than_ten_players_is_not_a_game():
    with pytest.raises(CaptureError):
        parse_end_of_game(eog(1, [player(f"W{i}xx") for i in range(6)], [player(f"L{i}xx") for i in range(5)]))


def test_numbers_beyond_64_bits_are_not_ids():
    with pytest.raises(CaptureError):
        parse_end_of_game(eog(10**30, [player("Cross")], [player("Bob")]))
    block = eog(1, [player("Cross")], [player("Bob")])
    block["teams"][0]["teamId"] = 10**30
    assert _by_id(parse_end_of_game(block))["Cross#EUW"].team_id is None
