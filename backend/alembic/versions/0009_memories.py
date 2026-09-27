"""memories — media reactions, recap sharing, and the expense backfill

Adds the tables backing "The Memories" (1.0.0-rc2): emoji reactions on media
(which feed the recap's "best of"), and per-event revocable public recap links.

Also backfills `expenses.event_id`. This part is not additive and deserves
explanation. The pro-rata split used to load *every* expense in the database
regardless of event, so untagged expenses (the default — the add-expense form
sent no event) still landed in the split by accident. The split is now scoped by
event_id, which is correct, but it means an untagged expense counts towards
nothing. On a single-event install that would silently zero out a working
treasury, so we assign the obvious ones:

  1. exactly one event in the database -> every untagged expense belongs to it
  2. otherwise -> assign where the expense date falls inside exactly one event's
     window; genuinely ambiguous rows are left alone

Anything still untagged afterwards is surfaced in the Treasury UI for the admin
to assign by hand, never silently dropped.

The table creates are additive (create_table, no SQLite batch mode needed). The
backfill is NOT reversed by downgrade() — it can't be, since the pre-migration
NULLs are indistinguishable from deliberate ones afterwards. Take a backup
first; the app's own backup endpoint is enough.

Revision ID: 0009_memories
Revises: 0008_gear
Create Date: 2026-07-17
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_memories"
down_revision = "0008_gear"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def _backfill_expense_events(bind) -> None:
    """Assign untagged expenses to an event where the answer is unambiguous."""
    if not (_has_table(bind, "expenses") and _has_table(bind, "lan_events")):
        return

    untagged = bind.execute(
        sa.text("SELECT COUNT(*) FROM expenses WHERE event_id IS NULL")
    ).scalar()
    if not untagged:
        return

    event_ids = [r[0] for r in bind.execute(sa.text("SELECT id FROM lan_events")).fetchall()]
    if not event_ids:
        return

    if len(event_ids) == 1:
        bind.execute(
            sa.text("UPDATE expenses SET event_id = :eid WHERE event_id IS NULL"),
            {"eid": event_ids[0]},
        )
        return

    # Multiple events: only assign where exactly one event's window contains the
    # expense date. A row matching two overlapping events, or none at all, is a
    # judgement call we don't get to make.
    bind.execute(sa.text("""
        UPDATE expenses
           SET event_id = (
                 SELECT e.id FROM lan_events e
                  WHERE expenses.date BETWEEN e.start_date AND e.end_date
               )
         WHERE event_id IS NULL
           AND date IS NOT NULL
           AND (
                 SELECT COUNT(*) FROM lan_events e
                  WHERE expenses.date BETWEEN e.start_date AND e.end_date
               ) = 1
    """))


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "media_reactions"):
        op.create_table(
            "media_reactions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("media_id", sa.Integer(), sa.ForeignKey("media_items.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("emoji", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("media_id", "user_id", "emoji"),
        )

    if not _has_table(bind, "recap_shares"):
        op.create_table(
            "recap_shares",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("lan_events.id"), nullable=False, unique=True),
            sa.Column("token", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )

    _backfill_expense_events(bind)


def downgrade() -> None:
    op.drop_table("recap_shares")
    op.drop_table("media_reactions")
    # The expense backfill is deliberately not reversed — see the module
    # docstring. Restore from a backup if you need the NULLs back.
