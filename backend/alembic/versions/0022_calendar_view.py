"""calendar view — schedule_blocks.color / users.planning_schedule_view

Adds the two columns needed by the Planning > Schedule calendar view
(md/2.features/calendarview.md):
  * schedule_blocks.color         — palette key chosen at lock time; NULL falls
                                     back to a deterministic hash of `game`
  * users.planning_schedule_view  — "list" | "calendar", per-account display
                                     preference; NULL = no preference saved yet

Mirrors 0020_steam_link.py: plain add_column, no backfill, no index needed
(neither column is looked up by value).

Revision ID: 0022_calendar_view
Revises: 0021_groceries
Create Date: 2026-09-10
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0022_calendar_view"
down_revision = "0021_groceries"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "schedule_blocks", "color"):
        op.add_column("schedule_blocks", sa.Column("color", sa.String(), nullable=True))
    if not _has_column(bind, "users", "planning_schedule_view"):
        op.add_column("users", sa.Column("planning_schedule_view", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "planning_schedule_view")
    op.drop_column("schedule_blocks", "color")
