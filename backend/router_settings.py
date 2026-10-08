from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from database import get_db
from models import AppSetting, EventRSVP, User
from event_utils import current_event
from schemas import AppSettingOut, AppSettingUpdate
from auth import require_admin, get_current_user

router = APIRouter()

ALLOWED_KEYS = {
    "twitch_client_id",
    "twitch_client_secret",
    "discord_invite_url",
    "discord_webhook_url",
    "discord_tpl_reminder",
    "discord_tpl_announcement",
    "discord_oauth_enabled",
    "discord_oauth_client_id",
    "discord_oauth_client_secret",
    "steam_link_enabled",
    "steam_web_api_key",
    "smtp_host",
    "smtp_port",
    "smtp_username",
    "smtp_password",
    "smtp_from_address",
    "smtp_use_tls",
    "app_base_url",
    "app_timezone",
    "reminder_days_before",
    "currency",
    "treasury_enabled",
    "sponsors_enabled",
    "prizes_enabled",
    "planning_enabled",
    "planning_default_can_propose",
    "planning_default_can_vote",
    "kiosk_enabled",
    "kiosk_live_drop_enabled",
    "gear_enabled",
    "groceries_enabled",
    "recap_enabled",
    "setup_enabled",
    "streams_enabled",
    "checklist_enabled",
    "merch_size_enabled",
    "minigames_enabled",
    "games_enabled",
    "craving_chat_enabled",
    "trophies_enabled",
    "lol_stats_enabled",
    "xp_enabled",
    # Guest WiFi (the spare network for phones/laptops — PCs are wired). Shown
    # only when wifi_ssid is set; the password never goes through /public-config,
    # only through GET /wifi (admins + current-event attendees) and the kiosk.
    "wifi_ssid",
    "wifi_password",
    "wifi_security",
    "wifi_hidden",
}

# Currency symbols the UI knows how to render. Keep in sync with the
# frontend selector in Settings.tsx and the CURRENCIES list there.
ALLOWED_CURRENCIES = {"€", "$", "£"}
DEFAULT_CURRENCY = "€"

# The `T:` values of the WIFI: QR payload. WPA covers WPA/WPA2/WPA3-transition
# for phone camera readers; "nopass" is an open network.
ALLOWED_WIFI_SECURITY = {"WPA", "WEP", "nopass"}
DEFAULT_WIFI_SECURITY = "WPA"


def get_setting(db: Session, key: str) -> Optional[str]:
    s = db.query(AppSetting).filter(AppSetting.key == key).first()
    return s.value if s else None


def is_feature_enabled(db: Session, feature: str) -> bool:
    """Single source of truth for optional-feature visibility. Mirrors the
    values returned by /public-config so the backend and UI never disagree.

    - prizes:   opt-in, default OFF
    - sponsors: opt-in, default OFF
    - planning: opt-in, default OFF
    - gear:     opt-in, default OFF
    - groceries: opt-in, default OFF (per-event food/drink shopping list)
    - recap:    opt-in, default OFF (the post-event recap page + badges)
    - setup:    opt-in, default OFF ("My Setup" + its public share link)
    - checklist: opt-in, default OFF (private per-event packing checklist)
    - minigames: opt-in, default OFF (embedded games + score leaderboard)
    - games:    opt-in, default OFF (profile game library/wishlist + games finder)
    - craving_chat: default ON, opt-out (per-event hype chat, open 30 days
      before an event's start through 15 days after its end — see
      router_chat.py's _window_open)
    - trophies: opt-in, default OFF (crew-defined trophies awarded per event,
      by vote or by an admin — see router_trophies.py)
    - lol_stats: opt-in, default OFF (League of Legends games captured by the
      desktop app during a LAN — see router_lol.py)
    - xp:       opt-in, default OFF (crew XP and levels, derived on read — see xp.py)
    - treasury: default ON, but auto-hidden when prizes is enabled
    - streams:  default ON, opt-out (not every LAN has a streamer in their ranks)
    - merch_size: default ON, opt-out (not every crew does event merch/t-shirts)
    """
    prizes_enabled = get_setting(db, "prizes_enabled") == "true"
    if feature == "prizes":
        return prizes_enabled
    if feature == "sponsors":
        return get_setting(db, "sponsors_enabled") == "true"
    if feature == "planning":
        return get_setting(db, "planning_enabled") == "true"
    if feature == "gear":
        return get_setting(db, "gear_enabled") == "true"
    if feature == "groceries":
        return get_setting(db, "groceries_enabled") == "true"
    if feature == "recap":
        return get_setting(db, "recap_enabled") == "true"
    if feature == "setup":
        return get_setting(db, "setup_enabled") == "true"
    if feature == "checklist":
        return get_setting(db, "checklist_enabled") == "true"
    if feature == "minigames":
        return get_setting(db, "minigames_enabled") == "true"
    if feature == "games":
        return get_setting(db, "games_enabled") == "true"
    if feature == "treasury":
        return get_setting(db, "treasury_enabled") != "false" and not prizes_enabled
    if feature == "streams":
        return get_setting(db, "streams_enabled") != "false"
    if feature == "merch_size":
        return get_setting(db, "merch_size_enabled") != "false"
    if feature == "craving_chat":
        return get_setting(db, "craving_chat_enabled") != "false"
    if feature == "trophies":
        return get_setting(db, "trophies_enabled") == "true"
    if feature == "lol_stats":
        return get_setting(db, "lol_stats_enabled") == "true"
    if feature == "xp":
        return get_setting(db, "xp_enabled") == "true"
    return True


def wifi_config(db: Session) -> Optional[dict]:
    """The guest WiFi as {ssid, password, security, hidden}, or None when no
    SSID is set (an empty SSID is how an admin hides the whole feature)."""
    ssid = (get_setting(db, "wifi_ssid") or "").strip()
    if not ssid:
        return None
    security = get_setting(db, "wifi_security") or DEFAULT_WIFI_SECURITY
    if security not in ALLOWED_WIFI_SECURITY:
        security = DEFAULT_WIFI_SECURITY
    return {
        "ssid": ssid,
        # An open network has no password, whatever might be left in the field.
        "password": None if security == "nopass" else (get_setting(db, "wifi_password") or None),
        "security": security,
        "hidden": get_setting(db, "wifi_hidden") == "true",
    }


def planning_defaults(db: Session) -> tuple[bool, bool]:
    """Global default for the two planning toggles (can_propose, can_vote).
    Both default ON ("Friends LAN") when unset — an admin opts a toggle out by
    storing "false". A per-event override on LanEvent supersedes these."""
    return (
        get_setting(db, "planning_default_can_propose") != "false",
        get_setting(db, "planning_default_can_vote") != "false",
    )


def require_feature(feature: str):
    """Dependency factory: reject requests to a disabled feature's endpoints.

    Turns UI-only hiding into real access control. Admins always pass through so
    they can still manage/configure a feature before (or after) enabling it —
    only non-admin members are blocked when the feature is off."""
    def dependency(
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> User:
        if user.role != "admin" and not is_feature_enabled(db, feature):
            raise HTTPException(404, "This feature is not enabled")
        return user

    return dependency


@router.get("/", response_model=List[AppSettingOut])
def list_settings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(AppSetting).filter(AppSetting.key.in_(ALLOWED_KEYS)).all()
    # Return a row for each key even if not stored yet
    stored = {r.key: r for r in rows}
    result = []
    for key in sorted(ALLOWED_KEYS):
        if key in stored:
            result.append(stored[key])
        else:
            # Virtual placeholder
            obj = AppSetting(key=key, value=None)
            result.append(obj)
    return result


@router.get("/discord-invite")
def get_discord_invite(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"discord_invite_url": get_setting(db, "discord_invite_url")}


@router.get("/public-config")
def get_public_config(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """App-wide config that any logged-in user needs to render the UI correctly
    (not just admins who can edit it): the currency symbol and which optional
    features are enabled."""
    can_propose, can_vote = planning_defaults(db)
    return {
        "currency": get_setting(db, "currency") or DEFAULT_CURRENCY,
        "treasury_enabled": is_feature_enabled(db, "treasury"),
        "sponsors_enabled": is_feature_enabled(db, "sponsors"),
        "prizes_enabled": is_feature_enabled(db, "prizes"),
        "planning_enabled": is_feature_enabled(db, "planning"),
        "planning_default_can_propose": can_propose,
        "planning_default_can_vote": can_vote,
        "gear_enabled": is_feature_enabled(db, "gear"),
        "groceries_enabled": is_feature_enabled(db, "groceries"),
        "recap_enabled": is_feature_enabled(db, "recap"),
        "setup_enabled": is_feature_enabled(db, "setup"),
        "streams_enabled": is_feature_enabled(db, "streams"),
        "checklist_enabled": is_feature_enabled(db, "checklist"),
        "merch_size_enabled": is_feature_enabled(db, "merch_size"),
        "minigames_enabled": is_feature_enabled(db, "minigames"),
        "games_enabled": is_feature_enabled(db, "games"),
        "craving_chat_enabled": is_feature_enabled(db, "craving_chat"),
        "trophies_enabled": is_feature_enabled(db, "trophies"),
        "lol_stats_enabled": is_feature_enabled(db, "lol_stats"),
        "xp_enabled": is_feature_enabled(db, "xp"),
    }


class WifiOut(BaseModel):
    ssid: str
    password: Optional[str]
    security: str
    hidden: bool
    # The event these credentials are handed out for — the event page only shows
    # the WiFi card on this one, not on every event the viewer happens to open.
    event_id: Optional[int]


@router.get("/wifi", response_model=Optional[WifiOut])
def get_wifi(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The guest WiFi credentials, for the people who'll actually be in the room:
    admins, and members with an "in" RSVP to the current event. Everyone else
    gets a 404 — same as a disabled feature, so the network's existence isn't
    advertised to members who aren't coming. `null` when no SSID is set."""
    event = current_event(db)
    if user.role != "admin":
        attending = event is not None and db.query(EventRSVP).filter(
            EventRSVP.event_id == event.id,
            EventRSVP.user_id == user.id,
            EventRSVP.status == "in",
        ).first() is not None
        if not attending:
            raise HTTPException(404, "Not found")
    wifi = wifi_config(db)
    return WifiOut(**wifi, event_id=event.id if event else None) if wifi else None


class DiscordTestRequest(BaseModel):
    type: str  # "announcement" | "reminder"


@router.post("/discord-test")
def discord_test(
    data: DiscordTestRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Post a sample Discord message so an admin can confirm the webhook + template
    render correctly before relying on the real announcement/reminder jobs."""
    # Imported here (not at module top) to avoid a circular import — discord_notify
    # imports get_setting from this module.
    from discord_notify import (
        send_discord_message,
        DEFAULT_REMINDER_TEMPLATE,
        DEFAULT_ANNOUNCEMENT_TEMPLATE,
    )
    from mailer import render_template

    if not get_setting(db, "discord_webhook_url"):
        raise HTTPException(400, "Discord webhook URL is not configured")

    sample = {
        "event_title": "Test LAN Party",
        "start_date": "2026-08-15",
        "end_date": "2026-08-17",
        "location": "Chris's basement",
        "app_base_url": get_setting(db, "app_base_url") or "",
    }

    if data.type == "reminder":
        tpl = get_setting(db, "discord_tpl_reminder") or DEFAULT_REMINDER_TEMPLATE
    elif data.type == "announcement":
        tpl = get_setting(db, "discord_tpl_announcement") or DEFAULT_ANNOUNCEMENT_TEMPLATE
    else:
        raise HTTPException(400, f"Unknown test type: {data.type}")

    content = "🧪 **[TEST]** " + render_template(tpl, **sample)
    if not send_discord_message(db, content):
        raise HTTPException(502, "Failed to post to Discord — check the webhook URL")
    return {"ok": True}


@router.put("/{key}", response_model=AppSettingOut)
def upsert_setting(
    key: str,
    data: AppSettingUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if key not in ALLOWED_KEYS:
        raise HTTPException(400, f"Unknown setting key: {key}")
    if key == "currency" and data.value and data.value not in ALLOWED_CURRENCIES:
        raise HTTPException(400, f"Unsupported currency: {data.value}")
    if key == "wifi_security" and data.value and data.value not in ALLOWED_WIFI_SECURITY:
        raise HTTPException(400, f"Unsupported WiFi security: {data.value}")
    s = db.query(AppSetting).filter(AppSetting.key == key).first()
    if s:
        s.value = data.value
    else:
        s = AppSetting(key=key, value=data.value)
        db.add(s)
    db.commit()
    db.refresh(s)
    return s
