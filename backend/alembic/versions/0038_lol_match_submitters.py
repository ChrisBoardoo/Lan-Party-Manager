"""lol_match_submitters — which members' apps sent a given game

A captured game is kept once (lol_matches.riot_game_id is unique), so until now
nothing recorded who else sent it: only the first sender, in `submitted_by`.
The monthly contract (quests._lol_squad) now counts a game for a member only
when their own app sent it — a forged block can't fill someone else's objective
(D-3 of the 2026-10-20 review). Backfilled from `submitted_by`: every existing
game counts for its first sender, as before.

CREATE TABLE guarded, backfill idempotent (NOT EXISTS), so a re-run after a
partial failure is safe. The downgrade drops the table; `submitted_by` stays.

Revision ID: 0038_lol_match_submitters
Revises: 0037_monthly_contracts
Create Date: 2026-10-21
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0038_lol_match_submitters"
down_revision = "0037_monthly_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    names = set(sa.inspect(bind).get_table_names())
    if "lol_match_submitters" not in names:
        op.create_table(
            "lol_match_submitters",
            sa.Column("match_id", sa.Integer(), sa.ForeignKey("lol_matches.id"), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
    if "lol_matches" not in names:
        return
    bind.execute(sa.text(
        """
        INSERT INTO lol_match_submitters (match_id, user_id, created_at)
        SELECT m.id, m.submitted_by, m.created_at
        FROM lol_matches m
        WHERE m.submitted_by IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM lol_match_submitters s
            WHERE s.match_id = m.id AND s.user_id = m.submitted_by
          )
        """
    ))


def downgrade() -> None:
    op.drop_table("lol_match_submitters")
