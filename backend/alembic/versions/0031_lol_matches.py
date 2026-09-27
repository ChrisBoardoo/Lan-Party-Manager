"""lol matches — League of Legends games captured during a LAN

Two new tables (see models.py's "League of Legends LAN stats" section):

- lol_matches         one captured game, unique on Riot's own game id
- lol_match_players   one player's K/D/A/damage line in it

CREATE TABLE only, so `server_default=sa.func.now()` is fine (the
non-constant-default restriction that broke 0024 only applies to ADD COLUMN).
Each table is guarded, so a re-run after a partial failure is safe.

Revision ID: 0031_lol_matches
Revises: 0030_games_favorites_riot_id
Create Date: 2026-09-23
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0031_lol_matches"
down_revision = "0030_games_favorites_riot_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "lol_matches" not in existing:
        op.create_table(
            "lol_matches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False),
            sa.Column("riot_game_id", sa.String(), nullable=False),
            sa.Column("game_mode", sa.String(), nullable=True),
            sa.Column("queue_type", sa.String(), nullable=True),
            sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("duration_s", sa.Integer(), nullable=True),
            sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("ix_lol_matches_id", "lol_matches", ["id"])
        op.create_index("ix_lol_matches_event_id", "lol_matches", ["event_id"])
        op.create_index("ix_lol_matches_riot_game_id", "lol_matches", ["riot_game_id"], unique=True)

    if "lol_match_players" not in existing:
        op.create_table(
            "lol_match_players",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("match_id", sa.Integer(), sa.ForeignKey("lol_matches.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("riot_id", sa.String(), nullable=False),
            sa.Column("riot_id_key", sa.String(), nullable=False),
            sa.Column("champion", sa.String(), nullable=True),
            sa.Column("team_id", sa.Integer(), nullable=True),
            sa.Column("win", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("kills", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("deaths", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("assists", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("damage", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.UniqueConstraint("match_id", "riot_id_key", name="uq_lol_match_player"),
        )
        op.create_index("ix_lol_match_players_id", "lol_match_players", ["id"])
        op.create_index("ix_lol_match_players_match_id", "lol_match_players", ["match_id"])
        op.create_index("ix_lol_match_players_user_id", "lol_match_players", ["user_id"])
        op.create_index("ix_lol_match_players_riot_id_key", "lol_match_players", ["riot_id_key"])


def downgrade() -> None:
    op.drop_table("lol_match_players")
    op.drop_table("lol_matches")
