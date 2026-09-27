"""games — shared game catalog + per-member library/wishlist

Adds a `games` catalog table (seeded from `backend/games_catalog_seed.json`, ~100
LAN-friendly titles extracted from the crew's own game-list notes), plus
`user_game_library` ("games I own/can host, with a max player count") and
`user_game_wishlist` ("games I'd like to play"). Powers the profile "Games" section
and the games-finder page ("who shares my games", "what can this group of N play").

The catalog is shared on purpose, not per-user free text like GearItem: a member
adding a custom game not in the seed still lands in the same table (looked up by
name, case-insensitive, in the router before insert), so cross-member matching works
on custom games too.

Purely additive — three fresh `create_table` calls guarded by has_table, no ALTER,
no backfill. Safe on a live database. Gated by the `games` feature flag (default
OFF) — see router_settings.ALLOWED_KEYS.

Revision ID: 0019_games
Revises: 0018_minigames
Create Date: 2026-09-08
"""
import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0019_games"
down_revision = "0018_minigames"
branch_labels = None
depends_on = None

SEED_FILE = Path(__file__).resolve().parents[2] / "games_catalog_seed.json"


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "games"):
        op.create_table(
            "games",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("name", sa.String(), nullable=False, index=True),
            sa.Column("genre", sa.String(), nullable=True),
            sa.Column("default_max_players", sa.Integer(), nullable=True),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("is_custom", sa.Boolean(), server_default=sa.false()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if not _has_table(bind, "user_game_library"):
        op.create_table(
            "user_game_library",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False, index=True),
            sa.Column("max_players_override", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "game_id", name="uq_game_library_user_game"),
        )

    if not _has_table(bind, "user_game_wishlist"):
        op.create_table(
            "user_game_wishlist",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "game_id", name="uq_game_wishlist_user_game"),
        )

    _seed_catalog(bind)


def _seed_catalog(bind) -> None:
    """Idempotent: skip any name that already exists (case-insensitive), so re-running
    this migration (or upgrading a DB that already has custom entries with the same
    name as a later seed addition) never creates duplicates."""
    if not SEED_FILE.exists():
        return
    games = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    if not games:
        return

    meta = sa.MetaData()
    games_table = sa.Table("games", meta, autoload_with=bind)

    existing = {
        (row[0] or "").strip().lower()
        for row in bind.execute(sa.select(games_table.c.name)).fetchall()
    }

    rows = []
    for g in games:
        name = (g.get("name") or "").strip()
        if not name or name.lower() in existing:
            continue
        existing.add(name.lower())
        rows.append({
            "name": name,
            "genre": g.get("genre"),
            "default_max_players": g.get("default_max_players"),
            "notes": g.get("notes"),
            "is_custom": False,
            "created_by": None,
        })

    if rows:
        bind.execute(games_table.insert(), rows)


def downgrade() -> None:
    op.drop_table("user_game_wishlist")
    op.drop_table("user_game_library")
    op.drop_table("games")
