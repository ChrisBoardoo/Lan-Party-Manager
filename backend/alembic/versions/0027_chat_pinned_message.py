"""chat — pinned message

Adds lan_events.pinned_message_id: at most one pinned chat message per event
(a carpool meeting point, a voice-chat link, …), pointing at chat_messages.id.
NULL = nothing pinned (every existing event, and the default state of a new
one). Modeled as a single pointer on LanEvent rather than a flag column on
ChatMessage, per md/2.features/craving_chat_suggestions.md's own suggestion — "at most
one" falls out naturally from a single FK instead of needing a uniqueness
constraint enforced elsewhere.

Same guarded ADD COLUMN style as 0024/0025/0026 — safe to re-run after a
partial failure. No sa.ForeignKey() on the column itself, same reasoning as
every other cross-table integer column added post-creation in this history
(SQLite can't ALTER TABLE ADD a constraint outside batch mode; the FK exists
at the ORM level only — see models.py's LanEvent.pinned_message_id).

Revision ID: 0027_chat_pinned_message
Revises: 0026_chat_mentions
Create Date: 2026-09-16
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0027_chat_pinned_message"
down_revision = "0026_chat_mentions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("lan_events")}
    if "pinned_message_id" not in cols:
        op.add_column("lan_events", sa.Column("pinned_message_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("lan_events", "pinned_message_id")
