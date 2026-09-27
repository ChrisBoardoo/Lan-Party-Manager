"""setup — "My Setup", a member's gaming PC and its public share link

Adds the three tables behind My Setup (1.0.0-rc3): `user_setups` (1:1 with a
user, the 14 fixed component columns plus that member's own share token),
`user_setup_fields` (whatever they invent beyond the fixed 14), and
`user_setup_photos` (capped at 5 in the router, not the schema).

Purely additive — three fresh `create_table` calls, no ALTER, no SQLite batch
mode, and deliberately **no backfill**. Unlike 0009, there is no historical data
to reinterpret: nobody had a setup before this migration. Safe on a live
database and boring on purpose.

Revision ID: 0010_setup
Revises: 0009_memories
Create Date: 2026-07-17
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_setup"
down_revision = "0009_memories"
branch_labels = None
depends_on = None

# The fixed component vocabulary. Their names are the i18n keys the frontend
# renders (`setup.field.<name>`), which is why they're columns rather than rows.
# `pc_case` is not a typo: `case` is a SQL reserved word.
_COMPONENT_COLUMNS = (
    "motherboard", "cpu", "cooler", "graphics_card", "ram", "power_supply",
    "fans", "storage", "pc_case", "display", "keyboard", "mouse", "headset", "mic",
)


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "user_setups"):
        op.create_table(
            "user_setups",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True, index=True),
            *(sa.Column(name, sa.String(), nullable=True) for name in _COMPONENT_COLUMNS),
            sa.Column("share_token", sa.String(), nullable=True, unique=True, index=True),
            sa.Column("share_created_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if not _has_table(bind, "user_setup_fields"):
        op.create_table(
            "user_setup_fields",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("setup_id", sa.Integer(), sa.ForeignKey("user_setups.id"), nullable=False, index=True),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("value", sa.String(), nullable=True),
            sa.Column("sort_order", sa.Integer(), server_default="0"),
        )

    if not _has_table(bind, "user_setup_photos"):
        op.create_table(
            "user_setup_photos",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("setup_id", sa.Integer(), sa.ForeignKey("user_setups.id"), nullable=False, index=True),
            sa.Column("url", sa.String(), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("user_setup_photos")
    op.drop_table("user_setup_fields")
    op.drop_table("user_setups")
