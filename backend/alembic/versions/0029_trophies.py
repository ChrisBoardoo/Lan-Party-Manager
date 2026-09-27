"""trophies — crew-defined honours awarded per event

Four new tables (see models.py's "Trophies" section for the full rationale):

- trophies               the definitions ("trophy cabinet"), reusable across events
- event_trophies         a trophy put in play at one event (mode vote|direct,
                         status draft|voting|closed|revealed)
- event_trophy_winners   the winner(s) of an edition, with an optional citation
- trophy_votes           one secret ballot per attendee per edition

CREATE TABLE only — the ADD COLUMN non-constant-default restriction that broke
0024 on the arm64 SQLite (see test_migrations.py) doesn't apply to a new table,
so `server_default=sa.func.now()` is fine here, as in every earlier
create_table revision. Each table is guarded so a re-run after a partial
failure is safe.

Revision ID: 0029_trophies
Revises: 0028_tournament_game_id
Create Date: 2026-09-19
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0029_trophies"
down_revision = "0028_tournament_game_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "trophies" not in existing:
        op.create_table(
            "trophies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("emoji", sa.String(), nullable=True),
            sa.Column("image_url", sa.String(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=True),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("ix_trophies_id", "trophies", ["id"])

    if "event_trophies" not in existing:
        op.create_table(
            "event_trophies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False),
            sa.Column("trophy_id", sa.Integer(), sa.ForeignKey("trophies.id"), nullable=False),
            sa.Column("mode", sa.String(), nullable=False, server_default="vote"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("revealed_at", sa.DateTime(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("event_id", "trophy_id", name="uq_event_trophy"),
        )
        op.create_index("ix_event_trophies_id", "event_trophies", ["id"])
        op.create_index("ix_event_trophies_event_id", "event_trophies", ["event_id"])
        op.create_index("ix_event_trophies_trophy_id", "event_trophies", ["trophy_id"])

    if "event_trophy_winners" not in existing:
        op.create_table(
            "event_trophy_winners",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_trophy_id", sa.Integer(), sa.ForeignKey("event_trophies.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("citation", sa.String(), nullable=True),
            sa.Column("vote_count", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("event_trophy_id", "user_id", name="uq_event_trophy_winner"),
        )
        op.create_index("ix_event_trophy_winners_id", "event_trophy_winners", ["id"])
        op.create_index("ix_event_trophy_winners_event_trophy_id", "event_trophy_winners", ["event_trophy_id"])
        op.create_index("ix_event_trophy_winners_user_id", "event_trophy_winners", ["user_id"])

    if "trophy_votes" not in existing:
        op.create_table(
            "trophy_votes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_trophy_id", sa.Integer(), sa.ForeignKey("event_trophies.id"), nullable=False),
            sa.Column("voter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("nominee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("event_trophy_id", "voter_id", name="uq_trophy_vote"),
        )
        op.create_index("ix_trophy_votes_id", "trophy_votes", ["id"])
        op.create_index("ix_trophy_votes_event_trophy_id", "trophy_votes", ["event_trophy_id"])


def downgrade() -> None:
    op.drop_table("trophy_votes")
    op.drop_table("event_trophy_winners")
    op.drop_table("event_trophies")
    op.drop_table("trophies")
