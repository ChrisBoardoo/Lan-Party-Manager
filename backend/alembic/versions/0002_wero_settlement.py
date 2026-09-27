"""wero settlement — user.phone, expense.paid_by, settlement_payments

Adds the schema needed for the Wero peer-to-peer settlement in Treasury:
  * users.phone            — optional contact number for Wero payments
  * expenses.paid_by       — who actually fronted the expense (nullable; legacy
                             rows fall back to created_by)
  * settlement_payments    — a debtor's self-declared "payment sent" markers

Revision ID: 0002_wero_settlement
Revises: 0001_baseline
Create Date: 2026-07-07
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_wero_settlement"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    # Idempotent adds — a DB stamped straight at baseline won't have these yet,
    # but guard anyway so re-runs are safe.
    if not _has_column(bind, "users", "phone"):
        op.add_column("users", sa.Column("phone", sa.String(), nullable=True))
    if not _has_column(bind, "expenses", "paid_by"):
        op.add_column("expenses", sa.Column("paid_by", sa.Integer(), nullable=True))

    if not _has_table(bind, "settlement_payments"):
        op.create_table(
            "settlement_payments",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False),
            sa.Column("from_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("to_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("marked_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("event_id", "from_user_id", "to_user_id"),
        )


def downgrade() -> None:
    op.drop_table("settlement_payments")
    op.drop_column("expenses", "paid_by")
    op.drop_column("users", "phone")
