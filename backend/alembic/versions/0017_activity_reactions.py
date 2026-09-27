"""activity_reactions — let members react to Hub activity feed entries

Adds `activity_reactions`, the MediaReaction shape pointed at `activity_logs`:
one row per (activity, member, emoji), row existence = the reaction, unique so
the toggle in the router can never double-count.

Purely additive — one fresh `create_table` guarded by has_table, no ALTER, no
backfill (nobody could react before this migration).

Revision ID: 0017_activity_reactions
Revises: 0016_deleted_username
Create Date: 2026-08-03
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0017_activity_reactions"
down_revision = "0016_deleted_username"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("activity_reactions"):
        return
    op.create_table(
        "activity_reactions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activity_logs.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("emoji", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("activity_id", "user_id", "emoji"),
    )


def downgrade() -> None:
    op.drop_table("activity_reactions")
