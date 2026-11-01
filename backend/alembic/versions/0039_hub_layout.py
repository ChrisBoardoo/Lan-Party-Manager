"""hub layout — users.hub_layout

The Hub's block arrangement (order, column, hidden), as JSON, chosen by each
member in the Hub's "Customize" mode — saved on the account like
games_library_filters, so it follows the member between the browser and the
desktop app. NULL = never customized, the frontend shows the default layout.

Mirrors 0030_games_favorites_riot_id.py: plain add_column, no backfill, no
index (never looked up by value). Column-existence guard, so a re-run after a
partial failure is safe.

Revision ID: 0039_hub_layout
Revises: 0038_lol_match_submitters
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0039_hub_layout"
down_revision = "0038_lol_match_submitters"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "users", "hub_layout"):
        op.add_column("users", sa.Column("hub_layout", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "hub_layout")
