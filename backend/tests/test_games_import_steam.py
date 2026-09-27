"""Tests for importing a linked Steam account's owned games into the library —
POST /api/games/me/import-steam."""

import pytest

import database
import models
import oauth_steam
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


def _enable_steam(client, admin):
    client.put("/api/settings/steam_link_enabled", json={"value": "true"}, headers=auth_header(admin)).raise_for_status()
    client.put("/api/settings/steam_web_api_key", json={"value": "test-key"}, headers=auth_header(admin)).raise_for_status()


def _link_steam(username: str, steam_id: str = "76561198000000001"):
    s = database.SessionLocal()
    try:
        u = s.query(models.User).filter_by(username=username).first()
        u.steam_id = steam_id
        s.commit()
    finally:
        s.close()


def test_requires_games_feature_enabled(client, admin):
    member = _member(client)
    assert client.post("/api/games/me/import-steam", headers=auth_header(member)).status_code == 404


def test_requires_linked_steam_account(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    resp = client.post("/api/games/me/import-steam", headers=auth_header(member))
    assert resp.status_code == 400


def test_requires_steam_link_configured(client, admin):
    _enable_games(client, admin)
    member = _member(client)
    _link_steam("member")
    # games_enabled is on, but steam_link_enabled/steam_web_api_key are not set.
    resp = client.post("/api/games/me/import-steam", headers=auth_header(member))
    assert resp.status_code == 404


def test_private_steam_library_returns_games_visible_false(client, admin, monkeypatch):
    _enable_games(client, admin)
    _enable_steam(client, admin)
    member = _member(client)
    _link_steam("member")
    monkeypatch.setattr(oauth_steam, "fetch_owned_games", lambda steam_id, api_key: None)

    resp = client.post("/api/games/me/import-steam", headers=auth_header(member))
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"games_visible": False, "imported": 0, "already_owned": 0, "added_custom": 0}


def test_import_matches_catalog_and_creates_custom_games(client, admin, monkeypatch):
    _enable_games(client, admin)
    _enable_steam(client, admin)
    member = _member(client)
    _link_steam("member")

    # Seed one catalog game (as if from the langames.md seed) that Steam also reports owning.
    client.post("/api/games/me/library", json={"name": "Overwatch 2"}, headers=auth_header(admin)).raise_for_status()

    monkeypatch.setattr(oauth_steam, "fetch_owned_games", lambda steam_id, api_key: [
        {"appid": 1, "name": "Overwatch 2"},          # matches existing catalog entry (case/exact match)
        {"appid": 2, "name": "overwatch 2"},          # case-insensitive dup of the above within the same import
        {"appid": 3, "name": "Some Obscure Indie Game"},  # not in catalog -> custom
    ])

    resp = client.post("/api/games/me/import-steam", headers=auth_header(member))
    assert resp.status_code == 200
    body = resp.json()
    assert body["games_visible"] is True
    assert body["imported"] == 2   # Overwatch 2 once, the obscure indie game once
    assert body["already_owned"] == 1  # the case-insensitive duplicate within the same Steam list
    assert body["added_custom"] == 1  # only the obscure indie game creates a new catalog row

    me = client.get("/api/games/me", headers=auth_header(member)).json()
    names = {g["name"] for g in me["library"]}
    assert names == {"Overwatch 2", "Some Obscure Indie Game"}


def test_import_skips_games_already_in_library(client, admin, monkeypatch):
    _enable_games(client, admin)
    _enable_steam(client, admin)
    member = _member(client)
    _link_steam("member")
    client.post("/api/games/me/library", json={"name": "Terraria"}, headers=auth_header(member)).raise_for_status()

    monkeypatch.setattr(oauth_steam, "fetch_owned_games", lambda steam_id, api_key: [
        {"appid": 1, "name": "Terraria"},
    ])

    resp = client.post("/api/games/me/import-steam", headers=auth_header(member))
    body = resp.json()
    assert body["imported"] == 0
    assert body["already_owned"] == 1

    me = client.get("/api/games/me", headers=auth_header(member)).json()
    assert len(me["library"]) == 1  # not duplicated


def test_import_does_not_overwrite_existing_max_players_override(client, admin, monkeypatch):
    _enable_games(client, admin)
    _enable_steam(client, admin)
    member = _member(client)
    _link_steam("member")
    client.post("/api/games/me/library", json={"name": "Chess", "max_players_override": 2},
                headers=auth_header(member)).raise_for_status()

    monkeypatch.setattr(oauth_steam, "fetch_owned_games", lambda steam_id, api_key: [
        {"appid": 1, "name": "Chess"},
    ])

    client.post("/api/games/me/import-steam", headers=auth_header(member))
    me = client.get("/api/games/me", headers=auth_header(member)).json()
    chess = next(g for g in me["library"] if g["name"] == "Chess")
    assert chess["max_players"] == 2


def test_steam_fetch_failure_returns_502(client, admin, monkeypatch):
    _enable_games(client, admin)
    _enable_steam(client, admin)
    member = _member(client)
    _link_steam("member")

    def _boom(steam_id, api_key):
        raise oauth_steam.SteamOAuthError("network down")
    monkeypatch.setattr(oauth_steam, "fetch_owned_games", _boom)

    resp = client.post("/api/games/me/import-steam", headers=auth_header(member))
    assert resp.status_code == 502
