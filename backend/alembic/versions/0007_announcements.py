"""announcements — admin PA messages

Adds the table backing the Announcements / PA banner (1.7): an admin posts a
message that shows as a dismissible in-app banner (and optionally fans out to
Discord).

Additive only — safe on a live database.

Revision ID: 0007_announcements
Revises: 0006_presence
Create Date: 2026-07-13
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_announcements"
down_revision = "0006_presence"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "announcements"):
        op.create_table(
            "announcements",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("level", sa.String(), nullable=False, server_default="info"),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("announcements")
