"""gear — BYO gear list ("who's bringing what")

Adds the table backing the per-event BYO gear list (1.9): members pledge kit
they're hauling, admins post requests ("we need a 4th monitor") a member can
claim, and a personal "gear locker" powers carryover suggestions.

Additive only — a fresh table (create_table), so no SQLite batch-mode needed.
Safe on a live database.

Revision ID: 0008_gear
Revises: 0007_announcements
Create Date: 2026-07-16
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0008_gear"
down_revision = "0007_announcements"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "gear_items"):
        op.create_table(
            "gear_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False, index=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("quantity", sa.Integer(), server_default="1"),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("pledged_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("is_request", sa.Boolean(), server_default=sa.false()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("gear_items")
