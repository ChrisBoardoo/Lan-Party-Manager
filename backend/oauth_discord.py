"""Discord OAuth2 (Authorization Code) helpers.

Two responsibilities, deliberately separated so the router stays thin and the
network calls are easy to monkeypatch in tests:

  * ``sign_state`` / ``verify_state`` — a short-lived signed token that carries
    the flow context (register vs link, invite code, linking user id) through
    the round-trip to Discord and back. Signed with the app ``SECRET_KEY``, so
    it doubles as CSRF protection: a callback whose ``state`` we didn't mint (or
    that has expired) is rejected.
  * ``build_authorize_url`` / ``exchange_code`` / ``fetch_user`` — the actual
    Discord endpoints.

Credentials (client id/secret) are read from the ``app_settings`` table by the
router, mirroring how the Twitch credentials are stored — never from ``.env``.
"""

from urllib.parse import urlencode

import httpx

import oauth_state

# The desktop app only opens this exact prefix (`is_expected_authorize_url` in
# desktopapp/src-tauri/src/main.rs) — changing it breaks desktop sign-in until a
# new MSI ships.
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
USER_URL = "https://discord.com/api/users/@me"

# `identify` gives us the account id + username; `email` gives the (verified)
# email we use to auto-link to an existing password account.
SCOPES = "identify email"
_HTTP_TIMEOUT = 10.0


class DiscordOAuthError(Exception):
    """Any failure talking to Discord, or an invalid/expired state token."""


# ── Signed state (CSRF + flow context) — see oauth_state.py ────────────────────

def sign_state(payload: dict) -> str:
    return oauth_state.sign_state(payload)


def verify_state(token: str) -> dict:
    return oauth_state.verify_state(token, DiscordOAuthError)


# ── Discord endpoints ──────────────────────────────────────────────────────────

def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "prompt": "consent",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """Trade the authorization code for an access token."""
    try:
        resp = httpx.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=_HTTP_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise DiscordOAuthError("Could not reach Discord to exchange the code") from exc
    if resp.status_code != 200:
        raise DiscordOAuthError(f"Discord token exchange failed ({resp.status_code})")
    return resp.json()


def fetch_user(access_token: str) -> dict:
    """Fetch the authenticated Discord user (id, username, email, verified, ...)."""
    try:
        resp = httpx.get(
            USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_HTTP_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise DiscordOAuthError("Could not reach Discord to fetch your profile") from exc
    if resp.status_code != 200:
        raise DiscordOAuthError(f"Discord profile fetch failed ({resp.status_code})")
    return resp.json()
