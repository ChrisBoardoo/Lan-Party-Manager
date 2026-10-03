"""Tests for the 0033 migration (users.token_version).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). Run against real
SQLite on a users table that already holds rows, so an ADD COLUMN NOT NULL
without a usable default would surface here and not on the Pi.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0033_token_version.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0033", MIGRATION_PATH)
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


def test_existing_users_start_at_version_zero():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        with engine.connect() as conn:
            values = conn.execute(text("SELECT token_version FROM users ORDER BY id")).scalars().all()
        assert values == [0, 0]
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent_and_downgrade_removes_the_column():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "upgrade")  # must not raise on re-run
        assert "token_version" in _columns(engine)
        _run(engine, "downgrade")
        assert "token_version" not in _columns(engine)
    finally:
        engine.dispose()
        os.remove(path)
