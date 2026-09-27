"""Registry of the embedded mini-games and what a "score" means for each one.

Up to 8 games are planned, and they do not share a metric: NeonSurvivor ranks on
seconds survived, a tower-defense ranks on waves cleared, a speedrun would rank on
elapsed time where *lower* is better. So `minigame_scores` stores one generic ranked
integer (`score`) plus a free-form `details` blob, and this module is the single place
that says, per game, what that integer counts, what bounds are plausible, and how to
sort it.

Adding game number 9 means one entry here, one folder under
`frontend/public/games/<slug>/`, and nothing else on the backend — no migration, no
new endpoint, no router change.

The frontend does not duplicate this list: it reads it from `GET /api/minigames/games`.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class MiniGameSpec:
    """One embedded game.

    slug            folder name under frontend/public/games/ AND the value stored in
                    `minigame_scores.game`. Never rename one in place — old rows keep
                    the old slug and would silently fall off the board.
    metric          what `score` counts. The frontend formats the number from this
                    (i18n key `minigames.metric.<metric>`), e.g. 412 -> "6:52".
    max_score       hard ceiling. A submission above it is rejected outright — this is
                    what makes an absurd forged score impossible regardless of timing.
    detail_fields   keys accepted in the `details` blob. Anything else is dropped, so a
                    tampered client can't grow the row into a storage hole.
    higher_is_better  False for speedrun-shaped games, where the board sorts ascending.
    title           name used in text the backend writes itself (the Hub activity feed,
                    desktop toasts). The frontend's own UI takes names from i18n
                    (`minigames.game.<slug>.name`); this only exists for server-side text.
    score_is_elapsed_seconds
                    True only when `score` literally counts seconds of play, which lets
                    the server bound it by the real time since the run opened. It must
                    stay False for every other metric: a points-based game legitimately
                    scores thousands in a few hundred seconds, and bounding those by the
                    clock would reject every honest run.
    check           extra per-game coherence rules, given the run's real elapsed time.
                    Duration floors live here rather than as a spec field because they
                    are never game-agnostic: "N waves need N×10s" depends on the claimed
                    progress, so a flat per-game minimum would reject an honest early
                    loss. Returns an error string, or None when the run is plausible.
    """

    slug: str
    metric: str
    max_score: int
    detail_fields: tuple[str, ...] = ()
    higher_is_better: bool = True
    title: str = ""
    score_is_elapsed_seconds: bool = False
    check: Optional[Callable[[int, dict, float], Optional[str]]] = field(default=None, repr=False)


def _check_neon_survivor(score: int, details: dict, elapsed_seconds: float) -> Optional[str]:
    """NeonSurvivor: `score` is whole seconds survived.

    The wave check is exact rather than heuristic — the game computes
    `wave = 1 + Math.floor(gameTime/30)` (index.html), so wave is a pure function of
    the score and any other pairing is a forged payload. One wave of tolerance absorbs
    the client's `Math.floor(gameTime)` rounding at a 30s boundary.
    """
    wave = details.get("wave")
    if wave is not None:
        expected = 1 + score // 30
        if abs(wave - expected) > 1:
            return f"wave {wave} is impossible after {score}s (expected ~{expected})"

    kills = details.get("kills")
    if kills is not None and kills > score * 12 + 50:
        return f"{kills} kills is implausible in {score}s"

    level = details.get("level")
    if level is not None and not (1 <= level <= 100):
        return f"level {level} out of range"

    return None



GAMES: dict[str, MiniGameSpec] = {
    "neon-survivor": MiniGameSpec(
        slug="neon-survivor",
        title="Neon Survivor",
        metric="seconds_survived",
        # NOT 600. The final boss spawns at 600s and victory() waits for it to die
        # (`gameTime >= 600 && !bossActive`, index.html), with no wave spawns during a
        # boss fight — so every run that reaches it ends past 10 minutes, win or lose,
        # and the game has no hard end. A 600 ceiling rejected all of them. One hour is
        # a sanity cap far beyond any real boss fight; the elapsed-time check below is
        # what actually bounds this game's score.
        max_score=3600,
        detail_fields=("kills", "wave", "level"),
        # The one game where score and elapsed time are the same quantity.
        score_is_elapsed_seconds=True,
        check=_check_neon_survivor,
    ),
}


def get_spec(slug: str) -> Optional[MiniGameSpec]:
    return GAMES.get(slug)


def format_score(spec: MiniGameSpec, score: int) -> str:
    """The score as players see it, for text the backend writes itself.

    Mirrors `formatMiniGameScore` in frontend/src/components/MiniGames.tsx: the Hub
    shows the leaderboard card and the activity feed side by side, so the feed must
    not say 412 where the card says 6:52.
    """
    if spec.metric in ("seconds_survived", "duration_seconds"):
        return f"{score // 60}:{score % 60:02d}"
    return str(score)


def clean_details(spec: MiniGameSpec, raw: Optional[dict]) -> dict:
    """Keep only the game's declared detail fields, coerced to int.

    Silently drops unknown keys and non-numeric values rather than rejecting: details
    are cosmetic, and a partially-garbled blob shouldn't cost a member a legitimate run.
    The ranked `score` gets no such leniency — see validate_submission.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key in spec.detail_fields:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out[key] = int(value)
    return out


def validate_submission(
    spec: MiniGameSpec, score: int, details: dict, elapsed_seconds: float
) -> Optional[str]:
    """Return an error string, or None when the run is acceptable.

    Three independent gates, cheapest first:
      1. bounds       — 0 <= score <= max_score
      2. clock        — for a game whose score IS a duration, the run cannot claim more
                        game time than really elapsed since the token was issued
                        (one-directional: pausing makes elapsed larger, which is fine).
                        For every other metric, the floor lives in spec.check, which
                        can scale it with the run's claimed progress.
      3. per-game     — spec.check, the rules only that game knows.

    None of this defeats a determined attacker; making it airtight would mean replaying
    the simulation server-side. It defeats the console-opening opportunist, which is the
    actual threat model for a crew of friends. An admin can delete an outlier by hand.
    """
    if not isinstance(score, int) or isinstance(score, bool):
        return "score must be an integer"
    if score < 0:
        return "score must not be negative"
    if score > spec.max_score:
        return f"score {score} exceeds the maximum possible for {spec.slug} ({spec.max_score})"

    # Only meaningful when the score IS a duration. Applying it to a points-based game
    # would reject every legitimate run — thousands of points accrue in minutes.
    # 10s of slack covers clock skew and the round-trip on both ends.
    if spec.score_is_elapsed_seconds and score > elapsed_seconds + 10:
        return f"score {score} exceeds the {int(elapsed_seconds)}s actually elapsed since the run started"

    if spec.check is not None:
        return spec.check(score, details, elapsed_seconds)

    return None
