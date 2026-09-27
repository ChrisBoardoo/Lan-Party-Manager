"""Regression tests for email case-insensitivity (1.10 bug fix).

Registration used to store the raw email casing and check uniqueness with an
exact match, while login/Discord matched case-insensitively — so "Bob@x.com" and
"bob@x.com" could both register, and forgot-password missed on a case mismatch.
"""
from datetime import date, timedelta

from conftest import register, login, auth_header


def test_email_normalized_to_lowercase(client):
    r = register(client, "founder", "Founder@Example.COM")
    assert r.status_code == 201
    assert r.json()["email"] == "founder@example.com"


def test_login_works_with_any_email_casing(client):
    register(client, "founder", "founder@example.com")
    # Log in via the email in a different case than typed at registration.
    resp = client.post("/api/auth/login", json={"username": "FOUNDER@EXAMPLE.com", "password": "password123"})
    assert resp.status_code == 200


def test_forgot_password_case_insensitive_no_error(client):
    register(client, "founder", "founder@example.com")
    resp = client.post("/api/auth/forgot-password", json={"email": "FOUNDER@EXAMPLE.COM"})
    assert resp.status_code == 200  # generic response, but must resolve the user without erroring


def test_duplicate_email_differing_only_by_case_rejected(client):
    # First user (admin, no invite needed).
    admin = login(client, "founder") if register(client, "founder", "founder@example.com").status_code == 201 else None
    admin = login(client, "founder")

    # An event + invite code so a second registration is allowed to proceed to
    # the uniqueness check.
    start = (date.today() + timedelta(days=2)).isoformat()
    end = (date.today() + timedelta(days=4)).isoformat()
    ev = client.post("/api/events/", json={"title": "LAN", "start_date": start, "end_date": end}, headers=auth_header(admin)).json()
    code = client.post(f"/api/events/{ev['id']}/invite", headers=auth_header(admin)).json()["code"]

    # Same email as the admin, different case → rejected as already registered.
    r = register(client, "intruder", "FOUNDER@example.com", invite_code=code,
                 arrival_date=start, departure_date=end)
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"].lower()
