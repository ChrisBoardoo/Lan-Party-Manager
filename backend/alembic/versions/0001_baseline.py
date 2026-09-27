"""baseline — current full schema

This is the adoption baseline for Alembic. It represents the entire schema as
defined by ``models.py`` at the time Alembic was introduced. Because the project
previously used ``create_all`` + idempotent ``ALTER`` statements, an existing
production database already matches this schema — ``db_migrate.run_migrations``
brings any older DB up to it and then *stamps* it at this revision rather than
re-running the create. On a brand-new database this revision creates everything.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-05
"""
from alembic import op

from database import Base
import models  # noqa: F401  (registers all tables on Base.metadata)

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: only creates tables that don't already exist.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
