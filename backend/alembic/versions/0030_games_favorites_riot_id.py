"""games favorites + saved library filters + riot id

Adds:
  * user_game_library.is_favorite  — a member's "we play this at LANs" star
                                     (NOT NULL, constant default 0, so every
                                     existing row reads as not-favorite)
  * users.games_library_filters    — the profile library's filter bar, as JSON
  * users.riot_id / riot_id_key    — Riot ID as typed, and its case-folded
                                     matching form (unique index, not a UNIQUE
                                     constraint, same as 0003/0020: no SQLite
                                     table rebuild, and NULLs don't collide)

ADD COLUMN only, every default a literal — the non-constant-default trap that
broke 0024 on the Pi's older SQLite (see test_migrations.py) doesn't apply.
Each column is guarded, so a re-run after a partial failure is safe.

Revision ID: 0030_games_favorites_riot_id
Revises: 0029_trophies
Create Date: 2026-09-23
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0030_games_favorites_riot_id"
down_revision = "0029_trophies"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "user_game_library", "is_favorite"):
        op.add_column(
            "user_game_library",
            sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    if not _has_column(bind, "users", "games_library_filters"):
        op.add_column("users", sa.Column("games_library_filters", sa.Text(), nullable=True))
    if not _has_column(bind, "users", "riot_id"):
        op.add_column("users", sa.Column("riot_id", sa.String(), nullable=True))
    if not _has_column(bind, "users", "riot_id_key"):
        op.add_column("users", sa.Column("riot_id_key", sa.String(), nullable=True))
        op.create_index("ix_users_riot_id_key", "users", ["riot_id_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_riot_id_key", table_name="users")
    op.drop_column("users", "riot_id_key")
    op.drop_column("users", "riot_id")
    op.drop_column("users", "games_library_filters")
    op.drop_column("user_game_library", "is_favorite")
