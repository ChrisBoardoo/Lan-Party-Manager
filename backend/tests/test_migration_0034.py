"""Tests for the 0034 migration (settlement_payments.amount, lan_countdown_sent).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). Run against real
SQLite, on a settlement_payments table that already holds a marker, so existing
"paid" flags are shown to survive as amount-less rows.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0034_settlement_amounts_countdown.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("m0034", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT)"))
        conn.execute(text("CREATE TABLE lan_events(id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text(
            "CREATE TABLE settlement_payments(id INTEGER PRIMARY KEY, event_id INTEGER, from_user_id INTEGER,"
            " to_user_id INTEGER, marked_at DATETIME, UNIQUE(event_id, from_user_id, to_user_id))"
        ))
        conn.execute(text("INSERT INTO settlement_payments(event_id, from_user_id, to_user_id) VALUES (1, 2, 1)"))
    return engine, path


def _run(engine, step):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mod, step)()
        conn.commit()


def test_existing_markers_keep_a_null_amount():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT from_user_id, to_user_id, amount FROM settlement_payments")).all()
        assert rows == [(2, 1, None)]
        assert "lan_countdown_sent" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent_and_downgrade_reverts():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "upgrade")  # must not raise on re-run
        _run(engine, "downgrade")
        insp = inspect(engine)
        assert "lan_countdown_sent" not in insp.get_table_names()
        assert "amount" not in {c["name"] for c in insp.get_columns("settlement_payments")}
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM settlement_payments")).scalar() == 1
    finally:
        engine.dispose()
        os.remove(path)
