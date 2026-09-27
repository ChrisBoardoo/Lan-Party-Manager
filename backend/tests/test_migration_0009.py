"""Tests for the 0009 migration — chiefly the expense backfill.

The normal test suite sets SKIP_MIGRATIONS=1 and builds schema straight from
Base.metadata, so migrations get no coverage from it at all. That is how the
0005 SQLite crash reached users. The backfill here rewrites financial data on a
live database, which is far too sharp an edge to ship on a hand-check, so it is
exercised directly against real SQLite.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0009_memories.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0009", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE lan_events(id INTEGER PRIMARY KEY, start_date DATE, end_date DATE)"))
        conn.execute(text("CREATE TABLE expenses(id INTEGER PRIMARY KEY, amount FLOAT, date DATE, event_id INTEGER)"))
    return engine, path


def _events(conn, rows):
    for eid, start, end in rows:
        conn.execute(
            text("INSERT INTO lan_events(id, start_date, end_date) VALUES (:i, :s, :e)"),
            {"i": eid, "s": start, "e": end},
        )


def _expenses(conn, rows):
    for xid, d, event_id in rows:
        conn.execute(
            text("INSERT INTO expenses(id, amount, date, event_id) VALUES (:i, 10.0, :d, :e)"),
            {"i": xid, "d": d, "e": event_id},
        )


def _event_ids(engine):
    with engine.connect() as conn:
        return {r[0]: r[1] for r in conn.execute(text("SELECT id, event_id FROM expenses")).fetchall()}


def _run_backfill(engine):
    mod = _migration()
    with engine.connect() as conn:
        mod._backfill_expense_events(conn)
        conn.commit()


def test_single_event_claims_every_untagged_expense():
    # The common install: one LAN, every expense untagged because the form
    # defaulted to no event. Scoping without this would zero out their split.
    engine, path = _fresh_db()
    try:
        with engine.begin() as conn:
            _events(conn, [(1, "2026-08-01", "2026-08-03")])
            # Note the last one is dated well outside the event window — bought
            # in advance. It still belongs to the only event there is.
            _expenses(conn, [(1, "2026-08-01", None), (2, "2026-08-02", None), (3, "2026-07-04", None)])
        _run_backfill(engine)
        assert _event_ids(engine) == {1: 1, 2: 1, 3: 1}
    finally:
        engine.dispose()
        os.remove(path)


def test_multiple_events_assign_by_date_window():
    engine, path = _fresh_db()
    try:
        with engine.begin() as conn:
            _events(conn, [(1, "2026-08-01", "2026-08-03"), (2, "2026-09-01", "2026-09-03")])
            _expenses(conn, [(1, "2026-08-02", None), (2, "2026-09-02", None)])
        _run_backfill(engine)
        assert _event_ids(engine) == {1: 1, 2: 2}
    finally:
        engine.dispose()
        os.remove(path)


def test_multiple_events_leave_an_out_of_window_expense_alone():
    engine, path = _fresh_db()
    try:
        with engine.begin() as conn:
            _events(conn, [(1, "2026-08-01", "2026-08-03"), (2, "2026-09-01", "2026-09-03")])
            _expenses(conn, [(1, "2026-07-04", None)])  # matches neither window
        _run_backfill(engine)
        assert _event_ids(engine) == {1: None}
    finally:
        engine.dispose()
        os.remove(path)


def test_multiple_events_leave_an_ambiguous_expense_alone():
    # Overlapping windows: the date matches two events, so there is no honest
    # answer and we must not guess at someone's money.
    engine, path = _fresh_db()
    try:
        with engine.begin() as conn:
            _events(conn, [(1, "2026-08-01", "2026-08-05"), (2, "2026-08-04", "2026-08-08")])
            _expenses(conn, [(1, "2026-08-04", None)])
        _run_backfill(engine)
        assert _event_ids(engine) == {1: None}
    finally:
        engine.dispose()
        os.remove(path)


def test_already_tagged_expenses_are_never_touched():
    engine, path = _fresh_db()
    try:
        with engine.begin() as conn:
            _events(conn, [(1, "2026-08-01", "2026-08-03"), (2, "2026-09-01", "2026-09-03")])
            # Deliberately tagged to event 2 despite sitting in event 1's window.
            _expenses(conn, [(1, "2026-08-02", 2)])
        _run_backfill(engine)
        assert _event_ids(engine) == {1: 2}
    finally:
        engine.dispose()
        os.remove(path)


def test_backfill_is_a_noop_with_no_events():
    engine, path = _fresh_db()
    try:
        with engine.begin() as conn:
            _expenses(conn, [(1, "2026-08-02", None)])
        _run_backfill(engine)
        assert _event_ids(engine) == {1: None}
    finally:
        engine.dispose()
        os.remove(path)


def test_backfill_is_idempotent():
    engine, path = _fresh_db()
    try:
        with engine.begin() as conn:
            _events(conn, [(1, "2026-08-01", "2026-08-03"), (2, "2026-09-01", "2026-09-03")])
            _expenses(conn, [(1, "2026-08-02", None), (2, "2026-07-04", None)])
        _run_backfill(engine)
        first = _event_ids(engine)
        _run_backfill(engine)
        assert _event_ids(engine) == first == {1: 1, 2: None}
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_creates_both_tables_on_sqlite():
    """0005 shipped a create/alter that crashed on SQLite. Run the real
    upgrade() against real SQLite so 0009 can't repeat it."""
    engine, path = _fresh_db()
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE media_items(id INTEGER PRIMARY KEY)"))
            _events(conn, [(1, "2026-08-01", "2026-08-03")])
            _expenses(conn, [(1, "2026-08-02", None)])

        mod = _migration()
        with engine.connect() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                mod.upgrade()
            conn.commit()

        tables = set(inspect(engine).get_table_names())
        assert {"media_reactions", "recap_shares"} <= tables
        # The same upgrade also runs the backfill.
        assert _event_ids(engine) == {1: 1}
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent_when_tables_already_exist():
    """The _has_table guards: re-running an upgrade must not blow up on a
    database that already has the tables (the pre-Alembic adoption path)."""
    engine, path = _fresh_db()
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE media_items(id INTEGER PRIMARY KEY)"))

        mod = _migration()
        for _ in range(2):
            with engine.connect() as conn:
                with Operations.context(MigrationContext.configure(conn)):
                    mod.upgrade()
                conn.commit()

        assert {"media_reactions", "recap_shares"} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
        os.remove(path)


def test_reaction_uniqueness_is_enforced_by_the_created_table():
    """The toggle relies on (media_id, user_id, emoji) being unique."""
    engine, path = _fresh_db()
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE media_items(id INTEGER PRIMARY KEY)"))

        mod = _migration()
        with engine.connect() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                mod.upgrade()
            conn.commit()

        insert = text("INSERT INTO media_reactions(media_id, user_id, emoji) VALUES (1, 1, '🔥')")
        with engine.begin() as conn:
            conn.execute(insert)

        duplicated = False
        try:
            with engine.begin() as conn:
                conn.execute(insert)
        except Exception:
            duplicated = True
        assert duplicated, "expected the unique constraint to reject a duplicate reaction"
    finally:
        engine.dispose()
        os.remove(path)


def test_backfill_tolerates_a_missing_expenses_table():
    # The guard: a database that predates the treasury shouldn't crash the
    # upgrade just because it has nothing to backfill.
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE lan_events(id INTEGER PRIMARY KEY, start_date DATE, end_date DATE)"))
        _run_backfill(engine)  # must not raise
    finally:
        engine.dispose()
        os.remove(path)
