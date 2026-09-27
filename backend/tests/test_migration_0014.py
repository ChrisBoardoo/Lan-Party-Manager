"""Tests for the 0014 migration.

conftest sets SKIP_MIGRATIONS=1 and builds schema from Base.metadata, so
migrations get **zero** coverage from the normal suite (see test_migration_0010's
docstring). Purely additive like 0010, so mirrors its shape.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0014_checklist.py"

CHECKLIST_TABLES = {"event_checklists", "event_checklist_fields"}


def _migration():
    spec = importlib.util.spec_from_file_location("m0014", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users(id) VALUES (1), (2)"))
        conn.execute(text("CREATE TABLE lan_events(id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO lan_events(id) VALUES (1), (2)"))
    return engine, path


def _upgrade(engine):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        conn.commit()


def test_upgrade_creates_both_tables_on_sqlite():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        assert CHECKLIST_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_creates_every_fixed_item_column():
    """The column names ARE the i18n keys — a typo here is a missing label."""
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        cols = {c["name"] for c in inspect(engine).get_columns("event_checklists")}
        expected = {
            "computer", "screen", "screen_psu", "keyboard_mouse", "cables",
            "mousepad", "headset", "vanity", "backpack",
        }
        assert expected <= cols
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        _upgrade(engine)
        assert CHECKLIST_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
        os.remove(path)


def test_event_user_uniqueness_is_enforced():
    """One checklist per (event, user) — the router's get-or-create relies on
    this to make a duplicate save impossible rather than merely unlikely."""
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        insert = text("INSERT INTO event_checklists(event_id, user_id) VALUES (:e, :u)")
        with engine.begin() as conn:
            conn.execute(insert, {"e": 1, "u": 1})

        duplicated = False
        try:
            with engine.begin() as conn:
                conn.execute(insert, {"e": 1, "u": 1})
        except Exception:
            duplicated = True
        assert duplicated, "expected a duplicate (event, user) checklist to be rejected"

        # A different event or a different user is a distinct row, not a conflict.
        with engine.begin() as conn:
            conn.execute(insert, {"e": 2, "u": 1})
            conn.execute(insert, {"e": 1, "u": 2})
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM event_checklists")).scalar() == 3
    finally:
        engine.dispose()
        os.remove(path)


def test_downgrade_drops_both():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        mod = _migration()
        with engine.connect() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                mod.downgrade()
            conn.commit()
        assert not (CHECKLIST_TABLES & set(inspect(engine).get_table_names()))
    finally:
        engine.dispose()
        os.remove(path)
