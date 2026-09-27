"""user_deletion — admin-only full account deletion (anonymize, don't hard-delete)

Adds `users.deleted_at`. `users.id` is referenced from ~25 other tables
(expenses created/paid, tournaments organized, media uploaded, audit log
actor, activity log actor, gear pledges, ...) — a literal `DELETE FROM
users` would either violate FK constraints or, if cascades were added to
make it not, silently destroy history other members still need (a
tournament someone else played in, an expense the treasury still accounts
for). So "delete" here means anonymize: scrub username/email/password/
Discord link/avatar/phone on the existing row (freeing the username and
email for the same person to register a fresh account) and stamp
`deleted_at`, while every foreign key into this row's id stays valid.

`deleted_at` (nullable, NULL = never deleted) is a separate signal from the
existing `is_active` (used for the reversible deactivate/reactivate toggle)
so the two states aren't conflated: deleted implies inactive, but inactive
doesn't imply deleted, and a deleted account should never show a
"reactivate" option since there is no real identity left to reactivate.

Revision ID: 0015_user_deletion
Revises: 0014_checklist
Create Date: 2026-08-02
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0015_user_deletion"
down_revision = "0014_checklist"
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
    if _has_column(bind, "users", "deleted_at"):
        return
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deleted_at")
