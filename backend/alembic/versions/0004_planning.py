"""planning "Calendar View" — schedule_blocks, block_votes, per-event toggles

Adds the tables + columns for the game × time-slot planning feature (1.7):
  * schedule_blocks              — a proposed/locked game to play at an event
  * block_votes                  — a member's approval of one hour-slot for a block
  * lan_events.planning_can_propose / planning_can_vote — per-event overrides of
    the two toggles (NULL = inherit the global default in app_settings)

Additive only — safe on a live database (guards mirror 0003_discord_sso).

Revision ID: 0004_planning
Revises: 0003_discord_sso
Create Date: 2026-07-13
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_planning"
down_revision = "0003_discord_sso"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "lan_events", "planning_can_propose"):
        op.add_column("lan_events", sa.Column("planning_can_propose", sa.Boolean(), nullable=True))
    if not _has_column(bind, "lan_events", "planning_can_vote"):
        op.add_column("lan_events", sa.Column("planning_can_vote", sa.Boolean(), nullable=True))

    if not _has_table(bind, "schedule_blocks"):
        op.create_table(
            "schedule_blocks",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False, index=True),
            sa.Column("game", sa.String(), nullable=False),
            sa.Column("proposed_start", sa.DateTime(), nullable=True),
            sa.Column("proposed_end", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="proposed"),
            sa.Column("locked_start", sa.DateTime(), nullable=True),
            sa.Column("locked_end", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if not _has_table(bind, "block_votes"):
        op.create_table(
            "block_votes",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("block_id", sa.Integer(), sa.ForeignKey("schedule_blocks.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("slot_start", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("block_id", "user_id", "slot_start", name="uq_block_vote"),
        )


def downgrade() -> None:
    op.drop_table("block_votes")
    op.drop_table("schedule_blocks")
    op.drop_column("lan_events", "planning_can_vote")
    op.drop_column("lan_events", "planning_can_propose")
