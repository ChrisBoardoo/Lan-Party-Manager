"""users.token_version — revocable sessions

Every session token now carries the account's token_version (`tv` claim);
bumping the column (password change or reset, deactivation, deletion) makes
every token issued before it invalid at once. See auth.revoke_sessions.

ADD COLUMN only, NOT NULL with a literal default (0), so every existing row
starts at version 0 and the non-constant-default trap that broke 0024 on the
Pi's older SQLite doesn't apply. Guarded, so a re-run is a no-op.

Tokens issued before this release carry no `tv` claim and are refused by
auth.user_from_token: everyone signs in once after the upgrade.

Revision ID: 0033_token_version
Revises: 0032_lol_event_nullable
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0033_token_version"
down_revision = "0032_lol_event_nullable"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column(op.get_bind(), "users", "token_version"):
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("token_version")
