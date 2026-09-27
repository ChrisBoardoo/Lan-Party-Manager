"""Tests for the 0029 migration (trophies tables), run against real SQLite.

conftest builds the schema from Base.metadata, so this is the only place the
migration file itself runs outside CI's arm64 job.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0029_trophies.py"
TABLES = {"trophies", "event_trophies", "event_trophy_winners", "trophy_votes"}


def _migration():
    spec = importlib.util.spec_from_file_location("m0029", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT)"))
        conn.execute(text("CREATE TABLE lan_events(id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO users(id, username) VALUES (1, 'alice'), (2, 'bob')"))
        conn.execute(text("INSERT INTO lan_events(id, title) VALUES (1, 'LAN')"))
    yield eng
    eng.dispose()
    os.remove(path)


def _upgrade(engine):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        conn.commit()


def test_creates_all_tables(engine):
    _upgrade(engine)
    assert TABLES <= set(inspect(engine).get_table_names())


def test_upgrade_is_idempotent(engine):
    _upgrade(engine)
    _upgrade(engine)
    assert TABLES <= set(inspect(engine).get_table_names())


def test_defaults_and_one_vote_per_voter(engine):
    _upgrade(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO trophies(id, name) VALUES (1, 'Golden Rage-Quit')"))
        conn.execute(text("INSERT INTO event_trophies(id, event_id, trophy_id) VALUES (1, 1, 1)"))
        mode, status = conn.execute(text("SELECT mode, status FROM event_trophies WHERE id = 1")).one()
        assert (mode, status) == ("vote", "draft")
        conn.execute(text("INSERT INTO trophy_votes(event_trophy_id, voter_id, nominee_id) VALUES (1, 1, 2)"))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO trophy_votes(event_trophy_id, voter_id, nominee_id) VALUES (1, 1, 1)"))
