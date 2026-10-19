"""cards & boosters

Adds:
  * card_faces          — a member's face for one edition (LAN), photo copied
                          into uploads/cards/ so an avatar change never
                          touches the cards already drawn
  * card_boosters       — boosters granted to members; unique per
                          (owner, source_type, source_id), the grants'
                          idempotency gate
  * cards               — the cards drawn into each booster (and each
                          member's signature card)
  * users.cards_opt_out — keep my face off the cards
  * users.cards_level_base — the XP level a member had when cards first
                          looked at them; level-up boosters start above it

CREATE TABLE and ADD COLUMN only. The two columns are NOT NULL with a literal
default or nullable, so the non-constant-default trap that broke 0024 on the
Pi's older SQLite doesn't apply. Guarded, so a re-run after a partial failure
is safe.

Revision ID: 0035_cards
Revises: 0034_settlement_amounts_countdown
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0035_cards"
down_revision = "0034_settlement_amounts_countdown"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "users", "cards_opt_out"):
        op.add_column(
            "users",
            sa.Column("cards_opt_out", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    if not _has_column(bind, "users", "cards_level_base"):
        op.add_column("users", sa.Column("cards_level_base", sa.Integer(), nullable=True))

    if not _has_table(bind, "card_faces"):
        op.create_table(
            "card_faces",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("username", sa.String(), nullable=False),
            sa.Column("image_url", sa.String(), nullable=True),
            sa.Column("xp_level", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("event_id", "user_id", name="uq_card_face"),
        )
    if not _has_table(bind, "card_boosters"):
        op.create_table(
            "card_boosters",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("source_type", sa.String(), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("epic_rate", sa.Float(), nullable=False),
            sa.Column("cost_xp", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("granted_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("opened_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("owner_id", "source_type", "source_id", name="uq_card_booster_source"),
        )
    if not _has_table(bind, "cards"):
        op.create_table(
            "cards",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("booster_id", sa.Integer(), sa.ForeignKey("card_boosters.id"), nullable=True, index=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("face_id", sa.Integer(), sa.ForeignKey("card_faces.id"), nullable=False),
            sa.Column("slot", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("rarity", sa.String(), nullable=False, server_default="common"),
            sa.Column("kind", sa.String(), nullable=False, server_default="pulled"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("cards")
    op.drop_table("card_boosters")
    op.drop_table("card_faces")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("cards_level_base")
        batch.drop_column("cards_opt_out")
