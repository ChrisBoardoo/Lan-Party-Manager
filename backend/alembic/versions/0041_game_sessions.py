"""game_sessions — game time detected by the desktop app

One row per stretch of a member playing one game, built from the heartbeats
their desktop app sends while the game runs (router_gametime.py). `event_id` is
the LAN it was played during, NULL outside any LAN; `game_id` the catalog row of
the same name when there is one.

New table, nothing to backfill. CREATE TABLE guarded, so a re-run after a
partial failure is safe. The downgrade drops the table.

Revision ID: 0041_game_sessions
Revises: 0040_transfers
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0041_game_sessions"
down_revision = "0040_transfers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "game_sessions" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "game_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=True),
        sa.Column("game_key", sa.String(), nullable=False),
        sa.Column("game_name", sa.String(), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_game_sessions_id", "game_sessions", ["id"])
    op.create_index("ix_game_sessions_user_id", "game_sessions", ["user_id"])
    op.create_index("ix_game_sessions_event_id", "game_sessions", ["event_id"])
    op.create_index("ix_game_sessions_last_seen_at", "game_sessions", ["last_seen_at"])


def downgrade() -> None:
    op.drop_table("game_sessions")
