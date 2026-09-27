"""deleted_username — preserve the pre-deletion username for admin history

Adds `users.deleted_username`. `delete_user` (0015) scrubs `username` itself
so it's free for the same person to register again — which means the
original username is otherwise gone the moment a deletion happens, with no
queryable record of who it *was* beyond a free-text line in the audit log
("User: bob"). The admin-facing "deleted / banned accounts" history (Settings)
needs an actual field to list, not a string it has to scrape out of audit
details.

Revision ID: 0016_deleted_username
Revises: 0015_user_deletion
Create Date: 2026-08-03
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0016_deleted_username"
down_revision = "0015_user_deletion"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("users"):
        return
    if _has_column(bind, "users", "deleted_username"):
        return
    op.add_column("users", sa.Column("deleted_username", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deleted_username")
