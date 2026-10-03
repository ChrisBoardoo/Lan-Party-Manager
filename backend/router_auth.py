import hashlib
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import parse_qs, quote, urlparse

from jose import JWTError, jwt

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import User, PasswordResetToken
from schemas import (
    UserCreate, UserLogin, UserOut, ForgotPasswordRequest, ResetPasswordConfirm, DiscordLinkTicketRequest,
    RESERVED_USERNAME_PREFIX,
)
from auth import (
    ALGORITHM,
    SECRET_KEY,
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    has_usable_password,
    invalidate_reset_tokens,
    revoke_sessions,
    UNUSABLE_PASSWORD,
)
from limiter import limiter
from router_events import _rsvp_in, lookup_event_invite
from router_settings import get_setting
from mailer import send_email, render_template
import oauth_discord
import oauth_state
import oauth_steam

router = APIRouter()

RESET_TOKEN_TTL = timedelta(hours=1)
DEFAULT_RESET_SUBJECT = "Reset your LAN Party Manager password"
DEFAULT_RESET_BODY = (
    "Hi {{username}},\n\n"
    "Someone requested a password reset for your account. If this was you, "
    "click the link below within the next hour:\n\n"
    "{{reset_link}}\n\n"
    "If you didn't request this, you can safely ignore this email."
)


@router.get("/invite-required")
def invite_required(db: Session = Depends(get_db)):
    return {"required": db.query(User).count() > 0}


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit("10/minute")
def register(request: Request, data: UserCreate, db: Session = Depends(get_db)):
    is_first = db.query(User).count() == 0

    # After the first (admin) user, every registration needs a valid event invite code
    event = None
    if not is_first:
        if not data.invite_code:
            raise HTTPException(403, "An invite code is required to register")
        event, full = lookup_event_invite(db, data.invite_code)
        if not event:
            raise HTTPException(403, "Invalid invite code")
        if full:
            raise HTTPException(403, "This event is full")
        if not data.arrival_date or not data.departure_date:
            raise HTTPException(400, "Arrival and departure dates are required")

    # Case-insensitive, so "Admin" and "ADMIN" can't coexist in rosters and chat.
    if db.query(User).filter(func.lower(User.username) == data.username.lower()).first():
        raise HTTPException(400, "Username already taken")
    # Case-insensitive: data.email is already normalised to lowercase, but match
    # func.lower(email) so a legacy mixed-case row still blocks a duplicate.
    if db.query(User).filter(func.lower(User.email) == data.email).first():
        raise HTTPException(400, "Email already registered")

    role = "admin" if is_first else "user"

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=get_password_hash(data.password),
        role=role,
    )
    db.add(user)
    db.flush()  # get user.id before commit

    if event is not None:
        _rsvp_in(db, event, user.id, data.arrival_date, data.departure_date)

    db.commit()
    db.refresh(user)
    return user


# Checked against when the account doesn't exist (or has no password), so a
# failed login takes the same time either way. Computed once at startup.
_DUMMY_HASH = get_password_hash(secrets.token_urlsafe(16))


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    ident = data.identifier.strip()
    # '@' is reserved out of usernames, so it unambiguously marks an email.
    # Email match is case-insensitive; username match stays exact.
    if "@" in ident:
        user = db.query(User).filter(func.lower(User.email) == ident.lower()).first()
    else:
        user = db.query(User).filter(User.username == ident).first()
    # Always pay for one bcrypt check, account or not: answering an unknown
    # name faster than a wrong password told which names and e-mails exist.
    hashed = user.hashed_password if user is not None and has_usable_password(user.hashed_password) else _DUMMY_HASH
    try:
        password_ok = verify_password(data.password, hashed) and hashed is not _DUMMY_HASH
    except ValueError:  # a malformed stored hash
        password_ok = False
    if not password_ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserOut.model_validate(user),
    }


@router.post("/refresh")
def refresh(current_user: User = Depends(get_current_user)):
    """Trade a still-valid token for a fresh one with a new full-length expiry.

    Lets a long-lived client (desktop tray app, PWA, mobile) stay signed in
    indefinitely by calling this periodically — e.g. on every app open, or on
    a daily timer — instead of forcing a password re-entry once the original
    token's 30 days are up. Requires the *current* token to still be valid;
    an already-expired token can't refresh itself, only a fresh login can.
    """
    token = create_access_token(current_user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserOut.model_validate(current_user),
    }


def reset_token_digest(token: str) -> str:
    """Reset links are stored as a SHA-256 of their token: the database (and
    its daily backups) never hold a link that works."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/forgot-password")
@limiter.limit("5/minute")
def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    generic_response = {"detail": "If that email is registered, a reset link has been sent."}

    user = db.query(User).filter(func.lower(User.email) == data.email).first()
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(
            user_id=user.id,
            token=reset_token_digest(token),
            expires_at=datetime.utcnow() + RESET_TOKEN_TTL,
        ))
        db.commit()

        base_url = get_setting(db, "app_base_url") or ""
        # In the fragment, which browsers never send to the server: the link
        # stays out of nginx's access log and out of Referer headers.
        reset_link = f"{base_url.rstrip('/')}/reset-password#token={token}"
        subject_tpl = DEFAULT_RESET_SUBJECT
        body_tpl = DEFAULT_RESET_BODY
        context = {"username": user.username, "reset_link": reset_link}
        # After the response, on its own session: sending through SMTP takes
        # seconds, and only for a real account — answering only once it was
        # done told which e-mails are registered.
        background_tasks.add_task(
            _send_reset_email, user.email,
            render_template(subject_tpl, **context), render_template(body_tpl, **context),
        )

    # Always return the same response, regardless of whether the email exists —
    # anything else would let a caller learn which emails are registered accounts.
    return generic_response


def _send_reset_email(to_address: str, subject: str, body: str) -> None:
    db = SessionLocal()
    try:
        send_email(db, to_address, subject, body)
    finally:
        db.close()


@router.post("/reset-password")
@limiter.limit("10/minute")
def reset_password(request: Request, data: ResetPasswordConfirm, db: Session = Depends(get_db)):
    reset_token = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token == reset_token_digest(data.token))
        .first()
    )
    if (
        not reset_token
        or reset_token.used_at is not None
        or reset_token.expires_at < datetime.utcnow()
    ):
        raise HTTPException(400, "This reset link is invalid or has expired")

    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(400, "This reset link is invalid or has expired")

    user.hashed_password = get_password_hash(data.new_password)
    # A reset is what someone does after losing control of the account: end
    # every session, and kill the other reset links still in flight.
    revoke_sessions(user)
    invalidate_reset_tokens(db, user.id)
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# ── Discord SSO ────────────────────────────────────────────────────────────────

def _discord_enabled(db: Session) -> bool:
    return (
        get_setting(db, "discord_oauth_enabled") == "true"
        and bool(get_setting(db, "discord_oauth_client_id"))
        and bool(get_setting(db, "discord_oauth_client_secret"))
    )


def _app_base_url(db: Session) -> str:
    return (get_setting(db, "app_base_url") or "").rstrip("/")


def _discord_redirect_uri(db: Session) -> str:
    return f"{_app_base_url(db)}/api/auth/discord/callback"


def _require_discord(db: Session) -> None:
    if not _discord_enabled(db):
        raise HTTPException(404, "Discord sign-in is not enabled")
    if not _app_base_url(db):
        raise HTTPException(400, "App base URL is not configured (Settings → app_base_url)")


def _front_redirect(base: str, path: str) -> RedirectResponse:
    # 303 so the browser follows with GET regardless of how it arrived here.
    return RedirectResponse(url=f"{base}{path}", status_code=303)


# What the desktop app sends as `desktop_nonce`: 32 random bytes, hex-encoded.
# Bounded so nothing else rides along in the signed state.
DESKTOP_NONCE_PATTERN = r"^[A-Za-z0-9]{32,128}$"


def _complete_redirect(base: str, path: str, st: dict) -> RedirectResponse:
    """Like `_front_redirect`, but when the flow was started by the desktop
    app (`desktop_port` in the verified state `st`), sends the browser to its
    local loopback listener instead of the LPM frontend — see
    desktopapp/src-tauri/src/main.rs's `start_oauth_auth`. `path` (e.g.
    `/auth/discord/complete#token=...` or `/profile?discord=linked`) is carried
    through as a single `target` query param, which the shell resolves against
    the server's origin before navigating the desktop app's main iframe there.

    `desktop_nonce` goes back alongside it. The app's listener accepts any
    connection on 127.0.0.1, so without it any local program could feed it a
    `target` — a token for another account (login CSRF) or, before the shell
    checked the origin, an arbitrary page. Desktop 1.3.2+ ignores a callback
    whose nonce doesn't match the one it generated; older apps don't send one,
    and simply get no nonce back."""
    desktop_port = st.get("desktop_port")
    if desktop_port:
        url = f"http://127.0.0.1:{desktop_port}/callback?target={quote(path, safe='')}"
        nonce = st.get("desktop_nonce")
        if nonce:
            url += f"&nonce={quote(nonce, safe='')}"
        return RedirectResponse(url=url, status_code=303)
    return _front_redirect(base, path)


# Browser binding for the web OAuth flows. The signed state proves the
# callback comes from a flow *we* started, not that it comes back to the
# browser that started it: without this, someone could start a link flow on
# their own account and get a victim to finish it, attaching the victim's
# Discord/Steam to the attacker's account. The start request (a same-origin
# XHR) sets a random cookie, the state carries the same value, the callback
# (a top-level GET, so a Lax cookie is sent) must present both. The desktop
# flow is started by the app itself, not a browser, and relies on its
# desktop_nonce instead.
OAUTH_BIND_COOKIE = "lpm_oauth_bind"


def _bind_browser(request: Request, response: Response, desktop_port) -> str | None:
    if desktop_port:
        return None
    value = secrets.token_urlsafe(16)
    response.set_cookie(
        OAUTH_BIND_COOKIE, value, max_age=int(oauth_state.STATE_TTL.total_seconds()),
        httponly=True, samesite="lax", secure=request.url.scheme == "https", path="/api/auth",
    )
    return value


def _same_browser(request: Request, st: dict) -> bool:
    expected = st.get("bind")
    if not expected:
        return True  # desktop flow, or a state signed before 1.3.4
    got = request.cookies.get(OAUTH_BIND_COOKIE, "")
    return secrets.compare_digest(got.encode("utf-8"), expected.encode("utf-8"))


def _unique_username(db: Session, raw: str) -> str:
    """Derive a valid, unique username from a Discord display name.

    Strips characters our username rules forbid ('@'/whitespace and anything
    outside [A-Za-z0-9_-]), pads short names, then appends a numeric suffix
    until it's unique."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", raw or "")
    if cleaned.lower().startswith(RESERVED_USERNAME_PREFIX):  # kept for deleted accounts
        cleaned = cleaned[len(RESERVED_USERNAME_PREFIX):]
    if len(cleaned) < 3:
        cleaned = (cleaned + "player")[:16] or "player"
    cleaned = cleaned[:40]
    candidate = cleaned
    n = 1
    while db.query(User).filter(func.lower(User.username) == candidate.lower()).first():
        suffix = str(n)
        candidate = f"{cleaned[: 50 - len(suffix)]}{suffix}"
        n += 1
    return candidate


@router.get("/discord/config")
def discord_config(db: Session = Depends(get_db)):
    """Public: lets the guest Login/Register pages decide whether to show the
    'Continue with Discord' button. Never exposes the client secret."""
    return {"enabled": _discord_enabled(db)}


@router.get("/discord/authorize")
@limiter.limit("20/minute")
def discord_authorize(
    request: Request,
    response: Response,
    code: str | None = None,
    desktop_port: int | None = None,
    desktop_nonce: str | None = Query(None, pattern=DESKTOP_NONCE_PATTERN),
    db: Session = Depends(get_db),
):
    """Start the login/registration flow. `code` is an optional event invite
    code, carried through the signed state so the callback can gate account
    creation on it. `desktop_port` is set only by the desktop app (see
    `_complete_redirect`) — absent for every normal browser caller, as is
    `desktop_nonce`."""
    _require_discord(db)
    state = oauth_discord.sign_state({
        "flow": "login", "invite_code": code,
        "desktop_port": desktop_port, "desktop_nonce": desktop_nonce,
        "bind": _bind_browser(request, response, desktop_port),
    })
    url = oauth_discord.build_authorize_url(
        get_setting(db, "discord_oauth_client_id"), _discord_redirect_uri(db), state
    )
    return {"authorize_url": url}


# A linked Discord is a second way into the account, so starting a link takes
# the password, not just a session: a token lifted from a log or a borrowed
# laptop must not be enough to plant the attacker's Discord on the account.
# The password is checked here and traded for a short ticket, because the link
# start itself is a GET the desktop app makes on the user's behalf — it
# forwards the ticket in the `code` param it already sends (the invite-code
# slot of the login flow), so desktop builds from before this change still work.
DISCORD_LINK_TICKET_TTL = timedelta(minutes=5)
DISCORD_LINK_TICKET_TYPE = "discord_link"


@router.post("/discord/link-ticket")
@limiter.limit("10/minute")
def discord_link_ticket(
    request: Request,
    data: DiscordLinkTicketRequest,
    current_user: User = Depends(get_current_user),
):
    if current_user.discord_id:
        raise HTTPException(409, "A Discord account is already linked; unlink it first")
    try:
        password_ok = verify_password(data.password, current_user.hashed_password)
    except ValueError:  # Discord-only account: no password to check
        password_ok = False
    if not password_ok:
        raise HTTPException(400, "Password is incorrect")
    ticket = jwt.encode(
        {
            "sub": str(current_user.id),
            "typ": DISCORD_LINK_TICKET_TYPE,
            "tv": current_user.token_version or 0,
            "exp": datetime.utcnow() + DISCORD_LINK_TICKET_TTL,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return {"ticket": ticket}


def _check_link_ticket(ticket: str | None, user: User) -> None:
    try:
        payload = jwt.decode(ticket or "", SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        payload = {}
    if (
        payload.get("typ") != DISCORD_LINK_TICKET_TYPE
        or payload.get("sub") != str(user.id)
        or payload.get("tv") != (user.token_version or 0)
    ):
        raise HTTPException(403, "Confirm your password to link Discord")


@router.get("/discord/link")
@limiter.limit("20/minute")
def discord_link(
    request: Request,
    response: Response,
    code: str | None = None,
    desktop_port: int | None = None,
    desktop_nonce: str | None = Query(None, pattern=DESKTOP_NONCE_PATTERN),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start the link flow for a logged-in user. `code` is the ticket from
    `/discord/link-ticket` (password confirmed). The signed state carries the
    user id so the callback attaches Discord to the right account.
    `desktop_port`/`desktop_nonce` — see `discord_authorize`."""
    _require_discord(db)
    _check_link_ticket(code, current_user)
    if current_user.discord_id:
        raise HTTPException(409, "A Discord account is already linked; unlink it first")
    state = oauth_discord.sign_state({
        "flow": "link", "user_id": current_user.id,
        "desktop_port": desktop_port, "desktop_nonce": desktop_nonce,
        "bind": _bind_browser(request, response, desktop_port),
    })
    url = oauth_discord.build_authorize_url(
        get_setting(db, "discord_oauth_client_id"), _discord_redirect_uri(db), state
    )
    return {"authorize_url": url}


@router.delete("/discord/link")
def discord_unlink(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlink Discord from the current account. Refused if the account has no
    usable password, since that would lock the user out entirely."""
    if not current_user.discord_id:
        raise HTTPException(400, "No Discord account is linked")
    if not has_usable_password(current_user.hashed_password):
        raise HTTPException(
            400,
            "Set a password first (use 'Forgot password') before unlinking Discord, "
            "otherwise you'd lose access to this account.",
        )
    current_user.discord_id = None
    current_user.discord_username = None
    current_user.discord_avatar = None
    db.commit()
    return {"ok": True}


@router.get("/discord/callback")
@limiter.limit("20/minute")
def discord_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    base = _app_base_url(db)
    if error or not code or not state:
        return _front_redirect(base, "/login?discord=error")
    try:
        st = oauth_discord.verify_state(state)
    except oauth_discord.DiscordOAuthError:
        return _front_redirect(base, "/login?discord=error")
    if not _same_browser(request, st):
        return _front_redirect(base, "/login?discord=error")

    flow = st.get("flow")
    link_target = "/profile" if flow == "link" else "/login"

    try:
        token = oauth_discord.exchange_code(
            get_setting(db, "discord_oauth_client_id"),
            get_setting(db, "discord_oauth_client_secret"),
            code,
            _discord_redirect_uri(db),
        )
        profile = oauth_discord.fetch_user(token["access_token"])
    except oauth_discord.DiscordOAuthError:
        return _complete_redirect(base, f"{link_target}?discord=error", st)

    discord_id = str(profile.get("id") or "")
    if not discord_id:
        return _complete_redirect(base, f"{link_target}?discord=error", st)
    discord_username = profile.get("global_name") or profile.get("username")
    discord_avatar = profile.get("avatar")
    email = profile.get("email")
    email_verified = bool(profile.get("verified"))

    # ── Link flow: attach Discord to the user named in the (trusted) state ──
    if flow == "link":
        user = db.query(User).filter(User.id == st.get("user_id")).first()
        if not user:
            return _complete_redirect(base, "/login?discord=error", st)
        clash = (
            db.query(User)
            .filter(User.discord_id == discord_id, User.id != user.id)
            .first()
        )
        if clash:
            return _complete_redirect(base, "/profile?discord=already_linked", st)
        # Never swap one Discord for another in place: replacing a link has to
        # go through an explicit unlink (which needs a usable password).
        if user.discord_id and user.discord_id != discord_id:
            return _complete_redirect(base, "/profile?discord=error", st)
        user.discord_id = discord_id
        user.discord_username = discord_username
        user.discord_avatar = discord_avatar
        db.commit()
        return _complete_redirect(base, "/profile?discord=linked", st)

    # ── Login / register flow ──
    user = db.query(User).filter(User.discord_id == discord_id).first()

    # An existing account with the same e-mail is NOT linked automatically:
    # LPM never verifies the e-mail typed at registration, so whoever typed it
    # first (and knows that account's password) would get the Discord
    # user's sessions too. Its owner signs in with the password and links
    # Discord from the profile instead. Only said for an e-mail Discord
    # verified, so it can't be used to probe which addresses are registered.
    if user is None and email and email_verified:
        if db.query(User).filter(func.lower(User.email) == email.lower()).first():
            return _complete_redirect(base, "/login?discord=link_required", st)

    if user is None:
        try:
            user = _create_discord_user(
                db, st.get("invite_code"), discord_id, discord_username, discord_avatar,
                email, email_verified,
            )
        except HTTPException as exc:
            reason = "invite_required" if exc.status_code == 403 else "error"
            return _complete_redirect(base, f"/register?discord={reason}", st)

    if not user.is_active:
        return _complete_redirect(base, "/login?discord=deactivated", st)

    jwt_token = create_access_token(user)
    # Hand the JWT to the SPA via the URL fragment (never sent to the server, so
    # it can't leak into access logs); a small front-end page reads and stores it.
    return _complete_redirect(base, f"/auth/discord/complete#token={jwt_token}", st)


def _create_discord_user(
    db: Session, invite_code, discord_id, discord_username, discord_avatar, email, email_verified
) -> User:
    """Create a brand-new account from a Discord profile, gated by the event
    invite code (except for the very first/bootstrap user). Auto-RSVPs into the
    invite's event using the full event window as default dates."""
    is_first = db.query(User).count() == 0

    event = None
    if not is_first:
        if not invite_code:
            raise HTTPException(403, "An invite code is required to register")
        event, full = lookup_event_invite(db, invite_code)
        if not event:
            raise HTTPException(403, "Invalid invite code")
        if full:
            raise HTTPException(400, "This event is full")

    # Discord may omit email (scope declined) — fall back to a non-routable
    # placeholder so the NOT NULL / unique constraint holds. Such accounts sign
    # in with Discord only.
    user_email = email if email else f"discord_{discord_id}@no-email.local"
    if db.query(User).filter(func.lower(User.email) == user_email.lower()).first():
        user_email = f"discord_{discord_id}@no-email.local"

    user = User(
        username=_unique_username(db, discord_username or f"player{discord_id[-4:]}"),
        email=user_email,
        hashed_password=UNUSABLE_PASSWORD,  # no password; Discord-only
        role="admin" if is_first else "user",
        discord_id=discord_id,
        discord_username=discord_username,
        discord_avatar=discord_avatar,
    )
    db.add(user)
    db.flush()

    if event is not None:
        _rsvp_in(db, event, user.id, event.start_date, event.end_date)

    db.commit()
    db.refresh(user)
    return user


# ── Steam Link ─────────────────────────────────────────────────────────────────
# Link-only — no sign-up/login via Steam. Steam's OpenID identity carries no
# email, so provisioning a brand-new account the way `_create_discord_user`
# does would need its own placeholder-email logic for a flow nobody asked for;
# a member links Steam to an *existing* LPM account from their profile instead.
# See md/2.features/Steam_Link.md for the full design.

def _steam_enabled(db: Session) -> bool:
    return (
        get_setting(db, "steam_link_enabled") == "true"
        and bool(get_setting(db, "steam_web_api_key"))
    )


def _steam_return_to(db: Session) -> str:
    return f"{_app_base_url(db)}/api/auth/steam/callback"


def _steam_return_to_matches(db: Session, return_to: str, state: str) -> bool:
    """The assertion's return_to is the exact callback URL we sent Steam,
    carrying this very state."""
    got, expected = urlparse(return_to), urlparse(_steam_return_to(db))
    return (
        (got.scheme, got.netloc, got.path) == (expected.scheme, expected.netloc, expected.path)
        and parse_qs(got.query).get("state") == [state]
    )


def _require_steam(db: Session) -> None:
    if not _steam_enabled(db):
        raise HTTPException(404, "Steam linking is not enabled")
    if not _app_base_url(db):
        raise HTTPException(400, "App base URL is not configured (Settings → app_base_url)")


@router.get("/steam/config")
def steam_config(db: Session = Depends(get_db)):
    """Public: lets Profile decide whether to show the 'Link Steam' button.
    Never exposes the Web API key."""
    return {"enabled": _steam_enabled(db)}


@router.get("/steam/link")
@limiter.limit("20/minute")
def steam_link(
    request: Request,
    response: Response,
    desktop_port: int | None = None,
    desktop_nonce: str | None = Query(None, pattern=DESKTOP_NONCE_PATTERN),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start the Steam link flow for the logged-in user. OpenID 2.0 has no
    native `state` param like OAuth2, so the signed flow context (which user
    is linking, `desktop_port`, `desktop_nonce`) is carried inside our own `openid.return_to`
    URL instead of a separate parameter Steam would forward untouched."""
    _require_steam(db)
    state = oauth_steam.sign_state({
        "user_id": current_user.id, "desktop_port": desktop_port, "desktop_nonce": desktop_nonce,
        "bind": _bind_browser(request, response, desktop_port),
    })
    return_to = f"{_steam_return_to(db)}?state={quote(state, safe='')}"
    url = oauth_steam.build_login_url(return_to, _app_base_url(db))
    return {"authorize_url": url}


@router.delete("/steam/link")
def steam_unlink(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlink Steam from the current account. Unlike Discord, there's no
    'would lock you out' guard needed: Steam can never be the account's only
    way in, since there's no sign-up-via-Steam flow to have created one."""
    if not current_user.steam_id:
        raise HTTPException(400, "No Steam account is linked")
    current_user.steam_id = None
    current_user.steam_username = None
    current_user.steam_avatar = None
    db.commit()
    return {"ok": True}


@router.get("/steam/callback")
@limiter.limit("20/minute")
def steam_callback(request: Request, db: Session = Depends(get_db)):
    base = _app_base_url(db)
    params = dict(request.query_params)
    state = params.get("state")
    # Steam's positive-assertion mode is "id_res"; a cancelled/failed login
    # comes back as "cancel" (or the mode/state are simply missing).
    if not state or params.get("openid.mode") != "id_res":
        return _front_redirect(base, "/profile?steam=error")
    try:
        st = oauth_steam.verify_state(state)
    except oauth_steam.SteamOAuthError:
        return _front_redirect(base, "/profile?steam=error")
    if not _same_browser(request, st):
        return _front_redirect(base, "/profile?steam=error")
    # A Steam-signed assertion is only valid for the site it was issued to:
    # without this check, one obtained on any other "Sign in through Steam"
    # site could be replayed here to link someone else's SteamID.
    if not _steam_return_to_matches(db, params.get("openid.return_to", ""), state):
        return _complete_redirect(base, "/profile?steam=error", st)


    try:
        verified = oauth_steam.verify_openid_response(params)
    except oauth_steam.SteamOAuthError:
        return _complete_redirect(base, "/profile?steam=error", st)
    if not verified:
        return _complete_redirect(base, "/profile?steam=error", st)

    steam_id = oauth_steam.extract_steam_id(params.get("openid.claimed_id", ""))
    if not steam_id:
        return _complete_redirect(base, "/profile?steam=error", st)

    user = db.query(User).filter(User.id == st.get("user_id")).first()
    if not user:
        return _complete_redirect(base, "/login?steam=error", st)

    clash = db.query(User).filter(User.steam_id == steam_id, User.id != user.id).first()
    if clash:
        return _complete_redirect(base, "/profile?steam=already_linked", st)

    # Display fields are best-effort — a summary-fetch failure shouldn't sink
    # an otherwise-verified link.
    api_key = get_setting(db, "steam_web_api_key")
    summary = {}
    if api_key:
        try:
            summary = oauth_steam.fetch_player_summary(steam_id, api_key)
        except oauth_steam.SteamOAuthError:
            summary = {}

    user.steam_id = steam_id
    user.steam_username = summary.get("personaname")
    user.steam_avatar = summary.get("avatarfull")
    db.commit()
    return _complete_redirect(base, "/profile?steam=linked", st)
