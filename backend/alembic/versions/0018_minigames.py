"""minigames — embedded mini-games with a per-player leaderboard

Adds `minigame_runs` (server-issued run tokens, so a submitted score can be tied to a
known start time and consumed once) and `minigame_scores` (accepted runs).

`minigame_scores` is deliberately game-agnostic: one generic ranked `score` integer plus
a JSON `details` blob, rather than NeonSurvivor's own kills/wave/level as columns. Up to
8 games are planned and they don't share a metric — seconds survived, waves cleared, a
speedrun where lower wins — so what `score` counts is defined per game in
`minigames_registry.py`. That's what lets game number 9 ship without another migration.

Purely additive — two fresh `create_table` calls guarded by has_table, no ALTER, no
backfill (nobody had a score before this migration). Safe on a live database.

Revision ID: 0018_minigames
Revises: 0017_activity_reactions
Create Date: 2026-08-16
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0018_minigames"
down_revision = "0017_activity_reactions"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "minigame_runs"):
        op.create_table(
            "minigame_runs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("token", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("game", sa.String(), nullable=False),
            sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()),
            # NULL until the run is submitted; set on submit to make the token single-use.
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
        )

    if not _has_table(bind, "minigame_scores"):
        op.create_table(
            "minigame_scores",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("game", sa.String(), nullable=False, index=True),
            sa.Column("mode", sa.String(), nullable=False, server_default="solo"),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("ix_minigame_scores_game_score", "minigame_scores", ["game", "score"])


def downgrade() -> None:
    op.drop_index("ix_minigame_scores_game_score", table_name="minigame_scores")
    op.drop_table("minigame_scores")
    op.drop_table("minigame_runs")
