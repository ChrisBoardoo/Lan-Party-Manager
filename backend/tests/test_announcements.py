"""Tests for Announcements / PA — /api/announcements."""

from datetime import datetime, timedelta

import pytest

from conftest import register, login, auth_header, make_user


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


def _member(client, username="member"):
    make_user(username, role="user")
    return login(client, username)


def test_admin_posts_and_everyone_sees(client, admin):
    member = _member(client)
    posted = client.post(
        "/api/announcements/",
        json={"message": "Pizza's here", "level": "info"},
        headers=auth_header(admin),
    )
    assert posted.status_code == 200
    assert posted.json()["message"] == "Pizza's here"

    feed = client.get("/api/announcements/", headers=auth_header(member)).json()
    assert [a["message"] for a in feed] == ["Pizza's here"]


def test_non_admin_cannot_post_or_delete(client, admin):
    member = _member(client)
    assert client.post(
        "/api/announcements/", json={"message": "hi"}, headers=auth_header(member)
    ).status_code == 403

    ann_id = client.post(
        "/api/announcements/", json={"message": "Finals in 5"}, headers=auth_header(admin)
    ).json()["id"]
    assert client.delete(f"/api/announcements/{ann_id}", headers=auth_header(member)).status_code == 403


def test_expired_announcements_are_hidden(client, admin):
    past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    future = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    client.post("/api/announcements/", json={"message": "old", "expires_at": past}, headers=auth_header(admin)).raise_for_status()
    client.post("/api/announcements/", json={"message": "current", "expires_at": future}, headers=auth_header(admin)).raise_for_status()
    client.post("/api/announcements/", json={"message": "forever"}, headers=auth_header(admin)).raise_for_status()

    messages = [a["message"] for a in client.get("/api/announcements/", headers=auth_header(admin)).json()]
    assert "current" in messages and "forever" in messages
    assert "old" not in messages


def test_admin_can_delete(client, admin):
    ann_id = client.post(
        "/api/announcements/", json={"message": "temp"}, headers=auth_header(admin)
    ).json()["id"]
    assert client.delete(f"/api/announcements/{ann_id}", headers=auth_header(admin)).status_code == 200
    assert client.get("/api/announcements/", headers=auth_header(admin)).json() == []


def test_invalid_level_rejected(client, admin):
    resp = client.post(
        "/api/announcements/", json={"message": "x", "level": "boom"}, headers=auth_header(admin)
    )
    assert resp.status_code == 400


def test_list_requires_auth(client):
    assert client.get("/api/announcements/").status_code in (401, 403)
