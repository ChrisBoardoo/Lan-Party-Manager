"""setup_photo_caption — let a member label their rig photos

Adds `user_setup_photos.caption`. Photos went out in the first cut of My Setup
with no way to say what you're looking at, which is most of the value on a
shared link — "before the cable management" / "the good side".

One nullable column, guarded so it's a no-op where it already exists. A plain
add_column with no inline ForeignKey (the 0005 trap), and nullable so existing
rows need no backfill.

Revision ID: 0012_setup_photo_caption
Revises: 0011_tournament_event_type
Create Date: 2026-07-17
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0012_setup_photo_caption"
down_revision = "0011_tournament_event_type"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("user_setup_photos"):
        return
    if _has_column(bind, "user_setup_photos", "caption"):
        return
    op.add_column("user_setup_photos", sa.Column("caption", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_setup_photos", "caption")
