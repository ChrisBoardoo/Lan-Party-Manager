"""Tests for the game library / wishlist / finder — /api/games."""
import pytest

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


def test_feature_gate(client, admin):
    member = _member(client)
    assert client.get("/api/games/catalog", headers=auth_header(member)).status_code == 404
    assert client.get("/api/games/catalog", headers=auth_header(admin)).status_code == 200
    _enable_games(client, admin)
    assert client.get("/api/games/catalog", headers=auth_header(member)).status_code == 200


def test_add_custom_game_to_library_and_wishlist(client, admin):
    _enable_games(client, admin)
    member = _member(client)

    r = client.post("/api/games/me/library", json={"name": "Lethal Company", "max_players_override": 4},
                     headers=auth_header(member))
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Lethal Company"
    assert body["max_players"] == 4
    assert body["is_custom"] is True

    r = client.post("/api/games/me/wishlist", json={"name": "Balatro"}, headers=auth_header(member))
    assert r.status_code == 201
    assert r.json()["name"] == "Balatro"

    me = client.get("/api/games/me", headers=auth_header(member)).json()
    assert [g["name"] for g in me["library"]] == ["Lethal Company"]
    assert [g["name"] for g in me["wishlist"]] == ["Balatro"]

    # The custom game now shows up in the shared catalog for autocomplete.
    catalog = client.get("/api/games/catalog", headers=auth_header(member)).json()
    assert any(g["name"] == "Lethal Company" and g["is_custom"] for g in catalog)


def test_custom_game_dedupes_case_insensitively(client, admin):
    _enable_games(client, admin)
    alice = _member(client, "alice")
    bob = _member(client, "bob")

    client.post("/api/games/me/library", json={"name": "Overwatch 2"}, headers=auth_header(alice)).raise_for_status()
    r = client.post("/api/games/me/library", json={"name": "overwatch 2"}, headers=auth_header(bob))
    assert r.status_code == 201

    catalog = client.get("/api/games/catalog", headers=auth_header(alice)).json()
    assert sum(1 for g in catalog if g["name"].lower() == "overwatch 2") == 1


def test_remove_from_library_and_wishlist(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    game_id = client.post("/api/games/me/library", json={"name": "Terraria"},
                           headers=auth_header(member)).json()["game_id"]
    assert client.delete(f"/api/games/me/library/{game_id}", headers=auth_header(member)).status_code == 200
    assert client.get("/api/games/me", headers=auth_header(member)).json()["library"] == []


def test_update_library_max_players_override(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    game_id = client.post("/api/games/me/library", json={"name": "Factorio", "max_players_override": 8},
                           headers=auth_header(member)).json()["game_id"]
    r = client.put(f"/api/games/me/library/{game_id}", json={"max_players_override": 3}, headers=auth_header(member))
    assert r.status_code == 200
    assert r.json()["max_players"] == 3


def test_matches_ranks_by_shared_game_count(client, admin):
    _enable_games(client, admin)
    alice = _member(client, "alice")
    bob = _member(client, "bob")
    carol = _member(client, "carol")

    for token in (alice, bob):
        client.post("/api/games/me/library", json={"name": "Terraria"}, headers=auth_header(token)).raise_for_status()
        client.post("/api/games/me/library", json={"name": "Factorio"}, headers=auth_header(token)).raise_for_status()
    client.post("/api/games/me/library", json={"name": "Terraria"}, headers=auth_header(carol)).raise_for_status()

    matches = client.get("/api/games/matches", headers=auth_header(alice)).json()
    by_user = {m["username"]: m for m in matches}
    assert by_user["bob"]["shared_count"] == 2
    assert by_user["carol"]["shared_count"] == 1
    # Bob (2 shared) ranks above Carol (1 shared).
    assert [m["username"] for m in matches] == ["bob", "carol"]


def test_session_builder_intersects_libraries_and_filters_by_player_count(client, admin):
    _enable_games(client, admin)
    alice = _member(client, "alice")
    bob = _member(client, "bob")
    alice_id = client.get("/api/users/", headers=auth_header(admin)).json()
    ids = {u["username"]: u["id"] for u in alice_id}

    # Both own a 4-max game and a 2-max game; only alice owns a solo game.
    client.post("/api/games/me/library", json={"name": "Overcooked", "max_players_override": 4},
                headers=auth_header(alice)).raise_for_status()
    client.post("/api/games/me/library", json={"name": "Overcooked", "max_players_override": 4},
                headers=auth_header(bob)).raise_for_status()
    client.post("/api/games/me/library", json={"name": "Chess", "max_players_override": 2},
                headers=auth_header(alice)).raise_for_status()
    client.post("/api/games/me/library", json={"name": "Chess", "max_players_override": 2},
                headers=auth_header(bob)).raise_for_status()
    client.post("/api/games/me/library", json={"name": "Solitaire", "max_players_override": 1},
                headers=auth_header(alice)).raise_for_status()

    r = client.post("/api/games/session", json={"user_ids": [ids["alice"], ids["bob"]]},
                     headers=auth_header(alice))
    assert r.status_code == 200
    names = {g["name"] for g in r.json()["games"]}
    # Solitaire is owned by only one of them, and Chess maxes at 2 < group size 2? group is 2 so Chess (2) qualifies.
    assert names == {"Overcooked", "Chess"}

    # Raising min_players above what Chess supports drops it.
    r = client.post("/api/games/session", json={"user_ids": [ids["alice"], ids["bob"]], "min_players": 3},
                     headers=auth_header(alice))
    assert {g["name"] for g in r.json()["games"]} == {"Overcooked"}


def test_public_config_exposes_games_flag(client, admin):
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["games_enabled"] is False
    _enable_games(client, admin)
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["games_enabled"] is True
