"""checklist — private per-event packing checklist

Adds `event_checklists` (one row per event+user, the 9 fixed item columns —
Computer, Screen, Screen PSU, Keyboard & Mouse, Cables, MousePad, Headset,
Vanity, Backpack) and `event_checklist_fields` (up to 10 member-invented extras
per checklist, capped in the router). Same split as 0010's user_setups /
user_setup_fields, applied per-event instead of once per user. Unlike Gear,
this is private: no endpoint ever reads another user's row.

Purely additive — two fresh `create_table` calls guarded by has_table, no
ALTER, no backfill (nobody had a checklist before this migration). Safe on a
live database.

Revision ID: 0014_checklist
Revises: 0013_setup_reactions
Create Date: 2026-08-01
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0014_checklist"
down_revision = "0013_setup_reactions"
branch_labels = None
depends_on = None

# The fixed item vocabulary. Their names are the i18n keys the frontend
# renders (`checklist.field.<name>`), which is why they're columns rather than rows.
_FIXED_ITEM_COLUMNS = (
    "computer", "screen", "screen_psu", "keyboard_mouse", "cables",
    "mousepad", "headset", "vanity", "backpack",
)


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "event_checklists"):
        op.create_table(
            "event_checklists",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            *(sa.Column(name, sa.Boolean(), server_default=sa.false()) for name in _FIXED_ITEM_COLUMNS),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("event_id", "user_id", name="uq_checklist_event_user"),
        )

    if not _has_table(bind, "event_checklist_fields"):
        op.create_table(
            "event_checklist_fields",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("checklist_id", sa.Integer(), sa.ForeignKey("event_checklists.id"), nullable=False, index=True),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("checked", sa.Boolean(), server_default=sa.false()),
            sa.Column("sort_order", sa.Integer(), server_default="0"),
        )


def downgrade() -> None:
    op.drop_table("event_checklist_fields")
    op.drop_table("event_checklists")
