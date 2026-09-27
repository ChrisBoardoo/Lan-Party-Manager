"""League of Legends end-of-game capture — the one place that knows the
League Client's JSON shape.

A member's desktop app forwards, untouched, the client's own end-of-game block
(`GET /lol-end-of-game/v1/eog-stats-block` on its local API, the "LCU") and the
game session it read at game start (`GET /lol-gameflow/v1/session`). Parsing
happens here, server-side, on purpose: the LCU is unofficial and a patch can
rename a field — fixing that here is one Pi redeploy, not a desktop release
every member has to install.

The field names below were first taken from community documentation, then
checked against a real capture on 2026-09-24 (an ARAM game, via
md/games_extensions/League_Of_Legends/lol_capture.ps1 — see
tests/test_lol_real_captures.py): every one of them is there. Lookups still go
through a list of candidate names, so a future rename is handled by adding a
name, not by rewriting the parser. Note the real block also carries lowercase
duplicates of some stats (`assists` next to `ASSISTS`, `kills`, `deaths`) —
harmless here, JSON keys are case-sensitive in Python.
"""
from dataclasses import dataclass
from typing import Any, List, Optional

from riot_id import riot_id_key

GAME_NAME_FIELDS = ("riotIdGameName", "gameName")
TAG_LINE_FIELDS = ("riotIdTagLine", "tagLine")
CHAMPION_FIELDS = ("championName", "skinName")
KILLS_FIELDS = ("CHAMPIONS_KILLED",)
DEATHS_FIELDS = ("NUM_DEATHS",)
ASSISTS_FIELDS = ("ASSISTS",)
DAMAGE_FIELDS = ("TOTAL_DAMAGE_DEALT_TO_CHAMPIONS",)


class CaptureError(ValueError):
    """The payload isn't an end-of-game block this parser can read."""


@dataclass(frozen=True)
class CapturedPlayer:
    riot_id: str          # display form, "GameName#TAG"
    riot_id_key: str      # matching form — see riot_id.riot_id_key
    champion: Optional[str]
    team_id: Optional[int]
    win: bool
    kills: int
    deaths: int
    assists: int
    damage: int


@dataclass(frozen=True)
class CapturedGame:
    riot_game_id: str
    game_mode: Optional[str]
    queue_type: Optional[str]
    is_custom: bool
    duration_s: Optional[int]
    players: List[CapturedPlayer]
    # A remake (the early vote when someone never loaded in) — not a game
    # anyone played, so router_lol doesn't count it.
    is_remake: bool = False


def _first(obj: Any, names) -> Any:
    if not isinstance(obj, dict):
        return None
    for name in names:
        value = obj.get(name)
        if value is not None and value != "":
            return value
    return None


def _count(stats: Any, names) -> int:
    """A stat as a non-negative int; missing or garbage counts as 0 rather
    than failing the whole game over one odd field."""
    try:
        return max(int(_first(stats, names)), 0)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _riot_id(player: dict) -> Optional[tuple[str, str]]:
    """(display, key), or None for a player with no usable Riot ID — a bot,
    or a shape we don't know. No Riot-rules validation here: whatever the
    client says is what the game used."""
    name = _first(player, GAME_NAME_FIELDS)
    tag = _first(player, TAG_LINE_FIELDS)
    if name is None or tag is None:
        # Older blocks only had a summonerName, which may carry the tag.
        legacy = _first(player, ("summonerName",))
        if not isinstance(legacy, str) or "#" not in legacy:
            return None
        name, _, tag = legacy.rpartition("#")
    name, tag = str(name).strip(), str(tag).strip()
    if not name or not tag:
        return None
    return f"{name}#{tag}", riot_id_key(name, tag)


def _is_custom(eog: dict, session: Optional[dict]) -> bool:
    game_data = session.get("gameData") if isinstance(session, dict) else None
    flag = game_data.get("isCustomGame") if isinstance(game_data, dict) else None
    if isinstance(flag, bool):
        return flag
    game_type = eog.get("gameType")
    return isinstance(game_type, str) and game_type.upper() == "CUSTOM_GAME"


def parse_end_of_game(eog: Any, session: Any = None) -> CapturedGame:
    if not isinstance(eog, dict):
        raise CaptureError("End-of-game block must be a JSON object")
    game_id = _optional_int(eog.get("gameId"))
    if not game_id or game_id <= 0:
        raise CaptureError("End-of-game block has no gameId")
    teams = eog.get("teams")
    if not isinstance(teams, list) or not teams:
        raise CaptureError("End-of-game block has no teams")

    players: List[CapturedPlayer] = []
    seen: set[str] = set()
    for team in teams:
        if not isinstance(team, dict):
            continue
        team_won = team.get("isWinningTeam") is True
        for p in team.get("players") or []:
            if not isinstance(p, dict) or p.get("botPlayer") is True:
                continue
            ident = _riot_id(p)
            if ident is None or ident[1] in seen:
                continue
            seen.add(ident[1])
            stats = p.get("stats")
            champion = _first(p, CHAMPION_FIELDS)
            players.append(CapturedPlayer(
                riot_id=ident[0],
                riot_id_key=ident[1],
                champion=str(champion) if champion is not None else None,
                team_id=_optional_int(team.get("teamId")),
                win=team_won,
                kills=_count(stats, KILLS_FIELDS),
                deaths=_count(stats, DEATHS_FIELDS),
                assists=_count(stats, ASSISTS_FIELDS),
                damage=_count(stats, DAMAGE_FIELDS),
            ))
    if not players:
        raise CaptureError("End-of-game block has no identifiable player")

    game_mode = eog.get("gameMode")
    queue_type = eog.get("queueType")
    return CapturedGame(
        riot_game_id=str(game_id),
        game_mode=game_mode if isinstance(game_mode, str) and game_mode else None,
        queue_type=queue_type if isinstance(queue_type, str) and queue_type else None,
        is_custom=_is_custom(eog, session),
        duration_s=_optional_int(eog.get("gameLength")),
        players=players,
        is_remake=eog.get("gameEndedInEarlySurrender") is True,
    )
