"""matches.played_at — backfill from the activity log

`matches.played_at` existed but was never written: no match the app finalized
has a decision time. From 1.4.0 `_finalize_match` records it, and XP only counts
matches decided at a LAN (xp.decided_at_a_lan). This fills it in for the matches
decided before, from the "match_completed" activity row `_finalize_match` has
always written (entity_type "match", entity_id = the match id), earliest one if
the match was saved several times. Both are naive UTC (`server_default=now()`).

Data only. A completed match without such a row keeps NULL — xp.py then gives it
the benefit of the doubt when its tournament belongs to a LAN. Guarded by
`played_at IS NULL`, so a re-run changes nothing. The downgrade leaves the
values: nothing tells the backfilled ones from the recorded ones, and the column
itself predates this revision.

Revision ID: 0036_match_played_at
Revises: 0035_cards
Create Date: 2026-10-18
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0036_match_played_at"
down_revision = "0035_cards"
branch_labels = None
depends_on = None


def _has_tables(bind, *tables: str) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return all(t in names for t in tables)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind, "matches", "activity_logs"):
        return
    bind.execute(sa.text(
        """
        UPDATE matches
        SET played_at = (
            SELECT MIN(a.created_at) FROM activity_logs a
            WHERE a.action = 'match_completed' AND a.entity_type = 'match' AND a.entity_id = matches.id
        )
        WHERE played_at IS NULL AND status = 'completed'
        """
    ))


def downgrade() -> None:
    pass
