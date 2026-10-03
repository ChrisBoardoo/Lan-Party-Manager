from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
from typing import Optional, List, Sequence
from pydantic import BaseModel
import asyncio, os, uuid

from database import get_db
from models import LanEvent, MediaItem, MediaReaction, User
from schemas import MediaItemOut, MediaItemUpdate, MediaReact, MediaReactionCount
from auth import get_current_user
from activity import add_activity
from file_validation import matches_declared
from uploads import UPLOAD_DIR, read_capped, remove_upload

router = APIRouter()
MAX_SIZE = 100 * 1024 * 1024  # 100 MB — a media policy, not an image one

# A fixed set rather than free text: it keeps "best of" scoring meaningful,
# keeps the UI a fixed row of buttons, and keeps arbitrary strings out of the
# database. Mirrored on the frontend in components/MediaReactions.tsx.
REACTION_EMOJI = ("🔥", "😂", "💀", "❤️", "🏆", "👀")


ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "video/mp4", "video/webm", "video/quicktime", "video/x-msvideo",
}

_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "video/x-msvideo": "avi",
}


async def _generate_video_thumbnail(video_path: str, upload_dir: str, base_name: str) -> Optional[str]:
    thumb_dir = os.path.join(upload_dir, "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)
    thumb_name = f"thumb_{base_name}.jpg"
    thumb_path = os.path.join(thumb_dir, thumb_name)
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", video_path, "-ss", "1", "-frames:v", "1", "-q:v", "4", thumb_path, "-y",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)
        if os.path.exists(thumb_path):
            return f"/uploads/thumbnails/{thumb_name}"
    except Exception:
        pass
    return None


def best_media_query(db: Session, event_id: Optional[int] = None):
    """Query for media ordered by how much the room reacted to it, most first.

    Shared with the recap (which needs the identical list for its "best of"),
    so it returns the query rather than the rows — callers apply their own limit.
    Items nobody reacted to aren't "best of" and are excluded by the join.
    """
    totals = (
        db.query(MediaReaction.media_id, func.count().label("n"))
        .group_by(MediaReaction.media_id)
        .subquery()
    )
    q = (
        db.query(MediaItem)
        .join(totals, totals.c.media_id == MediaItem.id)
        .options(selectinload(MediaItem.uploader))
    )
    if event_id is not None:
        q = q.filter(MediaItem.event_id == event_id)
    return q.order_by(totals.c.n.desc(), MediaItem.created_at.desc())


def hydrate_reactions(db: Session, items: Sequence[MediaItem], viewer_id: Optional[int]) -> list:
    """Attach `reactions` + `reaction_total` to each item, as instance attributes
    that MediaItemOut reads via getattr (the EventOut convention — not @property
    on the model).

    One query for the whole page, never one per row — raw rows rather than a
    GROUP BY, because the tooltip needs *who* reacted, not just how many.
    `viewer_id` is None for the public recap share, where "did I react" is
    meaningless — and there the `users` lists stay empty too, deliberately:
    reactor names are for logged-in members, never a public URL.
    """
    ids = [i.id for i in items]
    if not ids:
        return list(items)

    rows = (
        db.query(MediaReaction.media_id, MediaReaction.emoji, MediaReaction.user_id, User.username)
        .join(User, User.id == MediaReaction.user_id)
        .filter(MediaReaction.media_id.in_(ids))
        .order_by(MediaReaction.id)  # oldest first, so the tooltip reads in reaction order
        .all()
    )

    by_media: dict[int, dict[str, MediaReactionCount]] = {}
    for media_id, emoji, user_id, username in rows:
        tallies = by_media.setdefault(media_id, {})
        tally = tallies.get(emoji)
        if tally is None:
            tally = tallies[emoji] = MediaReactionCount(emoji=emoji, count=0, mine=False)
        tally.count += 1
        if viewer_id is not None:
            tally.users.append(username)
            if user_id == viewer_id:
                tally.mine = True

    for item in items:
        counts = list(by_media.get(item.id, {}).values())
        # Stable, meaningful order: most-reacted first, then the canonical set
        # order so the row doesn't reshuffle as counts change.
        counts.sort(key=lambda c: (-c.count, REACTION_EMOJI.index(c.emoji) if c.emoji in REACTION_EMOJI else 99))
        item.reactions = counts
        item.reaction_total = sum(c.count for c in counts)

    return list(items)


@router.get("/", response_model=list[MediaItemOut])
def list_media(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_id: Optional[int] = Query(None),
):
    q = db.query(MediaItem).options(selectinload(MediaItem.uploader))
    if event_id is not None:
        q = q.filter(MediaItem.event_id == event_id)
    items = q.order_by(MediaItem.created_at.desc()).offset(offset).limit(limit).all()
    return hydrate_reactions(db, items, user.id)


@router.get("/best", response_model=list[MediaItemOut])
def best_media(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(12, ge=1, le=50),
    event_id: Optional[int] = Query(None),
):
    """The crew's picks — derived from reaction counts rather than a `pinned`
    column. Reactions *are* the vote; a manual pin would only be an admin
    overruling it."""
    items = best_media_query(db, event_id).limit(limit).all()
    return hydrate_reactions(db, items, user.id)


@router.post("/upload", response_model=MediaItemOut)
async def upload_media(
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    event_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, "Unsupported file type. Allowed: JPEG, PNG, GIF, WebP, MP4, WebM, MOV, AVI.")

    content = await read_capped(file, MAX_SIZE)

    # Don't trust the client-declared content_type — verify the real bytes match.
    if not matches_declared(content, file.content_type):
        raise HTTPException(400, "File content does not match its declared type.")

    file_type = "image" if file.content_type.startswith("image/") else "video"
    ext = _MIME_TO_EXT.get(file.content_type, "bin")
    # A full uuid: /uploads/ is public, the name is the only thing guarding it.
    filename = f"media_{current_user.id}_{uuid.uuid4().hex}.{ext}"
    media_dir = os.path.join(UPLOAD_DIR, "media")
    os.makedirs(media_dir, exist_ok=True)

    file_path = os.path.join(media_dir, filename)
    with open(file_path, "wb") as f:
        f.write(content)

    thumbnail_url = None
    if file_type == "video":
        base_name = filename.rsplit(".", 1)[0]
        thumbnail_url = await _generate_video_thumbnail(file_path, UPLOAD_DIR, base_name)

    item = MediaItem(
        filename=filename,
        original_name=file.filename or filename,
        file_type=file_type,
        mime_type=file.content_type,
        file_size=len(content),
        url=f"/uploads/media/{filename}",
        thumbnail_url=thumbnail_url,
        caption=caption,
        event_id=event_id,
        uploaded_by=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    add_activity(db, current_user.id, "media_upload", f"Uploaded {file.filename or filename}", "media", item.id)
    db.commit()

    return item


@router.post("/{item_id}/react", response_model=MediaItemOut)
def react_to_media(
    item_id: int,
    data: MediaReact,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle one emoji on one item: react if you haven't, un-react if you have.

    A toggle rather than POST+DELETE because the UI is a toggle button, an emoji
    in a URL path means percent-encoding on both ends, and it makes the unique
    constraint unreachable instead of something to handle.
    """
    if data.emoji not in REACTION_EMOJI:
        raise HTTPException(400, "Unsupported reaction.")

    item = db.query(MediaItem).filter(MediaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Media not found")

    existing = (
        db.query(MediaReaction)
        .filter(
            MediaReaction.media_id == item_id,
            MediaReaction.user_id == current_user.id,
            MediaReaction.emoji == data.emoji,
        )
        .first()
    )
    if existing:
        db.delete(existing)
    else:
        db.add(MediaReaction(media_id=item_id, user_id=current_user.id, emoji=data.emoji))
    db.commit()
    db.refresh(item)

    return hydrate_reactions(db, [item], current_user.id)[0]


@router.patch("/{item_id}", response_model=MediaItemOut)
def update_media(
    item_id: int,
    data: MediaItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit a caption or re-tag which event a photo belongs to, after upload.

    Re-tagging matters more than it looks: media event_id is nullable and the
    gallery uploads with whatever filter is selected, so plenty of photos end up
    tied to no event and invisible to that event's recap. This is how they get
    put right.
    """
    item = db.query(MediaItem).filter(MediaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Media not found")
    if item.uploaded_by != current_user.id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")

    fields = data.model_dump(exclude_unset=True)
    if "event_id" in fields and fields["event_id"] is not None:
        if not db.query(LanEvent).filter(LanEvent.id == fields["event_id"]).first():
            raise HTTPException(404, "Event not found")

    for key, value in fields.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)

    return hydrate_reactions(db, [item], current_user.id)[0]


class BulkDeleteRequest(BaseModel):
    ids: List[int]


def _remove_media_files(item: MediaItem) -> None:
    """The file and, for a video, its thumbnail — a deleted clip's frame used
    to stay publicly reachable under /uploads/thumbnails/."""
    filepath = os.path.join(UPLOAD_DIR, "media", item.filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass
    remove_upload(item.thumbnail_url, "thumbnails")


@router.post("/bulk-delete")
def bulk_delete_media(
    data: BulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(403, "Admin only")
    if not data.ids:
        return {"deleted": 0}

    items = db.query(MediaItem).filter(MediaItem.id.in_(data.ids)).all()
    for item in items:
        _remove_media_files(item)
        db.delete(item)
    db.commit()
    return {"deleted": len(items)}


@router.delete("/{item_id}")
def delete_media(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(MediaItem).filter(MediaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Media not found")
    if item.uploaded_by != current_user.id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")

    _remove_media_files(item)
    db.delete(item)
    db.commit()
    return {"ok": True}
