"""groceries — per-event food/drink shopping list ("Courses")

Adds the table backing the per-event groceries list: any attendee can add an
item, assign who's buying it (a dropdown of event attendees), and tick it off
once bought. No price column on purpose — cost splitting stays in Treasury,
entered by hand by the treasurer.

Additive only — a fresh table (create_table), so no SQLite batch-mode needed.
Safe on a live database.

Revision ID: 0021_groceries
Revises: 0020_steam_link
Create Date: 2026-09-09
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0021_groceries"
down_revision = "0020_steam_link"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "grocery_items"):
        op.create_table(
            "grocery_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False, index=True),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("quantity", sa.String(), nullable=True),
            sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("is_bought", sa.Boolean(), server_default=sa.false()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("grocery_items")
