"""Tests for the 0020 migration (steam link columns).

conftest sets SKIP_MIGRATIONS=1 and builds schema from Base.metadata, so
migrations get **zero** coverage from the normal suite (see test_migration_0010's
docstring). Purely additive (add_column + a unique index, mirroring 0003's
Discord columns) — run against real SQLite so a rebuild/batch-mode issue with
`ADD COLUMN` would surface here rather than in production.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0020_steam_link.py"

STEAM_COLUMNS = {"steam_id", "steam_username", "steam_avatar"}


def _migration():
    spec = importlib.util.spec_from_file_location("m0020", MIGRATION_PATH)
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


def _upgrade(engine):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        conn.commit()


def test_upgrade_adds_all_three_columns():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        cols = {c["name"] for c in inspect(engine).get_columns("users")}
        assert STEAM_COLUMNS <= cols
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        _upgrade(engine)  # must not raise on re-run
        cols = {c["name"] for c in inspect(engine).get_columns("users")}
        assert STEAM_COLUMNS <= cols
    finally:
        engine.dispose()
        os.remove(path)


def test_steam_id_uniqueness_is_enforced():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET steam_id = '765611980001' WHERE id = 1"))

        duplicated = False
        try:
            with engine.begin() as conn:
                conn.execute(text("UPDATE users SET steam_id = '765611980001' WHERE id = 2"))
        except Exception:
            duplicated = True
        assert duplicated, "expected a duplicate steam_id to be rejected by the unique index"
    finally:
        engine.dispose()
        os.remove(path)


def test_steam_id_allows_multiple_nulls():
    """Unlinked accounts (steam_id = NULL) must coexist — a unique *constraint*
    would reject that on some backends, which is exactly why 0003/0020 use a
    unique *index* instead (NULLs don't collide in a SQLite unique index)."""
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        with engine.begin() as conn:
            conn.execute(text("SELECT steam_id FROM users"))  # both rows already NULL by default
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM users WHERE steam_id IS NULL")).scalar()
        assert count == 2
    finally:
        engine.dispose()
        os.remove(path)


def test_downgrade_drops_all_three_columns():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        mod = _migration()
        with engine.connect() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                mod.downgrade()
            conn.commit()
        cols = {c["name"] for c in inspect(engine).get_columns("users")}
        assert not (STEAM_COLUMNS & cols)
    finally:
        engine.dispose()
        os.remove(path)
