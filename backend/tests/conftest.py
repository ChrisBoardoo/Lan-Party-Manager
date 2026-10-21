"""Shared pytest fixtures.

The app's SQLAlchemy engine is built from ``DATABASE_URL`` at import time
(see ``database.py``), ``uploads.py`` reads ``UPLOAD_DIR`` at import time, and
``auth.py`` refuses to import without ``SECRET_KEY``. All three env vars are
therefore set here — before any app module is imported — so the whole suite runs
against throwaway temp storage and never touches the real ``./data/lanparty.db``
or ``./uploads``.
"""

import os
import shutil
import tempfile

# --- Environment must be set BEFORE importing any app module ---------------
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
# Tests manage their schema directly via Base.metadata (see fresh_db), so the
# app's Alembic migration runner is disabled on import.
os.environ["SKIP_MIGRATIONS"] = "1"

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

# Without this, any test that uploads writes into the real ./uploads and leaves
# the files there. Nothing exercised an upload endpoint until My Setup, so the
# gap sat here unnoticed while DATABASE_URL got all the care.
_upload_dir = tempfile.mkdtemp(prefix="lpm-test-uploads-")
os.environ["UPLOAD_DIR"] = _upload_dir

import bcrypt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import models  # noqa: E402
import xp  # noqa: E402
from limiter import limiter  # noqa: E402

# Rate limiting would make repeated register/login calls flaky (429s), so turn
# it off for the whole suite — the limiter itself isn't what we're testing.
limiter.enabled = False

# bcrypt at its production cost (12 rounds, ~0.2 s a hash) made every
# register + login in the suite cost half a second: ~4 of the 16 minutes
# (Q-5 of the 2026-10-20 review). Four rounds under test; the format ($2b$)
# and the verification path are the same, see test_password_hashing.py.
_real_gensalt = bcrypt.gensalt
bcrypt.gensalt = lambda rounds=4, prefix=b"2b": _real_gensalt(4, prefix)

# The schema is built once; each test starts from empty tables. A drop_all +
# create_all of 52 tables on a file database cost 0.6 s per test — 8 of the 16
# minutes (Q-5) — where deleting their rows costs 20 ms.
models.Base.metadata.create_all(bind=database.engine)
_TABLES = list(reversed(models.Base.metadata.sorted_tables))


@pytest.fixture(autouse=True)
def fresh_db():
    """Empty every table before each test for full isolation (ids start from 1
    again: SQLite reuses them without AUTOINCREMENT, as drop/create did).

    Uploaded files are cleared alongside the rows that referenced them —
    otherwise a test asserting on the contents of UPLOAD_DIR sees whatever an
    earlier test happened to leave there.
    """
    with database.engine.begin() as conn:
        for table in _TABLES:
            conn.execute(table.delete())
    shutil.rmtree(_upload_dir, ignore_errors=True)
    os.makedirs(_upload_dir, exist_ok=True)
    # The XP ledger cache is a process-wide 30 s memo (xp.build_ledger): off
    # here, or a test would read the previous test's crew.
    xp.LEDGER_TTL_S = 0
    xp.invalidate_ledger()
    yield


@pytest.fixture
def db():
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    # Import lazily so the temp DB env vars above are already in effect.
    # Instantiated without a `with` block so FastAPI startup events (the
    # background scheduler) don't fire during tests.
    import main

    return TestClient(main.app)


def register(client, username, email, password="password123", **extra):
    """Helper: POST /api/auth/register and return the raw response."""
    payload = {"username": username, "email": email, "password": password}
    payload.update(extra)
    return client.post("/api/auth/register", json=payload)


def login(client, username, password="password123"):
    """Helper: POST /api/auth/login and return the bearer token string."""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def make_user(username, role="user", password="password123"):
    """Insert a user directly (bypassing the invite flow) and return its id.

    Uses a real hashed password so the test can then log in via the API.
    """
    from auth import get_password_hash

    session = database.SessionLocal()
    try:
        user = models.User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=get_password_hash(password),
            role=role,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id
    finally:
        session.close()


def run_concurrently(*fns):
    """Call each function in its own thread, all released at the same instant
    by a barrier, and return their results in order (an exception in one is
    re-raised here). For the double-click races: two requests that both pass
    their checks before either one writes."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    barrier = threading.Barrier(len(fns))

    def run(fn):
        barrier.wait()
        return fn()

    with ThreadPoolExecutor(max_workers=len(fns)) as pool:
        return [f.result() for f in [pool.submit(run, fn) for fn in fns]]


class count_queries:
    """`with count_queries() as q:` — q.n is the number of SQL statements the
    engine ran inside the block, whatever thread ran them (the TestClient's
    included). For the N+1 regressions: compare q.n for 2 and for 8 rows."""

    def __enter__(self):
        from sqlalchemy import event

        self.n = 0

        def before(*_args, **_kwargs):
            self.n += 1

        self._listener = before
        event.listen(database.engine, "before_cursor_execute", before)
        return self

    def __exit__(self, *exc):
        from sqlalchemy import event

        event.remove(database.engine, "before_cursor_execute", self._listener)
        return False
