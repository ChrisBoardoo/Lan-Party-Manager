"""Real League Client captures, when this machine has some.

lol_capture.py's field names come from community documentation; this is the
test that holds them against the real thing. It reads the JSON files saved by
md/games_extensions/League_Of_Legends/lol_capture.ps1 — kept in the gitignored
md/ folder on purpose, since they carry the crew's Riot IDs — and skips when
there are none (CI, a fresh clone). Run it after capturing a game:

    pytest tests/test_lol_real_captures.py -v
"""
import json
from pathlib import Path

import pytest

from lol_capture import parse_end_of_game

CAPTURES = Path(__file__).resolve().parents[2] / "md" / "games_extensions" / "League_Of_Legends" / "captures"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


EOG_FILES = sorted(CAPTURES.glob("eog-*.json")) if CAPTURES.is_dir() else []
SESSIONS = {}
if CAPTURES.is_dir():
    for path in sorted(CAPTURES.glob("session-*.json")):
        game_id = (_read(path).get("gameData") or {}).get("gameId")
        if game_id:
            SESSIONS[str(game_id)] = _read(path)


@pytest.mark.skipif(not EOG_FILES, reason="no real League capture on this machine")
@pytest.mark.parametrize("path", EOG_FILES, ids=[p.name for p in EOG_FILES])
def test_real_capture_parses(path):
    eog = _read(path)
    session = SESSIONS.get(str(eog.get("gameId")))
    game = parse_end_of_game(eog, session)

    assert len(game.players) >= 2, "fewer than 2 identifiable players: check GAME_NAME_FIELDS / TAG_LINE_FIELDS"
    assert all("#" in p.riot_id for p in game.players)
    assert any(p.damage > 0 for p in game.players), "no damage for anyone: check DAMAGE_FIELDS"
    assert any(p.kills + p.assists > 0 for p in game.players), "no kills or assists at all: check KILLS/ASSISTS_FIELDS"
    assert any(p.win for p in game.players) and not all(p.win for p in game.players), \
        "no winner/loser split: check isWinningTeam"
    assert game.duration_s and game.duration_s > 60, "no game length: check gameLength"
    if session is not None:
        assert game.is_custom is session["gameData"]["isCustomGame"]
