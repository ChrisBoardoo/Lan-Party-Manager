"""card trades

Adds (lot C of md/2.features/cards/cards_v2_quetes_presence_echanges.md):
  * card_listings     — duplicates put up for trade in the crew's market, by
                        card type (face, rarity)
  * card_trades       — offers between two members; status computed on read
                        for expiry, re-checked in full when accepted
  * card_trade_items  — the cards on each side; after acceptance, the cards'
                        provenance
  * cards.acquired_at — when the current owner got the card by a trade

CREATE TABLE and a nullable ADD COLUMN only: nothing to backfill, and no
non-constant default (the trap that broke 0024 on the Pi's older SQLite).
Guarded, so a re-run after a partial failure is safe.

Revision ID: 0042_card_trades
Revises: 0041_game_sessions
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0042_card_trades"
down_revision = "0041_game_sessions"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if not _has_column(bind, "cards", "acquired_at"):
        op.add_column("cards", sa.Column("acquired_at", sa.DateTime(), nullable=True))

    if "card_listings" not in tables:
        op.create_table(
            "card_listings",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("face_id", sa.Integer(), sa.ForeignKey("card_faces.id"), nullable=False),
            sa.Column("rarity", sa.String(), nullable=False),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
        )
    if "card_trades" not in tables:
        op.create_table(
            "card_trades",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("proposer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("listing_id", sa.Integer(), sa.ForeignKey("card_listings.id"), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="pending", index=True),
            sa.Column("closed_reason", sa.String(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )
    if "card_trade_items" not in tables:
        op.create_table(
            "card_trade_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("trade_id", sa.Integer(), sa.ForeignKey("card_trades.id"), nullable=False, index=True),
            sa.Column("card_id", sa.Integer(), sa.ForeignKey("cards.id"), nullable=False, index=True),
            sa.Column("from_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("card_trade_items")
    op.drop_table("card_trades")
    op.drop_table("card_listings")
    with op.batch_alter_table("cards") as batch:
        batch.drop_column("acquired_at")
