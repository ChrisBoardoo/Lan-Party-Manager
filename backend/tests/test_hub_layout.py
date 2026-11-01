"""The Hub's saved block arrangement — /api/users/me/hub-layout."""
import pytest

import database
import models
from conftest import register, login, auth_header, make_user

URL = "/api/users/me/hub-layout"

LAYOUT = {"blocks": [
    {"id": "stats", "zone": "full", "hidden": False},
    {"id": "activity", "zone": "main", "hidden": False},
    {"id": "roster", "zone": "side", "hidden": True},
]}


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


def _member(client, username="member"):
    make_user(username, role="user")
    return login(client, username)


def test_no_layout_until_one_is_saved(client, admin):
    member = _member(client)
    r = client.get(URL, headers=auth_header(member))
    assert r.status_code == 200
    assert r.json() == {"blocks": None}


def test_saved_layout_reads_back(client, admin):
    member = _member(client)
    r = client.put(URL, json=LAYOUT, headers=auth_header(member))
    assert r.status_code == 200
    assert r.json() == LAYOUT
    assert client.get(URL, headers=auth_header(member)).json() == LAYOUT


def test_hidden_defaults_to_false(client, admin):
    member = _member(client)
    r = client.put(URL, json={"blocks": [{"id": "stats", "zone": "full"}]}, headers=auth_header(member))
    assert r.json() == {"blocks": [{"id": "stats", "zone": "full", "hidden": False}]}


def test_layout_is_per_account(client, admin):
    """Saving mine changes neither the admin's nor anyone else's."""
    alice = _member(client, "alice")
    bob = _member(client, "bob")
    client.put(URL, json=LAYOUT, headers=auth_header(alice)).raise_for_status()
    assert client.get(URL, headers=auth_header(bob)).json() == {"blocks": None}
    assert client.get(URL, headers=auth_header(admin)).json() == {"blocks": None}


def test_reset_goes_back_to_default(client, admin):
    member = _member(client)
    client.put(URL, json=LAYOUT, headers=auth_header(member)).raise_for_status()
    r = client.delete(URL, headers=auth_header(member))
    assert r.status_code == 200
    assert r.json() == {"blocks": None}
    assert client.get(URL, headers=auth_header(member)).json() == {"blocks": None}


@pytest.mark.parametrize("bad", [
    {},
    {"blocks": [{"id": "stats", "zone": "middle"}]},
    {"blocks": [{"id": "Stats", "zone": "full"}]},
    {"blocks": [{"id": "stats-bar", "zone": "full"}]},
    {"blocks": [{"id": "x" * 33, "zone": "full"}]},
    {"blocks": [{"id": "stats", "zone": "full"}, {"id": "stats", "zone": "side"}]},
    {"blocks": [{"id": f"b{i}", "zone": "full"} for i in range(33)]},
    {"blocks": [{"id": "stats", "zone": "full", "hidden": "maybe"}]},
])
def test_invalid_layouts_are_rejected(client, admin, bad):
    member = _member(client)
    assert client.put(URL, json=bad, headers=auth_header(member)).status_code == 422
    assert client.get(URL, headers=auth_header(member)).json() == {"blocks": None}


def test_unreadable_stored_layout_falls_back_to_default(client, admin):
    """A stored value that no longer validates (hand-edited, or a shape from
    another version) must not take the Hub down."""
    member = _member(client)
    s = database.SessionLocal()
    try:
        user = s.query(models.User).filter(models.User.username == "member").first()
        user.hub_layout = '{"blocks": [{"id": "stats", "zone": "sideways"}]}'
        s.commit()
    finally:
        s.close()
    r = client.get(URL, headers=auth_header(member))
    assert r.status_code == 200
    assert r.json() == {"blocks": None}


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_requires_a_session(client, admin, method):
    kwargs = {"json": LAYOUT} if method == "put" else {}
    assert getattr(client, method)(URL, **kwargs).status_code == 401


def test_other_user_routes_still_resolve(client, admin):
    """/me/hub-layout is declared before /{user_id}: make sure a numeric id
    still reaches the user routes."""
    member_id = make_user("carol", role="user")
    token = login(client, "carol")
    assert client.get(f"/api/users/{member_id}", headers=auth_header(token)).status_code == 200
