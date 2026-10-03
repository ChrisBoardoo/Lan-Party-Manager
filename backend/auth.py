import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
import models

logger = logging.getLogger(__name__)

# ── Signing key ────────────────────────────────────────────────────────────────
# Every session token is an HS256 JWT signed with this key, so whoever knows it
# can sign a token for any account, the admin included. Values that have been
# printed in LPM's own READMEs, compose files and stack templates are public:
# refuse them outright instead of running an instance anyone can take over.
_EXAMPLE_KEYS = {
    "lanparty-secret-change-me",
    "change-me-to-a-long-random-string",
    "une-longue-chaine-aleatoire-a-changer",
    "a-long-random-string",
    "your-secret",
    "change-me",
    "changeme",
    "secret",
}
MIN_KEY_LENGTH = 16
RECOMMENDED_KEY_LENGTH = 32
# Next to the database, so it lives on the same persisted volume (./data).
# Not part of backups (those hold lanparty.db and uploads/ only): an instance
# restored elsewhere just generates a new key, and everyone signs in again.
SECRET_KEY_FILE = os.getenv("SECRET_KEY_FILE", os.path.join("data", "secret_key"))
_GENERATE_HINT = 'python -c "import secrets; print(secrets.token_hex(32))"'


def _load_secret_key() -> str:
    """SECRET_KEY from the environment if set, otherwise the one generated on
    a previous start, otherwise a new random one written to SECRET_KEY_FILE.

    Empty counts as unset: Portainer turns `${SECRET_KEY:-...}` into an empty
    string, which used to make the backend exit and nginx answer 502."""
    key = (os.getenv("SECRET_KEY") or "").strip()
    if key:
        if key.lower() in _EXAMPLE_KEYS:
            raise RuntimeError(
                "SECRET_KEY is an example value from the documentation: anyone could forge "
                "session tokens with it. Remove SECRET_KEY to let LPM generate a key, or set "
                f"your own random one: {_GENERATE_HINT}"
            )
        if len(key) < MIN_KEY_LENGTH:
            raise RuntimeError(
                f"SECRET_KEY is shorter than {MIN_KEY_LENGTH} characters. Remove it to let LPM "
                f"generate a key, or set a random one: {_GENERATE_HINT}"
            )
        if len(key) < RECOMMENDED_KEY_LENGTH:
            logger.warning(
                "SECRET_KEY is shorter than %d characters; a random 64-character key is "
                "recommended (%s).", RECOMMENDED_KEY_LENGTH, _GENERATE_HINT,
            )
        return key

    path = Path(SECRET_KEY_FILE)
    if path.exists():
        stored = path.read_text(encoding="utf-8").strip()
        if not stored:
            raise RuntimeError(f"{path} is empty. Delete it to have a new key generated.")
        return stored

    path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_hex(32)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Created between the exists() check and here — use that one.
        return _load_secret_key()
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(generated)
    logger.warning(
        "SECRET_KEY is not set: generated a random key and saved it to %s. Keep that "
        "file with the database; deleting it signs everyone out.", path,
    )
    return generated


SECRET_KEY = _load_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30
# The `typ` claim keeps session tokens apart from the other things signed with
# the same key (OAuth state, Discord link tickets): only "access" logs in.
TOKEN_TYPE_ACCESS = "access"

_bearer = HTTPBearer()

# We call bcrypt directly instead of via passlib. passlib 1.7.4 is unmaintained
# and its bcrypt-version probing is what forced the old `bcrypt==3.2.2` pin.
# The hash format is identical ($2b$), so passwords hashed by the previous
# passlib-based code still verify unchanged. Input is UTF-8 encoded; bcrypt
# ignores bytes past 72 (schemas already reject passwords longer than that).


# Sentinel stored in `hashed_password` for accounts that have no password at all
# (created via Discord SSO). It isn't a valid bcrypt hash, so `verify_password`
# raises ValueError on it — which every password check already treats as "wrong
# password". This keeps `hashed_password` NOT NULL without a schema change and
# lets us detect password-less accounts (see `has_usable_password`).
UNUSABLE_PASSWORD = "!"


def verify_password(plain: str, hashed: str) -> bool:
    # bcrypt.checkpw raises ValueError on a malformed hash — callers that pass
    # untrusted input (login, change-password) already guard against that.
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def has_usable_password(hashed: Optional[str]) -> bool:
    """True if the stored hash is a real bcrypt hash (i.e. the user can log in
    with a password), False for the Discord-only sentinel."""
    return bool(hashed) and hashed.startswith("$2")


# ── Session tokens ─────────────────────────────────────────────────────────────
# A token carries the account's `token_version` (`tv`). Bumping the column
# (revoke_sessions) makes every token issued before it invalid at once: that's
# how a password change, a reset or a deactivation actually ends a stolen
# session. Tokens without `tv`/`typ` (issued before 1.3.4) are refused, so the
# upgrade itself signs everyone out once.

def create_access_token(user: models.User, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    payload = {
        "sub": str(user.id),
        "typ": TOKEN_TYPE_ACCESS,
        "tv": user.token_version or 0,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def revoke_sessions(user: models.User) -> None:
    """Invalidate every token issued so far for `user` (caller commits)."""
    user.token_version = (user.token_version or 0) + 1


def invalidate_reset_tokens(db: Session, user_id: int) -> None:
    """Mark every still-unused password-reset link of `user_id` as used, so a
    link sent before a password change can't undo it (caller commits)."""
    db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.user_id == user_id,
        models.PasswordResetToken.used_at.is_(None),
    ).update({models.PasswordResetToken.used_at: datetime.utcnow()}, synchronize_session=False)


def user_from_token(db: Session, token: str) -> Optional[models.User]:
    """The active user a session token belongs to, or None if the token is
    invalid, expired, of another type, or revoked."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("typ") != TOKEN_TYPE_ACCESS:
        return None
    try:
        user_id = int(payload["sub"])
        token_version = int(payload["tv"])
    except (KeyError, TypeError, ValueError):
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active or (user.token_version or 0) != token_version:
        return None
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User:
    user = user_from_token(db, credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_treasurer(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role not in ("treasurer", "admin"):
        raise HTTPException(status_code=403, detail="Treasurer or admin role required")
    return current_user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


# ── WebSocket sessions ─────────────────────────────────────────────────────────
# A browser can't set an Authorization header on a WebSocket, and a token in
# the URL lands in nginx's and uvicorn's access logs. So the client connects
# bare and sends {"type": "auth", "token": "..."} as its first frame.

WS_AUTH_TIMEOUT = 10  # seconds a client gets to send its auth frame
WS_CLOSE_UNAUTHORIZED = 4401
# How often (in push-loop ticks) an open socket re-checks that its session is
# still valid — a deactivation or password change must end it, not just block
# the next reconnect.
WS_RECHECK_EVERY = 15


async def _close_quietly(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except Exception:
        pass  # already gone


async def authenticate_websocket(websocket: WebSocket) -> Optional[tuple[int, int]]:
    """Accept the socket, read its auth frame, and return (user_id,
    token_version) — or close it with 4401 and return None."""
    await websocket.accept()
    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=WS_AUTH_TIMEOUT)
    except Exception:  # timeout, disconnect, binary or non-JSON frame
        await _close_quietly(websocket, WS_CLOSE_UNAUTHORIZED)
        return None
    token = data.get("token") if isinstance(data, dict) and data.get("type") == "auth" else None
    if not isinstance(token, str):
        await _close_quietly(websocket, WS_CLOSE_UNAUTHORIZED)
        return None
    db = SessionLocal()
    try:
        user = user_from_token(db, token)
        result = (user.id, user.token_version or 0) if user else None
    finally:
        db.close()
    if result is None:
        await _close_quietly(websocket, WS_CLOSE_UNAUTHORIZED)
    return result


def session_still_valid(db: Session, user_id: int, token_version: int) -> bool:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return user is not None and user.is_active and (user.token_version or 0) == token_version


async def close_unauthorized(websocket: WebSocket) -> None:
    await _close_quietly(websocket, WS_CLOSE_UNAUTHORIZED)
