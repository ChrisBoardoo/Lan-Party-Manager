"""tournament_event_type — add the column that never had a migration

`tournaments.event_type` ("team" | "individual") has been mapped in models.py
since the very commit that introduced Alembic — but no revision ever created it,
and it isn't in db_migrate.LEGACY_COLUMN_MIGRATIONS either. Three things hid
that for several releases:

  * `0001_baseline` is `Base.metadata.create_all()`, so **fresh** installs get
    the column and look perfectly healthy;
  * the test suite builds its schema from `Base.metadata` too, so it never
    noticed;
  * `create_all()` only adds missing *tables* — it will not add a missing
    *column* to a `tournaments` table that already exists.

Which means a database **adopted** from the pre-Alembic era got the frozen
legacy ALTERs (no event_type), was stamped at the baseline, and has been
considered up-to-date by Alembic ever since — with the column permanently
absent. Every query touching tournaments then raises
`sqlite3.OperationalError: no such column: tournaments.event_type`, taking out
ARENA, the kiosk's match/standings/champion scenes, and the recap's champion and
MVP. Per db_migrate's own docstring, the adoption path exists for "yours, and
every existing Docker Hub deployment" — so this is not a local quirk.

Guarded, so it's a no-op on the fresh installs that already have it. A plain
add_column with no inline ForeignKey: the inline-FK form compiles to an ADD
CONSTRAINT that SQLite rejects outright, which is exactly how 0005 crashed.

Revision ID: 0011_tournament_event_type
Revises: 0010_setup
Create Date: 2026-07-17
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_tournament_event_type"
down_revision = "0010_setup"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("tournaments"):
        return
    if _has_column(bind, "tournaments", "event_type"):
        return

    # server_default rather than a bare default: existing rows need a value, and
    # "team" is what models.py has always defaulted new tournaments to.
    op.add_column(
        "tournaments",
        sa.Column("event_type", sa.String(), nullable=True, server_default="team"),
    )


def downgrade() -> None:
    # Deliberately not dropped. The column is part of the ORM's expected schema
    # on every install; removing it would break the app rather than restore it.
    pass
