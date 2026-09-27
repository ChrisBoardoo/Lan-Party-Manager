"""Tests for the Kiosk / Big Screen — /api/kiosk.

The kiosk is authorized by a token alone (no user session), so these exercise
the enable-flag gate, the token compare, admin-only minting/revoking, and that
the summary reflects live data.
"""
from datetime import date, timedelta

import pytest

from conftest import register, login, auth_header, make_user


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


def _enable_kiosk(client, admin):
    client.put("/api/settings/kiosk_enabled", json={"value": "true"}, headers=auth_header(admin)).raise_for_status()


def _mint(client, admin):
    resp = client.post("/api/kiosk/admin/token", headers=auth_header(admin))
    resp.raise_for_status()
    return resp.json()["token"]


def test_summary_404_when_disabled(client, admin):
    # Even with a token, a disabled kiosk is invisible.
    token = _mint(client, admin)
    assert client.get(f"/api/kiosk/summary?token={token}").status_code == 404


def test_summary_401_without_or_wrong_token(client, admin):
    _enable_kiosk(client, admin)
    _mint(client, admin)
    assert client.get("/api/kiosk/summary").status_code == 401
    assert client.get("/api/kiosk/summary?token=nope").status_code == 401


def test_summary_200_with_valid_token_no_session(client, admin):
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    # No Authorization header at all — the projector has no user session.
    resp = client.get(f"/api/kiosk/summary?token={token}")
    assert resp.status_code == 200
    body = resp.json()
    assert "server_time" in body and "matches" in body and "arrivals" in body


def test_token_via_header_also_works(client, admin):
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    resp = client.get("/api/kiosk/summary", headers={"X-Kiosk-Token": token})
    assert resp.status_code == 200


def test_non_ascii_token_is_401_not_500(client, admin):
    # secrets.compare_digest raises TypeError on non-ASCII str; the fix compares
    # bytes so a garbage token is a clean 401, never a 500. Non-ASCII can only
    # arrive via the query param (HTTP header values are ASCII-only) — %C3%A9 = é.
    _enable_kiosk(client, admin)
    _mint(client, admin)
    resp = client.get("/api/kiosk/summary?token=caf%C3%A9-not-the-token")
    assert resp.status_code == 401


def test_revoke_invalidates_old_token(client, admin):
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    assert client.get(f"/api/kiosk/summary?token={token}").status_code == 200
    client.delete("/api/kiosk/admin/token", headers=auth_header(admin)).raise_for_status()
    assert client.get(f"/api/kiosk/summary?token={token}").status_code == 401


def test_rotate_invalidates_old_token(client, admin):
    _enable_kiosk(client, admin)
    old = _mint(client, admin)
    new = _mint(client, admin)
    assert old != new
    assert client.get(f"/api/kiosk/summary?token={old}").status_code == 401
    assert client.get(f"/api/kiosk/summary?token={new}").status_code == 200


def test_admin_endpoints_are_admin_only(client, admin):
    make_user("member", role="user")
    member = login(client, "member")
    assert client.get("/api/kiosk/admin", headers=auth_header(member)).status_code == 403
    assert client.post("/api/kiosk/admin/token", headers=auth_header(member)).status_code == 403
    assert client.delete("/api/kiosk/admin/token", headers=auth_header(member)).status_code == 403


def test_summary_reflects_event_and_announcement(client, admin, db):
    _enable_kiosk(client, admin)
    token = _mint(client, admin)

    # An upcoming event the current-event helper will select.
    start = (date.today() + timedelta(days=3)).isoformat()
    end = (date.today() + timedelta(days=5)).isoformat()
    client.post(
        "/api/events/",
        json={"title": "Summer LAN", "start_date": start, "end_date": end},
        headers=auth_header(admin),
    ).raise_for_status()

    client.post(
        "/api/announcements/",
        json={"message": "Pizza's here", "level": "info"},
        headers=auth_header(admin),
    ).raise_for_status()

    body = client.get(f"/api/kiosk/summary?token={token}").json()
    assert body["event"]["title"] == "Summer LAN"
    assert body["countdown"]["label"] == "Summer LAN"
    assert [a["message"] for a in body["announcements"]] == ["Pizza's here"]


# ── The photo wall is scoped to the event in scope ────────────────────────────

def _seed_photo(caption, event_id, uploaded_by, **extra):
    import database
    import models

    session = database.SessionLocal()
    try:
        fields = dict(
            filename=f"{caption}.jpg", original_name=f"{caption}.jpg", file_type="image",
            mime_type="image/jpeg", file_size=10, url=f"/uploads/media/{caption}.jpg",
            caption=caption, event_id=event_id, uploaded_by=uploaded_by,
        )
        fields.update(extra)
        item = models.MediaItem(**fields)
        session.add(item)
        session.commit()
        return item.id
    finally:
        session.close()


def _react(media_id, user_id, emoji):
    import database
    import models

    session = database.SessionLocal()
    try:
        session.add(models.MediaReaction(media_id=media_id, user_id=user_id, emoji=emoji))
        session.commit()
    finally:
        session.close()


def _two_events(client, admin):
    """The current-event helper picks the soonest event still running/upcoming,
    so 'Summer LAN' is the one in scope and 'Old LAN' is last year's."""
    import database
    import models

    session = database.SessionLocal()
    try:
        founder_id = session.query(models.User).filter_by(username="founder").first().id
        old = models.LanEvent(
            title="Old LAN",
            start_date=date.today() - timedelta(days=400),
            end_date=date.today() - timedelta(days=398),
            created_by=founder_id,
        )
        current = models.LanEvent(
            title="Summer LAN",
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=5),
            created_by=founder_id,
        )
        session.add_all([old, current])
        session.commit()
        return founder_id, old.id, current.id
    finally:
        session.close()


def test_photo_wall_excludes_another_events_photos(client, admin):
    """The projector showed last year's LAN: the media query had no event filter
    at all and simply took the newest 12 images in the database."""
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    founder_id, old_id, current_id = _two_events(client, admin)

    _seed_photo("from-this-lan", current_id, founder_id)
    _seed_photo("from-last-year", old_id, founder_id)

    captions = [m["caption"] for m in client.get(f"/api/kiosk/summary?token={token}").json()["media"]]
    assert "from-this-lan" in captions
    assert "from-last-year" not in captions


def test_photo_wall_still_shows_untagged_photos(client, admin):
    """Deliberately lenient, mirroring the tournaments query: media event_id is
    nullable and the gallery tags uploads with whatever filter was selected, so
    strict scoping would empty the wall for any crew that doesn't tag."""
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    founder_id, old_id, current_id = _two_events(client, admin)

    _seed_photo("untagged", None, founder_id)

    captions = [m["caption"] for m in client.get(f"/api/kiosk/summary?token={token}").json()["media"]]
    assert "untagged" in captions


def test_photo_wall_shows_everything_when_there_is_no_event(client, admin):
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    import database
    import models

    session = database.SessionLocal()
    try:
        founder_id = session.query(models.User).filter_by(username="founder").first().id
    finally:
        session.close()

    _seed_photo("orphan", None, founder_id)
    captions = [m["caption"] for m in client.get(f"/api/kiosk/summary?token={token}").json()["media"]]
    assert captions == ["orphan"]


def test_wall_shows_playable_videos_but_not_avi(client, admin):
    """The #LoveWall renders videos in a <video> (the old slideshow was
    <img>-only, hence images-only). AVI plays in no browser, so it stays off."""
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    founder_id, _old_id, current_id = _two_events(client, admin)

    _seed_photo("an-mp4", current_id, founder_id, file_type="video", mime_type="video/mp4",
                url="/uploads/media/clip.mp4", thumbnail_url="/uploads/thumbnails/clip.jpg")
    _seed_photo("an-avi", current_id, founder_id, file_type="video", mime_type="video/x-msvideo",
                url="/uploads/media/clip.avi")

    media = client.get(f"/api/kiosk/summary?token={token}").json()["media"]
    by_caption = {m["caption"]: m for m in media}
    assert by_caption["an-mp4"]["file_type"] == "video"
    assert by_caption["an-mp4"]["thumbnail_url"] == "/uploads/thumbnails/clip.jpg"
    assert "an-avi" not in by_caption


# ── #LoveWall: who posted, how the room reacted, the coup de cœur ─────────────

def test_wall_item_carries_uploader_and_reaction_counts_only(client, admin):
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    founder_id, _old_id, current_id = _two_events(client, admin)
    member_id = make_user("member", role="user")

    photo = _seed_photo("pizza", current_id, founder_id)
    _react(photo, founder_id, "🔥")
    _react(photo, member_id, "🔥")
    _react(photo, member_id, "😂")

    body = client.get(f"/api/kiosk/summary?token={token}").json()
    item = body["media"][0]
    assert item["id"] == photo
    assert item["uploader"] == "founder"
    assert item["reaction_total"] == 3
    assert item["reactions"] == [{"emoji": "🔥", "count": 2}, {"emoji": "😂", "count": 1}]
    # Who reacted never reaches the shared screen — counts only.
    assert "member" not in str(item["reactions"])
    assert body["media_total"] == 1
    assert body["media_reactions_total"] == 3


def test_love_pick_is_the_most_reacted_even_when_older_than_the_wall(client, admin):
    from datetime import datetime
    from router_kiosk import WALL_SIZE

    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    founder_id, _old_id, current_id = _two_events(client, admin)

    old_hit = _seed_photo("old-hit", current_id, founder_id, created_at=datetime(2020, 1, 1))
    _react(old_hit, founder_id, "❤️")
    for i in range(WALL_SIZE):
        _seed_photo(f"new-{i}", current_id, founder_id)

    body = client.get(f"/api/kiosk/summary?token={token}").json()
    media = body["media"]
    # The WALL_SIZE newest, plus the coup de cœur riding along at the end.
    assert len(media) == WALL_SIZE + 1
    assert media[-1]["caption"] == "old-hit"
    assert [m["caption"] for m in media if m["love_pick"]] == ["old-hit"]
    assert body["media_total"] == WALL_SIZE + 1


def test_no_love_pick_until_someone_reacts(client, admin):
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    founder_id, _old_id, current_id = _two_events(client, admin)
    _seed_photo("quiet", current_id, founder_id)

    media = client.get(f"/api/kiosk/summary?token={token}").json()["media"]
    assert [m["love_pick"] for m in media] == [False]


def test_love_pick_ignores_another_events_photos(client, admin):
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    founder_id, old_id, current_id = _two_events(client, admin)

    last_year = _seed_photo("last-year-hit", old_id, founder_id)
    _react(last_year, founder_id, "🔥")
    _seed_photo("this-lan", current_id, founder_id)

    media = client.get(f"/api/kiosk/summary?token={token}").json()["media"]
    assert [m["caption"] for m in media] == ["this-lan"]
    assert not any(m["love_pick"] for m in media)


def test_live_drop_defaults_on_and_is_admin_switchable(client, admin):
    _enable_kiosk(client, admin)
    token = _mint(client, admin)
    assert client.get(f"/api/kiosk/summary?token={token}").json()["live_drop"] is True

    client.put(
        "/api/settings/kiosk_live_drop_enabled", json={"value": "false"}, headers=auth_header(admin),
    ).raise_for_status()
    assert client.get(f"/api/kiosk/summary?token={token}").json()["live_drop"] is False
