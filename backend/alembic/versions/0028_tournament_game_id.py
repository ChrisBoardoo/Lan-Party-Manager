"""tournaments — link to the shared game catalog

Adds tournaments.game_id, pointing at games.id, so per-game stats (wins,
losses, matches played per player per game) can group tournaments by an actual
catalog entry instead of free text — "LoL", "League of Legends" and
"league of legends " were three different games before this.

`game_name` stays: it's the display snapshot the kiosk, recap, bracket and
activity feed already read, now copied from the canonical `Game.name` on
create/update (see router_tournaments.py).

Backfill: an existing tournament whose `game_name` matches a catalog name
(case-insensitively, trimmed) gets that game's id. Anything else stays NULL
and shows up as "unlinked" for an admin to attach from the Arena stats tab —
the migration deliberately doesn't create catalog rows out of free text it
can't vouch for.

Same guarded ADD COLUMN style as 0024–0027 (safe to re-run after a partial
failure). No sa.ForeignKey() and no server_default on the column — see 0027's
docstring for the former and test_migrations.py for the latter (the arm64
SQLite incident).

Revision ID: 0028_tournament_game_id
Revises: 0027_chat_pinned_message
Create Date: 2026-09-19
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0028_tournament_game_id"
down_revision = "0027_chat_pinned_message"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("tournaments")}
    if "game_id" not in cols:
        op.add_column("tournaments", sa.Column("game_id", sa.Integer(), nullable=True))
    indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("tournaments")}
    if "ix_tournaments_game_id" not in indexes:
        op.create_index("ix_tournaments_game_id", "tournaments", ["game_id"])

    op.execute(
        """
        UPDATE tournaments
        SET game_id = (
            SELECT g.id FROM games g
            WHERE lower(g.name) = lower(trim(tournaments.game_name))
            ORDER BY g.id
            LIMIT 1
        )
        WHERE game_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_tournaments_game_id", table_name="tournaments")
    op.drop_column("tournaments", "game_id")
