"""Tests for the 0037 migration (monthly_contracts).

conftest builds the schema from Base.metadata, so migrations get no coverage
from the normal suite (see test_migration_0020's docstring). The table is
created guarded: a re-run is a no-op, and an existing table (a database that
already ran a post-1.3.5 build) is left alone with its rows.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0037_monthly_contracts.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0037", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return create_engine(f"sqlite:///{path}"), path


def _upgrade(engine):
    mod = _migration()
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.op = Operations(ctx)
            mod.upgrade()


def test_creates_the_table_once_and_keeps_existing_rows():
    engine, path = _fresh_db()
    try:
        _upgrade(engine)
        cols = {c["name"] for c in inspect(engine).get_columns("monthly_contracts")}
        assert cols == {"month", "objectives", "required", "created_at"}
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO monthly_contracts(month, objectives, required) VALUES ('2026-10', '[]', 2)"
            ))
        _upgrade(engine)  # guarded: no error, the row survives
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM monthly_contracts")).scalar() == 1
    finally:
        engine.dispose()
        os.remove(path)
