"""steam link — user.steam_id / steam_username / steam_avatar

Adds the columns needed to link a Steam account (link-only — see
md/Steam_Link.md, no sign-up/login via Steam):
  * users.steam_id       — SteamID64 (unique; nullable)
  * users.steam_username — Steam persona name (for the profile UI)
  * users.steam_avatar   — Steam avatar URL (already a full URL, unlike
                            Discord's hash — display only)

Mirrors 0003_discord_sso.py exactly: add_column + a unique index (not a UNIQUE
constraint, so SQLite doesn't need a table rebuild), no backfill.

Revision ID: 0020_steam_link
Revises: 0019_games
Create Date: 2026-09-09
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0020_steam_link"
down_revision = "0019_games"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "users", "steam_id"):
        op.add_column("users", sa.Column("steam_id", sa.String(), nullable=True))
        op.create_index("ix_users_steam_id", "users", ["steam_id"], unique=True)
    if not _has_column(bind, "users", "steam_username"):
        op.add_column("users", sa.Column("steam_username", sa.String(), nullable=True))
    if not _has_column(bind, "users", "steam_avatar"):
        op.add_column("users", sa.Column("steam_avatar", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_index("ix_users_steam_id", table_name="users")
    op.drop_column("users", "steam_avatar")
    op.drop_column("users", "steam_username")
    op.drop_column("users", "steam_id")
