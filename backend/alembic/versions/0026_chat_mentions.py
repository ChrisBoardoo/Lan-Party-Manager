"""chat @mentions + targeted activity notifications

Two additive, independent changes:
  * activity_logs.recipient_user_id — nullable. NULL (existing rows, and
    every existing add_activity() call site) keeps today's behavior: visible
    to everyone via GET /api/activity/. A non-null value scopes that row to
    exactly one recipient (router_activity.py's list_activity/activity_ws
    now filter on `recipient_user_id IS NULL OR recipient_user_id == me`).
    This is what lets the desktop app's existing poll/toast/click pipeline
    (see main.rs's poll_activity/show_activity_notification) be reused for
    "you were mentioned" without notifying every other attendee too.
  * chat_message_mentions — one row per (message, mentioned user), same
    shape as chat_message_reactions (0024_craving_chat_v2.py) minus the
    emoji column. Populated in router_chat.py by matching @username tokens
    against the event's own attendee list (never a free-form regex token),
    so only someone actually proposed by the autocomplete can be recorded.

Same guarded-migration style as 0024/0025: ADD COLUMN checked against the
live schema, CREATE TABLE checked via inspector.has_table — safe to re-run
after a partial failure. No sa.ForeignKey() on the ALTER-added column, same
reasoning as every other cross-table integer column added post-creation in
this history (SQLite can't ALTER TABLE ADD a constraint outside batch mode;
the FK exists at the ORM level only).

Revision ID: 0026_chat_mentions
Revises: 0025_chat_link_preview
Create Date: 2026-09-15
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0026_chat_mentions"
down_revision = "0025_chat_link_preview"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    activity_cols = {c["name"] for c in inspector.get_columns("activity_logs")}
    if "recipient_user_id" not in activity_cols:
        op.add_column("activity_logs", sa.Column("recipient_user_id", sa.Integer(), nullable=True))

    if not inspector.has_table("chat_message_mentions"):
        op.create_table(
            "chat_message_mentions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("chat_messages.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("message_id", "user_id", name="uq_chat_mention_message_user"),
        )


def downgrade() -> None:
    op.drop_table("chat_message_mentions")
    op.drop_column("activity_logs", "recipient_user_id")
