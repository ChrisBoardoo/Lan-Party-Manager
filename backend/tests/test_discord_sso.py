"""Discord SSO: config gate, signed state, and the callback flows
(register-by-invite, auto-link by verified email, link/unlink)."""

from datetime import date, timedelta

import pytest

import database
import models
import oauth_discord
from auth import create_access_token, get_password_hash, UNUSABLE_PASSWORD
from conftest import register, auth_header


def _token_for(user_id):
    """A session token for `user_id`, carrying its current token_version."""
    s = database.SessionLocal()
    try:
        return create_access_token(s.get(models.User, user_id))
    finally:
        s.close()


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


def _enable_discord():
    _set_settings(
        discord_oauth_enabled="true",
        discord_oauth_client_id="cid",
        discord_oauth_client_secret="secret",
        app_base_url="https://lan.example",
    )


def _make_event_with_invite(code="INVITE"):
    s = database.SessionLocal()
    try:
        admin = s.query(models.User).first()
        ev = models.LanEvent(
            title="LAN",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=2),
            created_by=admin.id,
        )
        s.add(ev)
        s.flush()
        s.add(models.EventInvite(event_id=ev.id, code=code, created_by=admin.id))
        s.commit()
        return ev.id
    finally:
        s.close()


def _patch_discord(monkeypatch, profile):
    monkeypatch.setattr(oauth_discord, "exchange_code", lambda *a, **k: {"access_token": "tok"})
    monkeypatch.setattr(oauth_discord, "fetch_user", lambda token: profile)


def _get_user(discord_id=None, username=None):
    s = database.SessionLocal()
    try:
        q = s.query(models.User)
        if discord_id:
            q = q.filter(models.User.discord_id == discord_id)
        if username:
            q = q.filter(models.User.username == username)
        return q.first()
    finally:
        s.close()


# ── config + state ─────────────────────────────────────────────────────────────

def test_config_disabled_by_default(client):
    assert client.get("/api/auth/discord/config").json() == {"enabled": False}


def test_config_enabled_when_configured(client):
    _enable_discord()
    assert client.get("/api/auth/discord/config").json() == {"enabled": True}


def test_authorize_404_when_disabled(client):
    assert client.get("/api/auth/discord/authorize").status_code == 404


def test_authorize_returns_url_when_enabled(client):
    _enable_discord()
    body = client.get("/api/auth/discord/authorize?code=ABC").json()
    assert body["authorize_url"].startswith("https://discord.com/oauth2/authorize?")
    assert "redirect_uri=https%3A%2F%2Flan.example%2Fapi%2Fauth%2Fdiscord%2Fcallback" in body["authorize_url"]


def test_state_roundtrip_and_tamper_rejected():
    token = oauth_discord.sign_state({"flow": "login", "invite_code": "X"})
    assert oauth_discord.verify_state(token)["invite_code"] == "X"
    with pytest.raises(oauth_discord.DiscordOAuthError):
        oauth_discord.verify_state(token + "tampered")


# ── callback: register flow ────────────────────────────────────────────────────

def test_callback_creates_user_and_rsvp_with_valid_invite(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    event_id = _make_event_with_invite("INVITE")
    _enable_discord()
    _patch_discord(monkeypatch, {
        "id": "999", "username": "ghost", "global_name": "Ghost",
        "email": "ghost@discord.test", "verified": True,
    })
    state = oauth_discord.sign_state({"flow": "login", "invite_code": "INVITE"})

    resp = client.get(f"/api/auth/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code == 303
    assert "/auth/discord/complete#token=" in resp.headers["location"]

    user = _get_user(discord_id="999")
    assert user is not None
    assert user.hashed_password == UNUSABLE_PASSWORD
    s = database.SessionLocal()
    try:
        rsvp = s.query(models.EventRSVP).filter_by(user_id=user.id, event_id=event_id, status="in").first()
        assert rsvp is not None
    finally:
        s.close()


def test_callback_without_invite_redirects_to_register_error(client, monkeypatch):
    register(client, "founder", "founder@example.com")  # not first -> invite required
    _enable_discord()
    _patch_discord(monkeypatch, {"id": "999", "username": "ghost", "verified": True, "email": "g@d.test"})
    state = oauth_discord.sign_state({"flow": "login", "invite_code": None})

    resp = client.get(f"/api/auth/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code == 303
    assert "/register?discord=invite_required" in resp.headers["location"]
    assert _get_user(discord_id="999") is None


def test_callback_bad_state_redirects_error(client):
    _enable_discord()
    resp = client.get("/api/auth/discord/callback?code=abc&state=garbage", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login?discord=error" in resp.headers["location"]


# ── callback: auto-link by verified email ──────────────────────────────────────

def test_callback_does_not_autolink_existing_account_by_email(client, monkeypatch):
    # LPM never verified the e-mail typed at registration: linking on a match
    # would hand the Discord user's sessions to whoever registered it first.
    register(client, "founder", "founder@example.com")
    _enable_discord()
    _patch_discord(monkeypatch, {
        "id": "555", "username": "f", "email": "FOUNDER@example.com", "verified": True,
    })
    state = oauth_discord.sign_state({"flow": "login", "invite_code": None})

    resp = client.get(f"/api/auth/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login?discord=link_required" in resp.headers["location"]
    assert _get_user(discord_id="555") is None


def test_callback_unverified_email_does_not_autolink(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    _enable_discord()
    _patch_discord(monkeypatch, {
        "id": "556", "username": "f", "email": "founder@example.com", "verified": False,
    })
    state = oauth_discord.sign_state({"flow": "login", "invite_code": None})

    resp = client.get(f"/api/auth/discord/callback?code=abc&state={state}", follow_redirects=False)
    # No invite + no auto-link -> account creation is blocked
    assert "/register?discord=" in resp.headers["location"]
    assert _get_user(discord_id="556") is None


# ── callback: link flow + unlink ───────────────────────────────────────────────

def test_link_flow_attaches_discord_to_user(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    _enable_discord()
    _patch_discord(monkeypatch, {"id": "777", "username": "founderDiscord", "verified": True})
    state = oauth_discord.sign_state({"flow": "link", "user_id": admin.id})

    resp = client.get(f"/api/auth/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code == 303
    assert "/profile?discord=linked" in resp.headers["location"]
    assert _get_user(username="founder").discord_id == "777"


def test_link_flow_rejects_discord_id_already_linked(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    # someone else already owns discord id 777
    s = database.SessionLocal()
    try:
        other = models.User(username="other", email="other@x.test",
                            hashed_password=get_password_hash("password123"), discord_id="777")
        s.add(other)
        s.commit()
    finally:
        s.close()
    _enable_discord()
    _patch_discord(monkeypatch, {"id": "777", "username": "dup", "verified": True})
    state = oauth_discord.sign_state({"flow": "link", "user_id": admin.id})

    resp = client.get(f"/api/auth/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert "/profile?discord=already_linked" in resp.headers["location"]
    assert _get_user(username="founder").discord_id is None


def test_unlink_blocked_for_passwordless_account(client):
    # Discord-only account (no usable password)
    s = database.SessionLocal()
    try:
        u = models.User(username="discorduser", email="d@x.test",
                        hashed_password=UNUSABLE_PASSWORD, discord_id="888")
        s.add(u)
        s.commit()
        uid = u.id
    finally:
        s.close()
    token = _token_for(uid)
    resp = client.request("DELETE", "/api/auth/discord/link", headers=auth_header(token))
    assert resp.status_code == 400
    assert _get_user(discord_id="888") is not None  # still linked


def test_unlink_succeeds_for_password_account(client):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    s = database.SessionLocal()
    try:
        u = s.query(models.User).get(admin.id)
        u.discord_id = "999"
        s.commit()
    finally:
        s.close()
    token = _token_for(admin.id)
    resp = client.request("DELETE", "/api/auth/discord/link", headers=auth_header(token))
    assert resp.status_code == 200
    assert _get_user(username="founder").discord_id is None


# ── desktop app: loopback callback nonce (S13) ─────────────────────────────────
#
# The desktop app's loopback listener accepts any local connection, so the server
# hands back the nonce the app generated; the app ignores a callback without it.

NONCE = "a1" * 32  # the app sends 32 random bytes, hex-encoded


def _state_from(authorize_url):
    from urllib.parse import parse_qs, urlparse
    return oauth_discord.verify_state(parse_qs(urlparse(authorize_url).query)["state"][0])


def test_authorize_signs_the_desktop_nonce_into_state(client):
    _enable_discord()
    body = client.get(
        "/api/auth/discord/authorize", params={"desktop_port": 5555, "desktop_nonce": NONCE}
    ).json()
    st = _state_from(body["authorize_url"])
    assert st["desktop_port"] == 5555 and st["desktop_nonce"] == NONCE


def test_authorize_rejects_a_malformed_nonce(client):
    _enable_discord()
    for bad in ("short", "x" * 129, "not/hex&target=evil" + "a" * 20):
        resp = client.get("/api/auth/discord/authorize", params={"desktop_port": 5555, "desktop_nonce": bad})
        assert resp.status_code == 422, bad


def test_desktop_callback_carries_the_nonce_back(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    _enable_discord()
    _patch_discord(monkeypatch, {"id": "778", "username": "d", "verified": True})
    state = oauth_discord.sign_state(
        {"flow": "link", "user_id": admin.id, "desktop_port": 5555, "desktop_nonce": NONCE}
    )

    resp = client.get(f"/api/auth/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == (
        f"http://127.0.0.1:5555/callback?target=%2Fprofile%3Fdiscord%3Dlinked&nonce={NONCE}"
    )


def test_desktop_callback_from_an_older_app_has_no_nonce(client, monkeypatch):
    """Desktop 1.3.1 and older never send one — their flow must keep working."""
    register(client, "founder", "founder@example.com")
    admin = _get_user(username="founder")
    _enable_discord()
    _patch_discord(monkeypatch, {"id": "779", "username": "d", "verified": True})
    state = oauth_discord.sign_state({"flow": "link", "user_id": admin.id, "desktop_port": 5555})

    resp = client.get(f"/api/auth/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.headers["location"] == "http://127.0.0.1:5555/callback?target=%2Fprofile%3Fdiscord%3Dlinked"
