"""Tests for username changes via PUT /api/users/{id} (self or admin)."""

from conftest import register, login, auth_header, make_user


def _me(client, token):
    return client.get("/api/auth/me", headers=auth_header(token)).json()


def test_user_can_change_own_username(client):
    register(client, "founder", "founder@example.com")  # first user = admin
    bob_id = make_user("bob")
    bob = login(client, "bob")

    resp = client.put(f"/api/users/{bob_id}", json={"username": "bobby"}, headers=auth_header(bob))
    assert resp.status_code == 200
    assert resp.json()["username"] == "bobby"
    # New username is the live login identifier.
    assert login(client, "bobby") is not None


def test_admin_can_change_other_username(client):
    register(client, "founder", "founder@example.com")
    admin = login(client, "founder")
    bob_id = make_user("bob")

    resp = client.put(f"/api/users/{bob_id}", json={"username": "renamed"}, headers=auth_header(admin))
    assert resp.status_code == 200
    assert resp.json()["username"] == "renamed"


def test_duplicate_username_rejected(client):
    register(client, "founder", "founder@example.com")
    bob_id = make_user("bob")
    make_user("carol")
    bob = login(client, "bob")

    resp = client.put(f"/api/users/{bob_id}", json={"username": "carol"}, headers=auth_header(bob))
    assert resp.status_code == 400


def test_non_admin_cannot_change_other_username(client):
    register(client, "founder", "founder@example.com")
    bob_id = make_user("bob")
    make_user("carol")
    carol = login(client, "carol")

    resp = client.put(f"/api/users/{bob_id}", json={"username": "hijack"}, headers=auth_header(carol))
    assert resp.status_code == 403


def test_too_short_username_rejected(client):
    register(client, "founder", "founder@example.com")
    bob_id = make_user("bob")
    bob = login(client, "bob")

    # 2 chars -> fails pydantic min_length (422).
    resp = client.put(f"/api/users/{bob_id}", json={"username": "ab"}, headers=auth_header(bob))
    assert resp.status_code == 422

    # 3 chars but whitespace-padded down to <3 -> handled in-router (400).
    resp = client.put(f"/api/users/{bob_id}", json={"username": " a "}, headers=auth_header(bob))
    assert resp.status_code in (400, 422)
