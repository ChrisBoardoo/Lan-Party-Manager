"""craving chat — link preview

Adds the five nullable columns backing the WhatsApp-style link-preview card
requested after the v2 pass (md/Craving_chat_v2.md's follow-up feedback):
caching one Open Graph unfurl per message, fetched server-side in the
background — see link_preview.py and router_chat.py.

All five are plain nullable columns with NO default of any kind — the exact
pattern confirmed safe on every SQLite build in 0024_craving_chat_v2.py (a
non-constant server_default on an ALTER-added column is what broke on the
Raspberry Pi; a plain nullable column has never had that problem, CREATE
TABLE or ALTER alike). Guarded by `if "x" not in cols` like 0024, so this is
safe to re-run if it's ever interrupted partway through.

Revision ID: 0025_chat_link_preview
Revises: 0024_craving_chat_v2
Create Date: 2026-09-14
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0025_chat_link_preview"
down_revision = "0024_craving_chat_v2"
branch_labels = None
depends_on = None

NEW_COLUMNS = [
    ("link_preview_url", sa.String()),
    ("link_preview_title", sa.String()),
    ("link_preview_description", sa.Text()),
    ("link_preview_image_url", sa.String()),
    ("link_preview_site_name", sa.String()),
]


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("chat_messages")}
    for name, col_type in NEW_COLUMNS:
        if name not in cols:
            op.add_column("chat_messages", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    for name, _ in NEW_COLUMNS:
        op.drop_column("chat_messages", name)
