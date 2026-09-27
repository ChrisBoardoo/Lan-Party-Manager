"""setup_reactions — let members react to each other's rigs

Adds `setup_reactions`, the MediaReaction shape pointed at `user_setups`: one
row per (setup, member, emoji), row existence = the reaction, unique so the
toggle in the router can never double-count.

Purely additive — one fresh `create_table` guarded by has_table, no ALTER, no
backfill (nobody could react before this migration). The FK lives inline on
create_table, which is fine on SQLite — the 0005 trap is inline FKs on
*add_column* only.

Revision ID: 0013_setup_reactions
Revises: 0012_setup_photo_caption
Create Date: 2026-07-20
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0013_setup_reactions"
down_revision = "0012_setup_photo_caption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("setup_reactions"):
        return
    op.create_table(
        "setup_reactions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("setup_id", sa.Integer(), sa.ForeignKey("user_setups.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("emoji", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("setup_id", "user_id", "emoji"),
    )


def downgrade() -> None:
    op.drop_table("setup_reactions")
