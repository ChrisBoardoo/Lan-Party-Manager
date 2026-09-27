"""Tests for the 0030 migration (library favorites, saved filters, Riot ID).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). Purely additive —
run against real SQLite, on tables that already hold rows, so an ADD COLUMN
NOT NULL without a usable default would surface here and not on the Pi.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0030_games_favorites_riot_id.py"
)

USER_COLUMNS = {"games_library_filters", "riot_id", "riot_id_key"}


def _migration():
    spec = importlib.util.spec_from_file_location("m0030", MIGRATION_PATH)
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
        conn.execute(text(
            "CREATE TABLE user_game_library(id INTEGER PRIMARY KEY, user_id INTEGER, game_id INTEGER,"
            " max_players_override INTEGER)"
        ))
        conn.execute(text("INSERT INTO user_game_library(user_id, game_id) VALUES (1, 10), (2, 10)"))
    return engine, path


def _run(engine, step):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mod, step)()
        conn.commit()


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_upgrade_adds_every_column():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        assert USER_COLUMNS <= _columns(engine, "users")
        assert "is_favorite" in _columns(engine, "user_game_library")
    finally:
        engine.dispose()
        os.remove(path)


def test_existing_library_rows_are_not_favorites():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        with engine.connect() as conn:
            values = conn.execute(text("SELECT is_favorite FROM user_game_library")).scalars().all()
        assert values == [0, 0]
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "upgrade")  # must not raise on re-run
        assert USER_COLUMNS <= _columns(engine, "users")
    finally:
        engine.dispose()
        os.remove(path)


def test_riot_id_key_is_unique_but_allows_many_nulls():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        with engine.connect() as conn:
            nulls = conn.execute(text("SELECT COUNT(*) FROM users WHERE riot_id_key IS NULL")).scalar()
        assert nulls == 2

        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET riot_id_key = 'alice#euw' WHERE id = 1"))
        duplicated = False
        try:
            with engine.begin() as conn:
                conn.execute(text("UPDATE users SET riot_id_key = 'alice#euw' WHERE id = 2"))
        except Exception:
            duplicated = True
        assert duplicated, "expected a duplicate riot_id_key to be rejected by the unique index"
    finally:
        engine.dispose()
        os.remove(path)


def test_downgrade_drops_every_column():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "downgrade")
        assert not (USER_COLUMNS & _columns(engine, "users"))
        assert "is_favorite" not in _columns(engine, "user_game_library")
    finally:
        engine.dispose()
        os.remove(path)
