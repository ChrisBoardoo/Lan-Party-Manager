"""Tests for the private event packing checklist — /api/checklist."""
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


def _enable_checklist(client, admin):
    client.put("/api/settings/checklist_enabled", json={"value": "true"}, headers=auth_header(admin)).raise_for_status()


def _make_event(client, admin, title="Summer LAN"):
    start = (date.today() + timedelta(days=2)).isoformat()
    end = (date.today() + timedelta(days=4)).isoformat()
    r = client.post("/api/events/", json={"title": title, "start_date": start, "end_date": end}, headers=auth_header(admin))
    r.raise_for_status()
    return r.json()["id"]


def test_feature_gate(client, admin):
    member = _member(client)
    ev = _make_event(client, admin)
    assert client.get(f"/api/checklist/events/{ev}", headers=auth_header(member)).status_code == 404
    assert client.get(f"/api/checklist/events/{ev}", headers=auth_header(admin)).status_code == 200
    _enable_checklist(client, admin)
    assert client.get(f"/api/checklist/events/{ev}", headers=auth_header(member)).status_code == 200


def test_get_returns_empty_shape_when_unsaved(client, admin):
    _enable_checklist(client, admin)
    member = _member(client)
    ev = _make_event(client, admin)
    payload = client.get(f"/api/checklist/events/{ev}", headers=auth_header(member)).json()
    assert payload["started"] is False
    assert payload["items"]["computer"] is False
    assert payload["custom_fields"] == []
    assert payload["progress_total"] == 9
    assert payload["progress_checked"] == 0


def test_save_fixed_items_and_custom_fields(client, admin):
    _enable_checklist(client, admin)
    member = _member(client)
    ev = _make_event(client, admin)
    body = {
        "items": {"computer": True, "screen": True},
        "custom_fields": [{"label": "Passport", "checked": True}, {"label": "Chair", "checked": False}],
    }
    r = client.put(f"/api/checklist/events/{ev}", json=body, headers=auth_header(member))
    assert r.status_code == 200
    payload = r.json()
    assert payload["started"] is True
    assert payload["items"]["computer"] is True
    assert payload["items"]["screen"] is True
    assert payload["items"]["backpack"] is False
    assert [f["label"] for f in payload["custom_fields"]] == ["Passport", "Chair"]
    assert payload["progress_checked"] == 3  # computer + screen + Passport
    assert payload["progress_total"] == 11   # 9 fixed + 2 custom

    # Re-saving replaces the custom fields wholesale rather than appending.
    body2 = {"items": {"computer": True}, "custom_fields": [{"label": "Snacks"}]}
    r2 = client.put(f"/api/checklist/events/{ev}", json=body2, headers=auth_header(member))
    payload2 = r2.json()
    assert [f["label"] for f in payload2["custom_fields"]] == ["Snacks"]
    assert payload2["items"]["screen"] is False  # whole-state replace, not a merge


def test_custom_field_cap(client, admin):
    _enable_checklist(client, admin)
    member = _member(client)
    ev = _make_event(client, admin)
    body = {"items": {}, "custom_fields": [{"label": f"Item {i}"} for i in range(11)]}
    r = client.put(f"/api/checklist/events/{ev}", json=body, headers=auth_header(member))
    assert r.status_code == 400


def test_checklist_is_private_to_owner(client, admin):
    _enable_checklist(client, admin)
    member = _member(client)
    other = _member(client, "other")
    ev = _make_event(client, admin)
    client.put(
        f"/api/checklist/events/{ev}",
        json={"items": {"computer": True}, "custom_fields": [{"label": "Secret item"}]},
        headers=auth_header(member),
    ).raise_for_status()

    # Another member's GET for the same event returns THEIR (empty) checklist,
    # never member's — there is no route that can name another user's row.
    other_view = client.get(f"/api/checklist/events/{ev}", headers=auth_header(other)).json()
    assert other_view["started"] is False
    assert other_view["custom_fields"] == []

    # Even an admin sees their own (empty) checklist, not member's.
    admin_view = client.get(f"/api/checklist/events/{ev}", headers=auth_header(admin)).json()
    assert admin_view["started"] is False


def test_suggestions_and_carryover(client, admin):
    _enable_checklist(client, admin)
    member = _member(client)
    ev1 = _make_event(client, admin, "LAN One")
    ev2 = _make_event(client, admin, "LAN Two")

    # No suggestion yet — nothing saved anywhere.
    assert client.get("/api/checklist/suggestions", headers=auth_header(member)).json() is None

    client.put(
        f"/api/checklist/events/{ev1}",
        json={"items": {"computer": True, "headset": True}, "custom_fields": [{"label": "Passport", "checked": True}]},
        headers=auth_header(member),
    ).raise_for_status()

    suggestion = client.get("/api/checklist/suggestions", headers=auth_header(member)).json()
    assert suggestion["source_event_id"] == ev1
    assert suggestion["source_event_title"] == "LAN One"
    assert suggestion["items"]["computer"] is True
    assert [f["label"] for f in suggestion["custom_fields"]] == ["Passport"]

    # Carrying over into ev2 merges the fixed items and appends the custom field.
    carried = client.post(f"/api/checklist/events/{ev2}/carryover", headers=auth_header(member)).json()
    assert carried["items"]["computer"] is True
    assert carried["items"]["headset"] is True
    assert [f["label"] for f in carried["custom_fields"]] == ["Passport"]

    # Idempotent: running it again doesn't duplicate the custom field.
    carried_again = client.post(f"/api/checklist/events/{ev2}/carryover", headers=auth_header(member)).json()
    assert [f["label"] for f in carried_again["custom_fields"]] == ["Passport"]


def test_carryover_skips_duplicate_labels_case_insensitively(client, admin):
    _enable_checklist(client, admin)
    member = _member(client)
    ev1 = _make_event(client, admin, "LAN One")
    ev2 = _make_event(client, admin, "LAN Two")
    client.put(
        f"/api/checklist/events/{ev1}",
        json={"items": {}, "custom_fields": [{"label": "Passport"}]},
        headers=auth_header(member),
    ).raise_for_status()
    client.put(
        f"/api/checklist/events/{ev2}",
        json={"items": {}, "custom_fields": [{"label": "passport", "checked": True}]},
        headers=auth_header(member),
    ).raise_for_status()

    carried = client.post(f"/api/checklist/events/{ev2}/carryover", headers=auth_header(member)).json()
    assert len(carried["custom_fields"]) == 1
    assert carried["custom_fields"][0]["checked"] is True  # existing row untouched


def test_public_config_exposes_checklist_flag(client, admin):
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["checklist_enabled"] is False
    _enable_checklist(client, admin)
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["checklist_enabled"] is True
