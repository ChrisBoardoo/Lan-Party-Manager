"""Phase 1 access-control tests: email privacy + feature-flag enforcement."""

import pytest

from conftest import register, login, auth_header, make_user


@pytest.fixture
def founder_token(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


@pytest.fixture
def founder_id(client, founder_token):
    return client.get("/api/auth/me", headers=auth_header(founder_token)).json()["id"]


# ── Email privacy ──────────────────────────────────────────────────────────

def test_self_sees_own_email(client, founder_token):
    bob_id = make_user("bob")
    bob_token = login(client, "bob")
    resp = client.get(f"/api/users/{bob_id}", headers=auth_header(bob_token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "bob@example.com"


def test_admin_sees_others_email(client, founder_token):
    bob_id = make_user("bob")
    resp = client.get(f"/api/users/{bob_id}", headers=auth_header(founder_token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "bob@example.com"


def test_non_admin_cannot_see_others_email(client, founder_token, founder_id):
    make_user("bob")
    bob_token = login(client, "bob")
    resp = client.get(f"/api/users/{founder_id}", headers=auth_header(bob_token))
    assert resp.status_code == 200
    assert "email" not in resp.json()  # UserPublic — no email leaked


def test_roster_never_includes_email(client, founder_token):
    make_user("bob")
    bob_token = login(client, "bob")
    resp = client.get("/api/users/", headers=auth_header(bob_token))
    assert resp.status_code == 200
    assert all("email" not in u for u in resp.json())


# ── Feature-flag enforcement ───────────────────────────────────────────────

def _set(client, token, key, value):
    client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(token))


def test_treasury_read_allowed_by_default(client, founder_token):
    make_user("bob")
    bob_token = login(client, "bob")
    assert client.get("/api/expenses/", headers=auth_header(bob_token)).status_code == 200


def test_treasury_read_blocked_for_member_when_disabled(client, founder_token):
    make_user("bob")
    bob_token = login(client, "bob")
    _set(client, founder_token, "prizes_enabled", "true")  # auto-hides treasury
    resp = client.get("/api/expenses/", headers=auth_header(bob_token))
    assert resp.status_code == 404


def test_admin_still_reads_disabled_feature(client, founder_token):
    _set(client, founder_token, "prizes_enabled", "true")  # treasury off
    # Admin retains access to manage/configure.
    assert client.get("/api/expenses/", headers=auth_header(founder_token)).status_code == 200


def test_sponsors_read_blocked_for_member_when_off(client, founder_token):
    make_user("bob")
    bob_token = login(client, "bob")
    # Sponsors default OFF.
    assert client.get("/api/sponsors/active", headers=auth_header(bob_token)).status_code == 404
    _set(client, founder_token, "sponsors_enabled", "true")
    assert client.get("/api/sponsors/active", headers=auth_header(bob_token)).status_code == 200


def test_streams_read_allowed_by_default(client, founder_token):
    make_user("bob")
    bob_token = login(client, "bob")
    # Live/streams default ON — not every LAN has a streamer, but most do.
    assert client.get("/api/streams/", headers=auth_header(bob_token)).status_code == 200


def test_streams_read_blocked_for_member_when_disabled(client, founder_token):
    make_user("bob")
    bob_token = login(client, "bob")
    _set(client, founder_token, "streams_enabled", "false")
    resp = client.get("/api/streams/", headers=auth_header(bob_token))
    assert resp.status_code == 404


def test_admin_still_reads_disabled_streams(client, founder_token):
    _set(client, founder_token, "streams_enabled", "false")
    assert client.get("/api/streams/", headers=auth_header(founder_token)).status_code == 200


def test_prizes_read_blocked_for_member_when_off(client, founder_token):
    make_user("bob")
    bob_token = login(client, "bob")
    resp = client.get("/api/prizes/?event_id=1", headers=auth_header(bob_token))
    assert resp.status_code == 404
