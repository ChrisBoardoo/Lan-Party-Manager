"""Regression test for the 0005 migration SQLite crash (1.10 bug fix).

`op.add_column(... sa.ForeignKey ...)` compiles to an ADD CONSTRAINT on SQLite,
which raises `NotImplementedError: No support for ALTER of constraints in SQLite
dialect` when the migration runs against an *existing* table (the pre-Alembic
adoption path). The fix drops the inline FK. This locks that the add_column the
migration performs succeeds on a bare SQLite table.
"""
import os
import tempfile

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_add_reported_by_column_succeeds_on_sqlite():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE matches(id INTEGER PRIMARY KEY)"))
        with engine.connect() as conn:
            op = Operations(MigrationContext.configure(conn))
            # Exactly what 0005 now does — a plain nullable Integer, no inline FK.
            op.add_column("matches", sa.Column("reported_by", sa.Integer(), nullable=True))
            conn.commit()
        cols = {c["name"] for c in inspect(engine).get_columns("matches")}
        assert "reported_by" in cols
    finally:
        engine.dispose()
        os.remove(path)


def test_inline_fk_add_column_would_crash_on_sqlite():
    """Documents *why* the FK was dropped: the old form raises on SQLite."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE matches(id INTEGER PRIMARY KEY)"))
        with engine.connect() as conn:
            op = Operations(MigrationContext.configure(conn))
            try:
                op.add_column("matches", sa.Column("x", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
                crashed = False
            except NotImplementedError:
                crashed = True
        assert crashed, "expected SQLite to reject an inline-FK add_column"
    finally:
        engine.dispose()
        os.remove(path)
