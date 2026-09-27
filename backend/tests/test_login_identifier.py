"""Login by nickname *or* email, and the '@'-in-username guard.

The `login` conftest helper still posts `{"username": ...}`, so the existing
test_auth.py suite already covers the back-compat alias. These tests cover the
new behaviour: email login, case-insensitivity, the `identifier` field key, and
rejecting '@' in a username at registration."""

from conftest import register


def test_login_with_identifier_field_by_username(client):
    register(client, "founder", "founder@example.com")
    resp = client.post(
        "/api/auth/login", json={"identifier": "founder", "password": "password123"}
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == "founder"


def test_login_by_email(client):
    register(client, "founder", "founder@example.com")
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "founder@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == "founder"


def test_login_by_email_is_case_insensitive(client):
    register(client, "founder", "founder@example.com")
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "FOUNDER@Example.COM", "password": "password123"},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == "founder"


def test_login_by_email_wrong_password_rejected(client):
    register(client, "founder", "founder@example.com")
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "founder@example.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401


def test_login_unknown_email_rejected(client):
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "ghost@example.com", "password": "password123"},
    )
    assert resp.status_code == 401


def test_backcompat_username_field_still_accepted(client):
    register(client, "founder", "founder@example.com")
    resp = client.post(
        "/api/auth/login", json={"username": "founder", "password": "password123"}
    )
    assert resp.status_code == 200


def test_register_rejects_at_sign_in_username(client):
    resp = register(client, "foo@bar", "foo@example.com")
    assert resp.status_code == 422  # pydantic validation error


def test_register_rejects_whitespace_in_username(client):
    resp = register(client, "foo bar", "foobar@example.com")
    assert resp.status_code == 422
