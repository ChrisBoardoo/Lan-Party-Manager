"""Tests for the 0041 migration (game_sessions).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). A new table: run
against real SQLite, twice to check the guard, then down.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0041_game_sessions.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0041", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE lan_events(id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE games(id INTEGER PRIMARY KEY)"))
    return engine, path


def _run(engine, step):
    mod = _migration()
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.op = Operations(ctx)
            getattr(mod, step)()


def test_creates_the_table_reruns_cleanly_and_downgrades():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "upgrade")  # guarded: no error the second time
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("game_sessions")}
        assert cols == {"id", "user_id", "event_id", "game_id", "game_key", "game_name", "visible",
                        "started_at", "last_seen_at"}
        indexed = {tuple(i["column_names"]) for i in insp.get_indexes("game_sessions")}
        assert {("user_id",), ("event_id",), ("last_seen_at",)} <= indexed
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO game_sessions(user_id, game_key, game_name, started_at, last_seen_at)"
                " VALUES (1, 'exe:cs2', 'Counter-Strike 2', '2026-10-15 20:00:00', '2026-10-15 21:00:00')"
            ))
            assert conn.execute(text("SELECT visible, event_id FROM game_sessions")).one() == (1, None)
        _run(engine, "downgrade")
        assert "game_sessions" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        os.remove(path)
