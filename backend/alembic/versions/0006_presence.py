"""presence — users.last_seen

Adds the column backing the HUB "online now" indicator (1.7): a browser
heartbeat updates users.last_seen; "online" = seen within a short window.

Additive only — safe on a live database.

Revision ID: 0006_presence
Revises: 0005_match_reporting
Create Date: 2026-07-13
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_presence"
down_revision = "0005_match_reporting"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "users", "last_seen"):
        op.add_column("users", sa.Column("last_seen", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_seen")
