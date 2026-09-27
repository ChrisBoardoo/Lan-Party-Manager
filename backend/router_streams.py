from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import re

from database import get_db
from models import LiveStream, User
from schemas import LiveStreamCreate, LiveStreamUpdate, LiveStreamOut
from auth import get_current_user, require_admin
from activity import add_activity
from router_settings import require_feature

router = APIRouter()

_twitch_token_cache: dict = {"token": None, "expires_at": None}


def _parse_twitch_input(raw: str) -> tuple[str, str, Optional[str]]:
    """Return (stream_type, channel_name_or_clip_slug, clip_slug)."""
    raw = raw.strip()

    clip_match = re.search(r"clips\.twitch\.tv/([A-Za-z0-9_-]+)", raw)
    if not clip_match:
        clip_match = re.search(r"/clip/([A-Za-z0-9_-]+)", raw)

    if clip_match:
        slug = clip_match.group(1)
        return "clip", slug, slug

    channel = re.sub(r"^https?://(www\.)?twitch\.tv/", "", raw, flags=re.IGNORECASE)
    channel = channel.split("/")[0].lower().strip()
    return "channel", channel, None


@router.get("/", response_model=list[LiveStreamOut])
def list_streams(db: Session = Depends(get_db), _: User = Depends(require_feature("streams"))):
    return db.query(LiveStream).order_by(LiveStream.created_at.desc()).all()


@router.post("/", response_model=LiveStreamOut)
def create_stream(
    data: LiveStreamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    stream_type, channel_name, clip_slug = _parse_twitch_input(data.channel_name)
    stream = LiveStream(
        channel_name=channel_name,
        title=data.title,
        is_active=data.is_active,
        stream_type=stream_type,
        clip_slug=clip_slug,
        created_by=current_user.id,
    )
    db.add(stream)
    db.commit()
    db.refresh(stream)
    add_activity(db, current_user.id, "stream_added", f"Added stream: {stream.channel_name}", "live_stream", stream.id)
    db.commit()
    return stream


@router.put("/{stream_id}", response_model=LiveStreamOut)
def update_stream(
    stream_id: int,
    data: LiveStreamUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    stream = db.query(LiveStream).filter(LiveStream.id == stream_id).first()
    if not stream:
        raise HTTPException(404, "Stream not found")

    if data.channel_name is not None:
        stream_type, channel_name, clip_slug = _parse_twitch_input(data.channel_name)
        stream.channel_name = channel_name
        stream.stream_type = stream_type
        stream.clip_slug = clip_slug
    if data.title is not None:
        stream.title = data.title
    if data.is_active is not None:
        stream.is_active = data.is_active

    db.commit()
    db.refresh(stream)
    return stream


@router.delete("/{stream_id}")
def delete_stream(
    stream_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    stream = db.query(LiveStream).filter(LiveStream.id == stream_id).first()
    if not stream:
        raise HTTPException(404, "Stream not found")
    db.delete(stream)
    db.commit()
    return {"ok": True}


@router.get("/live-status")
async def get_live_status(db: Session = Depends(get_db), _: User = Depends(require_feature("streams"))):
    from router_settings import get_setting
    from datetime import datetime, timedelta

    channels = (
        db.query(LiveStream)
        .filter(LiveStream.is_active == True, LiveStream.stream_type == "channel")
        .all()
    )
    if not channels:
        return {}

    client_id = get_setting(db, "twitch_client_id")
    client_secret = get_setting(db, "twitch_client_secret")
    if not client_id or not client_secret:
        return {}

    now = datetime.utcnow()
    token = _twitch_token_cache.get("token")
    expires_at = _twitch_token_cache.get("expires_at")

    if not token or not expires_at or expires_at <= now:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://id.twitch.tv/oauth2/token",
                    params={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "grant_type": "client_credentials",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    token = payload["access_token"]
                    _twitch_token_cache["token"] = token
                    _twitch_token_cache["expires_at"] = now + timedelta(seconds=payload["expires_in"] - 300)
                else:
                    return {}
        except Exception:
            return {}

    try:
        import httpx
        channel_names = [c.channel_name for c in channels]
        params = [("user_login", n) for n in channel_names]
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.twitch.tv/helix/streams",
                params=params,
                headers={"Authorization": f"Bearer {token}", "Client-Id": client_id},
                timeout=10,
            )
            if resp.status_code == 200:
                live_data = resp.json().get("data", [])
                live_map = {s["user_login"].lower(): s for s in live_data}
                return {
                    name: {
                        "is_live": name.lower() in live_map,
                        "game": live_map.get(name.lower(), {}).get("game_name", ""),
                        "viewers": live_map.get(name.lower(), {}).get("viewer_count", 0),
                        "title": live_map.get(name.lower(), {}).get("title", ""),
                    }
                    for name in channel_names
                }
    except Exception:
        pass

    return {}
