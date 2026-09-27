"""My Setup — a member's gaming PC, and the public link they can share it with.

Gated by the `setup` feature flag (opt-in, default off).

**Owner-mints-own-link, enforced structurally.** Every route that writes the
*owner's* stuff is `/me`. There is deliberately no `/{user_id}/share`, no
`/{user_id}/photos`, no `/{user_id}` PUT. The owner-only rule is enforced by
*the shape of the URL space*, not by an
`if current_user.id != user_id and current_user.role != "admin"`
check — because that check, which is exactly what avatar upload does, is what
would hand an admin the power to publish a public link to somebody else's PC.
If a route cannot name another user, that bug cannot be written.

The one write route that DOES name another user is `POST /{user_id}/react` —
and that's consistent, not an exception: the row it writes belongs to the
*caller* (their own reaction, keyed on current_user.id), never touches the
owner's components, photos or share state, and reacting to someone else's rig
is the entire point. It cannot express the admin-publishes-your-link bug.

So: an admin may read any member's setup in-app (same as any member) and may
switch the whole feature off for the crew. An admin may **not** mint, rotate or
revoke another member's share link, edit their components, or touch their photos.
There is no admin override and no admin UI for it. This is the one place this
feature must not mirror the recap, whose share link is admin-minted because it
belongs to an event rather than a person.

**The share payload never carries PII** beyond a username and an avatar — see
SetupSharedOut. A public URL is the internet.
"""
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session, selectinload

from auth import get_current_user
from database import get_db
from limiter import limiter
from models import SetupReaction, User, UserSetup, UserSetupField, UserSetupPhoto
from router_media import REACTION_EMOJI
from router_settings import is_feature_enabled, require_feature
from schemas import (
    MAX_SETUP_CUSTOM_FIELDS,
    MAX_SETUP_PHOTOS,
    SETUP_FIELDS,
    MediaReact,
    MediaReactionCount,
    SetupComponents,
    SetupFieldOut,
    SetupOut,
    SetupPhotoOut,
    SetupPhotoUpdate,
    SetupShareOut,
    SetupSharedOut,
    SetupUpdate,
)
from uploads import remove_upload, save_image_upload

router = APIRouter()

SETUP_PHOTO_SUBDIR = "setup"
SETUP_PHOTO_BOX = (1600, 1600)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_setup_enabled(db: Session) -> None:
    """Explicit flag check for routes that must respect it even for an admin.

    require_feature lets admins through by design (so they can configure a
    feature before enabling it), which means anything with real-world effect
    beyond the admin's own account has to ask again — the router_gear /
    router_recap pattern. Minting a public URL for a feature the crew has
    switched off is exactly that.
    """
    if not is_feature_enabled(db, "setup"):
        raise HTTPException(404, "This feature is not enabled")


def _load(db: Session, user_id: int) -> Optional[UserSetup]:
    return (
        db.query(UserSetup)
        .options(selectinload(UserSetup.fields), selectinload(UserSetup.photos))
        .filter(UserSetup.user_id == user_id)
        .first()
    )


def _get_or_create(db: Session, user_id: int) -> UserSetup:
    setup = _load(db, user_id)
    if not setup:
        setup = UserSetup(user_id=user_id)
        db.add(setup)
        db.commit()
        db.refresh(setup)
    return setup


def _components(setup: Optional[UserSetup]) -> SetupComponents:
    if not setup:
        return SetupComponents()
    return SetupComponents(**{name: getattr(setup, name) for name in SETUP_FIELDS})


def _sorted_fields(setup: UserSetup) -> List[UserSetupField]:
    return sorted(setup.fields, key=lambda f: (f.sort_order, f.id))


def _sorted_photos(setup: UserSetup) -> List[UserSetupPhoto]:
    return sorted(setup.photos, key=lambda p: (p.sort_order, p.id))


def _has_content(setup: Optional[UserSetup]) -> bool:
    """Whether there's anything worth showing — so a profile can hide an empty
    section rather than render fourteen blank rows."""
    if not setup:
        return False
    return (
        any(getattr(setup, name) for name in SETUP_FIELDS)
        or bool(setup.fields)
        or bool(setup.photos)
    )


def _reaction_counts(db: Session, setup: Optional[UserSetup], viewer_id: int) -> List[MediaReactionCount]:
    """Per-emoji tallies, who's in each, and the viewer's own membership — the
    single-item version of router_media.hydrate_reactions, same ordering rule.
    Every caller here has a session (SetupSharedOut carries no reactions at
    all), so unlike the media version there's no anonymous branch: `users` is
    always populated."""
    if not setup:
        return []
    rows = (
        db.query(SetupReaction.emoji, SetupReaction.user_id, User.username)
        .join(User, User.id == SetupReaction.user_id)
        .filter(SetupReaction.setup_id == setup.id)
        .order_by(SetupReaction.id)  # oldest first, so the tooltip reads in reaction order
        .all()
    )
    tallies: dict[str, MediaReactionCount] = {}
    for emoji, user_id, username in rows:
        tally = tallies.get(emoji)
        if tally is None:
            tally = tallies[emoji] = MediaReactionCount(emoji=emoji, count=0, mine=False)
        tally.count += 1
        tally.users.append(username)
        if user_id == viewer_id:
            tally.mine = True
    counts = list(tallies.values())
    counts.sort(key=lambda c: (-c.count, REACTION_EMOJI.index(c.emoji) if c.emoji in REACTION_EMOJI else 99))
    return counts


def _serialize(db: Session, setup: Optional[UserSetup], user: User, viewer_id: int) -> SetupOut:
    reactions = _reaction_counts(db, setup, viewer_id)
    return SetupOut(
        user_id=user.id,
        username=user.username,
        avatar_url=user.avatar_url,
        components=_components(setup),
        custom_fields=[SetupFieldOut.model_validate(f) for f in (_sorted_fields(setup) if setup else [])],
        photos=[SetupPhotoOut.model_validate(p) for p in (_sorted_photos(setup) if setup else [])],
        has_content=_has_content(setup),
        reactions=reactions,
        reaction_total=sum(c.count for c in reactions),
    )


def require_setup_token(
    x_setup_token: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> UserSetup:
    """Authorize a public setup view by its share token alone — no user session.

    404 when the feature is off, so switching `setup_enabled` off instantly kills
    every live link. 401 on missing or wrong. Header-only, deliberately: a token
    in a query string lands in access logs, browser history and Referer headers.

    Diverges from require_recap_token, which compare_digests every row: there is
    one setup per member and the roster is the whole crew, so this uses the
    indexed lookup (share_token is unique + indexed) and compare_digests the
    single hit. A B-tree probe isn't constant-time, but the token is 192 bits —
    nobody is timing an index to find it. The empty-token guard above is what
    stops `WHERE share_token = ''` doing anything interesting; SQL `= NULL` never
    matches the un-minted rows regardless.
    """
    if not is_feature_enabled(db, "setup"):
        raise HTTPException(404, "This feature is not enabled")
    if not x_setup_token:
        raise HTTPException(401, "Invalid setup token")

    setup = (
        db.query(UserSetup)
        .options(selectinload(UserSetup.fields), selectinload(UserSetup.photos))
        .filter(UserSetup.share_token == x_setup_token)
        .first()
    )
    # compare_digest on bytes: on a non-ASCII str it raises TypeError, which
    # would surface as a 500 instead of a clean 401. The kiosk shipped that bug.
    if not setup or not setup.share_token or not secrets.compare_digest(
        x_setup_token.encode("utf-8"), setup.share_token.encode("utf-8")
    ):
        raise HTTPException(401, "Invalid setup token")
    return setup


# ── Public ────────────────────────────────────────────────────────────────────
# Declared before /{user_id} so "shared" is never parsed as a user id.

@router.get("/shared", response_model=SetupSharedOut)
@limiter.limit("30/minute")
def get_shared_setup(
    request: Request,
    setup: UserSetup = Depends(require_setup_token),
    db: Session = Depends(get_db),
):
    """A setup fetched with a share token — no login. Rate-limited: this is the
    app's newest unauthenticated, DB-touching surface."""
    owner = db.query(User).filter(User.id == setup.user_id).first()
    if not owner:
        raise HTTPException(404, "Setup not found")
    return SetupSharedOut(
        username=owner.username,
        avatar_url=owner.avatar_url,
        components=_components(setup),
        custom_fields=[SetupFieldOut.model_validate(f) for f in _sorted_fields(setup)],
        photos=[SetupPhotoOut.model_validate(p) for p in _sorted_photos(setup)],
    )


# ── The owner's own setup ─────────────────────────────────────────────────────

@router.get("/me", response_model=SetupOut)
def get_my_setup(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("setup")),
):
    """Returns an empty shape rather than 404 when nothing's been saved yet —
    the form has to render before there's a row to render it from."""
    return _serialize(db, _load(db, user.id), user, user.id)


@router.put("/me", response_model=SetupOut)
def update_my_setup(
    data: SetupUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("setup")),
):
    """Save the 14 components and the whole custom-field list in one request.

    Custom fields are replace-all (delete then re-insert, re-enumerating
    sort_order): the simplest correct semantics for a <=10 list, and it makes
    reordering free if we ever want it.
    """
    if len(data.custom_fields) > MAX_SETUP_CUSTOM_FIELDS:
        raise HTTPException(400, f"A setup is limited to {MAX_SETUP_CUSTOM_FIELDS} custom fields")

    setup = _get_or_create(db, user.id)

    for name, value in data.components.model_dump().items():
        setattr(setup, name, (value or "").strip() or None)

    for existing in list(setup.fields):
        db.delete(existing)
    db.flush()
    for i, field in enumerate(data.custom_fields):
        db.add(UserSetupField(
            setup_id=setup.id, label=field.label.strip(),
            value=(field.value or "").strip() or None, sort_order=i,
        ))

    db.commit()
    db.refresh(setup)
    return _serialize(db, _load(db, user.id), user, user.id)


@router.post("/me/photos", response_model=SetupOut)
async def upload_my_setup_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("setup")),
):
    """Add a photo of the rig, up to MAX_SETUP_PHOTOS.

    The cap is checked **before** the file is read. If it ran afterwards, the
    6th upload would still cost a 12 MB buffer and a full decode before being
    refused — bounding storage while not bounding work, which is most of the
    point of having a cap at all.

    (The count can race two concurrent uploads into a 6th row. On SQLite with one
    uvicorn worker that's effectively unreachable, and the worst case is one
    extra photo — not worth a lock.)
    """
    setup = _get_or_create(db, user.id)

    if db.query(UserSetupPhoto).filter(UserSetupPhoto.setup_id == setup.id).count() >= MAX_SETUP_PHOTOS:
        raise HTTPException(400, f"A setup is limited to {MAX_SETUP_PHOTOS} photos")

    url = await save_image_upload(
        file, subdir=SETUP_PHOTO_SUBDIR, prefix=f"setup_{user.id}", box=SETUP_PHOTO_BOX, quality=82,
    )

    # max(existing)+1, not count(): with count(), deleting the middle photo and
    # then uploading collides on sort_order.
    highest = max((p.sort_order or 0 for p in setup.photos), default=-1)
    db.add(UserSetupPhoto(setup_id=setup.id, url=url, sort_order=highest + 1))
    db.commit()
    return _serialize(db, _load(db, user.id), user, user.id)


def _my_photo_or_404(db: Session, user_id: int, photo_id: int) -> UserSetupPhoto:
    """A photo on the caller's OWN setup.

    404 rather than 403 for somebody else's photo id: no reason to confirm it
    exists to a caller who has no business with it. The setup_id match is what
    makes this owner-only — there's no user_id on the route to get wrong.
    """
    setup = _load(db, user_id)
    photo = (
        db.query(UserSetupPhoto)
        .filter(UserSetupPhoto.id == photo_id, UserSetupPhoto.setup_id == (setup.id if setup else None))
        .first()
    )
    if not photo:
        raise HTTPException(404, "Photo not found")
    return photo


@router.patch("/me/photos/{photo_id}", response_model=SetupOut)
def update_my_setup_photo(
    photo_id: int,
    data: SetupPhotoUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("setup")),
):
    """Caption one of my photos. Blank clears it."""
    photo = _my_photo_or_404(db, user.id, photo_id)
    photo.caption = (data.caption or "").strip() or None
    db.commit()
    return _serialize(db, _load(db, user.id), user, user.id)


@router.delete("/me/photos/{photo_id}", response_model=SetupOut)
def delete_my_setup_photo(
    photo_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("setup")),
):
    photo = _my_photo_or_404(db, user.id, photo_id)

    remove_upload(photo.url, SETUP_PHOTO_SUBDIR)
    db.delete(photo)
    db.commit()
    return _serialize(db, _load(db, user.id), user, user.id)


# ── The owner's own share link ────────────────────────────────────────────────

@router.get("/me/share", response_model=SetupShareOut)
def get_my_share(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("setup")),
):
    _require_setup_enabled(db)
    setup = _load(db, user.id)
    return SetupShareOut(token=setup.share_token if setup else None)


@router.post("/me/share", response_model=SetupShareOut)
def mint_my_share(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("setup")),
):
    """Mint or rotate my own public link. Rotating invalidates the old URL
    immediately — that's also how you revoke a link that got out."""
    _require_setup_enabled(db)
    setup = _get_or_create(db, user.id)
    setup.share_token = secrets.token_urlsafe(24)
    setup.share_created_at = datetime.utcnow()
    db.commit()
    return SetupShareOut(token=setup.share_token)


@router.delete("/me/share", response_model=SetupShareOut)
def revoke_my_share(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("setup")),
):
    _require_setup_enabled(db)
    setup = _load(db, user.id)
    if setup:
        setup.share_token = None
        setup.share_created_at = None
        db.commit()
    return SetupShareOut(token=None)


# ── Another member's setup, in-app ────────────────────────────────────────────
# Last, so /shared and /me are never parsed as a user id. Reads — plus /react,
# the one write that names another user; see the module docstring for why that
# doesn't breach the owner-only rule (the row written belongs to the caller).

@router.get("/{user_id}", response_model=SetupOut)
def get_user_setup(
    user_id: int,
    db: Session = Depends(get_db),
    viewer: User = Depends(require_feature("setup")),
):
    owner = db.query(User).filter(User.id == user_id).first()
    if not owner:
        raise HTTPException(404, "User not found")
    return _serialize(db, _load(db, user_id), owner, viewer.id)


@router.post("/{user_id}/react", response_model=SetupOut)
def react_to_setup(
    user_id: int,
    data: MediaReact,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("setup")),
):
    """Toggle one emoji on one member's rig — the router_media.react_to_media
    semantics (toggle, fixed emoji set, unique constraint unreachable). Reacting
    to your own setup is allowed, same as reacting to your own photos.

    404 when the owner has never saved a setup: there's no rig to react to, and
    the UI never shows the bar for an empty section anyway.
    """
    if data.emoji not in REACTION_EMOJI:
        raise HTTPException(400, "Unsupported reaction.")

    owner = db.query(User).filter(User.id == user_id).first()
    if not owner:
        raise HTTPException(404, "User not found")
    setup = _load(db, user_id)
    if not setup:
        raise HTTPException(404, "Setup not found")

    existing = (
        db.query(SetupReaction)
        .filter(
            SetupReaction.setup_id == setup.id,
            SetupReaction.user_id == current_user.id,
            SetupReaction.emoji == data.emoji,
        )
        .first()
    )
    if existing:
        db.delete(existing)
    else:
        db.add(SetupReaction(setup_id=setup.id, user_id=current_user.id, emoji=data.emoji))
    db.commit()

    return _serialize(db, _load(db, user_id), owner, current_user.id)
