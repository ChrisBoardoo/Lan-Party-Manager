"""self-service score reporting — matches.reported_* columns

Adds the columns for phone/self-service score reporting (1.7): a participant
submits a proposed score that an organizer confirms.
  * matches.reported_score_a / reported_score_b — the proposed score
  * matches.reported_by                         — who submitted it (users.id)
  * matches.reported_at                         — when (NULL = no pending report)

Additive only — safe on a live database.

Revision ID: 0005_match_reporting
Revises: 0004_planning
Create Date: 2026-07-13
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_match_reporting"
down_revision = "0004_planning"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "matches", "reported_score_a"):
        op.add_column("matches", sa.Column("reported_score_a", sa.Integer(), nullable=True))
    if not _has_column(bind, "matches", "reported_score_b"):
        op.add_column("matches", sa.Column("reported_score_b", sa.Integer(), nullable=True))
    if not _has_column(bind, "matches", "reported_by"):
        # No inline ForeignKey: SQLite's ALTER TABLE can't ADD a constraint, so
        # `op.add_column` with a `sa.ForeignKey` raises NotImplementedError when
        # this runs on an existing table (the pre-Alembic adoption path). The FK
        # is unenforced on SQLite anyway; the model still declares it for other
        # dialects and documentation. Plain nullable Integer is the safe add.
        op.add_column("matches", sa.Column("reported_by", sa.Integer(), nullable=True))
    if not _has_column(bind, "matches", "reported_at"):
        op.add_column("matches", sa.Column("reported_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "reported_at")
    op.drop_column("matches", "reported_by")
    op.drop_column("matches", "reported_score_b")
    op.drop_column("matches", "reported_score_a")
