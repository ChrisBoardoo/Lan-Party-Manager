"""Craving Chat — /api/chat

A single lightweight group chat per event ("what are you craving for the
LAN?"), open only to confirmed attendees (EventRSVP.status == "in"), and only
during a fixed window around the event: from 30 days before `start_date`
through 15 days after `end_date`. Outside that window, or for a non-attendee,
every endpoint (REST and WebSocket) answers as if the room doesn't exist.

Real-time delivery reuses router_activity.py's "poll-and-push" WebSocket
idea, but not its exact mechanism: activity only ever gets new rows, so it
can poll on "did MAX(id) grow". Chat messages can also be *edited* or
*reacted to* after the fact with no new row appearing, so this instead polls
on `updated_at > last_seen_time` (see chat_ws) — a edit or a reaction both
bump `updated_at`, a plain new message already has `updated_at == created_at`
which is naturally caught by the same watermark check.

Moderation v1: a user can delete only their own messages. No admin-delete yet
— see md/2.features/craving_chat_suggestions.md for future ideas.
"""
import asyncio
import logging
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, selectinload

import link_preview
from activity import add_activity
from auth import (
    WS_RECHECK_EVERY,
    authenticate_websocket,
    close_unauthorized,
    get_current_user,
    session_still_valid,
)
from database import SessionLocal, get_db
from models import ChatMessage, ChatMessageMention, ChatMessageReaction, EventRSVP, LanEvent, User
from schemas import (
    ChatLinkPreviewOut, ChatMentionOut, ChatMessageCreate, ChatMessageOut, ChatMessageReplyPreview,
    ChatMessageUpdate, ChatReactionIn, ChatReactionOut, PinnedMessageOut,
)
from router_settings import is_feature_enabled

logger = logging.getLogger(__name__)

router = APIRouter()

CHAT_OPENS_DAYS_BEFORE = 30
CHAT_CLOSES_DAYS_AFTER = 15
HISTORY_LIMIT = 200  # no pagination for v1 — "très léger"
EDIT_WINDOW = timedelta(minutes=10)
REPLY_PREVIEW_LEN = 140

_MESSAGE_LOAD_OPTIONS = (
    selectinload(ChatMessage.user),
    selectinload(ChatMessage.reply_to).selectinload(ChatMessage.user),
    selectinload(ChatMessage.reactions),
    selectinload(ChatMessage.mentions).selectinload(ChatMessageMention.user),
)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _event_or_404(db: Session, event_id: int) -> LanEvent:
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


def _message_or_404(db: Session, event_id: int, message_id: int) -> ChatMessage:
    msg = (
        db.query(ChatMessage)
        .options(*_MESSAGE_LOAD_OPTIONS)
        .filter(ChatMessage.id == message_id, ChatMessage.event_id == event_id)
        .first()
    )
    if not msg:
        raise HTTPException(404, "Message not found")
    return msg


def _window_open(event: LanEvent, today: date | None = None) -> bool:
    today = today or date.today()
    opens = event.start_date - timedelta(days=CHAT_OPENS_DAYS_BEFORE)
    closes = event.end_date + timedelta(days=CHAT_CLOSES_DAYS_AFTER)
    return opens <= today <= closes


def _is_attendee(db: Session, event_id: int, user_id: int) -> bool:
    return (
        db.query(EventRSVP)
        .filter(EventRSVP.event_id == event_id, EventRSVP.user_id == user_id, EventRSVP.status == "in")
        .first()
        is not None
    )


def _event_attendees(db: Session, event_id: int) -> list[User]:
    return (
        db.query(User)
        .join(EventRSVP, EventRSVP.user_id == User.id)
        .filter(EventRSVP.event_id == event_id, EventRSVP.status == "in")
        .all()
    )


def _resolve_mentions(db: Session, event_id: int, content: str, author_id: int) -> list[User]:
    """Which attendees does `content` @-mention? Matched against the event's
    own attendee list (never a free-form "@token" regex) so only someone the
    autocomplete could actually have proposed can ever be recorded here or
    trigger a notification — avoids prefix ambiguity too (e.g. "@Cross"
    wrongly matching both "CrossWax" and "Crossy"). Usernames can't contain
    '@' or whitespace (schemas.py's _check_username), so no escaping/token-
    splitting edge case to worry about beyond the regex-special characters a
    username might otherwise contain (still escaped via re.escape)."""
    mentioned = []
    for attendee in _event_attendees(db, event_id):
        if attendee.id == author_id:
            continue
        pattern = r"(?:^|\s)@" + re.escape(attendee.username) + r"(?=$|\s|[.,!?;:])"
        if re.search(pattern, content, re.IGNORECASE):
            mentioned.append(attendee)
    return mentioned


def _require_room_access(db: Session, event: LanEvent, user: User) -> None:
    """Admins bypass the feature flag (so they can turn it on/inspect it
    before anyone else can), same convention as require_feature — but nobody,
    admins included, bypasses the attendance/window gates: those aren't a
    visibility toggle, they're what the room *is*."""
    if user.role != "admin" and not is_feature_enabled(db, "craving_chat"):
        raise HTTPException(404, "This feature is not enabled")
    if not _window_open(event):
        raise HTTPException(403, "The Craving Chat is closed for this event")
    if not _is_attendee(db, event.id, user.id):
        raise HTTPException(403, "Only confirmed attendees can use the Craving Chat")


def _reaction_summaries(msg: ChatMessage, viewer_id: int) -> list[ChatReactionOut]:
    tallies: dict[str, ChatReactionOut] = {}
    for r in msg.reactions:
        tally = tallies.get(r.emoji)
        if tally is None:
            tally = tallies[r.emoji] = ChatReactionOut(emoji=r.emoji, count=0, mine=False)
        tally.count += 1
        if r.user_id == viewer_id:
            tally.mine = True
    return list(tallies.values())


def _link_preview_out(msg: ChatMessage) -> ChatLinkPreviewOut | None:
    if not msg.link_preview_url:
        return None
    if not (msg.link_preview_title or msg.link_preview_description or msg.link_preview_image_url):
        return None
    return ChatLinkPreviewOut(
        url=msg.link_preview_url,
        title=msg.link_preview_title,
        description=msg.link_preview_description,
        image_url=msg.link_preview_image_url,
        site_name=msg.link_preview_site_name,
    )


def _pinned_out(msg: ChatMessage) -> PinnedMessageOut:
    return PinnedMessageOut(
        id=msg.id,
        user_id=msg.user_id,
        username=msg.user.username,
        avatar_url=msg.user.avatar_url,
        content=msg.content,
        created_at=msg.created_at,
    )


def _serialize(msg: ChatMessage, viewer_id: int) -> ChatMessageOut:
    reply_to = None
    if msg.reply_to is not None:
        content = msg.reply_to.content
        reply_to = ChatMessageReplyPreview(
            id=msg.reply_to.id,
            username=msg.reply_to.user.username,
            content=content[:REPLY_PREVIEW_LEN] + "…" if len(content) > REPLY_PREVIEW_LEN else content,
        )
    return ChatMessageOut(
        id=msg.id,
        event_id=msg.event_id,
        user_id=msg.user_id,
        username=msg.user.username,
        avatar_url=msg.user.avatar_url,
        is_admin=msg.user.role == "admin",
        content=msg.content,
        created_at=msg.created_at,
        edited_at=msg.edited_at,
        is_mine=msg.user_id == viewer_id,
        reply_to=reply_to,
        reactions=_reaction_summaries(msg, viewer_id),
        link_preview=_link_preview_out(msg),
        mentions=[ChatMentionOut(user_id=m.user_id, username=m.user.username) for m in msg.mentions],
    )


def _fetch_and_store_link_preview(message_id: int, url: str) -> None:
    """Runs in a FastAPI BackgroundTask, after the response for the send/edit
    that scheduled it has already gone out — the message appears instantly,
    the preview card pops in a moment later once this lands (same UX as
    WhatsApp/Discord/Slack), rather than making the sender wait on an
    outbound fetch to an arbitrary external site before their message even
    shows up. Own DB session: the request's session is long closed by the
    time this runs."""
    try:
        preview = link_preview.fetch_preview(url)
    except Exception:
        logger.exception("Link preview fetch crashed for message %s", message_id)
        return
    if not preview:
        return

    db = SessionLocal()
    try:
        msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        if not msg or link_preview.first_url(msg.content) != url:
            # Deleted, or edited to a different (or no) link, before this
            # background fetch landed — applying a stale preview here would
            # silently reattach a link the sender already removed/changed.
            return
        msg.link_preview_url = preview["url"]
        msg.link_preview_title = preview["title"]
        msg.link_preview_description = preview["description"]
        msg.link_preview_image_url = preview["image_url"]
        msg.link_preview_site_name = preview["site_name"]
        msg.updated_at = datetime.utcnow()  # bump the WS poll watermark
        db.commit()
    finally:
        db.close()


# ── REST ──────────────────────────────────────────────────────────────────────

@router.get("/{event_id}/messages", response_model=list[ChatMessageOut])
def list_messages(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = _event_or_404(db, event_id)
    _require_room_access(db, event, user)
    messages = (
        db.query(ChatMessage)
        .options(*_MESSAGE_LOAD_OPTIONS)
        .filter(ChatMessage.event_id == event_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    return [_serialize(m, user.id) for m in reversed(messages)]


@router.post("/{event_id}/messages", response_model=ChatMessageOut, status_code=201)
def post_message(
    event_id: int,
    data: ChatMessageCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = _event_or_404(db, event_id)
    _require_room_access(db, event, user)

    reply_to_id = None
    if data.reply_to_id is not None:
        target = (
            db.query(ChatMessage)
            .filter(ChatMessage.id == data.reply_to_id, ChatMessage.event_id == event_id)
            .first()
        )
        if not target:
            raise HTTPException(400, "Message being replied to was not found in this event")
        reply_to_id = target.id

    content = data.content.strip()
    msg = ChatMessage(event_id=event_id, user_id=user.id, content=content, reply_to_id=reply_to_id)
    db.add(msg)
    db.commit()
    db.refresh(msg)

    mentioned = _resolve_mentions(db, event_id, content, user.id)
    for attendee in mentioned:
        db.add(ChatMessageMention(message_id=msg.id, user_id=attendee.id))
        # recipient_user_id-scoped: only this one attendee's desktop app will
        # ever poll this row (router_activity.py's _visible_to) — everyone
        # else's activity feed/toast pipeline never sees it.
        add_activity(
            db, user_id=user.id, action="chat_mention",
            description=f"mentioned you in {event.title}'s chat",
            entity_type="chat_message", entity_id=msg.id, recipient_user_id=attendee.id,
        )
    if mentioned:
        db.commit()

    url = link_preview.first_url(content)
    if url:
        background_tasks.add_task(_fetch_and_store_link_preview, msg.id, url)

    msg = _message_or_404(db, event_id, msg.id)  # re-load with reply_to/user/reactions/mentions eager-loaded
    return _serialize(msg, user.id)


@router.patch("/{event_id}/messages/{message_id}", response_model=ChatMessageOut)
def edit_message(
    event_id: int,
    message_id: int,
    data: ChatMessageUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = _event_or_404(db, event_id)
    _require_room_access(db, event, user)
    msg = _message_or_404(db, event_id, message_id)
    if msg.user_id != user.id:
        raise HTTPException(403, "You can only edit your own messages")
    if datetime.utcnow() - msg.created_at > EDIT_WINDOW:
        raise HTTPException(403, "This message is too old to edit (10-minute window)")

    old_url = link_preview.first_url(msg.content)
    content = data.content.strip()
    new_url = link_preview.first_url(content)

    now = datetime.utcnow()
    msg.content = content
    msg.edited_at = now
    msg.updated_at = now

    # Recomputed so the (server-confirmed) highlighting stays correct after
    # an edit — but deliberately fires no new notification either way: a
    # newly-added mention on edit doesn't toast the recipient, and a removed
    # one doesn't retract an already-delivered toast. Keeps this v1 simple
    # and avoids notifying on every typo fix.
    db.query(ChatMessageMention).filter(ChatMessageMention.message_id == msg.id).delete()
    for attendee in _resolve_mentions(db, event_id, content, user.id):
        db.add(ChatMessageMention(message_id=msg.id, user_id=attendee.id))

    if new_url != old_url:
        # The link changed (or was removed) — drop the stale preview right
        # away rather than leaving yesterday's link's card under today's
        # text; a fresh one is re-fetched below if there's a new link.
        msg.link_preview_url = None
        msg.link_preview_title = None
        msg.link_preview_description = None
        msg.link_preview_image_url = None
        msg.link_preview_site_name = None
    db.commit()
    db.refresh(msg)

    if new_url and new_url != old_url:
        background_tasks.add_task(_fetch_and_store_link_preview, msg.id, new_url)

    return _serialize(msg, user.id)


@router.post("/{event_id}/messages/{message_id}/react", response_model=ChatMessageOut)
def react_to_message(
    event_id: int,
    message_id: int,
    data: ChatReactionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """WhatsApp-style: at most one reaction per person per message. Sending
    the same emoji again clears it; sending a different one replaces it."""
    event = _event_or_404(db, event_id)
    _require_room_access(db, event, user)
    msg = _message_or_404(db, event_id, message_id)

    existing = (
        db.query(ChatMessageReaction)
        .filter(ChatMessageReaction.message_id == message_id, ChatMessageReaction.user_id == user.id)
        .first()
    )
    if existing and existing.emoji == data.emoji:
        db.delete(existing)
    elif existing:
        existing.emoji = data.emoji
    else:
        db.add(ChatMessageReaction(message_id=message_id, user_id=user.id, emoji=data.emoji))

    # Not a content edit — edited_at stays untouched — but it must still bump
    # updated_at, the only signal chat_ws's poll loop has that this row
    # changed (no new row is inserted for a reaction).
    msg.updated_at = datetime.utcnow()
    db.commit()
    msg = _message_or_404(db, event_id, message_id)
    return _serialize(msg, user.id)


@router.delete("/{event_id}/messages/{message_id}")
def delete_message(
    event_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = _event_or_404(db, event_id)
    _require_room_access(db, event, user)
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id, ChatMessage.event_id == event_id).first()
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.user_id != user.id:
        raise HTTPException(403, "You can only delete your own messages")
    db.delete(msg)
    db.commit()
    return {"ok": True}


@router.get("/{event_id}/pinned", response_model=PinnedMessageOut | None)
def get_pinned(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = _event_or_404(db, event_id)
    _require_room_access(db, event, user)
    if not event.pinned_message_id:
        return None
    msg = (
        db.query(ChatMessage)
        .options(selectinload(ChatMessage.user))
        .filter(ChatMessage.id == event.pinned_message_id)
        .first()
    )
    return _pinned_out(msg) if msg else None


@router.post("/{event_id}/pin/{message_id}", response_model=PinnedMessageOut)
def pin_message(
    event_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Admin-only, same tier as posting an announcement — pinning displaces
    whatever else was pinned (at most one per event, see LanEvent's own
    docstring on pinned_message_id). Live-pushed to every connected client
    by chat_ws's poll loop (it watches event.pinned_message_id alongside
    message changes), so this endpoint itself doesn't need to touch the
    WebSocket layer at all."""
    event = _event_or_404(db, event_id)
    _require_room_access(db, event, user)
    if user.role != "admin":
        raise HTTPException(403, "Only admins can pin a message")
    msg = _message_or_404(db, event_id, message_id)
    event.pinned_message_id = msg.id
    db.commit()
    return _pinned_out(msg)


@router.delete("/{event_id}/pin")
def unpin_message(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = _event_or_404(db, event_id)
    _require_room_access(db, event, user)
    if user.role != "admin":
        raise HTTPException(403, "Only admins can unpin a message")
    event.pinned_message_id = None
    db.commit()
    return {"ok": True}


# ── WebSocket (live push) ────────────────────────────────────────────────────

# event_id -> every currently-connected socket in that room's chat_ws. Purely
# in-process (fine for this app's single-worker, self-hosted-per-crew model —
# same assumption the SQLite backing store already makes). Used only for the
# "typing…" ping below: it's ephemeral, never touches the DB, and needs to
# reach every OTHER open connection immediately — unlike messages/pinned,
# which are already covered by each connection's own poll-and-push loop.
_event_connections: dict[int, set[WebSocket]] = defaultdict(set)
# Open sockets per (event, user): a few tabs or devices are normal, a script
# opening hundreds is not.
_user_connections: dict[tuple[int, int], int] = defaultdict(int)
MAX_SOCKETS_PER_USER = 5
# At most one "typing" relay per connection per this many seconds.
TYPING_MIN_INTERVAL = 1.0


async def _broadcast(event_id: int, payload: dict, *, exclude: WebSocket) -> None:
    dead = []
    for ws in _event_connections.get(event_id, ()):
        if ws is exclude:
            continue
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _event_connections[event_id].discard(ws)


def _may_stay_connected(db: Session, event_id: int, user_id: int, token_version: int) -> bool:
    """Everything chat_ws checks at connect, re-checked on an open socket: the
    session is still valid, the feature is on (or the user is an admin), the
    chat window is open and the user still attends."""
    if not session_still_valid(db, user_id, token_version):
        return False
    user = db.query(User).filter(User.id == user_id).first()
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if event is None:
        return False
    if user.role != "admin" and not is_feature_enabled(db, "craving_chat"):
        return False
    return _window_open(event) and _is_attendee(db, event_id, user_id)


async def _push_loop(websocket: WebSocket, event_id: int, user_id: int, token_version: int) -> None:
    """Polls for anything a connected client needs pushed to it: changed
    messages (watermark, not an id — a message can change via edit/reaction
    with no new row appearing, so "did MAX(id) grow" isn't enough here, every
    tick re-fetches anything touched since the last one) and, piggybacked on
    the same 2s tick since it changes about as rarely, the event's pinned
    message pointer. One extra cheap column read per tick beats a second poll
    loop for something that changes this infrequently."""
    last_seen_time = datetime.utcnow()
    db = SessionLocal()
    try:
        last_pinned_id = db.query(LanEvent.pinned_message_id).filter(LanEvent.id == event_id).scalar()
    finally:
        db.close()

    tick = 0
    while True:
        db = SessionLocal()
        try:
            tick += 1
            if tick % WS_RECHECK_EVERY == 0 and not _may_stay_connected(db, event_id, user_id, token_version):
                await close_unauthorized(websocket)
                return
            tick_time = datetime.utcnow()
            changed = (
                db.query(ChatMessage)
                .options(*_MESSAGE_LOAD_OPTIONS)
                .filter(ChatMessage.event_id == event_id, ChatMessage.updated_at > last_seen_time)
                .order_by(ChatMessage.id.asc())
                .all()
            )
            if changed:
                items = [_serialize(m, user_id).model_dump(mode="json") for m in changed]
                await websocket.send_json({"type": "messages", "items": items})
            last_seen_time = tick_time

            pinned_id = db.query(LanEvent.pinned_message_id).filter(LanEvent.id == event_id).scalar()
            if pinned_id != last_pinned_id:
                pinned_payload = None
                if pinned_id is not None:
                    msg = (
                        db.query(ChatMessage)
                        .options(selectinload(ChatMessage.user))
                        .filter(ChatMessage.id == pinned_id)
                        .first()
                    )
                    pinned_payload = _pinned_out(msg).model_dump(mode="json") if msg else None
                await websocket.send_json({"type": "pinned", "message": pinned_payload})
                last_pinned_id = pinned_id
        finally:
            db.close()
        await asyncio.sleep(2)


async def _receive_loop(websocket: WebSocket, event_id: int, user_id: int, username: str) -> None:
    """The only thing a client ever sends is an ephemeral "I'm typing" ping
    (no persistence, nothing to poll for) — relayed to every other currently
    connected client in the same room. Anything malformed/unexpected is
    ignored rather than killing the connection; a disconnect ends this loop,
    and so does any other receive error (a closed socket would otherwise
    spin here forever). Typing relays are throttled per connection."""
    last_typing = 0.0
    while True:
        try:
            data = await websocket.receive_json()
        except (ValueError, KeyError):  # not JSON, or a binary frame
            continue
        if isinstance(data, dict) and data.get("type") == "typing":
            now = time.monotonic()
            if now - last_typing < TYPING_MIN_INTERVAL:
                continue
            last_typing = now
            await _broadcast(event_id, {"type": "typing", "user_id": user_id, "username": username}, exclude=websocket)


@router.websocket("/{event_id}/ws")
async def chat_ws(websocket: WebSocket, event_id: int):
    # The client authenticates with its first frame — see auth.authenticate_websocket.
    session = await authenticate_websocket(websocket)
    if session is None:
        return
    user_id, token_version = session

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
        event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
        if user is None or event is None:
            await websocket.close(code=4404)
            return
        if user.role != "admin" and not is_feature_enabled(db, "craving_chat"):
            await websocket.close(code=4404)
            return
        if not _window_open(event) or not _is_attendee(db, event_id, user_id):
            await websocket.close(code=4403)
            return
        username = user.username
    finally:
        db.close()

    if _user_connections[(event_id, user_id)] >= MAX_SOCKETS_PER_USER:
        await websocket.close(code=4429)
        return
    _user_connections[(event_id, user_id)] += 1
    _event_connections[event_id].add(websocket)
    try:
        push_task = asyncio.create_task(_push_loop(websocket, event_id, user_id, token_version))
        receive_task = asyncio.create_task(_receive_loop(websocket, event_id, user_id, username))
        done, pending = await asyncio.wait({push_task, receive_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            try:
                task.result()
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass
    finally:
        _user_connections[(event_id, user_id)] -= 1
        if _user_connections[(event_id, user_id)] <= 0:
            del _user_connections[(event_id, user_id)]
        conns = _event_connections.get(event_id)
        if conns is not None:
            conns.discard(websocket)
            if not conns:
                del _event_connections[event_id]
