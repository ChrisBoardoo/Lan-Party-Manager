"""Tests for the 0028 migration (tournaments.game_id + backfill).

conftest builds the schema from Base.metadata, so the migration file itself only
runs here (and in CI's arm64 smoke job). The backfill is the interesting part:
it must match catalog names case-insensitively and ignoring stray whitespace,
and must leave anything it can't match as NULL rather than guess.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0028_tournament_game_id.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0028", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE games(id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("CREATE TABLE tournaments(id INTEGER PRIMARY KEY, game_name TEXT)"))
        conn.execute(text(
            "INSERT INTO games(id, name) VALUES (1, 'League of Legends'), (2, 'Counter-Strike 2 / CS:S')"
        ))
        conn.execute(text(
            "INSERT INTO tournaments(id, game_name) VALUES "
            "(1, 'League of Legends'), (2, '  league of LEGENDS '), (3, 'CS2'), (4, 'Counter-Strike 2 / CS:S')"
        ))
    return engine, path


def _upgrade(engine):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        conn.commit()


def _game_ids(engine):
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT id, game_id FROM tournaments ORDER BY id")).all())


def test_adds_column_and_backfills_by_name():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        assert "game_id" in {c["name"] for c in inspect(engine).get_columns("tournaments")}
        # Case/whitespace-insensitive match; an alias it can't vouch for stays NULL.
        assert _game_ids(engine) == {1: 1, 2: 1, 3: None, 4: 2}
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent_and_keeps_manual_links():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        # An admin attaches the "CS2" tournament by hand after the first run…
        with engine.begin() as conn:
            conn.execute(text("UPDATE tournaments SET game_id = 2 WHERE id = 3"))
        _upgrade(engine)  # …and a re-run must neither raise nor undo it.
        assert _game_ids(engine) == {1: 1, 2: 1, 3: 2, 4: 2}
    finally:
        engine.dispose()
        os.remove(path)
