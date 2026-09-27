"""Tests for the 0012 migration — user_setup_photos.caption.

Migrations get zero coverage from the normal suite (SKIP_MIGRATIONS=1 + schema
from Base.metadata), so an additive column still gets run against real SQLite
here. Same shape as 0011: guarded add_column, idempotent, no inline FK.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0012_setup_photo_caption.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0012", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _db(with_caption: bool):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    cols = "id INTEGER PRIMARY KEY, setup_id INTEGER, url VARCHAR, sort_order INTEGER"
    if with_caption:
        cols += ", caption VARCHAR"
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE user_setup_photos({cols})"))
    return engine, path


def _upgrade(engine):
    mod = _migration()
    with engine.connect() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        conn.commit()


def _columns(engine):
    return {c["name"] for c in inspect(engine).get_columns("user_setup_photos")}


def test_caption_is_added_when_missing():
    engine, path = _db(with_caption=False)
    try:
        assert "caption" not in _columns(engine)
        _upgrade(engine)
        assert "caption" in _columns(engine)
    finally:
        engine.dispose()
        os.remove(path)


def test_existing_photos_survive_with_a_null_caption():
    engine, path = _db(with_caption=False)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO user_setup_photos(id, setup_id, url, sort_order) VALUES (1, 1, '/u/x.webp', 0)"))
        _upgrade(engine)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT caption FROM user_setup_photos WHERE id = 1")).scalar() is None
    finally:
        engine.dispose()
        os.remove(path)


def test_it_is_a_noop_when_the_column_exists():
    engine, path = _db(with_caption=True)
    try:
        _upgrade(engine)
        assert "caption" in _columns(engine)
    finally:
        engine.dispose()
        os.remove(path)


def test_it_is_idempotent():
    engine, path = _db(with_caption=False)
    try:
        _upgrade(engine)
        _upgrade(engine)  # must not raise "duplicate column name"
        assert "caption" in _columns(engine)
    finally:
        engine.dispose()
        os.remove(path)


def test_it_tolerates_a_missing_table():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    try:
        _upgrade(engine)  # must not raise
    finally:
        engine.dispose()
        os.remove(path)
