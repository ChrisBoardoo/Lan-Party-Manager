"""Tests for the 0036 migration (matches.played_at backfilled from the activity log).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). Run against real
SQLite with a completed match that has two "match_completed" rows (saved twice),
one without any, one still pending, and one already timestamped.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0036_match_played_at.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0036", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE matches(id INTEGER PRIMARY KEY, status TEXT, played_at DATETIME)"))
        conn.execute(text(
            "CREATE TABLE activity_logs(id INTEGER PRIMARY KEY, action TEXT, entity_type TEXT, entity_id INTEGER,"
            " created_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO matches(id, status, played_at) VALUES"
            " (1, 'completed', NULL), (2, 'completed', NULL), (3, 'pending', NULL),"
            " (4, 'completed', '2026-10-15 20:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO activity_logs(action, entity_type, entity_id, created_at) VALUES"
            " ('match_completed', 'match', 1, '2026-10-16 21:30:00'),"
            " ('match_completed', 'match', 1, '2026-10-16 21:45:00'),"
            " ('match_completed', 'match', 3, '2026-10-16 22:00:00'),"
            " ('match_completed', 'match', 4, '2026-10-16 23:00:00'),"
            " ('media_upload', 'media', 2, '2026-10-16 22:00:00')"
        ))
    return engine, path


def _run(engine, step):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mod, step)()
        conn.commit()


def _played(engine):
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT id, played_at FROM matches ORDER BY id")).all())


def test_backfills_completed_matches_from_their_first_completion_row():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        played = _played(engine)
        assert str(played[1]).startswith("2026-10-16 21:30")  # earliest of its two rows
        assert played[2] is None  # no completion row (the other row is a photo's)
        assert played[3] is None  # not completed: left alone
        assert str(played[4]).startswith("2026-10-15 20:00")  # already set: untouched
    finally:
        engine.dispose()
        os.remove(path)


def test_rerun_and_downgrade_change_nothing():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        once = _played(engine)
        _run(engine, "upgrade")
        _run(engine, "downgrade")
        assert _played(engine) == once
    finally:
        engine.dispose()
        os.remove(path)
