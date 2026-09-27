"""Builders for League Client end-of-game payloads, shared by the LoL tests.

A minimal version of `/lol-end-of-game/v1/eog-stats-block` (teams → players →
stats), with only the fields lol_capture.py reads — checked against a real
capture on 2026-09-24. Real captures themselves stay out of git (they carry the
crew's Riot IDs): test_lol_real_captures.py reads them from the local md/ folder.
"""


def player(name, tag="EUW", *, champion="Ahri", kills=0, deaths=0, assists=0, damage=0, **extra):
    p = {
        "riotIdGameName": name,
        "riotIdTagLine": tag,
        "championName": champion,
        "stats": {
            "CHAMPIONS_KILLED": kills,
            "NUM_DEATHS": deaths,
            "ASSISTS": assists,
            "TOTAL_DAMAGE_DEALT_TO_CHAMPIONS": damage,
        },
    }
    p.update(extra)
    return p


def eog(game_id, winners, losers, *, game_mode="CLASSIC", queue_type="", game_length=1800, **extra):
    block = {
        "gameId": game_id,
        "gameMode": game_mode,
        "queueType": queue_type,
        "gameLength": game_length,
        "teams": [
            {"teamId": 100, "isWinningTeam": True, "players": winners},
            {"teamId": 200, "isWinningTeam": False, "players": losers},
        ],
    }
    block.update(extra)
    return block


def session(is_custom=True):
    return {"gameData": {"isCustomGame": is_custom, "queue": {"id": 0 if is_custom else 450}}}


def capture(game_id, winners, losers, *, is_custom=True, **eog_kwargs):
    """The POST /api/lol/matches body the desktop app sends."""
    return {"eog": eog(game_id, winners, losers, **eog_kwargs), "session": session(is_custom)}
