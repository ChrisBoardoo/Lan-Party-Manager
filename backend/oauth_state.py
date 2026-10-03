"""Shared signed-state helper (CSRF + flow context) for OAuth/OpenID link flows.

Used by both ``oauth_discord.py`` and ``oauth_steam.py`` to carry a short-lived,
tamper-evident payload (which user is linking, the desktop loopback port, ...)
through the round-trip to the external provider and back. Signed with the app's
own ``SECRET_KEY``, so a callback whose state we didn't mint (or that's
expired) is rejected outright — this IS the CSRF protection, there's no
separate state cookie to cross-check.

This was split out of ``oauth_discord.py`` when Steam linking was added: the
signing/verification logic itself has nothing Discord-specific about it, and
duplicating security-sensitive code (rather than UI patterns, which this
codebase repeats freely) risks the two copies quietly drifting apart. Each
provider module wraps ``verify_state`` with its own exception type (e.g.
``DiscordOAuthError``, ``SteamOAuthError``) so callers can keep catching a
single, provider-scoped error without this module knowing about either
provider.
"""

from datetime import datetime, timedelta

from jose import JWTError, jwt

from auth import ALGORITHM, SECRET_KEY

STATE_TTL = timedelta(minutes=10)
# Same key as session tokens, so the type claim is what keeps the two apart:
# a state is never accepted as a session (auth.user_from_token wants "access"),
# and a session token is never accepted as a state.
STATE_TYPE = "oauth_state"


def sign_state(payload: dict) -> str:
    data = {**payload, "typ": STATE_TYPE, "exp": datetime.utcnow() + STATE_TTL}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def verify_state(token: str, error_cls: type[Exception] = ValueError) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise error_cls("Invalid or expired sign-in state") from exc
    if payload.get("typ") != STATE_TYPE:
        raise error_cls("Invalid or expired sign-in state")
    return payload
