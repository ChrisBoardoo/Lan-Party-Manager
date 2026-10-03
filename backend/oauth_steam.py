"""Steam OpenID 2.0 helpers — link-only (no login/registration via Steam).

Steam uses OpenID 2.0, not OAuth2: there's no client_id/client_secret pair and
no code-for-token exchange. The relying party (us) sends the user to Steam's
login page with a `return_to` URL; Steam redirects back with `openid.*`
parameters including a claimed identity URL, and authenticity is confirmed by
re-posting those same parameters back to Steam with
`openid.mode=check_authentication` rather than trusting the redirect outright
— OpenID 2.0's stateless alternative to a client secret.

A Steam Web API key (free, steamcommunity.com/dev/apikey) is only needed for
the calls *after* a successful link — fetching the account's display
name/avatar and its owned-games list — never for the login/link step itself.

See md/2.features/Steam_Link.md for the full design (gitignored, local-only per this
repo's `.gitignore` convention for `md/`).
"""

import re
from urllib.parse import urlencode

import httpx

import oauth_state

# The desktop app only opens this exact prefix (`is_expected_authorize_url` in
# desktopapp/src-tauri/src/main.rs) — changing it breaks desktop Steam linking
# until a new MSI ships.
STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"
PLAYER_SUMMARY_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
_HTTP_TIMEOUT = 10.0

# OpenID 2.0's way of saying "let the provider pick the identity" — Steam
# always resolves this to the signed-in account, there's no account picker to
# configure since a Steam login only ever yields one identity.
_IDENTIFIER_SELECT = "http://specs.openid.net/auth/2.0/identifier_select"
_CLAIMED_ID_RE = re.compile(r"^https?://steamcommunity\.com/openid/id/(\d+)$")


class SteamOAuthError(Exception):
    """Any failure talking to Steam, or an invalid/expired state token."""


# ── Signed state (CSRF + flow context) — see oauth_state.py ────────────────────

def sign_state(payload: dict) -> str:
    return oauth_state.sign_state(payload)


def verify_state(token: str) -> dict:
    return oauth_state.verify_state(token, SteamOAuthError)


# ── Steam OpenID ─────────────────────────────────────────────────────────────

def build_login_url(return_to: str, realm: str) -> str:
    query = urlencode({
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": realm,
        "openid.identity": _IDENTIFIER_SELECT,
        "openid.claimed_id": _IDENTIFIER_SELECT,
    })
    return f"{STEAM_OPENID_URL}?{query}"


def verify_openid_response(params: dict) -> bool:
    """Re-post the callback's openid.* params back to Steam with
    check_authentication — Steam's stateless way of confirming they weren't
    forged, since OpenID 2.0 has no client secret to sign a request with.
    Only openid.* keys are forwarded; anything else on our callback URL
    (our own `state` param) is irrelevant to Steam's verification."""
    payload = {k: v for k, v in params.items() if k.startswith("openid.")}
    payload["openid.mode"] = "check_authentication"
    try:
        resp = httpx.post(STEAM_OPENID_URL, data=payload, timeout=_HTTP_TIMEOUT)
    except httpx.HTTPError as exc:
        raise SteamOAuthError("Could not reach Steam to verify sign-in") from exc
    if resp.status_code != 200:
        raise SteamOAuthError(f"Steam verification failed ({resp.status_code})")
    return "is_valid:true" in resp.text


def extract_steam_id(claimed_id: str) -> str | None:
    """Pulls the SteamID64 off the end of `openid.claimed_id`
    (`https://steamcommunity.com/openid/id/<id>`); `None` if it doesn't match
    that shape at all."""
    match = _CLAIMED_ID_RE.match(claimed_id or "")
    return match.group(1) if match else None


def fetch_player_summary(steam_id: str, api_key: str) -> dict:
    """`{}` (not an error) if Steam has no record for this id — display fields
    are best-effort, the link itself doesn't depend on them succeeding."""
    try:
        resp = httpx.get(
            PLAYER_SUMMARY_URL,
            params={"key": api_key, "steamids": steam_id},
            timeout=_HTTP_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise SteamOAuthError("Could not reach Steam to fetch your profile") from exc
    if resp.status_code != 200:
        raise SteamOAuthError(f"Steam profile fetch failed ({resp.status_code})")
    players = resp.json().get("response", {}).get("players", [])
    return players[0] if players else {}


def fetch_owned_games(steam_id: str, api_key: str) -> list[dict] | None:
    """`None` (not an empty list) when the response has no `games` key at all
    — the signal that this Steam profile's game list is set to private,
    distinct from an empty-but-public library. Each entry has at least
    `appid`/`name` (with `include_appinfo=1`)."""
    try:
        resp = httpx.get(
            OWNED_GAMES_URL,
            params={"key": api_key, "steamid": steam_id, "include_appinfo": 1},
            timeout=_HTTP_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise SteamOAuthError("Could not reach Steam to fetch owned games") from exc
    if resp.status_code != 200:
        raise SteamOAuthError(f"Steam owned-games fetch failed ({resp.status_code})")
    body = resp.json().get("response", {})
    if "games" not in body:
        return None
    return body["games"]
