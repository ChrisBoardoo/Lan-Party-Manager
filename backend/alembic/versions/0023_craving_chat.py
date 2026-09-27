"""craving chat — per-event pre-LAN hype chat

Adds the table backing the Craving Chat: a single group chat room per event,
open to attendees only (RSVP status "in"), visible from 30 days before the
event's start through 15 days after its end (see router_chat.py's
_window_open). Moderation v1 is self-service only — a user can delete their
own messages, no admin-delete yet — so no extra column is needed for that.

Additive only — a fresh table (create_table), so no SQLite batch-mode needed.
Safe on a live database. Mirrors 0021_groceries.py.

Revision ID: 0023_craving_chat
Revises: 0022_calendar_view
Create Date: 2026-09-14
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0023_craving_chat"
down_revision = "0022_calendar_view"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "chat_messages"):
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("chat_messages")
