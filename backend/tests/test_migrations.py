"""Guards against Alembic migration bugs that pytest's normal fixtures never
exercise — `conftest.fresh_db` builds the schema straight from `Base.metadata`
(see its docstring: "the app's Alembic migration runner is disabled"), so
until now nothing ever actually ran a single migration file.

That gap let a real bug ship: `0024_craving_chat_v2`'s original
`op.add_column("chat_messages", sa.Column("updated_at", ..., server_default=
sa.func.now()))` worked fine against the newer SQLite bundled with this
project's Windows dev venv (and would have on ubuntu-latest's CI runner too),
but raised `sqlite3.OperationalError: Cannot add a column with non-constant
default` in production, against the older SQLite bundled in the arm64
`python:3.11-slim` Docker image running on a Raspberry Pi 4. CREATE TABLE has
never had this restriction — only ALTER TABLE ADD COLUMN does — so a
same-host pytest run alone can't reliably catch it (it depends on which
SQLite build is on the machine running the test, not on Python/Alembic
version). The static scan below catches the exact pattern deterministically,
on any machine; the second test exercises `db_migrate.run_migrations()`'s own
adoption logic end-to-end, which had zero coverage before this file existed.

See alembic/versions/0024_craving_chat_v2.py's own comment for the full story
and the fix (a client-side ORM `default=`, not `server_default=`).
"""
import ast
import os
import sqlite3
import tempfile
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"

# Anything SQLite treats as a non-constant default for ADD COLUMN purposes.
# (A literal number/string/boolean, or NULL, is fine — CURRENT_* and any
# function call are not.)
NON_CONSTANT_DEFAULT_MARKERS = ("func.now", "CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME")


def _add_column_bad_defaults(source: str) -> list[str]:
    """Deliberately simple: a real parser for every way `server_default`
    could be spelled isn't worth it for a project this size. This catches the
    actual pattern that broke production; any future migration needing a
    timestamp column added after the fact should follow the fix's pattern
    (server_default=None + a client-side ORM default, or an explicit
    backfill UPDATE) rather than reinvent one."""
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        is_add_column = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_column"
        )
        if not is_add_column:
            continue
        for arg in node.args:
            is_column = (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Attribute)
                and arg.func.attr == "Column"
            )
            if not is_column:
                continue
            for kw in arg.keywords:
                if kw.arg != "server_default":
                    continue
                snippet = ast.unparse(kw.value)
                if any(marker in snippet for marker in NON_CONSTANT_DEFAULT_MARKERS):
                    offenders.append(f"line {node.lineno}: server_default={snippet}")
    return offenders


def test_no_add_column_uses_a_non_constant_server_default():
    bad: dict[str, list[str]] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        offenders = _add_column_bad_defaults(path.read_text(encoding="utf-8"))
        if offenders:
            bad[path.name] = offenders

    assert not bad, (
        "op.add_column(...) with a non-constant server_default (func.now() / "
        "CURRENT_TIMESTAMP) breaks on some SQLite builds — confirmed live on "
        "a Raspberry Pi 4's python:3.11-slim (arm64) image — even though it "
        "can silently pass on a newer dev/CI SQLite. CREATE TABLE is fine; "
        "only ALTER TABLE ADD COLUMN is affected. Fix: server_default=None, "
        "value supplied by a client-side ORM `default=` instead (see "
        "models.py's ChatMessage.updated_at), plus an explicit UPDATE "
        "backfill for existing rows if needed. Offending line(s):\n"
        + "\n".join(f"  {fname}: {o}" for fname, items in bad.items() for o in items)
    )


def test_run_migrations_is_clean_from_scratch_and_idempotent(monkeypatch):
    """Exercises db_migrate.run_migrations()'s actual adoption logic — the
    "brand-new DB" path (alembic upgrade head from nothing) — end to end,
    which conftest.fresh_db never touches. Also checks upgrading twice in a
    row is a no-op the second time, since that's exactly what happens on
    every container restart in production."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)  # run_migrations must create it from nothing
    try:
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
        monkeypatch.delenv("SKIP_MIGRATIONS", raising=False)

        # database.py / db_migrate.py read DATABASE_URL at import time, so a
        # fresh engine bound to the temp file is built here rather than
        # reusing the already-imported (and already-pointed-elsewhere) module.
        from sqlalchemy import create_engine, inspect
        import db_migrate

        db_migrate.engine = create_engine(f"sqlite:///{db_path}")
        db_migrate.run_migrations()
        db_migrate.run_migrations()  # must not raise the second time

        conn = sqlite3.connect(db_path)
        try:
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            assert version is not None
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert "chat_messages" in tables
            assert "chat_message_reactions" in tables
        finally:
            conn.close()

        engine_inspector = inspect(db_migrate.engine)
        chat_cols = {c["name"] for c in engine_inspector.get_columns("chat_messages")}
        assert {"reply_to_id", "updated_at", "edited_at"} <= chat_cols
    finally:
        try:
            os.remove(db_path)
        except OSError:
            pass
