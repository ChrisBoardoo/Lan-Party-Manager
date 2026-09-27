"""Tests for the 0019 migration.

conftest sets SKIP_MIGRATIONS=1 and builds schema from Base.metadata, so
migrations get **zero** coverage from the normal suite (see test_migration_0010's
docstring). Purely additive like 0018, so mirrors its shape.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0019_games.py"

GAMES_TABLES = {"games", "user_game_library", "user_game_wishlist"}


def _migration():
    spec = importlib.util.spec_from_file_location("m0019", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users(id) VALUES (1), (2)"))
    return engine, path


def _upgrade(engine):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        conn.commit()


def test_upgrade_creates_all_three_tables_on_sqlite():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        assert GAMES_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_seeds_the_catalog_from_the_checked_in_json():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM games")).scalar()
            custom_count = conn.execute(text("SELECT COUNT(*) FROM games WHERE is_custom = 1")).scalar()
        assert count >= 100
        assert custom_count == 0
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent_and_does_not_duplicate_the_seed():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        with engine.connect() as conn:
            first_count = conn.execute(text("SELECT COUNT(*) FROM games")).scalar()
        _upgrade(engine)
        with engine.connect() as conn:
            second_count = conn.execute(text("SELECT COUNT(*) FROM games")).scalar()
        assert GAMES_TABLES <= set(inspect(engine).get_table_names())
        assert first_count == second_count
    finally:
        engine.dispose()
        os.remove(path)


def test_library_and_wishlist_uniqueness_is_enforced():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO games(name) VALUES ('Test Game')"))
        insert = text("INSERT INTO user_game_library(user_id, game_id) VALUES (:u, :g)")
        with engine.begin() as conn:
            conn.execute(insert, {"u": 1, "g": 1})

        duplicated = False
        try:
            with engine.begin() as conn:
                conn.execute(insert, {"u": 1, "g": 1})
        except Exception:
            duplicated = True
        assert duplicated, "expected a duplicate (user, game) library row to be rejected"

        # A different user or a different game is a distinct row, not a conflict.
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO games(name) VALUES ('Another Game')"))
            conn.execute(insert, {"u": 2, "g": 1})
            conn.execute(insert, {"u": 1, "g": 2})
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM user_game_library")).scalar() == 3
    finally:
        engine.dispose()
        os.remove(path)


def test_downgrade_drops_all_three():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        mod = _migration()
        with engine.connect() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                mod.downgrade()
            conn.commit()
        assert not (GAMES_TABLES & set(inspect(engine).get_table_names()))
    finally:
        engine.dispose()
        os.remove(path)
