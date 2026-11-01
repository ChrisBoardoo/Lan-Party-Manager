"""Tests for the 0040 migration (transfers ledger + frozen settlement plans).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). This one copies
data — settlement_payments rows with an amount become transfers — so it's run
against real SQLite, on tables that already hold rows, re-run, and rolled back.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0040_transfers.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0040", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT)"))
        conn.execute(text("INSERT INTO users(id, username) VALUES (1, 'alice'), (2, 'bob'), (3, 'cara')"))
        conn.execute(text("CREATE TABLE lan_events(id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO lan_events(id, title) VALUES (7, 'LAN')"))
        conn.execute(text(
            "CREATE TABLE settlement_payments(id INTEGER PRIMARY KEY, event_id INTEGER, from_user_id INTEGER,"
            " to_user_id INTEGER, amount FLOAT, marked_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO settlement_payments(id, event_id, from_user_id, to_user_id, amount, marked_at) VALUES"
            " (1, 7, 2, 1, 144.12, '2026-10-16 21:04:00'),"   # a 1.3.4+ payment with its amount
            " (2, 7, 3, 1, NULL, '2026-09-01 10:00:00'),"     # a pre-1.3.4 'paid' flag: stays a flag
            " (3, 7, 3, 2, 17.385, '2026-10-17 09:00:00')"    # rounds to the cent
        ))
    return engine, path


def _run(engine, step):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mod, step)()
        conn.commit()


def _transfers(engine):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT event_id, from_user_id, to_user_id, amount_cents, transferred_on, note, recorded_by"
            " FROM transfers ORDER BY id"
        )).all()


def test_upgrade_creates_both_tables_and_copies_payments_with_an_amount():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        tables = set(inspect(engine).get_table_names())
        assert {"transfers", "settlement_plans"} <= tables
        assert _transfers(engine) == [
            (7, 2, 1, 14412, "2026-10-16", None, 2),
            (7, 3, 2, 1739, "2026-10-17", None, 3),
        ]
        with engine.connect() as conn:
            # settlement_payments is left as it was (1.4.1 still reads it after a rollback).
            assert conn.execute(text("SELECT COUNT(*) FROM settlement_payments")).scalar() == 3
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent_and_never_copies_twice():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "upgrade")  # must not raise, nor duplicate the copy
        assert len(_transfers(engine)) == 2
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_without_settlement_payments_table():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE lan_events(id INTEGER PRIMARY KEY)"))
        _run(engine, "upgrade")
        assert _transfers(engine) == []
    finally:
        engine.dispose()
        os.remove(path)


def test_downgrade_drops_the_new_tables_and_keeps_settlement_payments():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "downgrade")
        tables = set(inspect(engine).get_table_names())
        assert "transfers" not in tables and "settlement_plans" not in tables
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM settlement_payments")).scalar() == 3
    finally:
        engine.dispose()
        os.remove(path)
