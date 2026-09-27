"""lol matches outside a LAN — lol_matches.event_id becomes nullable

League of Legends games are now captured whenever a member plays, not only
during a LAN: a game played outside any LAN the sender attends is kept with
event_id NULL and counts in the global stats only (see router_lol.py).

SQLite can't change a column's nullability in place, so this goes through
Alembic's batch mode, which copies the table into a new one and swaps them
(indexes and foreign keys are carried over by reflection). No ADD COLUMN, so
0024's non-constant-default trap on older SQLite doesn't apply. Guarded, so a
re-run on an already-nullable column is a no-op.

Downgrade drops the games kept outside any LAN first: the old schema has
nowhere to put them.

Revision ID: 0032_lol_event_nullable
Revises: 0031_lol_matches
Create Date: 2026-09-24
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0032_lol_event_nullable"
down_revision = "0031_lol_matches"
branch_labels = None
depends_on = None


def _event_id_nullable(bind):
    """None when the table doesn't exist (nothing to do)."""
    insp = sa.inspect(bind)
    if "lol_matches" not in insp.get_table_names():
        return None
    return {c["name"]: c for c in insp.get_columns("lol_matches")}["event_id"]["nullable"]


def upgrade() -> None:
    if _event_id_nullable(op.get_bind()) is not False:
        return
    with op.batch_alter_table("lol_matches") as batch:
        batch.alter_column("event_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    if _event_id_nullable(bind) is not True:
        return
    bind.execute(sa.text(
        "DELETE FROM lol_match_players WHERE match_id IN (SELECT id FROM lol_matches WHERE event_id IS NULL)"
    ))
    bind.execute(sa.text("DELETE FROM lol_matches WHERE event_id IS NULL"))
    with op.batch_alter_table("lol_matches") as batch:
        batch.alter_column("event_id", existing_type=sa.Integer(), nullable=False)
