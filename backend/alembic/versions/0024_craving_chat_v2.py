"""craving chat v2 — replies, edits, reactions

Adds what the v1 Craving Chat table didn't have yet, per crew feedback after
the first live test (md/2.features/Craving_chat_v2.md):
  * chat_messages.reply_to_id — self-referential FK, for quoting/replying to
    another message in the same room (blockquote preview in the UI).
  * chat_messages.updated_at  — a poll watermark bumped by BOTH a content
    edit and a reaction change, so the WebSocket loop can detect "this row
    changed" without a new row existing (see router_chat.py's chat_ws, which
    now polls on `updated_at > last_seen_time` instead of "did MAX(id) grow").
  * chat_messages.edited_at   — the display-facing "(edited)" flag, set only
    by an actual content edit within a 10-minute window of posting; reactions
    must never touch this one.
  * chat_message_reactions    — one row per (message, user): at most one
    emoji reaction per person per message (WhatsApp-style), any emoji string
    (sourced from the OS's own picker), not the fixed REACTION_EMOJI set used
    by Media/Activity reactions elsewhere in the app.

Additive only (new columns + a new table) — no SQLite batch mode needed, safe
on a live database. `updated_at` is added with NO server-side default (see
the comment at its add_column call) and is instead populated by the ORM
(models.py's ChatMessage.updated_at uses a client-side `default=`) — existing
rows are backfilled to `created_at`'s value here so they don't all appear
"just changed" to the very first WS poll after this migration.

Each ADD COLUMN is guarded by `if "x" not in cols`, checked against the
*live* schema at the top of upgrade() — this migration can safely be re-run
after a partial failure (e.g. it previously added `reply_to_id` fine, then
blew up on `updated_at`'s bad default below): whatever already landed on
disk is skipped, only what's still missing gets (re)applied.

Revision ID: 0024_craving_chat_v2
Revises: 0023_craving_chat
Create Date: 2026-09-14
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0024_craving_chat_v2"
down_revision = "0023_craving_chat"
branch_labels = None
depends_on = None


def _column_names(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = _column_names(bind, "chat_messages")

    if "reply_to_id" not in cols:
        # No sa.ForeignKey() here on purpose: SQLite can't ALTER TABLE ADD a
        # constraint outside of Alembic's batch mode (raises
        # NotImplementedError), and this app never turns on
        # `PRAGMA foreign_keys` anyway (see database.py) — the FK exists at
        # the ORM level only (models.py's ChatMessage.reply_to_id), same as
        # every other cross-table integer column added via a plain
        # add_column in this migration history.
        op.add_column("chat_messages", sa.Column("reply_to_id", sa.Integer(), nullable=True))
    if "updated_at" not in cols:
        # No server_default here — SQLite's ALTER TABLE ADD COLUMN rejects a
        # non-constant default ("Cannot add a column with non-constant
        # default") for anything CURRENT_TIMESTAMP-like. This raised cleanly
        # in dev (Windows, a newer bundled SQLite) but failed hard in
        # production on a Raspberry Pi 4 (python:3.11-slim's older SQLite) —
        # confirmed live, see md/ notes. CREATE TABLE has never had this
        # restriction (chat_messages.created_at itself uses server_default
        # fine, added via 0023's create_table, not an ALTER), so this is
        # specific to columns added after the fact. The actual value is
        # supplied by the ORM instead (models.py's ChatMessage.updated_at
        # uses a client-side `default=`), so no DB-level default is needed.
        op.add_column("chat_messages", sa.Column("updated_at", sa.DateTime(), nullable=True))
        # Backfill existing rows explicitly — a NULL updated_at would make
        # every pre-existing message look "changed since the beginning of
        # time" to the first WS poll's `updated_at > last_seen_time` check.
        op.execute("UPDATE chat_messages SET updated_at = created_at WHERE updated_at IS NULL")
    if "edited_at" not in cols:
        op.add_column("chat_messages", sa.Column("edited_at", sa.DateTime(), nullable=True))

    if not inspector.has_table("chat_message_reactions"):
        op.create_table(
            "chat_message_reactions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("chat_messages.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("emoji", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("message_id", "user_id", name="uq_chat_reaction_message_user"),
        )


def downgrade() -> None:
    op.drop_table("chat_message_reactions")
    op.drop_column("chat_messages", "edited_at")
    op.drop_column("chat_messages", "updated_at")
    op.drop_column("chat_messages", "reply_to_id")
