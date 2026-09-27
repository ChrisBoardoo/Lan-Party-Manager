"""Media reactions, caption editing, event re-tagging, and the "best of" list.

Reactions are the crew's vote on what was funny, so they're also what the recap's
"best of" is derived from — there's no separate pin. A row's existence is the
reaction; posting the same emoji twice removes it.
"""
from datetime import date

import database
import models
from conftest import auth_header, login, make_user


def _media(uploaded_by, event_id=None, caption=None, file_type="image"):
    session = database.SessionLocal()
    try:
        item = models.MediaItem(
            filename=f"m{uploaded_by}_{caption or 'x'}.jpg",
            original_name="photo.jpg",
            file_type=file_type,
            mime_type="image/jpeg",
            file_size=1234,
            url="/uploads/media/photo.jpg",
            caption=caption,
            event_id=event_id,
            uploaded_by=uploaded_by,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return item.id
    finally:
        session.close()


def _event(created_by, title="Summer LAN"):
    session = database.SessionLocal()
    try:
        event = models.LanEvent(
            title=title, start_date=date(2026, 8, 1), end_date=date(2026, 8, 3), created_by=created_by
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event.id
    finally:
        session.close()


def _react(client, token, media_id, emoji="🔥"):
    return client.post(f"/api/media/{media_id}/react", json={"emoji": emoji}, headers=auth_header(token))


def _get(client, token, media_id):
    resp = client.get("/api/media/", headers=auth_header(token))
    assert resp.status_code == 200
    return next(i for i in resp.json() if i["id"] == media_id)


# ── Reacting ──────────────────────────────────────────────────────────────────

def test_reacting_then_reacting_again_toggles_it_off(client):
    uid = make_user("founder", role="admin")
    token = login(client, "founder")
    mid = _media(uid)

    body = _react(client, token, mid).json()
    assert body["reaction_total"] == 1
    assert body["reactions"] == [{"emoji": "🔥", "count": 1, "mine": True, "users": ["founder"]}]

    body = _react(client, token, mid).json()
    assert body["reaction_total"] == 0
    assert body["reactions"] == []


def test_another_members_reaction_counts_but_is_not_mine(client):
    uid = make_user("founder", role="admin")
    make_user("bob")
    mid = _media(uid)

    founder_token = login(client, "founder")
    bob_token = login(client, "bob")

    _react(client, founder_token, mid)
    _react(client, bob_token, mid)

    seen_by_bob = _get(client, bob_token, mid)
    assert seen_by_bob["reaction_total"] == 2
    # users is who reacted, oldest first — it's what the hover tooltip shows.
    assert seen_by_bob["reactions"] == [{"emoji": "🔥", "count": 2, "mine": True, "users": ["founder", "bob"]}]

    # Bob un-reacts: the founder still sees one, but it isn't Bob's any more.
    _react(client, bob_token, mid)
    seen_by_bob = _get(client, bob_token, mid)
    assert seen_by_bob["reactions"] == [{"emoji": "🔥", "count": 1, "mine": False, "users": ["founder"]}]


def test_distinct_emoji_are_counted_separately(client):
    uid = make_user("founder", role="admin")
    token = login(client, "founder")
    mid = _media(uid)

    _react(client, token, mid, "🔥")
    body = _react(client, token, mid, "😂").json()

    assert body["reaction_total"] == 2
    assert {r["emoji"] for r in body["reactions"]} == {"🔥", "😂"}


def test_reactions_are_ordered_most_reacted_first(client):
    uid = make_user("founder", role="admin")
    make_user("bob")
    mid = _media(uid)
    founder, bob = login(client, "founder"), login(client, "bob")

    _react(client, founder, mid, "🔥")
    _react(client, founder, mid, "😂")
    _react(client, bob, mid, "😂")

    body = _get(client, founder, mid)
    assert [r["emoji"] for r in body["reactions"]] == ["😂", "🔥"]


def test_an_emoji_outside_the_set_is_rejected(client):
    uid = make_user("founder", role="admin")
    token = login(client, "founder")
    mid = _media(uid)
    assert _react(client, token, mid, "🍕").status_code == 400


def test_reacting_to_missing_media_is_404(client):
    make_user("founder", role="admin")
    assert _react(client, login(client, "founder"), 999).status_code == 404


def test_deleting_media_removes_its_reactions(client):
    # SQLite doesn't enforce FKs by default, so this depends entirely on the
    # cascade on MediaItem.reactions.
    uid = make_user("founder", role="admin")
    token = login(client, "founder")
    mid = _media(uid)
    _react(client, token, mid)

    assert client.delete(f"/api/media/{mid}", headers=auth_header(token)).status_code == 200

    session = database.SessionLocal()
    try:
        assert session.query(models.MediaReaction).filter_by(media_id=mid).count() == 0
    finally:
        session.close()


def test_bulk_delete_removes_reactions_too(client):
    uid = make_user("founder", role="admin")
    token = login(client, "founder")
    mid = _media(uid)
    _react(client, token, mid)

    resp = client.post("/api/media/bulk-delete", json={"ids": [mid]}, headers=auth_header(token))
    assert resp.status_code == 200

    session = database.SessionLocal()
    try:
        assert session.query(models.MediaReaction).filter_by(media_id=mid).count() == 0
    finally:
        session.close()


# ── Captions & re-tagging ─────────────────────────────────────────────────────

def test_uploader_can_edit_their_caption(client):
    uid = make_user("founder", role="admin")
    make_user("bob")
    mid = _media(uid, caption="old")
    token = login(client, "founder")

    resp = client.patch(f"/api/media/{mid}", json={"caption": "new"}, headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["caption"] == "new"


def test_another_member_cannot_edit_someone_elses_caption(client):
    uid = make_user("founder", role="admin")
    make_user("bob")
    mid = _media(uid, caption="old")

    resp = client.patch(f"/api/media/{mid}", json={"caption": "hacked"}, headers=auth_header(login(client, "bob")))
    assert resp.status_code == 403


def test_admin_can_edit_anyones_caption(client):
    make_user("founder", role="admin")
    bob_id = make_user("bob")
    mid = _media(bob_id, caption="old")

    resp = client.patch(f"/api/media/{mid}", json={"caption": "moderated"}, headers=auth_header(login(client, "founder")))
    assert resp.status_code == 200


def test_retagging_moves_the_item_between_event_filters(client):
    uid = make_user("founder", role="admin")
    token = login(client, "founder")
    event_id = _event(uid)
    mid = _media(uid, event_id=None)

    assert client.get(f"/api/media/?event_id={event_id}", headers=auth_header(token)).json() == []

    resp = client.patch(f"/api/media/{mid}", json={"event_id": event_id}, headers=auth_header(token))
    assert resp.status_code == 200

    tagged = client.get(f"/api/media/?event_id={event_id}", headers=auth_header(token)).json()
    assert [i["id"] for i in tagged] == [mid]


def test_retagging_to_a_missing_event_is_404(client):
    uid = make_user("founder", role="admin")
    mid = _media(uid)
    resp = client.patch(f"/api/media/{mid}", json={"event_id": 999}, headers=auth_header(login(client, "founder")))
    assert resp.status_code == 404


def test_caption_can_be_cleared(client):
    uid = make_user("founder", role="admin")
    mid = _media(uid, caption="something")
    resp = client.patch(f"/api/media/{mid}", json={"caption": None}, headers=auth_header(login(client, "founder")))
    assert resp.status_code == 200
    assert resp.json()["caption"] is None


# ── Best of ───────────────────────────────────────────────────────────────────

def test_best_orders_by_reaction_count_and_skips_the_unreacted(client):
    uid = make_user("founder", role="admin")
    make_user("bob")
    founder, bob = login(client, "founder"), login(client, "bob")

    quiet = _media(uid, caption="quiet")
    popular = _media(uid, caption="popular")
    middling = _media(uid, caption="middling")

    _react(client, founder, popular, "🔥")
    _react(client, bob, popular, "🔥")
    _react(client, founder, middling, "😂")

    best = client.get("/api/media/best", headers=auth_header(founder)).json()
    assert [i["id"] for i in best] == [popular, middling]
    assert quiet not in [i["id"] for i in best]


def test_best_respects_the_event_filter(client):
    uid = make_user("founder", role="admin")
    token = login(client, "founder")
    event_id = _event(uid)
    tagged = _media(uid, event_id=event_id)
    untagged = _media(uid, event_id=None)

    _react(client, token, tagged)
    _react(client, token, untagged)

    best = client.get(f"/api/media/best?event_id={event_id}", headers=auth_header(token)).json()
    assert [i["id"] for i in best] == [tagged]


def test_best_is_empty_when_nobody_has_reacted(client):
    uid = make_user("founder", role="admin")
    _media(uid)
    assert client.get("/api/media/best", headers=auth_header(login(client, "founder"))).json() == []


# ── Privacy ───────────────────────────────────────────────────────────────────

def test_media_does_not_leak_the_uploaders_email_or_phone(client):
    """The gallery shows every item to every member and the recap can surface
    photos on a public share link, so the nested uploader must be UserPublic.
    It was UserOut, which carries email and phone."""
    uid = make_user("founder", role="admin")
    make_user("bob")
    _media(uid)

    item = client.get("/api/media/", headers=auth_header(login(client, "bob"))).json()[0]
    assert item["uploader"]["username"] == "founder"
    assert "email" not in item["uploader"]
    assert "phone" not in item["uploader"]
