"""Tests for the 0039 migration (users.hub_layout).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). Purely additive —
run against real SQLite, on a users table that already holds rows.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0039_hub_layout.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0039", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT)"))
        conn.execute(text("INSERT INTO users(id, username) VALUES (1, 'alice'), (2, 'bob')"))
    return engine, path


def _run(engine, step):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mod, step)()
        conn.commit()


def _columns(engine):
    return {c["name"] for c in inspect(engine).get_columns("users")}


def test_upgrade_adds_the_column_empty_for_existing_users():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        assert "hub_layout" in _columns(engine)
        with engine.connect() as conn:
            values = conn.execute(text("SELECT hub_layout FROM users")).scalars().all()
        assert values == [None, None]
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "upgrade")  # must not raise on re-run
        assert "hub_layout" in _columns(engine)
    finally:
        engine.dispose()
        os.remove(path)


def test_downgrade_drops_the_column():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "downgrade")
        assert "hub_layout" not in _columns(engine)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar() == 2
    finally:
        engine.dispose()
        os.remove(path)
