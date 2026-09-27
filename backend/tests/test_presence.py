"""Tests for the HUB presence heartbeat — /api/presence/ping + is_online."""

from datetime import datetime, timedelta

import database
import models
from conftest import register, login, auth_header


def _roster_me(client, token, username="founder"):
    roster = client.get("/api/users/", headers=auth_header(token)).json()
    return next(u for u in roster if u["username"] == username)


def test_ping_marks_user_online(client):
    register(client, "founder", "founder@example.com")
    token = login(client, "founder")

    # Before any ping: offline, no last_seen.
    me = _roster_me(client, token)
    assert me["is_online"] is False
    assert me["last_seen"] is None

    # Ping → online, last_seen set.
    assert client.post("/api/presence/ping", headers=auth_header(token)).status_code == 200
    me = _roster_me(client, token)
    assert me["is_online"] is True
    assert me["last_seen"] is not None


def test_ping_requires_auth(client):
    assert client.post("/api/presence/ping").status_code in (401, 403)


def test_stale_last_seen_reads_offline(client):
    register(client, "founder", "founder@example.com")
    token = login(client, "founder")
    client.post("/api/presence/ping", headers=auth_header(token)).raise_for_status()

    # Backdate the heartbeat beyond the online window.
    s = database.SessionLocal()
    try:
        u = s.query(models.User).filter(models.User.username == "founder").first()
        u.last_seen = datetime.utcnow() - timedelta(minutes=10)
        s.commit()
    finally:
        s.close()

    assert _roster_me(client, token)["is_online"] is False


def test_single_user_endpoint_includes_online(client):
    register(client, "founder", "founder@example.com")
    token = login(client, "founder")
    uid = client.get("/api/auth/me", headers=auth_header(token)).json()["id"]
    client.post("/api/presence/ping", headers=auth_header(token)).raise_for_status()

    u = client.get(f"/api/users/{uid}", headers=auth_header(token)).json()
    assert u["is_online"] is True
