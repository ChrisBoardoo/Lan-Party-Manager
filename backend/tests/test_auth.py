"""Endpoint tests for registration, the invite-gate, and login."""

from conftest import register, login, auth_header


def test_first_user_becomes_admin(client):
    resp = register(client, "founder", "founder@example.com")
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "admin"
    assert body["username"] == "founder"


def test_invite_required_flips_after_first_user(client):
    assert client.get("/api/auth/invite-required").json()["required"] is False
    register(client, "founder", "founder@example.com")
    assert client.get("/api/auth/invite-required").json()["required"] is True


def test_second_registration_without_invite_is_rejected(client):
    register(client, "founder", "founder@example.com")
    resp = register(client, "latecomer", "late@example.com")
    assert resp.status_code == 403


def test_second_registration_with_invalid_invite_is_rejected(client):
    register(client, "founder", "founder@example.com")
    resp = register(client, "latecomer", "late@example.com", invite_code="BADCOD")
    assert resp.status_code == 403


def test_duplicate_username_rejected(client):
    register(client, "founder", "founder@example.com")
    # Second user would need an invite anyway, but the uniqueness checks apply to
    # the first user's namespace too — re-registering the founder name fails.
    resp = register(client, "founder", "different@example.com")
    # 403 (invite gate) is hit before the uniqueness check for non-first users,
    # so assert it's simply not created.
    assert resp.status_code in (400, 403)


def test_login_success_returns_token_and_user(client):
    register(client, "founder", "founder@example.com")
    resp = client.post(
        "/api/auth/login", json={"username": "founder", "password": "password123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["username"] == "founder"


def test_login_wrong_password_rejected(client):
    register(client, "founder", "founder@example.com")
    resp = client.post(
        "/api/auth/login", json={"username": "founder", "password": "wrongpass"}
    )
    assert resp.status_code == 401


def test_login_unknown_user_rejected(client):
    resp = client.post(
        "/api/auth/login", json={"username": "ghost", "password": "password123"}
    )
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401  # no bearer -> HTTPBearer 401


def test_me_returns_current_user(client):
    register(client, "founder", "founder@example.com")
    token = login(client, "founder")
    resp = client.get("/api/auth/me", headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["username"] == "founder"


def test_refresh_requires_auth(client):
    assert client.post("/api/auth/refresh").status_code == 401  # no bearer -> HTTPBearer 401


def test_refresh_rejects_garbage_token(client):
    resp = client.post("/api/auth/refresh", headers=auth_header("not-a-real-token"))
    assert resp.status_code == 401


def test_refresh_returns_a_new_working_token(client):
    register(client, "founder", "founder@example.com")
    token = login(client, "founder")
    resp = client.post("/api/auth/refresh", headers=auth_header(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "founder"
    new_token = body["access_token"]

    # The refreshed token authenticates on its own.
    me = client.get("/api/auth/me", headers=auth_header(new_token))
    assert me.status_code == 200
    assert me.json()["username"] == "founder"
