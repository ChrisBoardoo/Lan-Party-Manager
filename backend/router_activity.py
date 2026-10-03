import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload
from typing import Sequence

from auth import (
    WS_RECHECK_EVERY,
    authenticate_websocket,
    close_unauthorized,
    get_current_user,
    session_still_valid,
)
from database import SessionLocal, get_db
from models import ActivityLog, ActivityReaction, MediaItem, MediaReaction, User
from schemas import ActivityLogOut, MediaReact, MediaReactionCount
from router_media import REACTION_EMOJI, hydrate_reactions

router = APIRouter()


def _hydrate_media(db: Session, entries: Sequence[ActivityLog], viewer_id: int) -> None:
    """Attach a `media` attribute (hydrated MediaItem, or None) to each entry
    whose entity_type is "media" — lets the Hub feed show a thumbnail and open
    it in the same Lightbox as the gallery, without a second lookup per row.

    The media's own `reactions`/`reaction_total` are hydrated for real (via
    router_media.hydrate_reactions — the same tallies the gallery shows) and
    mirrored onto the entry itself, rather than tracked separately: a photo
    reacted to from the Hub and from the Media page must show one count, not
    two independent ones. `_hydrate_activity_reactions` skips any entry this
    function has already set `reactions` on.
    """
    media_ids = [e.entity_id for e in entries if e.entity_type == "media" and e.entity_id is not None]
    if not media_ids:
        for e in entries:
            e.media = None
        return

    items = {
        m.id: m
        for m in db.query(MediaItem)
        .filter(MediaItem.id.in_(media_ids))
        .options(selectinload(MediaItem.uploader))
        .all()
    }
    hydrate_reactions(db, list(items.values()), viewer_id)

    for e in entries:
        media = items.get(e.entity_id) if e.entity_type == "media" else None
        e.media = media
        if media is not None:
            e.reactions = media.reactions
            e.reaction_total = media.reaction_total


def _hydrate_activity_reactions(db: Session, entries: Sequence[ActivityLog], viewer_id: int) -> None:
    """Attach `reactions` + `reaction_total` to every entry `_hydrate_media`
    didn't already mirror from a MediaItem — the router_media.hydrate_reactions
    shape, applied to activity_reactions for activity types with no reaction-
    bearing entity of their own (match results, expenses, etc.)."""
    entries = [e for e in entries if e.media is None]
    ids = [e.id for e in entries]
    if not ids:
        return

    rows = (
        db.query(ActivityReaction.activity_id, ActivityReaction.emoji, ActivityReaction.user_id, User.username)
        .join(User, User.id == ActivityReaction.user_id)
        .filter(ActivityReaction.activity_id.in_(ids))
        .order_by(ActivityReaction.id)  # oldest first, so the tooltip reads in reaction order
        .all()
    )

    by_activity: dict[int, dict[str, MediaReactionCount]] = {}
    for activity_id, emoji, user_id, username in rows:
        tallies = by_activity.setdefault(activity_id, {})
        tally = tallies.get(emoji)
        if tally is None:
            tally = tallies[emoji] = MediaReactionCount(emoji=emoji, count=0, mine=False)
        tally.count += 1
        tally.users.append(username)
        if user_id == viewer_id:
            tally.mine = True

    for e in entries:
        counts = list(by_activity.get(e.id, {}).values())
        counts.sort(key=lambda c: (-c.count, REACTION_EMOJI.index(c.emoji) if c.emoji in REACTION_EMOJI else 99))
        e.reactions = counts
        e.reaction_total = sum(c.count for c in counts)


def _visible_to(query, user_id: int):
    """A NULL recipient_user_id is a broadcast entry (every entry before that
    column existed, and every add_activity() call that doesn't pass it) —
    visible to everyone, same as before this column existed. A non-null one
    is a targeted notification (e.g. a chat @mention) — visible only to that
    recipient, so it never leaks to (or spams the desktop toast of) anyone
    else it wasn't meant for."""
    return query.filter(or_(ActivityLog.recipient_user_id.is_(None), ActivityLog.recipient_user_id == user_id))


@router.get("/", response_model=list[ActivityLogOut])
def list_activity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    entries = (
        _visible_to(db.query(ActivityLog), current_user.id)
        .options(selectinload(ActivityLog.user))
        .order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    _hydrate_media(db, entries, current_user.id)
    _hydrate_activity_reactions(db, entries, current_user.id)
    return entries


@router.post("/{activity_id}/react", response_model=ActivityLogOut)
def react_to_activity(
    activity_id: int,
    data: MediaReact,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle one emoji on one activity entry: react if you haven't, un-react if
    you have — same semantics as router_media.react_to_media.

    For a media_upload entry this toggles the *same* media_reactions row the
    gallery/Lightbox use (keyed on entity_id, the MediaItem's own id), not a
    separate activity_reactions row — otherwise the same photo could show a
    different reaction count in the Hub than on the Media page. Every other
    activity type has no reaction-bearing entity of its own, so those still
    use activity_reactions.
    """
    if data.emoji not in REACTION_EMOJI:
        raise HTTPException(400, "Unsupported reaction.")

    # Same visibility as the feed: someone else's targeted entry (a mention)
    # is a 404 here too, not a way to learn it exists.
    entry = (
        _visible_to(db.query(ActivityLog), current_user.id)
        .options(selectinload(ActivityLog.user))
        .filter(ActivityLog.id == activity_id)
        .first()
    )
    if not entry:
        raise HTTPException(404, "Activity entry not found")

    if entry.entity_type == "media" and entry.entity_id is not None:
        existing = (
            db.query(MediaReaction)
            .filter(
                MediaReaction.media_id == entry.entity_id,
                MediaReaction.user_id == current_user.id,
                MediaReaction.emoji == data.emoji,
            )
            .first()
        )
        if existing:
            db.delete(existing)
        else:
            db.add(MediaReaction(media_id=entry.entity_id, user_id=current_user.id, emoji=data.emoji))
    else:
        existing = (
            db.query(ActivityReaction)
            .filter(
                ActivityReaction.activity_id == activity_id,
                ActivityReaction.user_id == current_user.id,
                ActivityReaction.emoji == data.emoji,
            )
            .first()
        )
        if existing:
            db.delete(existing)
        else:
            db.add(ActivityReaction(activity_id=activity_id, user_id=current_user.id, emoji=data.emoji))
    db.commit()

    _hydrate_media(db, [entry], current_user.id)
    _hydrate_activity_reactions(db, [entry], current_user.id)
    return entry


@router.websocket("/ws")
async def activity_ws(websocket: WebSocket):
    """Live push for the activity feed, replacing what would otherwise be every
    connected client polling `GET /api/activity` on its own timer. Rather than
    threading a broadcast call through every `add_activity()` call site (10+
    routers, almost all plain sync `def`s, none holding a reference to this
    event loop), this does one cheap "did the newest id change?" check per
    connection per tick and only fans out the new rows when it has — turns N
    clients polling every 30s into ~1 lightweight query every 2s per
    connection, with sub-3s perceived latency instead of up to 30s.

    The client authenticates with its first frame (see auth.authenticate_websocket),
    and the session is re-checked every WS_RECHECK_EVERY ticks so a deactivation
    or password change closes an already-open socket too.
    """
    session = await authenticate_websocket(websocket)
    if session is None:
        return
    user_id, token_version = session

    last_seen_id: int | None = None
    tick = 0
    try:
        while True:
            db = SessionLocal()
            try:
                tick += 1
                if tick % WS_RECHECK_EVERY == 0 and not session_still_valid(db, user_id, token_version):
                    await close_unauthorized(websocket)
                    return
                newest = db.query(ActivityLog.id).order_by(ActivityLog.id.desc()).first()
                newest_id = newest[0] if newest else None
                if newest_id is not None and newest_id != last_seen_id:
                    if last_seen_id is not None:
                        new_entries = (
                            _visible_to(db.query(ActivityLog), user_id)
                            .options(selectinload(ActivityLog.user))
                            .filter(ActivityLog.id > last_seen_id)
                            .order_by(ActivityLog.id.asc())
                            .all()
                        )
                        _hydrate_media(db, new_entries, user_id)
                        _hydrate_activity_reactions(db, new_entries, user_id)
                        items = [
                            ActivityLogOut.model_validate(e).model_dump(mode="json")
                            for e in new_entries
                        ]
                        await websocket.send_json({"type": "activity", "items": items})
                    last_seen_id = newest_id
            finally:
                db.close()
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
