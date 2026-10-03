from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
import secrets

from database import get_db
from models import Game, User
from schemas import (
    BadgeOut, DeletedUserOut, UserGameStatsLine, UserOut, UserPublic, UserUpdate, UserPasswordChange,
    RESERVED_USERNAME_PREFIX,
)
from auth import (
    create_access_token,
    get_current_user,
    get_password_hash,
    invalidate_reset_tokens,
    require_admin,
    revoke_sessions,
    verify_password,
    UNUSABLE_PASSWORD,
)
from activity import add_audit
from limiter import limiter
from badges import user_badges
from riot_id import parse_riot_id
from router_lol import link_captured_players
from router_presence import is_user_online
from router_settings import is_feature_enabled, require_feature
from tournament_stats import linked_tournaments, player_game_records
from uploads import remove_upload, rotate_image_file, save_image_upload

router = APIRouter()


@router.get("/", response_model=list[UserPublic])
def get_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    # Roster is a public view — email is never included here (see UserPublic).
    # To see a member's email, an admin opens that member's profile below.
    #
    # A deleted account never appears here, even to an admin — it has no
    # identity left worth showing in the live crew list (the row's username
    # is scrubbed to "deleted_user_N"). Admins see it via the dedicated
    # history endpoint below instead. A merely *deactivated* (not deleted)
    # account still shows for an admin, same as before, so they can reactivate it.
    query = db.query(User).filter(User.deleted_at.is_(None))
    if current_user.role != "admin":
        query = query.filter(User.is_active == True)  # noqa: E712
    users = query.order_by(User.created_at).offset(offset).limit(limit).all()
    # Annotate the computed "online now" flag (read by UserPublic via getattr).
    for u in users:
        u.is_online = is_user_online(u)
    return users


@router.get("/deleted", response_model=list[DeletedUserOut])
def get_deleted_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """History of deleted accounts, for the admin Settings panel — the same
    place a future "banned" list would live (see md/2.features/ban-feature-idea.md).
    Newest deletion first."""
    return (
        db.query(User)
        .filter(User.deleted_at.isnot(None))
        .order_by(User.deleted_at.desc())
        .all()
    )


@router.get("/{user_id}", response_model=None)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.is_online = is_user_online(user)
    # Email is visible only to the user themselves or an admin.
    if current_user.id == user.id or current_user.role == "admin":
        return UserOut.model_validate(user)
    return UserPublic.model_validate(user)


@router.get("/{user_id}/game-stats", response_model=list[UserGameStatsLine])
def get_user_game_stats(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """A member's tournament record per game (matches, W/L/D, titles), most
    played first. Derived on read from the tournaments they were linked into —
    see tournament_stats.player_game_records for the counting rules."""
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(404, "User not found")
    records = [
        r for r in player_game_records(linked_tournaments(db, user_id=user_id)) if r.user_id == user_id
    ]
    names = (
        {g.id: g.name for g in db.query(Game).filter(Game.id.in_({r.game_id for r in records})).all()}
        if records else {}
    )
    records.sort(key=lambda r: (-r.played, -r.wins, names.get(r.game_id, "").lower()))
    return [
        UserGameStatsLine(
            game_id=r.game_id, name=names[r.game_id], played=r.played, wins=r.wins, losses=r.losses,
            draws=r.draws, win_rate=r.win_rate, tournaments=r.tournaments, titles=r.titles,
        )
        for r in records if r.game_id in names
    ]


@router.get("/{user_id}/badges", response_model=list[BadgeOut])
def get_user_badges(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("recap")),
):
    """A member's all-time badges, for their profile. Part of the recap feature,
    so it's gated with it. Derived on read — there is no achievements table."""
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(404, "User not found")
    return [
        BadgeOut(
            code=a.code, user_id=a.user_id, username=a.username,
            avatar_url=a.avatar_url, value=a.value,
        )
        for a in user_badges(db, user_id)
    ]


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    fields = data.model_dump(exclude_unset=True)

    # Username is unique and used as the login identifier — validate before applying.
    if "username" in fields:
        new_username = (fields.pop("username") or "").strip()
        if len(new_username) < 3:
            raise HTTPException(400, "Username must be at least 3 characters")
        if new_username.lower().startswith(RESERVED_USERNAME_PREFIX):
            raise HTTPException(400, "This username is reserved")
        if new_username != user.username:
            # Case-insensitive, like registration.
            taken = (
                db.query(User)
                .filter(func.lower(User.username) == new_username.lower(), User.id != user.id)
                .first()
            )
            if taken:
                raise HTTPException(400, "Username already taken")
            user.username = new_username

    # Riot ID — already format-checked by UserUpdate (None = clear). Unique on
    # its case-folded key, so a LoL capture can never match two members.
    if "riot_id" in fields:
        new_riot_id = fields.pop("riot_id")
        if new_riot_id is None:
            user.riot_id = None
            user.riot_id_key = None
        else:
            display, key = parse_riot_id(new_riot_id)
            taken = (
                db.query(User)
                .filter(User.riot_id_key == key, User.id != user.id)
                .first()
            )
            if taken:
                raise HTTPException(409, "Riot ID already linked to another member")
            user.riot_id = display
            user.riot_id_key = key
            link_captured_players(db, user)

    for field, value in fields.items():
        setattr(user, field, value)

    # Merch size is opt-out — once a crew turns it off, nobody can supply a
    # clothing_size any more, so it can't stay the sole gate on completeness.
    user.profile_complete = bool(user.clothing_size) or not is_feature_enabled(db, "merch_size")

    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/change-password")
@limiter.limit("10/minute")  # it checks the current password: no free guessing
def change_password(
    request: Request,
    user_id: int,
    data: UserPasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")

    try:
        current_ok = verify_password(data.current_password, current_user.hashed_password)
    except ValueError:
        current_ok = False
    if not current_ok:
        raise HTTPException(400, "Current password is incorrect")

    current_user.hashed_password = get_password_hash(data.new_password)
    # Changing the password is what you do when you think someone else has
    # it: end every session (this one included) and dead-end old reset links.
    # The caller gets a fresh token so their own session carries on.
    revoke_sessions(current_user)
    invalidate_reset_tokens(db, current_user.id)
    db.commit()
    return {"ok": True, "access_token": create_access_token(current_user)}


@router.post("/{user_id}/avatar", response_model=UserOut)
async def upload_avatar(
    user_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    user.avatar_url = await save_image_upload(
        file, subdir=None, prefix=f"avatar_{user_id}", box=(400, 400),
        replaces=user.avatar_url,
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/avatar/rotate", response_model=UserOut)
def rotate_avatar(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if not user.avatar_url:
        raise HTTPException(400, "No avatar to rotate")

    user.avatar_url = rotate_image_file(
        user.avatar_url, subdir=None, prefix=f"avatar_{user_id}",
    )
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.id == user_id:
        raise HTTPException(400, "You cannot deactivate your own account")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    user.is_active = False
    # Reactivating must not bring the old sessions back with it.
    revoke_sessions(user)
    add_audit(db, current_user.id, "user_deactivated", f"User: {user.username}")
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/reactivate", response_model=UserOut)
def reactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.deleted_at is not None:
        raise HTTPException(400, "A deleted account can't be reactivated")

    user.is_active = True
    add_audit(db, current_user.id, "user_reactivated", f"User: {user.username}")
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=UserOut)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Permanently delete a member's account (admin-only).

    Anonymizes rather than hard-deletes the row: `users.id` is referenced
    from money (expenses, settlements), tournaments (organizer), audit
    history, media uploads, and more — a literal row delete would either
    violate a foreign key or (if cascades were added to avoid that) silently
    destroy other members' history along with it. Scrubbing username, email,
    password, Discord link, and avatar frees the username/email for the same
    person to register a brand-new account, while every foreign key into
    this row's id stays valid.
    """
    if current_user.id == user_id:
        raise HTTPException(400, "You cannot delete your own account")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.deleted_at is not None:
        raise HTTPException(400, "This account is already deleted")

    original_username = user.username

    # Deliberately does NOT touch EventRSVP rows. A deleted member already
    # disappears from every event's attendee list and capacity count purely
    # because those queries filter on User.is_active (router_events._enrich,
    # _rsvp_in) — no RSVP-row deletion needed for that. Actually deleting the
    # rows would be actively wrong for prorata: a past event's cost split is
    # settled history keyed on those same RSVP rows (arrival/departure
    # dates), and event_utils.event_prorata_inputs only excludes an inactive
    # member's share for a CURRENT event, leaving past ones exactly as they
    # were — which requires the RSVP row to still exist.
    remove_upload(user.avatar_url)

    anon = f"deleted_user_{user.id}"
    user.deleted_username = original_username
    user.username = anon
    user.email = f"{anon}@deleted.invalid"
    user.hashed_password = UNUSABLE_PASSWORD
    user.avatar_url = None
    user.phone = None
    user.clothing_size = None
    user.discord_id = None
    user.discord_username = None
    user.discord_avatar = None
    user.steam_id = None
    user.steam_username = None
    user.steam_avatar = None
    user.riot_id = None
    user.riot_id_key = None
    user.is_active = False
    user.deleted_at = datetime.utcnow()
    revoke_sessions(user)

    add_audit(db, current_user.id, "user_deleted", f"User: {original_username}")
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.deleted_at is not None:
        raise HTTPException(400, "A deleted account can't be reset")

    temp_password = secrets.token_urlsafe(9)
    user.hashed_password = get_password_hash(temp_password)
    revoke_sessions(user)
    invalidate_reset_tokens(db, user.id)
    add_audit(db, current_user.id, "password_reset", f"User: {user.username}")
    db.commit()

    return {"temp_password": temp_password}


@router.put("/{user_id}/role", response_model=UserOut)
def update_role(
    user_id: int,
    role: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if role not in ("admin", "treasurer", "user"):
        raise HTTPException(400, "Invalid role. Must be admin, treasurer, or user.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.deleted_at is not None:
        raise HTTPException(400, "A deleted account can't be given a role")

    # Never leave the instance without an active admin: recovering from that
    # takes a hand edit of the database.
    if user.role == "admin" and role != "admin":
        other_admins = (
            db.query(User)
            .filter(User.role == "admin", User.is_active == True, User.id != user.id)  # noqa: E712
            .count()
        )
        if other_admins == 0:
            raise HTTPException(400, "This is the last admin: make someone else admin first")

    if user.role != role:
        # Roles grant money (treasurer) or everything (admin): keep a trace,
        # like deactivation, deletion and resets already do.
        add_audit(db, current_user.id, "role_changed", f"User: {user.username} — {user.role} → {role}")
    user.role = role
    db.commit()
    db.refresh(user)
    return user
