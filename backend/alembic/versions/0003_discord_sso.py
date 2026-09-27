"""discord sso — user.discord_id / discord_username / discord_avatar

Adds the columns needed to sign in with / link a Discord account:
  * users.discord_id        — Discord user snowflake (unique; nullable)
  * users.discord_username  — Discord display name (for the profile UI)
  * users.discord_avatar    — Discord avatar hash/URL (optional display)

Revision ID: 0003_discord_sso
Revises: 0002_wero_settlement
Create Date: 2026-07-11
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_discord_sso"
down_revision = "0002_wero_settlement"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "users", "discord_id"):
        op.add_column("users", sa.Column("discord_id", sa.String(), nullable=True))
        # Unique index (not a UNIQUE constraint) so SQLite can add it without a
        # table rebuild; NULLs are allowed to coexist, matching the ORM model.
        op.create_index("ix_users_discord_id", "users", ["discord_id"], unique=True)
    if not _has_column(bind, "users", "discord_username"):
        op.add_column("users", sa.Column("discord_username", sa.String(), nullable=True))
    if not _has_column(bind, "users", "discord_avatar"):
        op.add_column("users", sa.Column("discord_avatar", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_index("ix_users_discord_id", table_name="users")
    op.drop_column("users", "discord_avatar")
    op.drop_column("users", "discord_username")
    op.drop_column("users", "discord_id")
