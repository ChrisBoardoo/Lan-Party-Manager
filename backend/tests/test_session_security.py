"""Session security: signing-key loading, token revocation (token_version),
token types, WebSocket auth by first frame, and the password-gated Discord link.
"""

from datetime import datetime, timedelta

import pytest
from jose import jwt
from starlette.websockets import WebSocketDisconnect

import auth
import database
import models
import oauth_discord
import oauth_state
from conftest import auth_header, login, make_user
from router_auth import reset_token_digest


def _user(user_id):
    s = database.SessionLocal()
    try:
        return s.get(models.User, user_id)
    finally:
        s.close()


def _me(client, token):
    return client.get("/api/auth/me", headers=auth_header(token))


# ── signing key ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "lanparty-secret-CHANGE-ME",
    "change-me-to-a-long-random-string",
    "une-longue-chaine-aleatoire-a-changer",
    "  your-secret  ",
])
def test_example_keys_are_refused(monkeypatch, value):
    monkeypatch.setenv("SECRET_KEY", value)
    with pytest.raises(RuntimeError, match="example value"):
        auth._load_secret_key()


def test_short_key_is_refused(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * (auth.MIN_KEY_LENGTH - 1))
    with pytest.raises(RuntimeError, match="shorter than"):
        auth._load_secret_key()


def test_short_but_acceptable_key_only_warns(monkeypatch, caplog):
    monkeypatch.setenv("SECRET_KEY", "k" * 25)
    assert auth._load_secret_key() == "k" * 25
    assert "shorter than" in caplog.text


@pytest.mark.parametrize("unset", [None, "", "   "])
def test_missing_key_is_generated_once_and_reused(monkeypatch, tmp_path, unset):
    if unset is None:
        monkeypatch.delenv("SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("SECRET_KEY", unset)
    key_file = tmp_path / "data" / "secret_key"
    monkeypatch.setattr(auth, "SECRET_KEY_FILE", str(key_file))

    first = auth._load_secret_key()
    assert len(first) == 64 and key_file.read_text() == first
    assert auth._load_secret_key() == first  # reused, not regenerated


def test_empty_key_file_is_an_error(monkeypatch, tmp_path):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    key_file = tmp_path / "secret_key"
    key_file.write_text("")
    monkeypatch.setattr(auth, "SECRET_KEY_FILE", str(key_file))
    with pytest.raises(RuntimeError, match="is empty"):
        auth._load_secret_key()


# ── token shape ────────────────────────────────────────────────────────────────

def test_pre_134_token_without_version_is_refused(client):
    uid = make_user("alice")
    legacy = jwt.encode(
        {"sub": str(uid), "exp": datetime.utcnow() + timedelta(days=1)}, auth.SECRET_KEY, algorithm=auth.ALGORITHM
    )
    assert _me(client, legacy).status_code == 401


def test_oauth_state_is_not_a_session_and_vice_versa(client):
    uid = make_user("alice")
    state = oauth_state.sign_state({"sub": str(uid), "tv": 0, "flow": "login"})
    assert _me(client, state).status_code == 401
    with pytest.raises(ValueError):
        oauth_state.verify_state(login(client, "alice"))


# ── revocation ─────────────────────────────────────────────────────────────────

def test_password_change_revokes_old_tokens_and_returns_a_new_one(client):
    uid = make_user("alice")
    stolen = login(client, "alice")
    resp = client.post(
        f"/api/users/{uid}/change-password",
        json={"current_password": "password123", "new_password": "a-new-password"},
        headers=auth_header(stolen),
    )
    assert resp.status_code == 200
    assert _me(client, stolen).status_code == 401
    assert client.post("/api/auth/refresh", headers=auth_header(stolen)).status_code == 401
    assert _me(client, resp.json()["access_token"]).status_code == 200


def test_deactivation_revokes_and_reactivation_does_not_revive(client):
    make_user("admin", role="admin")
    uid = make_user("bob")
    admin_t, bob_t = login(client, "admin"), login(client, "bob")
    assert client.put(f"/api/users/{uid}/deactivate", headers=auth_header(admin_t)).status_code == 200
    assert client.put(f"/api/users/{uid}/reactivate", headers=auth_header(admin_t)).status_code == 200
    assert _me(client, bob_t).status_code == 401
    assert _me(client, login(client, "bob")).status_code == 200


def test_admin_reset_revokes_sessions(client):
    make_user("admin", role="admin")
    uid = make_user("bob")
    admin_t, bob_t = login(client, "admin"), login(client, "bob")
    assert client.post(f"/api/users/{uid}/reset-password", headers=auth_header(admin_t)).status_code == 200
    assert _me(client, bob_t).status_code == 401


def test_deleted_account_cannot_be_reactivated_or_reset(client):
    make_user("admin", role="admin")
    uid = make_user("bob")
    admin_t = login(client, "admin")
    assert client.delete(f"/api/users/{uid}", headers=auth_header(admin_t)).status_code == 200
    assert client.put(f"/api/users/{uid}/reactivate", headers=auth_header(admin_t)).status_code == 400
    assert client.post(f"/api/users/{uid}/reset-password", headers=auth_header(admin_t)).status_code == 400


def test_reset_link_revokes_sessions_and_other_links(client):
    uid = make_user("alice")
    stolen = login(client, "alice")
    s = database.SessionLocal()
    try:
        for token in ("link-one", "link-two"):
            s.add(models.PasswordResetToken(
                user_id=uid, token=reset_token_digest(token),
                expires_at=datetime.utcnow() + timedelta(hours=1),
            ))
        s.commit()
    finally:
        s.close()

    resp = client.post("/api/auth/reset-password", json={"token": "link-one", "new_password": "brand-new-pass"})
    assert resp.status_code == 200
    assert _me(client, stolen).status_code == 401
    # The other link sent before the reset can't be used to take the account back.
    resp = client.post("/api/auth/reset-password", json={"token": "link-two", "new_password": "attacker-pass"})
    assert resp.status_code == 400


# ── WebSockets: auth by first frame ────────────────────────────────────────────

def _ws_close_code(client, url, first_frame):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(url) as ws:
            if first_frame is not None:
                ws.send_json(first_frame)
            ws.receive_json()
    return exc.value.code


def test_ws_refuses_missing_or_bad_auth_frame(client):
    assert _ws_close_code(client, "/api/activity/ws", {"type": "typing"}) == 4401
    assert _ws_close_code(client, "/api/activity/ws", {"type": "auth", "token": "nope"}) == 4401


def test_ws_ignores_a_token_in_the_query_string(client):
    make_user("alice")
    token = login(client, "alice")
    # The old way: no auth frame, token in the URL. It must not be honored.
    assert _ws_close_code(client, f"/api/activity/ws?token={token}", {"type": "typing"}) == 4401


def test_ws_auth_frame_gets_past_authentication(client):
    make_user("alice")
    token = login(client, "alice")
    # Event 999 doesn't exist: 4404 means the token was accepted and the
    # socket moved on to the chat checks.
    assert _ws_close_code(client, "/api/chat/999/ws", {"type": "auth", "token": token}) == 4404


def test_open_ws_is_closed_when_the_session_is_revoked(client, monkeypatch):
    import router_activity
    monkeypatch.setattr(router_activity, "WS_RECHECK_EVERY", 1)
    uid = make_user("alice")
    token = login(client, "alice")
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/activity/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            s = database.SessionLocal()
            try:
                auth.revoke_sessions(s.get(models.User, uid))
                s.commit()
            finally:
                s.close()
            ws.receive_json()
    assert exc.value.code == 4401


# ── Discord link: password first ───────────────────────────────────────────────

def _enable_discord():
    s = database.SessionLocal()
    try:
        for k, v in {
            "discord_oauth_enabled": "true",
            "discord_oauth_client_id": "cid",
            "discord_oauth_client_secret": "secret",
            "app_base_url": "https://lan.example",
        }.items():
            s.add(models.AppSetting(key=k, value=v))
        s.commit()
    finally:
        s.close()


def test_discord_link_needs_a_password_ticket(client):
    _enable_discord()
    make_user("alice")
    token = login(client, "alice")
    # A session alone (e.g. a stolen token) can't start a link.
    assert client.get("/api/auth/discord/link", headers=auth_header(token)).status_code == 403
    wrong = client.post("/api/auth/discord/link-ticket", json={"password": "nope"}, headers=auth_header(token))
    assert wrong.status_code == 400

    ticket = client.post(
        "/api/auth/discord/link-ticket", json={"password": "password123"}, headers=auth_header(token)
    ).json()["ticket"]
    resp = client.get("/api/auth/discord/link", params={"code": ticket}, headers=auth_header(token))
    assert resp.status_code == 200 and "discord.com" in resp.json()["authorize_url"]


def test_discord_link_ticket_is_bound_to_its_user(client):
    _enable_discord()
    make_user("alice")
    make_user("mallory")
    alice_t, mallory_t = login(client, "alice"), login(client, "mallory")
    mallory_ticket = client.post(
        "/api/auth/discord/link-ticket", json={"password": "password123"}, headers=auth_header(mallory_t)
    ).json()["ticket"]
    resp = client.get("/api/auth/discord/link", params={"code": mallory_ticket}, headers=auth_header(alice_t))
    assert resp.status_code == 403


def test_discord_link_refused_when_already_linked(client):
    _enable_discord()
    uid = make_user("alice")
    s = database.SessionLocal()
    try:
        s.get(models.User, uid).discord_id = "111"
        s.commit()
    finally:
        s.close()
    token = login(client, "alice")
    resp = client.post("/api/auth/discord/link-ticket", json={"password": "password123"}, headers=auth_header(token))
    assert resp.status_code == 409


def test_link_callback_never_replaces_an_existing_discord(client, monkeypatch):
    _enable_discord()
    uid = make_user("alice")
    s = database.SessionLocal()
    try:
        s.get(models.User, uid).discord_id = "111"
        s.commit()
    finally:
        s.close()
    monkeypatch.setattr(oauth_discord, "exchange_code", lambda *a, **k: {"access_token": "tok"})
    monkeypatch.setattr(oauth_discord, "fetch_user", lambda token: {"id": "999", "username": "mallory"})
    state = oauth_discord.sign_state({"flow": "link", "user_id": uid})
    resp = client.get(f"/api/auth/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert "discord=error" in resp.headers["location"]
    assert _user(uid).discord_id == "111"


def test_web_oauth_flow_must_return_to_the_browser_that_started_it(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse

    from fastapi.testclient import TestClient

    import main

    _enable_discord()
    make_user("alice")
    monkeypatch.setattr(oauth_discord, "exchange_code", lambda *a, **k: {"access_token": "tok"})
    monkeypatch.setattr(oauth_discord, "fetch_user", lambda token: {"id": "4242", "username": "x"})
    url = client.get("/api/auth/discord/authorize").json()["authorize_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    callback = f"/api/auth/discord/callback?code=abc&state={state}"

    # Someone else's browser (no binding cookie) can't finish this flow...
    other = TestClient(main.app).get(callback, follow_redirects=False)
    assert other.headers["location"].endswith("/login?discord=error")
    # ...the browser that started it can (here: no invite, so registration is refused).
    same = client.get(callback, follow_redirects=False)
    assert "discord=error" not in same.headers["location"]
