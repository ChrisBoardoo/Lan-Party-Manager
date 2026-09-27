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

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import models  # noqa: E402
from limiter import limiter  # noqa: E402

# Rate limiting would make repeated register/login calls flaky (429s), so turn
# it off for the whole suite — the limiter itself isn't what we're testing.
limiter.enabled = False


@pytest.fixture(autouse=True)
def fresh_db():
    """Drop and recreate every table before each test for full isolation.

    Uploaded files are cleared alongside the rows that referenced them —
    otherwise a test asserting on the contents of UPLOAD_DIR sees whatever an
    earlier test happened to leave there.
    """
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)
    shutil.rmtree(_upload_dir, ignore_errors=True)
    os.makedirs(_upload_dir, exist_ok=True)
    yield
    models.Base.metadata.drop_all(bind=database.engine)


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
