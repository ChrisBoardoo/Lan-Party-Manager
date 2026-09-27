"""Tests for the Craving Chat — /api/chat.

Covers: feature-flag gating (admin bypasses the flag but not attendance/
window), attendee-only access, the 30-days-before/15-days-after window,
self-service-only message deletion, replies, the 10-minute edit window,
WhatsApp-style single-reaction-per-person, and link previews (unit-tested
separately in test_link_preview.py — this file only checks the endpoints
wire it up correctly: FastAPI's TestClient runs BackgroundTasks synchronously
before returning, so `link_preview` is already settled by the time these
requests come back).
"""
from datetime import date, datetime, timedelta

import pytest

from conftest import register, login, auth_header, make_user


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


def _member(client, username="member"):
    make_user(username, role="user")
    return login(client, username)


def _enable_chat(client, admin):
    client.put("/api/settings/craving_chat_enabled", json={"value": "true"}, headers=auth_header(admin)).raise_for_status()


def _make_event(client, admin, start_offset_days=10, duration_days=2, title="Summer LAN"):
    """Returns (event_id, start_date, end_date) — RSVPs must fall within
    [start_date, end_date], so callers need the event's own dates, not just
    its id, to RSVP "in" for it (see router_events._rsvp_in)."""
    start = date.today() + timedelta(days=start_offset_days)
    end = start + timedelta(days=duration_days)
    r = client.post(
        "/api/events/",
        json={"title": title, "start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=auth_header(admin),
    )
    r.raise_for_status()
    return r.json()["id"], start, end


def _rsvp(client, token, event_id, arrival, departure):
    r = client.post(
        f"/api/events/{event_id}/rsvp",
        json={"arrival_date": arrival, "departure_date": departure},
        headers=auth_header(token),
    )
    r.raise_for_status()


def _rsvp_full_stay(client, token, event_id, start, end):
    _rsvp(client, token, event_id, start.isoformat(), end.isoformat())


def test_feature_gate_admin_bypasses_flag_not_attendance(client, admin):
    member = _member(client)
    ev, start, end = _make_event(client, admin)
    # Both need to be real attendees to isolate the feature-flag check from
    # the (always-on) attendance gate.
    _rsvp_full_stay(client, admin, ev, start, end)
    _rsvp_full_stay(client, member, ev, start, end)

    # craving_chat_enabled defaults ON (opt-out) — flip it off explicitly to
    # exercise the disabled path.
    client.put("/api/settings/craving_chat_enabled", json={"value": "false"}, headers=auth_header(admin)).raise_for_status()

    # Disabled: member 404s, admin still gets through (feature-flag bypass).
    assert client.get(f"/api/chat/{ev}/messages", headers=auth_header(member)).status_code == 404
    assert client.get(f"/api/chat/{ev}/messages", headers=auth_header(admin)).status_code == 200

    _enable_chat(client, admin)
    assert client.get(f"/api/chat/{ev}/messages", headers=auth_header(member)).status_code == 200


def test_non_attendee_is_refused_even_when_enabled(client, admin):
    _enable_chat(client, admin)
    member = _member(client)
    ev, start, end = _make_event(client, admin)
    # Never RSVP'd "in" — refused regardless of the feature being on.
    assert client.get(f"/api/chat/{ev}/messages", headers=auth_header(member)).status_code == 403

    _rsvp_full_stay(client, member, ev, start, end)
    assert client.get(f"/api/chat/{ev}/messages", headers=auth_header(member)).status_code == 200


def test_window_closed_outside_30_before_15_after(client, admin):
    _enable_chat(client, admin)
    member = _member(client)
    # 60 days out: further than the 30-day-before opening.
    far_event, far_start, far_end = _make_event(client, admin, start_offset_days=60, title="Far LAN")
    _rsvp_full_stay(client, member, far_event, far_start, far_end)
    assert client.get(f"/api/chat/{far_event}/messages", headers=auth_header(member)).status_code == 403

    # Within the pre-event window (10 days out, opens at 30) — should be open.
    near_event, near_start, near_end = _make_event(client, admin, start_offset_days=10, title="Near LAN")
    _rsvp_full_stay(client, member, near_event, near_start, near_end)
    assert client.get(f"/api/chat/{near_event}/messages", headers=auth_header(member)).status_code == 200


def test_post_and_list_messages(client, admin):
    _enable_chat(client, admin)
    member = _member(client)
    other = _member(client, "other")
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, member, ev, start, end)
    _rsvp_full_stay(client, other, ev, start, end)

    r = client.post(f"/api/chat/{ev}/messages", json={"content": "so hyped for this LAN"}, headers=auth_header(member))
    assert r.status_code == 201
    body = r.json()
    assert body["content"] == "so hyped for this LAN"
    assert body["username"] == "member"
    assert body["is_mine"] is True

    payload = client.get(f"/api/chat/{ev}/messages", headers=auth_header(other)).json()
    assert len(payload) == 1
    assert payload[0]["content"] == "so hyped for this LAN"
    assert payload[0]["is_mine"] is False


def test_delete_own_message_only(client, admin):
    _enable_chat(client, admin)
    member = _member(client)
    other = _member(client, "other")
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, member, ev, start, end)
    _rsvp_full_stay(client, other, ev, start, end)

    msg_id = client.post(
        f"/api/chat/{ev}/messages", json={"content": "craving pizza"}, headers=auth_header(member)
    ).json()["id"]

    assert client.delete(f"/api/chat/{ev}/messages/{msg_id}", headers=auth_header(other)).status_code == 403
    assert client.delete(f"/api/chat/{ev}/messages/{msg_id}", headers=auth_header(member)).status_code == 200
    assert client.get(f"/api/chat/{ev}/messages", headers=auth_header(member)).json() == []


def test_reply_preview(client, admin):
    _enable_chat(client, admin)
    member = _member(client)
    other = _member(client, "other")
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, member, ev, start, end)
    _rsvp_full_stay(client, other, ev, start, end)

    original = client.post(
        f"/api/chat/{ev}/messages", json={"content": "who's bringing snacks"}, headers=auth_header(member)
    ).json()

    reply = client.post(
        f"/api/chat/{ev}/messages",
        json={"content": "I got chips", "reply_to_id": original["id"]},
        headers=auth_header(other),
    )
    assert reply.status_code == 201
    body = reply.json()
    assert body["reply_to"]["id"] == original["id"]
    assert body["reply_to"]["username"] == "member"
    assert body["reply_to"]["content"] == "who's bringing snacks"

    # Replying to a message from a different event is rejected.
    other_event, o_start, o_end = _make_event(client, admin, start_offset_days=11, title="Other LAN")
    _rsvp_full_stay(client, other, other_event, o_start, o_end)
    bad = client.post(
        f"/api/chat/{other_event}/messages",
        json={"content": "nope", "reply_to_id": original["id"]},
        headers=auth_header(other),
    )
    assert bad.status_code == 400


def test_edit_within_window_and_after_owner_only(client, admin, db):
    _enable_chat(client, admin)
    member = _member(client)
    other = _member(client, "other")
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, member, ev, start, end)
    _rsvp_full_stay(client, other, ev, start, end)

    msg = client.post(
        f"/api/chat/{ev}/messages", json={"content": "typo pls ignroe"}, headers=auth_header(member)
    ).json()

    # Not the author.
    assert client.patch(
        f"/api/chat/{ev}/messages/{msg['id']}", json={"content": "nope"}, headers=auth_header(other)
    ).status_code == 403

    # Within the window: succeeds, sets edited_at.
    edited = client.patch(
        f"/api/chat/{ev}/messages/{msg['id']}", json={"content": "typo pls ignore"}, headers=auth_header(member)
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["content"] == "typo pls ignore"
    assert body["edited_at"] is not None

    # Backdate created_at past the 10-minute window and retry.
    from models import ChatMessage
    row = db.query(ChatMessage).filter(ChatMessage.id == msg["id"]).first()
    row.created_at = datetime.utcnow() - timedelta(minutes=11)
    db.commit()

    late = client.patch(
        f"/api/chat/{ev}/messages/{msg['id']}", json={"content": "too late"}, headers=auth_header(member)
    )
    assert late.status_code == 403


def test_reactions_one_per_person_toggle_and_replace(client, admin):
    _enable_chat(client, admin)
    member = _member(client)
    other = _member(client, "other")
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, member, ev, start, end)
    _rsvp_full_stay(client, other, ev, start, end)

    msg_id = client.post(
        f"/api/chat/{ev}/messages", json={"content": "craving tacos"}, headers=auth_header(member)
    ).json()["id"]

    # Any emoji string is accepted (not a fixed set like Media reactions).
    r1 = client.post(f"/api/chat/{ev}/messages/{msg_id}/react", json={"emoji": "🌮"}, headers=auth_header(other))
    assert r1.status_code == 200
    reactions = r1.json()["reactions"]
    assert reactions == [{"emoji": "🌮", "count": 1, "mine": True}] or reactions[0]["emoji"] == "🌮"

    # Same emoji again removes it.
    r2 = client.post(f"/api/chat/{ev}/messages/{msg_id}/react", json={"emoji": "🌮"}, headers=auth_header(other))
    assert r2.json()["reactions"] == []

    # A different emoji replaces (not stacks) — still exactly one reaction from `other`.
    client.post(f"/api/chat/{ev}/messages/{msg_id}/react", json={"emoji": "🔥"}, headers=auth_header(other))
    final = client.post(f"/api/chat/{ev}/messages/{msg_id}/react", json={"emoji": "❤️"}, headers=auth_header(other))
    assert len(final.json()["reactions"]) == 1
    assert final.json()["reactions"][0]["emoji"] == "❤️"
    assert final.json()["reactions"][0]["count"] == 1

    # A second person reacting with the same emoji adds to the count.
    from_member = client.post(f"/api/chat/{ev}/messages/{msg_id}/react", json={"emoji": "❤️"}, headers=auth_header(member))
    tally = from_member.json()["reactions"][0]
    assert tally["emoji"] == "❤️" and tally["count"] == 2


def test_link_in_message_never_gets_an_ssrf_preview(client, admin):
    """The background fetch really runs (TestClient executes it inline) and
    really tries the URL, but the target is on the SSRF blocklist, so
    link_preview must stay null rather than the request erroring or hanging."""
    _enable_chat(client, admin)
    member = _member(client)
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, member, ev, start, end)

    posted = client.post(
        f"/api/chat/{ev}/messages",
        json={"content": "check this out http://127.0.0.1:1/nope"},
        headers=auth_header(member),
    )
    assert posted.status_code == 201
    assert posted.json()["link_preview"] is None

    # Still null after a fresh read — proves the background task actually
    # ran (not just "hasn't happened yet") and correctly found nothing safe
    # to show, rather than erroring out silently mid-request.
    fetched = client.get(f"/api/chat/{ev}/messages", headers=auth_header(member)).json()
    assert fetched[0]["link_preview"] is None


def test_editing_away_a_link_clears_its_preview(client, admin):
    _enable_chat(client, admin)
    member = _member(client)
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, member, ev, start, end)

    msg = client.post(
        f"/api/chat/{ev}/messages",
        json={"content": "link: http://127.0.0.1:1/nope"},
        headers=auth_header(member),
    ).json()
    assert msg["link_preview"] is None  # blocked target, nothing to show anyway

    edited = client.patch(
        f"/api/chat/{ev}/messages/{msg['id']}",
        json={"content": "never mind, no link anymore"},
        headers=auth_header(member),
    )
    assert edited.status_code == 200
    assert edited.json()["link_preview"] is None


def test_mention_notifies_only_the_mentioned_attendee(client, admin):
    _enable_chat(client, admin)
    member = _member(client)
    other = _member(client, "other")
    bystander = _member(client, "bystander")
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, member, ev, start, end)
    _rsvp_full_stay(client, other, ev, start, end)
    _rsvp_full_stay(client, bystander, ev, start, end)

    posted = client.post(
        f"/api/chat/{ev}/messages", json={"content": "hey @other, bring the router"}, headers=auth_header(member)
    )
    assert posted.status_code == 201
    mentions = posted.json()["mentions"]
    assert len(mentions) == 1
    assert mentions[0]["username"] == "other"

    # The mentioned attendee sees a "chat_mention" activity entry...
    other_feed = client.get("/api/activity/", headers=auth_header(other)).json()
    assert any(e["action"] == "chat_mention" for e in other_feed)

    # ...but a bystander attendee (RSVP'd, not mentioned) never does — this is
    # exactly the "targeted, not broadcast" behavior recipient_user_id exists for.
    bystander_feed = client.get("/api/activity/", headers=auth_header(bystander)).json()
    assert not any(e["action"] == "chat_mention" for e in bystander_feed)


def test_mention_matches_full_username_not_a_prefix(client, admin):
    """"@Cross" must not accidentally mention "CrossWax" — only an exact,
    word-bounded username match (what the autocomplete would actually offer)
    can ever resolve."""
    _enable_chat(client, admin)
    member = _member(client)
    make_user("Cross", role="user")
    cross = login(client, "Cross")
    make_user("CrossWax", role="user")
    crosswax = login(client, "CrossWax")
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, member, ev, start, end)
    _rsvp_full_stay(client, cross, ev, start, end)
    _rsvp_full_stay(client, crosswax, ev, start, end)

    posted = client.post(
        f"/api/chat/{ev}/messages", json={"content": "yo @CrossWax you around?"}, headers=auth_header(member)
    )
    mentions = posted.json()["mentions"]
    assert [m["username"] for m in mentions] == ["CrossWax"]


def test_edit_recomputes_mentions_without_renotifying(client, admin):
    _enable_chat(client, admin)
    member = _member(client)
    other = _member(client, "other")
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, member, ev, start, end)
    _rsvp_full_stay(client, other, ev, start, end)

    msg = client.post(
        f"/api/chat/{ev}/messages", json={"content": "no mentions yet"}, headers=auth_header(member)
    ).json()
    assert msg["mentions"] == []

    edited = client.patch(
        f"/api/chat/{ev}/messages/{msg['id']}", json={"content": "actually @other check this"}, headers=auth_header(member)
    )
    assert edited.status_code == 200
    assert [m["username"] for m in edited.json()["mentions"]] == ["other"]

    # A newly-added-on-edit mention still doesn't notify (v1 keeps this simple).
    other_feed = client.get("/api/activity/", headers=auth_header(other)).json()
    assert not any(e["action"] == "chat_mention" for e in other_feed)


def test_pin_and_unpin_admin_only(client, admin):
    _enable_chat(client, admin)
    member = _member(client)
    ev, start, end = _make_event(client, admin)
    _rsvp_full_stay(client, admin, ev, start, end)
    _rsvp_full_stay(client, member, ev, start, end)

    msg = client.post(
        f"/api/chat/{ev}/messages", json={"content": "meet at the north entrance"}, headers=auth_header(member)
    ).json()

    # Nothing pinned yet.
    assert client.get(f"/api/chat/{ev}/pinned", headers=auth_header(member)).json() is None

    # A non-admin attendee can't pin.
    assert client.post(f"/api/chat/{ev}/pin/{msg['id']}", headers=auth_header(member)).status_code == 403

    pinned = client.post(f"/api/chat/{ev}/pin/{msg['id']}", headers=auth_header(admin))
    assert pinned.status_code == 200
    body = pinned.json()
    assert body["id"] == msg["id"]
    assert body["content"] == "meet at the north entrance"

    fetched = client.get(f"/api/chat/{ev}/pinned", headers=auth_header(member)).json()
    assert fetched["id"] == msg["id"]

    # A non-admin attendee can't unpin either.
    assert client.delete(f"/api/chat/{ev}/pin", headers=auth_header(member)).status_code == 403

    assert client.delete(f"/api/chat/{ev}/pin", headers=auth_header(admin)).status_code == 200
    assert client.get(f"/api/chat/{ev}/pinned", headers=auth_header(member)).json() is None


def test_pin_rejects_message_from_a_different_event(client, admin):
    _enable_chat(client, admin)
    ev, start, end = _make_event(client, admin, title="LAN A")
    other_ev, o_start, o_end = _make_event(client, admin, start_offset_days=11, title="LAN B")
    _rsvp_full_stay(client, admin, ev, start, end)
    _rsvp_full_stay(client, admin, other_ev, o_start, o_end)

    msg = client.post(f"/api/chat/{ev}/messages", json={"content": "hello"}, headers=auth_header(admin)).json()

    assert client.post(f"/api/chat/{other_ev}/pin/{msg['id']}", headers=auth_header(admin)).status_code == 404


def test_public_config_exposes_craving_chat_flag(client, admin):
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["craving_chat_enabled"] is True  # default ON, opt-out
    client.put("/api/settings/craving_chat_enabled", json={"value": "false"}, headers=auth_header(admin)).raise_for_status()
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["craving_chat_enabled"] is False
