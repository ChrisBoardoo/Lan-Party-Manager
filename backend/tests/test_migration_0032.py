"""Tests for the 0032 migration (lol_matches.event_id becomes nullable).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). This one is the
project's first batch-mode (copy-and-swap) migration, so run it against real
SQLite, on top of a real 0031 schema holding a captured game: the data, the
indexes and the foreign keys must all survive the table rebuild.
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

VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _load(filename):
    spec = importlib.util.spec_from_file_location(filename[:-3], VERSIONS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(engine, filename, step):
    mod = _load(filename)
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mod, step)()
        conn.commit()


@pytest.fixture
def engine():
    """A 0031-era database with one game captured during LAN 1."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT)"))
        conn.execute(text("CREATE TABLE lan_events(id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO users(id, username) VALUES (1, 'cross')"))
        conn.execute(text("INSERT INTO lan_events(id, title) VALUES (1, 'LAN')"))
    _run(eng, "0031_lol_matches.py", "upgrade")
    with eng.begin() as conn:
        conn.execute(text(
            "INSERT INTO lol_matches(id, event_id, riot_game_id, is_custom, submitted_by) VALUES (1, 1, 'g1', 1, 1)"
        ))
        conn.execute(text(
            "INSERT INTO lol_match_players(match_id, user_id, riot_id, riot_id_key, win, kills, deaths, assists, damage)"
            " VALUES (1, 1, 'Cross#EUW', 'cross#euw', 1, 10, 2, 8, 32000)"
        ))
    yield eng
    eng.dispose()
    os.remove(path)


def _nullable(engine):
    return {c["name"]: c for c in inspect(engine).get_columns("lol_matches")}["event_id"]["nullable"]


def test_upgrade_makes_event_id_nullable_and_keeps_everything(engine):
    assert _nullable(engine) is False
    _run(engine, "0032_lol_event_nullable.py", "upgrade")
    assert _nullable(engine) is True

    with engine.begin() as conn:
        assert conn.execute(text("SELECT event_id, riot_game_id FROM lol_matches")).all() == [(1, "g1")]
        assert conn.execute(text("SELECT kills FROM lol_match_players WHERE match_id = 1")).scalar() == 10
        # A game played outside any LAN now fits.
        conn.execute(text("INSERT INTO lol_matches(id, event_id, riot_game_id, is_custom) VALUES (2, NULL, 'g2', 0)"))

    insp = inspect(engine)
    assert {"ix_lol_matches_event_id", "ix_lol_matches_riot_game_id"} <= {i["name"] for i in insp.get_indexes("lol_matches")}
    assert {fk["referred_table"] for fk in insp.get_foreign_keys("lol_matches")} == {"lan_events", "users"}
    # Riot's game id is still unique after the rebuild.
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO lol_matches(event_id, riot_game_id, is_custom) VALUES (1, 'g1', 0)"))


def test_upgrade_is_idempotent(engine):
    _run(engine, "0032_lol_event_nullable.py", "upgrade")
    _run(engine, "0032_lol_event_nullable.py", "upgrade")
    assert _nullable(engine) is True


def test_downgrade_drops_games_outside_a_lan_and_restores_not_null(engine):
    _run(engine, "0032_lol_event_nullable.py", "upgrade")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO lol_matches(id, event_id, riot_game_id, is_custom) VALUES (2, NULL, 'g2', 0)"))
        conn.execute(text(
            "INSERT INTO lol_match_players(match_id, riot_id, riot_id_key, win, kills, deaths, assists, damage)"
            " VALUES (2, 'Bob#EUW', 'bob#euw', 0, 1, 1, 1, 1)"
        ))

    _run(engine, "0032_lol_event_nullable.py", "downgrade")
    assert _nullable(engine) is False
    with engine.begin() as conn:
        assert conn.execute(text("SELECT riot_game_id FROM lol_matches")).scalars().all() == ["g1"]
        assert conn.execute(text("SELECT match_id FROM lol_match_players")).scalars().all() == [1]
    _run(engine, "0032_lol_event_nullable.py", "downgrade")  # a re-run is a no-op
