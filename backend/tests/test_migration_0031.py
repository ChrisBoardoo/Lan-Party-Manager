"""Tests for the 0031 migration (captured League of Legends games).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). CREATE TABLE only
— run against real SQLite to prove it upgrades, re-runs and downgrades.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0031_lol_matches.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0031", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT)"))
        conn.execute(text("CREATE TABLE lan_events(id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO users(id, username) VALUES (1, 'cross')"))
        conn.execute(text("INSERT INTO lan_events(id, title) VALUES (1, 'LAN')"))
    return engine, path


def _run(engine, step):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mod, step)()
        conn.commit()


def _tables(engine):
    return set(inspect(engine).get_table_names())


def test_upgrade_creates_both_tables():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        assert {"lol_matches", "lol_match_players"} <= _tables(engine)
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "upgrade")  # must not raise on re-run
        assert {"lol_matches", "lol_match_players"} <= _tables(engine)
    finally:
        engine.dispose()
        os.remove(path)


def test_defaults_and_uniqueness():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO lol_matches(id, event_id, riot_game_id) VALUES (1, 1, '7001')"))
            conn.execute(text(
                "INSERT INTO lol_match_players(match_id, riot_id, riot_id_key) VALUES (1, 'Cross#EUW', 'cross#euw')"
            ))
        with engine.connect() as conn:
            is_custom = conn.execute(text("SELECT is_custom FROM lol_matches")).scalar()
            line = conn.execute(text("SELECT win, kills, deaths, assists, damage FROM lol_match_players")).one()
        assert is_custom == 0
        assert tuple(line) == (0, 0, 0, 0, 0)

        for sql in (
            "INSERT INTO lol_matches(event_id, riot_game_id) VALUES (1, '7001')",
            "INSERT INTO lol_match_players(match_id, riot_id, riot_id_key) VALUES (1, 'cross#EUW', 'cross#euw')",
        ):
            duplicated = False
            try:
                with engine.begin() as conn:
                    conn.execute(text(sql))
            except Exception:
                duplicated = True
            assert duplicated, f"expected a duplicate to be rejected: {sql}"
    finally:
        engine.dispose()
        os.remove(path)


def test_downgrade_drops_both_tables():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "downgrade")
        assert not ({"lol_matches", "lol_match_players"} & _tables(engine))
    finally:
        engine.dispose()
        os.remove(path)
