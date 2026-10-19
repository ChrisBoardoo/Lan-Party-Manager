"""monthly contracts

Adds monthly_contracts: each month's contract (quests.py), its objectives drawn
once and kept. CREATE TABLE only, guarded, so a re-run after a partial failure
is safe.

Revision ID: 0037_monthly_contracts
Revises: 0036_match_played_at
Create Date: 2026-10-19
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0037_monthly_contracts"
down_revision = "0036_match_played_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "monthly_contracts" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "monthly_contracts",
        sa.Column("month", sa.String(), primary_key=True),
        sa.Column("objectives", sa.Text(), nullable=False),
        sa.Column("required", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("monthly_contracts")
