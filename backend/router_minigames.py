"""Mini-games: run tokens, score submission, and the per-player leaderboard.

Shape of a scored run:

    POST /runs                  -> {token}        (server records started_at)
    ... the member plays ...
    POST /runs/{token}/submit   -> {accepted, personal_best, rank}

The two-step exists so a score can be checked against real elapsed time and the token
consumed exactly once. See `minigames_registry.validate_submission` for what is and
isn't caught, and why that's the right level of effort here.

Nothing in this module knows about any specific game — every game-specific fact lives
in `minigames_registry.GAMES`, so a new game is one entry there plus a folder under
`frontend/public/games/`.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from activity import add_activity
from auth import get_current_user, require_admin
from database import get_db
from models import MiniGameRun, MiniGameScore, User
from minigames_registry import (
    GAMES,
    clean_details,
    format_score,
    get_spec,
    validate_submission,
)
from router_settings import require_feature
from schemas import (
    MiniGameInfo,
    MiniGameRunStart,
    MiniGameRunToken,
    MiniGameScoreOut,
    MiniGameSubmit,
    MiniGameSubmitResult,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# A run token stays usable this long. Generous on purpose: NeonSurvivor can be paused
# indefinitely, so a short TTL would throw away legitimate runs. It isn't what stops a
# forged score — the max_score ceiling and the elapsed-time check are. This only keeps
# abandoned rows from accumulating forever.
RUN_TOKEN_TTL = timedelta(hours=12)

# Rows returned by the leaderboard when the caller doesn't ask for a specific size.
DEFAULT_LEADERBOARD_LIMIT = 20


def _spec_or_404(game: str):
    spec = get_spec(game)
    if spec is None:
        raise HTTPException(404, f"Unknown mini-game: {game}")
    return spec


def _load_details(row: MiniGameScore) -> dict:
    if not row.details:
        return {}
    try:
        parsed = json.loads(row.details)
    except ValueError:
        # A row written by a future/older version shouldn't break the whole board.
        logger.warning("minigame_scores.id=%s has unparseable details", row.id)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _serialize(row: MiniGameScore) -> MiniGameScoreOut:
    return MiniGameScoreOut(
        id=row.id,
        game=row.game,
        score=row.score,
        details=_load_details(row),
        created_at=row.created_at,
        user=row.user,
    )


def _personal_bests(db: Session, game: str, higher_is_better: bool):
    """Every player's single best run at `game`, best first.

    One row per player — a leaderboard where one person occupies the top five slots
    isn't a leaderboard. Ties break on the earlier run: first to get there keeps the
    higher place.
    """
    order = MiniGameScore.score.desc() if higher_is_better else MiniGameScore.score.asc()

    ranked = (
        db.query(
            MiniGameScore.id.label("id"),
            func.row_number()
            .over(
                partition_by=MiniGameScore.user_id,
                order_by=(order, MiniGameScore.created_at.asc()),
            )
            .label("rn"),
        )
        .filter(MiniGameScore.game == game)
        .subquery()
    )

    return (
        db.query(MiniGameScore)
        .join(ranked, ranked.c.id == MiniGameScore.id)
        .filter(ranked.c.rn == 1)
        .order_by(order, MiniGameScore.created_at.asc())
    )


@router.get("/games", response_model=list[MiniGameInfo])
def list_games(_: User = Depends(require_feature("minigames"))):
    """The registry, so the frontend never keeps a second copy of the catalogue."""
    return [
        MiniGameInfo(
            slug=spec.slug,
            metric=spec.metric,
            max_score=spec.max_score,
            higher_is_better=spec.higher_is_better,
            detail_fields=list(spec.detail_fields),
        )
        for spec in GAMES.values()
    ]


@router.post("/runs", response_model=MiniGameRunToken)
def start_run(
    data: MiniGameRunStart,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("minigames")),
):
    spec = _spec_or_404(data.game)

    run = MiniGameRun(
        token=uuid.uuid4().hex,
        user_id=current_user.id,
        game=spec.slug,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return MiniGameRunToken(token=run.token, game=run.game)


@router.post("/runs/{token}/submit", response_model=MiniGameSubmitResult)
def submit_run(
    token: str,
    data: MiniGameSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("minigames")),
):
    run = db.query(MiniGameRun).filter(MiniGameRun.token == token).first()
    if not run:
        raise HTTPException(404, "Unknown run")
    # Someone else's token is "unknown" as far as the caller is concerned — don't
    # confirm that a token exists to whoever guessed at it.
    if run.user_id != current_user.id:
        raise HTTPException(404, "Unknown run")
    if run.submitted_at is not None:
        raise HTTPException(409, "This run has already been submitted")

    started = run.started_at or datetime.utcnow()
    if datetime.utcnow() - started > RUN_TOKEN_TTL:
        raise HTTPException(410, "This run expired before it was submitted")

    spec = _spec_or_404(run.game)
    details = clean_details(spec, data.details)
    elapsed = (datetime.utcnow() - started).total_seconds()

    error = validate_submission(spec, data.score, details, elapsed)
    if error:
        # Consume the token anyway: a rejected submission must not leave a valid token
        # behind for a second, better-shaped attempt at the same elapsed budget.
        run.submitted_at = datetime.utcnow()
        db.commit()
        logger.info(
            "Rejected %s submission from user %s: %s", run.game, current_user.id, error
        )
        raise HTTPException(400, error)

    previous_best = (
        db.query(func.max(MiniGameScore.score) if spec.higher_is_better else func.min(MiniGameScore.score))
        .filter(
            MiniGameScore.game == run.game,
            MiniGameScore.user_id == current_user.id,
        )
        .scalar()
    )

    score = MiniGameScore(
        user_id=current_user.id,
        game=run.game,
        mode="solo",
        score=data.score,
        details=json.dumps(details) if details else None,
    )
    db.add(score)
    run.submitted_at = datetime.utcnow()
    db.commit()
    db.refresh(score)

    is_best = previous_best is None or (
        data.score > previous_best if spec.higher_is_better else data.score < previous_best
    )

    rank = None
    if is_best:
        board = _personal_bests(db, run.game, spec.higher_is_better).all()
        for position, row in enumerate(board, start=1):
            if row.user_id == current_user.id:
                rank = position
                break

        # Only personal bests reach the Hub feed. Every run would drown it — someone
        # playing for twenty minutes would push everything else off the page.
        add_activity(
            db,
            current_user.id,
            "minigame_best",
            f"New personal best on {spec.title or spec.slug}: {format_score(spec, data.score)}",
            "minigame_score",
            score.id,
        )
        db.commit()

    return MiniGameSubmitResult(
        accepted=True,
        personal_best=is_best,
        rank=rank,
        score=_serialize(score),
    )


@router.get("/leaderboard", response_model=list[MiniGameScoreOut])
def leaderboard(
    game: str = Query(...),
    limit: int = Query(DEFAULT_LEADERBOARD_LIMIT, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("minigames")),
):
    spec = _spec_or_404(game)
    rows = _personal_bests(db, spec.slug, spec.higher_is_better).limit(limit).all()
    return [_serialize(row) for row in rows]


@router.get("/me/best", response_model=Optional[MiniGameScoreOut])
def my_best(
    game: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("minigames")),
):
    spec = _spec_or_404(game)
    order = MiniGameScore.score.desc() if spec.higher_is_better else MiniGameScore.score.asc()
    row = (
        db.query(MiniGameScore)
        .filter(
            MiniGameScore.game == spec.slug,
            MiniGameScore.user_id == current_user.id,
        )
        .order_by(order, MiniGameScore.created_at.asc())
        .first()
    )
    return _serialize(row) if row else None


@router.delete("/scores/{score_id}")
def delete_score(
    score_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """The honest backstop to the validation above: an admin removes an outlier by hand.

    Nothing here can defeat a determined cheat, so the feature ships with a way to
    undo one rather than pretending otherwise."""
    row = db.query(MiniGameScore).filter(MiniGameScore.id == score_id).first()
    if not row:
        raise HTTPException(404, "Score not found")
    db.delete(row)
    db.commit()
    return {"status": "deleted"}
