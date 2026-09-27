"""Tests for the 0010 migration.

conftest sets SKIP_MIGRATIONS=1 and builds schema from Base.metadata, so
migrations get **zero** coverage from the normal suite — that is how the 0005
SQLite crash reached users. 0010 is purely additive and therefore boring, but
"boring" is a claim, and this is where it gets checked.

The two UNIQUE constraints below are load-bearing, not decoration:
`user_setups.share_token` UNIQUE is what makes the router's indexed token lookup
sound, and `user_setups.user_id` UNIQUE is the 1:1 claim the whole design rests on.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0010_setup.py"

SETUP_TABLES = {"user_setups", "user_setup_fields", "user_setup_photos"}


def _migration():
    spec = importlib.util.spec_from_file_location("m0010", MIGRATION_PATH)
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
        assert SETUP_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_creates_every_component_column():
    """The column names ARE the i18n keys — a typo here is a missing label."""
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        cols = {c["name"] for c in inspect(engine).get_columns("user_setups")}
        expected = {
            "motherboard", "cpu", "cooler", "graphics_card", "ram", "power_supply",
            "fans", "storage", "pc_case", "display", "keyboard", "mouse", "headset", "mic",
        }
        assert expected <= cols
        assert "case" not in cols  # reserved word — it must be pc_case
    finally:
        engine.dispose()
        os.remove(path)


def test_upgrade_is_idempotent():
    """The _has_table guards — the pre-Alembic adoption path re-runs this."""
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        _upgrade(engine)
        assert SETUP_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
        os.remove(path)


def test_share_token_uniqueness_is_enforced_by_the_created_table():
    """The router looks a token up by index and then compare_digests the single
    hit. That is only sound because the column is UNIQUE."""
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        insert = text("INSERT INTO user_setups(user_id, share_token) VALUES (:u, 'tok')")
        with engine.begin() as conn:
            conn.execute(insert, {"u": 1})

        duplicated = False
        try:
            with engine.begin() as conn:
                conn.execute(insert, {"u": 2})
        except Exception:
            duplicated = True
        assert duplicated, "expected a duplicate share_token to be rejected"
    finally:
        engine.dispose()
        os.remove(path)


def test_user_id_uniqueness_enforces_the_one_to_one():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO user_setups(user_id) VALUES (1)"))

        duplicated = False
        try:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO user_setups(user_id) VALUES (1)"))
        except Exception:
            duplicated = True
        assert duplicated, "expected a second setup for the same user to be rejected"
    finally:
        engine.dispose()
        os.remove(path)


def test_two_setups_may_both_have_no_token():
    """NULL share_token is the un-minted state; SQLite treats NULLs as distinct
    under UNIQUE, and the whole design depends on that being true."""
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO user_setups(user_id) VALUES (1)"))
            conn.execute(text("INSERT INTO user_setups(user_id) VALUES (2)"))
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM user_setups")).scalar() == 2
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
        assert not (SETUP_TABLES & set(inspect(engine).get_table_names()))
    finally:
        engine.dispose()
        os.remove(path)
