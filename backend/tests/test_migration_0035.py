"""Tests for the 0035 migration (cards & boosters).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). Run against real
SQLite, on a users table that already holds a member, so existing accounts are
shown to start opted in with no level base.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0035_cards.py"
TABLES = {"card_faces", "card_boosters", "cards"}


def _migration():
    spec = importlib.util.spec_from_file_location("m0035", MIGRATION_PATH)
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
        conn.execute(text("INSERT INTO users(username) VALUES ('alice')"))
    return engine, path


def _run(engine, step):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mod, step)()
        conn.commit()


def test_existing_members_start_opted_in_with_no_level_base():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        with engine.connect() as conn:
            row = conn.execute(text("SELECT username, cards_opt_out, cards_level_base FROM users")).one()
        assert tuple(row) == ("alice", 0, None)
        assert TABLES <= set(inspect(engine).get_table_names())
        uniques = {u["name"] for u in inspect(engine).get_unique_constraints("card_boosters")}
        assert "uq_card_booster_source" in uniques
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent_and_downgrade_reverts():
    engine, path = _fresh_db()
    try:
        _run(engine, "upgrade")
        _run(engine, "upgrade")  # must not raise on re-run
        _run(engine, "downgrade")
        insp = inspect(engine)
        assert not TABLES & set(insp.get_table_names())
        assert {"cards_opt_out", "cards_level_base"}.isdisjoint({c["name"] for c in insp.get_columns("users")})
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1
    finally:
        engine.dispose()
        os.remove(path)
