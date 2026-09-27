"""Tests for the 0011 migration — the column that never had one.

`tournaments.event_type` is mapped in models.py but was created by no migration:
0001_baseline is `Base.metadata.create_all()` (so fresh installs get it and look
healthy), the test suite builds from Base.metadata too (so it never noticed),
and `create_all` won't add a column to a table that already exists. A database
adopted from the pre-Alembic era therefore got stamped at the baseline without
it and has been missing it permanently — breaking every tournament query.

That's precisely the shape this file has to exercise: a `tournaments` table that
exists **without** the column, which is a state Base.metadata can't produce.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0011_tournament_event_type.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0011", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _db(with_event_type: bool):
    """A tournaments table in the two states that exist in the wild: an adopted
    DB (no event_type) and a fresh one (has it)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    cols = "id INTEGER PRIMARY KEY, game_name VARCHAR"
    if with_event_type:
        cols += ", event_type VARCHAR DEFAULT 'team'"
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE tournaments({cols})"))
    return engine, path


def _upgrade(engine):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        conn.commit()


def _columns(engine):
    return {c["name"] for c in inspect(engine).get_columns("tournaments")}


def test_the_column_is_added_when_missing():
    """The adopted-database case — the whole reason this revision exists."""
    engine, path = _db(with_event_type=False)
    try:
        assert "event_type" not in _columns(engine)
        _upgrade(engine)
        assert "event_type" in _columns(engine)
    finally:
        engine.dispose()
        os.remove(path)


def test_existing_rows_get_the_default():
    """Tournaments created before the fix must not come back with a NULL type —
    models.py has always defaulted new ones to "team"."""
    engine, path = _db(with_event_type=False)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO tournaments(id, game_name) VALUES (1, 'Valorant')"))
        _upgrade(engine)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT event_type FROM tournaments WHERE id = 1")).scalar() == "team"
    finally:
        engine.dispose()
        os.remove(path)


def test_it_is_a_noop_when_the_column_already_exists():
    """The fresh-install case: baseline's create_all already made it."""
    engine, path = _db(with_event_type=True)
    try:
        _upgrade(engine)
        assert "event_type" in _columns(engine)
    finally:
        engine.dispose()
        os.remove(path)


def test_it_does_not_clobber_an_existing_value():
    engine, path = _db(with_event_type=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO tournaments(id, game_name, event_type) VALUES (1, 'Chess', 'individual')"))
        _upgrade(engine)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT event_type FROM tournaments WHERE id = 1")).scalar() == "individual"
    finally:
        engine.dispose()
        os.remove(path)


def test_it_is_idempotent():
    engine, path = _db(with_event_type=False)
    try:
        _upgrade(engine)
        _upgrade(engine)  # must not raise "duplicate column name"
        assert "event_type" in _columns(engine)
    finally:
        engine.dispose()
        os.remove(path)


def test_it_tolerates_a_missing_tournaments_table():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    try:
        _upgrade(engine)  # must not raise
    finally:
        engine.dispose()
        os.remove(path)


# NOTE: there's no separate "add_column carries no inline ForeignKey" test — the
# 0005 trap. It doesn't need one: every test above runs the real upgrade() against
# real SQLite, and an inline FK raises NotImplementedError there. That's a
# stronger check than grepping the source, which would also match the docstring
# explaining why the FK isn't there.
