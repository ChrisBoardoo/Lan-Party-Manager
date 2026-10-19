"""Craving Chat window settings (router_chat._window_open, router_settings.chat_window_config).

The rules pinned here:
- defaults stay 30 days before / 15 days after;
- an admin tunes both, validated as 0–365 days, exposed by /public-config;
- "always open" chains the rooms: a LAN's room is open from its creation, and
  once over stays open until a later LAN exists — never closing sooner than the
  "after" days.
"""
from datetime import date, timedelta

import pytest

import database
import models
from conftest import auth_header, login, make_user


@pytest.fixture
def crew(client):
    make_user("boss", role="admin")
    make_user("member")
    tokens = {"boss": login(client, "boss"), "member": login(client, "member")}
    _set(client, tokens["boss"], "craving_chat_enabled", "true")
    return tokens


def _set(client, token, key, value):
    return client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(token))


def _lan(start_offset, days=2, member_in=True):
    """A LAN starting `start_offset` days from today, the member attending.
    Inserted directly: members can't RSVP once a LAN has started."""
    s = database.SessionLocal()
    try:
        boss = s.query(models.User).filter_by(username="boss").one()
        member = s.query(models.User).filter_by(username="member").one()
        start = date.today() + timedelta(days=start_offset)
        event = models.LanEvent(title=f"LAN {start_offset}", start_date=start, end_date=start + timedelta(days=days),
                                created_by=boss.id)
        s.add(event)
        s.flush()
        if member_in:
            s.add(models.EventRSVP(event_id=event.id, user_id=member.id, status="in",
                                   arrival_date=event.start_date, departure_date=event.end_date))
        s.commit()
        return event.id
    finally:
        s.close()


def _open(client, crew, event_id):
    status = client.get(f"/api/chat/{event_id}/messages", headers=auth_header(crew["member"])).status_code
    assert status in (200, 403), status
    return status == 200


def test_defaults_are_thirty_before_fifteen_after(client, crew):
    config = client.get("/api/settings/public-config", headers=auth_header(crew["member"])).json()
    assert (config["craving_chat_open_days_before"], config["craving_chat_close_days_after"],
            config["craving_chat_always_open"]) == (30, 15, False)
    assert _open(client, crew, _lan(10))
    assert not _open(client, crew, _lan(45))
    assert _open(client, crew, _lan(-14))   # ended 12 days ago
    assert not _open(client, crew, _lan(-20))  # ended 18 days ago


def test_an_admin_tunes_both_ends(client, crew):
    soon, ended = _lan(10), _lan(-20)
    assert _set(client, crew["boss"], "craving_chat_open_days_before", "5").status_code == 200
    assert _set(client, crew["boss"], "craving_chat_close_days_after", "30").status_code == 200
    assert not _open(client, crew, soon)  # opens 5 days before now
    assert _open(client, crew, ended)     # 18 days after, within 30
    config = client.get("/api/settings/public-config", headers=auth_header(crew["member"])).json()
    assert (config["craving_chat_open_days_before"], config["craving_chat_close_days_after"]) == (5, 30)


def test_days_are_validated(client, crew):
    for bad in ("abc", "-3", "366", "1.5"):
        assert _set(client, crew["boss"], "craving_chat_open_days_before", bad).status_code == 400, bad
    assert _set(client, crew["boss"], "craving_chat_close_days_after", "0").status_code == 200
    assert _set(client, crew["boss"], "craving_chat_close_days_after", "").status_code == 200  # back to default
    assert client.get("/api/settings/public-config", headers=auth_header(crew["member"])).json()[
        "craving_chat_close_days_after"] == 15


def test_always_open_chains_the_rooms(client, crew):
    assert _set(client, crew["boss"], "craving_chat_always_open", "true").status_code == 200
    far = _lan(200)
    assert _open(client, crew, far)  # open as soon as the LAN exists
    long_ago = _lan(-200)
    # Over long ago, but a later LAN (`far`) exists: it took over.
    assert not _open(client, crew, long_ago)


def test_the_last_lan_keeps_its_room_until_the_next_one_exists(client, crew):
    _set(client, crew["boss"], "craving_chat_always_open", "true")
    last = _lan(-60)
    assert _open(client, crew, last)  # 58 days after its end, nothing newer: still open
    _lan(120)
    assert not _open(client, crew, last)  # the next LAN exists: it takes over


def test_never_closes_sooner_than_the_after_days(client, crew):
    # A crew creating the next LAN the day the last one ends doesn't cut the
    # post-LAN chatter.
    _set(client, crew["boss"], "craving_chat_always_open", "true")
    just_ended = _lan(-4)
    _lan(90)
    assert _open(client, crew, just_ended)  # ended 2 days ago, within 15


def test_attendees_only_still_applies(client, crew):
    _set(client, crew["boss"], "craving_chat_always_open", "true")
    assert not _open(client, crew, _lan(30, member_in=False))
