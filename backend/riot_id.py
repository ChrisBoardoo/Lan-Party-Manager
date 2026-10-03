"""Riot ID — the `GameName#TAG` a member types on their profile.

It exists so League of Legends end-of-game captures (not built yet — see
md/2.features/games_extensions/League_Of_Legends/lol_extension.md) can be matched to LPM
accounts. Declarative, not verified: Riot's own sign-in (RSO) needs an
approved production key, so unlike Discord/Steam there is no OAuth link.

Riot's rules: game name 3–16 characters, tag line 3–5 alphanumeric
characters. Matching ignores case and the spaces around the `#` — that's the
`key`, stored unique on the user so two members can't claim the same
account. The capture side will compare against the same key.
"""

NAME_MIN, NAME_MAX = 3, 16
TAG_MIN, TAG_MAX = 3, 5


def riot_id_key(game_name: str, tag_line: str) -> str:
    return f"{game_name.strip().casefold()}#{tag_line.strip().casefold()}"


def parse_riot_id(raw: str) -> tuple[str, str]:
    """(display, key) for a typed Riot ID. Raises ValueError when malformed.

    `display` keeps the member's own casing, trimmed around the `#`."""
    name, sep, tag = raw.strip().rpartition("#")
    name, tag = name.strip(), tag.strip()
    if not sep or not name or not tag:
        raise ValueError("Riot ID must look like GameName#TAG")
    if "#" in name or not NAME_MIN <= len(name) <= NAME_MAX:
        raise ValueError(f"Riot ID game name must be {NAME_MIN}-{NAME_MAX} characters")
    if not tag.isalnum() or not TAG_MIN <= len(tag) <= TAG_MAX:
        raise ValueError(f"Riot ID tag must be {TAG_MIN}-{TAG_MAX} letters or digits")
    return f"{name}#{tag}", riot_id_key(name, tag)
