"""transfers — Trésorerie 2.0 ledger + frozen settlement plans

Adds `transfers` (one row per money transfer between two members for an event:
amount in cents, real date, note, who entered it) and `settlement_plans` (an
event's "who owes whom" plan as shown, frozen — md/2.features/treso2.0.md).

Copies every settlement_payments row that carries an amount (1.3.4 → 1.4.1:
"payment sent" with the line's amount) into transfers: amount → cents,
transferred_on = the day it was marked, recorded_by = the debtor. The copy only
runs while transfers is empty, so a re-run after a partial failure doesn't
duplicate anything. settlement_payments is left untouched: its amount-less rows
(pre-1.3.4 "paid" flags) are still read as flags, and 1.4.1 keeps reading it if
the image is rolled back (transfers entered in 1.4.2 are then not seen).

Revision ID: 0040_transfers
Revises: 0039_hub_layout
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0040_transfers"
down_revision = "0039_hub_layout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    names = set(sa.inspect(bind).get_table_names())
    if "transfers" not in names:
        op.create_table(
            "transfers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False),
            sa.Column("from_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("to_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("transferred_on", sa.Date(), nullable=False),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("ix_transfers_id", "transfers", ["id"])
        op.create_index("ix_transfers_event_id", "transfers", ["event_id"])
        op.create_index("ix_transfers_from_user_id", "transfers", ["from_user_id"])
        op.create_index("ix_transfers_to_user_id", "transfers", ["to_user_id"])
    if "settlement_plans" not in names:
        op.create_table(
            "settlement_plans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False, unique=True),
            sa.Column("lines", sa.Text(), nullable=False),
            sa.Column("baked_transfer_ids", sa.Text(), nullable=False),
            sa.Column("fingerprint", sa.String(), nullable=False),
            sa.Column("frozen_on", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("ix_settlement_plans_id", "settlement_plans", ["id"])

    if "settlement_payments" not in names:
        return
    already = bind.execute(sa.text("SELECT COUNT(*) FROM transfers")).scalar()
    if already:
        return
    # SQLite: date(marked_at) gives 'YYYY-MM-DD'; a row without marked_at (never
    # happens via the API) falls back to today.
    bind.execute(sa.text(
        """
        INSERT INTO transfers (event_id, from_user_id, to_user_id, amount_cents, transferred_on, note, recorded_by, created_at)
        SELECT event_id, from_user_id, to_user_id,
               CAST(ROUND(amount * 100) AS INTEGER),
               COALESCE(date(marked_at), date('now')),
               NULL, from_user_id, COALESCE(marked_at, CURRENT_TIMESTAMP)
        FROM settlement_payments
        WHERE amount IS NOT NULL AND amount > 0
        ORDER BY id
        """
    ))


def downgrade() -> None:
    op.drop_table("settlement_plans")
    op.drop_table("transfers")
