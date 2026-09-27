from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import os

from database import get_db
import models

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is not set. Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

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


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise exc
    except JWTError:
        raise exc

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise exc
    return user


def require_treasurer(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role not in ("treasurer", "admin"):
        raise HTTPException(status_code=403, detail="Treasurer or admin role required")
    return current_user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user
