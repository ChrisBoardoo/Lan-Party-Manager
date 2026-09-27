"""Tests for the BYO gear list — /api/gear."""
from datetime import date, timedelta

import pytest

from conftest import register, login, auth_header, make_user


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


def _member(client, username="member"):
    make_user(username, role="user")
    return login(client, username)


def _enable_gear(client, admin):
    client.put("/api/settings/gear_enabled", json={"value": "true"}, headers=auth_header(admin)).raise_for_status()


def _make_event(client, admin, title="Summer LAN"):
    start = (date.today() + timedelta(days=2)).isoformat()
    end = (date.today() + timedelta(days=4)).isoformat()
    r = client.post("/api/events/", json={"title": title, "start_date": start, "end_date": end}, headers=auth_header(admin))
    r.raise_for_status()
    return r.json()["id"]


def test_feature_gate(client, admin):
    member = _member(client)
    ev = _make_event(client, admin)
    # Disabled: member 404, admin passes through.
    assert client.get(f"/api/gear/events/{ev}", headers=auth_header(member)).status_code == 404
    assert client.get(f"/api/gear/events/{ev}", headers=auth_header(admin)).status_code == 200
    _enable_gear(client, admin)
    assert client.get(f"/api/gear/events/{ev}", headers=auth_header(member)).status_code == 200


def test_member_pledges_and_counts(client, admin):
    _enable_gear(client, admin)
    member = _member(client)
    ev = _make_event(client, admin)
    r = client.post(f"/api/gear/events/{ev}/items", json={"name": "5-port switch", "category": "network"}, headers=auth_header(member))
    assert r.status_code == 201
    assert r.json()["pledged_username"] == "member"

    payload = client.get(f"/api/gear/events/{ev}", headers=auth_header(member)).json()
    assert payload["pledged_count"] == 1
    assert payload["open_request_count"] == 0
    assert payload["items"][0]["name"] == "5-port switch"


def test_admin_request_claim_and_release(client, admin):
    _enable_gear(client, admin)
    member = _member(client)
    ev = _make_event(client, admin)
    req = client.post(f"/api/gear/events/{ev}/requests", json={"name": "4th monitor", "category": "display"}, headers=auth_header(admin))
    assert req.status_code == 201
    item_id = req.json()["id"]
    assert req.json()["is_request"] is True and req.json()["pledged_by"] is None

    payload = client.get(f"/api/gear/events/{ev}", headers=auth_header(member)).json()
    assert payload["open_request_count"] == 1

    claimed = client.post(f"/api/gear/items/{item_id}/claim", headers=auth_header(member))
    assert claimed.status_code == 200
    assert claimed.json()["pledged_username"] == "member"

    # Double-claim is a conflict.
    other = _member(client, "other")
    assert client.post(f"/api/gear/items/{item_id}/claim", headers=auth_header(other)).status_code == 409

    # Claimer releases it back to open.
    released = client.post(f"/api/gear/items/{item_id}/unclaim", headers=auth_header(member))
    assert released.status_code == 200 and released.json()["pledged_by"] is None


def test_member_requests_forbidden(client, admin):
    _enable_gear(client, admin)
    member = _member(client)
    ev = _make_event(client, admin)
    assert client.post(f"/api/gear/events/{ev}/requests", json={"name": "x"}, headers=auth_header(member)).status_code == 403


def test_gear_locker_dedupes_past_pledges(client, admin):
    _enable_gear(client, admin)
    member = _member(client)
    ev1 = _make_event(client, admin, "LAN One")
    ev2 = _make_event(client, admin, "LAN Two")
    for ev in (ev1, ev2):
        client.post(f"/api/gear/events/{ev}/items", json={"name": "Switch", "category": "network"}, headers=auth_header(member)).raise_for_status()
    client.post(f"/api/gear/events/{ev1}/items", json={"name": "HDMI cable"}, headers=auth_header(member)).raise_for_status()

    locker = client.get("/api/gear/suggestions", headers=auth_header(member)).json()
    names = {s["name"]: s for s in locker}
    assert set(names) == {"Switch", "HDMI cable"}          # deduped
    assert names["Switch"]["times_brought"] == 2            # counted across events


def test_carryover_is_idempotent(client, admin):
    _enable_gear(client, admin)
    member = _member(client)
    ev = _make_event(client, admin)
    body = {"items": [{"name": "Switch", "category": "network"}, {"name": "Beer fridge"}]}
    first = client.post(f"/api/gear/events/{ev}/carryover", json=body, headers=auth_header(member)).json()
    assert first["pledged_count"] == 2
    # Re-running the same carryover doesn't duplicate.
    second = client.post(f"/api/gear/events/{ev}/carryover", json=body, headers=auth_header(member)).json()
    assert second["pledged_count"] == 2


def test_edit_and_delete_permissions(client, admin):
    _enable_gear(client, admin)
    member = _member(client)
    other = _member(client, "other")
    ev = _make_event(client, admin)
    item_id = client.post(f"/api/gear/events/{ev}/items", json={"name": "Switch"}, headers=auth_header(member)).json()["id"]

    # A different member can't edit or delete it; the owner and admin can.
    assert client.put(f"/api/gear/items/{item_id}", json={"quantity": 2}, headers=auth_header(other)).status_code == 403
    assert client.put(f"/api/gear/items/{item_id}", json={"quantity": 2}, headers=auth_header(member)).status_code == 200
    assert client.delete(f"/api/gear/items/{item_id}", headers=auth_header(admin)).status_code == 200


def test_public_config_exposes_gear_flag(client, admin):
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["gear_enabled"] is False
    _enable_gear(client, admin)
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["gear_enabled"] is True
