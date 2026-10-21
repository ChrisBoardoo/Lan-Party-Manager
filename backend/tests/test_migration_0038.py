"""Tests for the 0038 migration (lol_match_submitters, backfilled from submitted_by).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). Run against real
SQLite with two games that have a sender, one without, and once more to check
the backfill is idempotent.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0038_lol_match_submitters.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0038", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db(with_matches=True):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
        if with_matches:
            conn.execute(text(
                "CREATE TABLE lol_matches(id INTEGER PRIMARY KEY, riot_game_id TEXT, submitted_by INTEGER,"
                " created_at DATETIME)"
            ))
            conn.execute(text(
                "INSERT INTO lol_matches(id, riot_game_id, submitted_by, created_at) VALUES"
                " (1, 'EUW1_1', 7, '2026-10-15 20:00:00'), (2, 'EUW1_2', 8, '2026-10-15 21:00:00'),"
                " (3, 'EUW1_3', NULL, '2026-10-15 22:00:00')"
            ))
    return engine, path


def _upgrade(engine):
    mod = _migration()
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.op = Operations(ctx)
            mod.upgrade()


def _rows(engine):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT match_id, user_id, created_at FROM lol_match_submitters ORDER BY match_id"
        )).fetchall()


def test_backfills_the_first_sender_and_reruns_cleanly():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        assert [(m, u) for m, u, _ in _rows(engine)] == [(1, 7), (2, 8)]
        assert _rows(engine)[0][2] == "2026-10-15 20:00:00"  # the game's own capture time
        _upgrade(engine)  # idempotent: no duplicate, no error
        assert [(m, u) for m, u, _ in _rows(engine)] == [(1, 7), (2, 8)]
        cols = {c["name"] for c in inspect(engine).get_columns("lol_match_submitters")}
        assert cols == {"match_id", "user_id", "created_at"}
    finally:
        engine.dispose()
        os.remove(path)


def test_without_lol_matches_only_creates_the_table():
    engine, path = _fresh_db(with_matches=False)
    try:
        _upgrade(engine)
        assert "lol_match_submitters" in inspect(engine).get_table_names()
        assert _rows(engine) == []
    finally:
        engine.dispose()
        os.remove(path)
