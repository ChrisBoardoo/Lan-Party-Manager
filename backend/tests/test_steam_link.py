"""Steam link: config gate, signed state, and the callback flow (link-only —
no login/registration via Steam, see md/Steam_Link.md)."""

import pytest

import database
import models
import oauth_steam
from auth import create_access_token, get_password_hash
from conftest import register, auth_header


# ── helpers ────────────────────────────────────────────────────────────────────

def _set_settings(**kv):
    s = database.SessionLocal()
    try:
        for k, v in kv.items():
            row = s.query(models.AppSetting).filter_by(key=k).first()
            if row:
                row.value = v
            else:
                s.add(models.AppSetting(key=k, value=v))
        s.commit()
    finally:
        s.close()


def _enable_steam():
    _set_settings(
        steam_link_enabled="true",
        steam_web_api_key="test-api-key",
        app_base_url="https://lan.example",
    )


def _get_user(steam_id=None, username=None):
    s = database.SessionLocal()
    try:
        q = s.query(models.User)
        if steam_id:
            q = q.filter(models.User.steam_id == steam_id)
        if username:
            q = q.filter(models.User.username == username)
        return q.first()
    finally:
        s.close()


def _callback_url(state: str, claimed_id: str, mode: str = "id_res") -> str:
    from urllib.parse import quote
    return (
        "/api/auth/steam/callback"
        f"?openid.mode={mode}&openid.claimed_id={quote(claimed_id, safe='')}"
        f"&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
        f"&state={quote(state, safe='')}"
    )


# ── config + state ─────────────────────────────────────────────────────────────

def test_config_disabled_by_default(client):
    assert client.get("/api/auth/steam/config").json() == {"enabled": False}


def test_config_enabled_when_configured(client):
    _enable_steam()
    assert client.get("/api/auth/steam/config").json() == {"enabled": True}


def test_link_404_when_disabled(client):
    register(client, "founder", "founder@example.com")
    token = create_access_token({"sub": str(_get_user(username="founder").id)})
    assert client.get("/api/auth/steam/link", headers=auth_header(token)).status_code == 404


def test_link_requires_auth(client):
    _enable_steam()
    assert client.get("/api/auth/steam/link").status_code in (401, 403)


def test_link_returns_steam_login_url_when_enabled(client):
    register(client, "founder", "founder@example.com")
    _enable_steam()
    token = create_access_token({"sub": str(_get_user(username="founder").id)})
    body = client.get("/api/auth/steam/link", headers=auth_header(token)).json()
    assert body["authorize_url"].startswith("https://steamcommunity.com/openid/login?")
    assert "openid.return_to=https%3A%2F%2Flan.example%2Fapi%2Fauth%2Fsteam%2Fcallback" in body["authorize_url"]
    assert "openid.realm=https%3A%2F%2Flan.example" in body["authorize_url"]


def test_state_roundtrip_and_tamper_rejected():
    token = oauth_steam.sign_state({"user_id": 42})
    assert oauth_steam.verify_state(token)["user_id"] == 42
    with pytest.raises(oauth_steam.SteamOAuthError):
        oauth_steam.verify_state(token + "tampered")


def test_extract_steam_id():
    assert oauth_steam.extract_steam_id("https://steamcommunity.com/openid/id/76561198000000001") == "76561198000000001"
    assert oauth_steam.extract_steam_id("https://steamcommunity.com/openid/id/") is None
    assert oauth_steam.extract_steam_id("not a url") is None
    assert oauth_steam.extract_steam_id(None) is None


# ── callback: link flow ─────────────────────────────────────────────────────────

def test_link_flow_attaches_steam_to_user(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    _enable_steam()
    claimed_id = "https://steamcommunity.com/openid/id/76561198000000001"
    monkeypatch.setattr(oauth_steam, "verify_openid_response", lambda params: True)
    monkeypatch.setattr(oauth_steam, "fetch_player_summary",
                         lambda steam_id, api_key: {"personaname": "FounderSteam", "avatarfull": "https://x/avatar.jpg"})
    state = oauth_steam.sign_state({"user_id": admin.id, "desktop_port": None})

    resp = client.get(_callback_url(state, claimed_id), follow_redirects=False)
    assert resp.status_code == 303
    assert "/profile?steam=linked" in resp.headers["location"]

    linked = _get_user(username="founder")
    assert linked.steam_id == "76561198000000001"
    assert linked.steam_username == "FounderSteam"
    assert linked.steam_avatar == "https://x/avatar.jpg"


def test_link_flow_rejects_steam_id_already_linked(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    s = database.SessionLocal()
    try:
        other = models.User(username="other", email="other@x.test",
                             hashed_password=get_password_hash("password123"),
                             steam_id="76561198000000001")
        s.add(other)
        s.commit()
    finally:
        s.close()
    _enable_steam()
    claimed_id = "https://steamcommunity.com/openid/id/76561198000000001"
    monkeypatch.setattr(oauth_steam, "verify_openid_response", lambda params: True)
    monkeypatch.setattr(oauth_steam, "fetch_player_summary", lambda steam_id, api_key: {})
    state = oauth_steam.sign_state({"user_id": admin.id, "desktop_port": None})

    resp = client.get(_callback_url(state, claimed_id), follow_redirects=False)
    assert "/profile?steam=already_linked" in resp.headers["location"]
    assert _get_user(username="founder").steam_id is None


def test_callback_missing_state_redirects_error(client):
    _enable_steam()
    resp = client.get("/api/auth/steam/callback?openid.mode=id_res", follow_redirects=False)
    assert resp.status_code == 303
    assert "/profile?steam=error" in resp.headers["location"]


def test_callback_bad_state_redirects_error(client):
    _enable_steam()
    resp = client.get(_callback_url("garbage", "https://steamcommunity.com/openid/id/1"), follow_redirects=False)
    assert "/profile?steam=error" in resp.headers["location"]


def test_callback_cancelled_login_redirects_error(client):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    _enable_steam()
    state = oauth_steam.sign_state({"user_id": admin.id, "desktop_port": None})
    resp = client.get(_callback_url(state, "", mode="cancel"), follow_redirects=False)
    assert "/profile?steam=error" in resp.headers["location"]


def test_callback_failed_verification_redirects_error(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    _enable_steam()
    claimed_id = "https://steamcommunity.com/openid/id/76561198000000001"
    monkeypatch.setattr(oauth_steam, "verify_openid_response", lambda params: False)
    state = oauth_steam.sign_state({"user_id": admin.id, "desktop_port": None})

    resp = client.get(_callback_url(state, claimed_id), follow_redirects=False)
    assert "/profile?steam=error" in resp.headers["location"]
    assert _get_user(username="founder").steam_id is None


def test_callback_unreachable_verification_redirects_error(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    _enable_steam()
    claimed_id = "https://steamcommunity.com/openid/id/76561198000000001"

    def _boom(params):
        raise oauth_steam.SteamOAuthError("network down")
    monkeypatch.setattr(oauth_steam, "verify_openid_response", _boom)
    state = oauth_steam.sign_state({"user_id": admin.id, "desktop_port": None})

    resp = client.get(_callback_url(state, claimed_id), follow_redirects=False)
    assert "/profile?steam=error" in resp.headers["location"]


def test_link_survives_player_summary_failure(client, monkeypatch):
    """A Steam profile-summary fetch failure shouldn't sink an otherwise-verified link."""
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    _enable_steam()
    claimed_id = "https://steamcommunity.com/openid/id/76561198000000001"
    monkeypatch.setattr(oauth_steam, "verify_openid_response", lambda params: True)

    def _boom(steam_id, api_key):
        raise oauth_steam.SteamOAuthError("summary unavailable")
    monkeypatch.setattr(oauth_steam, "fetch_player_summary", _boom)
    state = oauth_steam.sign_state({"user_id": admin.id, "desktop_port": None})

    resp = client.get(_callback_url(state, claimed_id), follow_redirects=False)
    assert "/profile?steam=linked" in resp.headers["location"]
    linked = _get_user(username="founder")
    assert linked.steam_id == "76561198000000001"
    assert linked.steam_username is None


# ── unlink ───────────────────────────────────────────────────────────────────────

def test_unlink_requires_existing_link(client):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    token = create_access_token({"sub": str(admin.id)})
    resp = client.request("DELETE", "/api/auth/steam/link", headers=auth_header(token))
    assert resp.status_code == 400


def test_unlink_succeeds_no_password_guard_needed(client):
    """Unlike Discord, Steam-link never needs a 'you'd lock yourself out' guard
    — there's no sign-up-via-Steam flow that could have made it the only way in."""
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    s = database.SessionLocal()
    try:
        u = s.query(models.User).get(admin.id)
        u.steam_id = "76561198000000001"
        u.steam_username = "FounderSteam"
        s.commit()
    finally:
        s.close()
    token = create_access_token({"sub": str(admin.id)})
    resp = client.request("DELETE", "/api/auth/steam/link", headers=auth_header(token))
    assert resp.status_code == 200
    linked = _get_user(username="founder")
    assert linked.steam_id is None
    assert linked.steam_username is None


def test_public_config_never_exposes_steam_api_key(client):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    _enable_steam()
    token = create_access_token({"sub": str(admin.id)})
    cfg = client.get("/api/settings/public-config", headers=auth_header(token)).json()
    assert "steam_link_enabled" not in cfg
    assert "steam_web_api_key" not in cfg


# ── desktop app: loopback callback nonce (S13) ─────────────────────────────────

NONCE = "b2" * 32


def test_link_signs_the_desktop_nonce_into_state(client):
    from urllib.parse import parse_qs, urlparse
    register(client, "founder", "founder@example.com")
    _enable_steam()
    token = create_access_token({"sub": str(_get_user(username="founder").id)})
    body = client.get(
        "/api/auth/steam/link", params={"desktop_port": 5555, "desktop_nonce": NONCE},
        headers=auth_header(token),
    ).json()
    return_to = parse_qs(urlparse(body["authorize_url"]).query)["openid.return_to"][0]
    st = oauth_steam.verify_state(parse_qs(urlparse(return_to).query)["state"][0])
    assert st["desktop_port"] == 5555 and st["desktop_nonce"] == NONCE


def test_desktop_callback_carries_the_nonce_back(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    _enable_steam()
    monkeypatch.setattr(oauth_steam, "verify_openid_response", lambda params: True)
    monkeypatch.setattr(oauth_steam, "fetch_player_summary", lambda steam_id, api_key: {})
    state = oauth_steam.sign_state({"user_id": admin.id, "desktop_port": 5555, "desktop_nonce": NONCE})

    resp = client.get(
        _callback_url(state, "https://steamcommunity.com/openid/id/76561198000000009"), follow_redirects=False
    )
    assert resp.headers["location"] == (
        f"http://127.0.0.1:5555/callback?target=%2Fprofile%3Fsteam%3Dlinked&nonce={NONCE}"
    )
