"""Tests for the groceries ("courses") list — /api/groceries."""
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


def _enable_groceries(client, admin):
    client.put("/api/settings/groceries_enabled", json={"value": "true"}, headers=auth_header(admin)).raise_for_status()


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
    assert client.get(f"/api/groceries/events/{ev}", headers=auth_header(member)).status_code == 404
    assert client.get(f"/api/groceries/events/{ev}", headers=auth_header(admin)).status_code == 200
    _enable_groceries(client, admin)
    assert client.get(f"/api/groceries/events/{ev}", headers=auth_header(member)).status_code == 200


def test_member_adds_item_and_counts(client, admin):
    _enable_groceries(client, admin)
    member = _member(client)
    ev = _make_event(client, admin)
    r = client.post(
        f"/api/groceries/events/{ev}/items",
        json={"category": "Snacks", "name": "Chips", "quantity": "2 bags"},
        headers=auth_header(member),
    )
    assert r.status_code == 201
    assert r.json()["assigned_to"] is None
    assert r.json()["is_bought"] is False

    payload = client.get(f"/api/groceries/events/{ev}", headers=auth_header(member)).json()
    assert payload["total_count"] == 1
    assert payload["bought_count"] == 0
    assert payload["items"][0]["name"] == "Chips"


def test_assign_another_attendee(client, admin):
    _enable_groceries(client, admin)
    member = _member(client)
    other_id = make_user("other", role="user")
    ev = _make_event(client, admin)

    r = client.post(
        f"/api/groceries/events/{ev}/items",
        json={"name": "Soda", "assigned_to": other_id},
        headers=auth_header(member),
    )
    assert r.status_code == 201
    assert r.json()["assigned_to"] == other_id
    assert r.json()["assigned_username"] == "other"

    # Assigning to a user that doesn't exist is rejected.
    bad = client.post(
        f"/api/groceries/events/{ev}/items",
        json={"name": "Chips", "assigned_to": 999999},
        headers=auth_header(member),
    )
    assert bad.status_code == 400


def test_toggle_bought(client, admin):
    _enable_groceries(client, admin)
    member = _member(client)
    ev = _make_event(client, admin)
    item_id = client.post(
        f"/api/groceries/events/{ev}/items", json={"name": "Beer"}, headers=auth_header(member)
    ).json()["id"]

    r = client.put(f"/api/groceries/items/{item_id}", json={"is_bought": True}, headers=auth_header(member))
    assert r.status_code == 200
    assert r.json()["is_bought"] is True

    payload = client.get(f"/api/groceries/events/{ev}", headers=auth_header(member)).json()
    assert payload["bought_count"] == 1


def test_edit_and_delete_permissions(client, admin):
    _enable_groceries(client, admin)
    member = _member(client)
    other = _member(client, "other")
    ev = _make_event(client, admin)
    item_id = client.post(
        f"/api/groceries/events/{ev}/items", json={"name": "Pizza"}, headers=auth_header(member)
    ).json()["id"]

    # A different member (not creator/assignee/admin) can't edit or delete it.
    assert client.put(f"/api/groceries/items/{item_id}", json={"quantity": "3"}, headers=auth_header(other)).status_code == 403
    assert client.delete(f"/api/groceries/items/{item_id}", headers=auth_header(other)).status_code == 403
    # The creator can edit it, and an admin can delete it.
    assert client.put(f"/api/groceries/items/{item_id}", json={"quantity": "3"}, headers=auth_header(member)).status_code == 200
    assert client.delete(f"/api/groceries/items/{item_id}", headers=auth_header(admin)).status_code == 200


def test_no_price_field_in_schema(client, admin):
    _enable_groceries(client, admin)
    member = _member(client)
    ev = _make_event(client, admin)
    r = client.post(f"/api/groceries/events/{ev}/items", json={"name": "Buns", "price": 12}, headers=auth_header(member))
    assert r.status_code == 201
    assert "price" not in r.json()


def test_import_bulk_adds_and_matches_usernames(client, admin):
    _enable_groceries(client, admin)
    member = _member(client)
    make_user("other", role="user")
    ev = _make_event(client, admin)

    body = {
        "items": [
            {"category": "Snacks", "name": "Chips", "quantity": "2", "assigned_username": "other"},
            {"category": "Boissons", "name": "Soda", "assigned_username": "OTHER"},  # case-insensitive
            {"name": "Pizza"},  # no assignee
            {"name": "Ghost item", "assigned_username": "nobody-such-user"},
        ]
    }
    r = client.post(f"/api/groceries/events/{ev}/import", json=body, headers=auth_header(member))
    assert r.status_code == 200
    result = r.json()
    assert result["imported"] == 4
    assert result["unmatched_usernames"] == ["nobody-such-user"]

    payload = client.get(f"/api/groceries/events/{ev}", headers=auth_header(member)).json()
    assert payload["total_count"] == 4
    names = {i["name"]: i for i in payload["items"]}
    assert names["Chips"]["assigned_username"] == "other"
    assert names["Soda"]["assigned_username"] == "other"
    assert names["Pizza"]["assigned_to"] is None
    assert names["Ghost item"]["assigned_to"] is None


def test_import_respects_feature_gate(client, admin):
    member = _member(client)
    ev = _make_event(client, admin)
    body = {"items": [{"name": "Chips"}]}
    assert client.post(f"/api/groceries/events/{ev}/import", json=body, headers=auth_header(member)).status_code == 404


def test_public_config_exposes_groceries_flag(client, admin):
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["groceries_enabled"] is False
    _enable_groceries(client, admin)
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["groceries_enabled"] is True
