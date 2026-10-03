"""settlement amounts + LAN countdown reminders

Adds:
  * settlement_payments.amount — what a debtor declared sending (nullable:
                                 rows from before this release stay plain
                                 "paid" flags, see prorata._normalize_payments)
  * lan_countdown_sent         — one row per J-10 / J-7 / J-1 reminder sent,
                                 the daily job's idempotency gate

ADD COLUMN (nullable, no default) and CREATE TABLE only — the non-constant
default trap that broke 0024 on the Pi's older SQLite doesn't apply. Guarded,
so a re-run after a partial failure is safe.

Revision ID: 0034_settlement_amounts_countdown
Revises: 0033_token_version
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0034_settlement_amounts_countdown"
down_revision = "0033_token_version"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "settlement_payments") and not _has_column(bind, "settlement_payments", "amount"):
        op.add_column("settlement_payments", sa.Column("amount", sa.Float(), nullable=True))
    if not _has_table(bind, "lan_countdown_sent"):
        op.create_table(
            "lan_countdown_sent",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("days_before", sa.Integer(), nullable=False),
            sa.Column("sent_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("event_id", "user_id", "days_before"),
        )


def downgrade() -> None:
    op.drop_table("lan_countdown_sent")
    with op.batch_alter_table("settlement_payments") as batch:
        batch.drop_column("amount")
