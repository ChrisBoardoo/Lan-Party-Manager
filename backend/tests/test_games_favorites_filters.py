"""Library favorites (the star) and the saved filter bar — /api/games/me/*."""
import pytest

import database
import models
from conftest import register, login, auth_header, make_user


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


def _member(client, username="member"):
    make_user(username, role="user")
    return login(client, username)


def _enable_games(client, admin):
    client.put("/api/settings/games_enabled", json={"value": "true"}, headers=auth_header(admin)).raise_for_status()


def _add(client, token, name, max_players=None):
    r = client.post("/api/games/me/library", json={"name": name, "max_players_override": max_players},
                    headers=auth_header(token))
    r.raise_for_status()
    return r.json()["game_id"]


def _star(client, token, game_id, value=True):
    return client.put(f"/api/games/me/library/{game_id}/favorite", json={"is_favorite": value},
                      headers=auth_header(token))


# ── Favorites ─────────────────────────────────────────────────────────────────

def test_new_library_game_is_not_a_favorite(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    _add(client, member, "Terraria")
    assert client.get("/api/games/me", headers=auth_header(member)).json()["library"][0]["is_favorite"] is False


def test_star_and_unstar(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    game_id = _add(client, member, "League of Legends")

    r = _star(client, member, game_id)
    assert r.status_code == 200
    assert r.json()["is_favorite"] is True
    assert client.get("/api/games/me", headers=auth_header(member)).json()["library"][0]["is_favorite"] is True

    assert _star(client, member, game_id, False).json()["is_favorite"] is False
    assert client.get("/api/games/me", headers=auth_header(member)).json()["library"][0]["is_favorite"] is False


def test_star_keeps_the_player_count(client, admin):
    """The reason the star has its own route: PUT /me/library/{id} always
    writes max_players_override, so toggling through it would wipe it."""
    _enable_games(client, admin)
    member = _member(client)
    game_id = _add(client, member, "Factorio", max_players=6)
    assert _star(client, member, game_id).json()["max_players"] == 6


def test_editing_the_player_count_keeps_the_star(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    game_id = _add(client, member, "Factorio", max_players=6)
    _star(client, member, game_id).raise_for_status()
    r = client.put(f"/api/games/me/library/{game_id}", json={"max_players_override": 3}, headers=auth_header(member))
    assert r.json()["is_favorite"] is True


def test_re_adding_a_game_keeps_the_star(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    game_id = _add(client, member, "Terraria")
    _star(client, member, game_id).raise_for_status()
    _add(client, member, "terraria", max_players=8)
    assert client.get("/api/games/me", headers=auth_header(member)).json()["library"][0]["is_favorite"] is True


def test_star_a_game_not_in_my_library_is_404(client, admin):
    _enable_games(client, admin)
    alice = _member(client, "alice")
    bob = _member(client, "bob")
    game_id = _add(client, alice, "Terraria")
    assert _star(client, bob, game_id).status_code == 404


def test_favorites_are_private_to_their_owner(client, admin):
    """Another member's star never leaks through the finder."""
    _enable_games(client, admin)
    alice = _member(client, "alice")
    bob = _member(client, "bob")
    game_id = _add(client, alice, "Terraria")
    _add(client, bob, "Terraria")
    _star(client, alice, game_id).raise_for_status()

    matches = client.get("/api/games/matches", headers=auth_header(bob)).json()
    assert matches[0]["username"] == "alice"
    assert matches[0]["shared_games"][0]["is_favorite"] is False

    ids = {u["username"]: u["id"] for u in client.get("/api/users/", headers=auth_header(admin)).json()}
    session = client.post("/api/games/session", json={"user_ids": [ids["alice"], ids["bob"]]},
                          headers=auth_header(bob)).json()
    assert [g["is_favorite"] for g in session["games"]] == [False]


def test_favorite_route_is_feature_gated(client, admin):
    member = _member(client)
    assert _star(client, member, 1).status_code == 404


# ── Saved filters ─────────────────────────────────────────────────────────────

DEFAULT_FILTERS = {"sort": None, "min_players": None, "max_players": None,
                   "playable_only": False, "favorites_only": False}


def test_filters_default_when_never_saved(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    assert client.get("/api/games/me", headers=auth_header(member)).json()["filters"] == DEFAULT_FILTERS


def test_filters_round_trip(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    filters = {"sort": "desc", "min_players": 4, "max_players": 10,
               "playable_only": True, "favorites_only": True}

    r = client.put("/api/games/me/filters", json=filters, headers=auth_header(member))
    assert r.status_code == 200
    assert r.json() == filters
    assert client.get("/api/games/me", headers=auth_header(member)).json()["filters"] == filters


def test_filters_are_per_member(client, admin):
    _enable_games(client, admin)
    alice = _member(client, "alice")
    bob = _member(client, "bob")
    client.put("/api/games/me/filters", json={"favorites_only": True}, headers=auth_header(alice)).raise_for_status()
    assert client.get("/api/games/me", headers=auth_header(bob)).json()["filters"] == DEFAULT_FILTERS


def test_partial_filters_fill_in_the_defaults(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    r = client.put("/api/games/me/filters", json={"sort": "asc"}, headers=auth_header(member))
    assert r.json() == {**DEFAULT_FILTERS, "sort": "asc"}


@pytest.mark.parametrize("bad", [
    {"sort": "sideways"},
    {"min_players": 0},
    {"max_players": 1000},
    {"playable_only": "maybe"},
])
def test_invalid_filters_are_rejected(client, admin, bad):
    _enable_games(client, admin)
    member = _member(client)
    assert client.put("/api/games/me/filters", json=bad, headers=auth_header(member)).status_code == 422


def test_unreadable_stored_filters_fall_back_to_defaults(client, admin):
    """A stored value that no longer validates (hand-edited, or a shape from
    another version) must not take the profile page down."""
    _enable_games(client, admin)
    member = _member(client)
    s = database.SessionLocal()
    try:
        user = s.query(models.User).filter(models.User.username == "member").first()
        user.games_library_filters = '{"sort": "sideways"'
        s.commit()
    finally:
        s.close()
    r = client.get("/api/games/me", headers=auth_header(member))
    assert r.status_code == 200
    assert r.json()["filters"] == DEFAULT_FILTERS


def test_filters_route_is_feature_gated(client, admin):
    member = _member(client)
    assert client.put("/api/games/me/filters", json={}, headers=auth_header(member)).status_code == 404
