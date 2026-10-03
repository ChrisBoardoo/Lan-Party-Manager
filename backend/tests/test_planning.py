"""Tests for the Planning ("Calendar View") feature — /api/planning.

Covers: feature-flag gating, the two toggles (propose/vote) with per-event
override, RSVP-bounded ("honest slot") vote validation, vote tallies, and
lock/unlock permissions.
"""

import pytest

from conftest import register, login, auth_header, make_user

EVENT_START = "2099-08-15"
EVENT_END = "2099-08-17"


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


def _set(client, token, key, value):
    resp = client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(token))
    resp.raise_for_status()


def _member(client, username="member"):
    make_user(username, role="user")
    return login(client, username)


def _create_event(client, admin_token, **extra):
    payload = {"title": "Summer LAN", "start_date": EVENT_START, "end_date": EVENT_END}
    payload.update(extra)
    resp = client.post("/api/events/", json=payload, headers=auth_header(admin_token))
    resp.raise_for_status()
    return resp.json()["id"]


def _rsvp(client, token, event_id, arrival, departure):
    resp = client.post(
        f"/api/events/{event_id}/rsvp",
        json={"arrival_date": arrival, "departure_date": departure},
        headers=auth_header(token),
    )
    resp.raise_for_status()


def _propose(client, token, event_id, game="Valorant"):
    resp = client.post(
        f"/api/planning/events/{event_id}/blocks",
        json={"game": game},
        headers=auth_header(token),
    )
    return resp


# ── Feature flag gating ─────────────────────────────────────────────────────────

def test_public_config_planning_defaults(client, admin):
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["planning_enabled"] is False           # opt-in, default OFF
    assert cfg["planning_default_can_propose"] is True   # both toggles default ON
    assert cfg["planning_default_can_vote"] is True


def test_planning_gated_for_members_when_off(client, admin):
    event_id = _create_event(client, admin)
    member = _member(client)
    # Off by default: member gets 404, admin passes through to configure it.
    assert client.get(f"/api/planning/events/{event_id}", headers=auth_header(member)).status_code == 404
    assert client.get(f"/api/planning/events/{event_id}", headers=auth_header(admin)).status_code == 200
    # Once enabled, the member can read it too.
    _set(client, admin, "planning_enabled", "true")
    assert client.get(f"/api/planning/events/{event_id}", headers=auth_header(member)).status_code == 200


# ── Propose toggle ──────────────────────────────────────────────────────────────

def test_propose_respects_toggle_and_override(client, admin):
    _set(client, admin, "planning_enabled", "true")
    event_id = _create_event(client, admin)
    member = _member(client)

    # Default can_propose ON → member may propose.
    assert _propose(client, member, event_id, "CS2").status_code == 201

    # Turn the global default OFF → member blocked, admin still allowed.
    _set(client, admin, "planning_default_can_propose", "false")
    assert _propose(client, member, event_id, "Dota").status_code == 403
    assert _propose(client, admin, event_id, "Dota").status_code == 201

    # Per-event override turns it back ON for this event only.
    client.put(
        f"/api/events/{event_id}",
        json={"planning_can_propose": True},
        headers=auth_header(admin),
    ).raise_for_status()
    assert _propose(client, member, event_id, "Rocket League").status_code == 201


# ── Vote: RSVP-bounded honest slots ─────────────────────────────────────────────

def test_vote_is_bounded_by_rsvp_window(client, admin):
    _set(client, admin, "planning_enabled", "true")
    event_id = _create_event(client, admin)
    member = _member(client)
    _rsvp(client, member, event_id, "2099-08-15", "2099-08-16")  # present 15→16 only
    block_id = _propose(client, admin, event_id).json()["id"]

    def vote(token, slots):
        return client.put(
            f"/api/planning/blocks/{block_id}/votes",
            json={"slots": slots}, headers=auth_header(token),
        )

    # In-window, on the hour → OK, tally + my_slots reflect it.
    ok = vote(member, ["2099-08-15T20:00:00"])
    assert ok.status_code == 200
    body = ok.json()
    assert body["my_slots"] == ["2099-08-15T20:00:00"]
    assert body["tallies"] == [{"slot_start": "2099-08-15T20:00:00", "count": 1}]

    # After the member's departure day → rejected.
    assert vote(member, ["2099-08-17T20:00:00"]).status_code == 400
    # Before the event starts → rejected.
    assert vote(member, ["2099-08-14T20:00:00"]).status_code == 400
    # Not top-of-the-hour → rejected.
    assert vote(member, ["2099-08-15T20:30:00"]).status_code == 400


def test_vote_requires_rsvp(client, admin):
    _set(client, admin, "planning_enabled", "true")
    event_id = _create_event(client, admin)
    member = _member(client)  # no RSVP
    block_id = _propose(client, admin, event_id).json()["id"]
    resp = client.put(
        f"/api/planning/blocks/{block_id}/votes",
        json={"slots": ["2099-08-15T20:00:00"]}, headers=auth_header(member),
    )
    assert resp.status_code == 400


def test_vote_toggle_blocks_members_but_not_admin(client, admin):
    _set(client, admin, "planning_enabled", "true")
    _set(client, admin, "planning_default_can_vote", "false")
    event_id = _create_event(client, admin)
    _rsvp(client, admin, event_id, "2099-08-15", "2099-08-17")
    member = _member(client)
    _rsvp(client, member, event_id, "2099-08-15", "2099-08-17")
    block_id = _propose(client, admin, event_id).json()["id"]

    # Member blocked by the toggle; admin bypasses it (still bounded by RSVP).
    assert client.put(
        f"/api/planning/blocks/{block_id}/votes",
        json={"slots": ["2099-08-15T21:00:00"]}, headers=auth_header(member),
    ).status_code == 403
    assert client.put(
        f"/api/planning/blocks/{block_id}/votes",
        json={"slots": ["2099-08-15T21:00:00"]}, headers=auth_header(admin),
    ).status_code == 200


def test_tally_counts_multiple_voters(client, admin):
    _set(client, admin, "planning_enabled", "true")
    event_id = _create_event(client, admin)
    _rsvp(client, admin, event_id, "2099-08-15", "2099-08-17")
    m1 = _member(client, "alice")
    m2 = _member(client, "bob")
    _rsvp(client, m1, event_id, "2099-08-15", "2099-08-17")
    _rsvp(client, m2, event_id, "2099-08-15", "2099-08-17")
    block_id = _propose(client, admin, event_id).json()["id"]

    slot = ["2099-08-16T20:00:00"]
    for tok in (m1, m2):
        client.put(f"/api/planning/blocks/{block_id}/votes", json={"slots": slot}, headers=auth_header(tok)).raise_for_status()

    blocks = client.get(f"/api/planning/events/{event_id}", headers=auth_header(admin)).json()["blocks"]
    tallies = blocks[0]["tallies"]
    assert tallies == [{"slot_start": "2099-08-16T20:00:00", "count": 2}]


# ── Lock / unlock ────────────────────────────────────────────────────────────────

def test_lock_unlock_permissions(client, admin):
    _set(client, admin, "planning_enabled", "true")
    event_id = _create_event(client, admin)
    member = _member(client)
    stranger = _member(client, "stranger")
    block_id = _propose(client, member, event_id).json()["id"]

    lock_body = {"locked_start": "2099-08-16T20:00:00", "locked_end": "2099-08-16T22:00:00"}

    # A non-proposer, non-admin member cannot lock.
    assert client.post(
        f"/api/planning/blocks/{block_id}/lock", json=lock_body, headers=auth_header(stranger)
    ).status_code == 403

    # Admin locks → status flips and window is stored.
    locked = client.post(f"/api/planning/blocks/{block_id}/lock", json=lock_body, headers=auth_header(admin))
    assert locked.status_code == 200
    assert locked.json()["status"] == "locked"
    assert locked.json()["locked_start"] == "2099-08-16T20:00:00"

    # Unlock clears it.
    unlocked = client.post(f"/api/planning/blocks/{block_id}/unlock", headers=auth_header(admin))
    assert unlocked.json()["status"] == "proposed"
    assert unlocked.json()["locked_start"] is None


def test_lock_rejects_backwards_window(client, admin):
    _set(client, admin, "planning_enabled", "true")
    event_id = _create_event(client, admin)
    block_id = _propose(client, admin, event_id).json()["id"]
    resp = client.post(
        f"/api/planning/blocks/{block_id}/lock",
        json={"locked_start": "2099-08-16T22:00:00", "locked_end": "2099-08-16T20:00:00"},
        headers=auth_header(admin),
    )
    assert resp.status_code == 400


# ── Calendar view: color + saved view preference ────────────────────────────────

def test_lock_with_and_without_color(client, admin):
    _set(client, admin, "planning_enabled", "true")
    event_id = _create_event(client, admin)
    block_id = _propose(client, admin, event_id).json()["id"]

    locked = client.post(
        f"/api/planning/blocks/{block_id}/lock",
        json={"locked_start": "2099-08-16T20:00:00", "locked_end": "2099-08-16T22:00:00", "color": "peacock"},
        headers=auth_header(admin),
    )
    assert locked.status_code == 200
    assert locked.json()["color"] == "peacock"

    # Locking without a color leaves it null — the frontend derives a default.
    block_id_2 = _propose(client, admin, event_id, game="Overwatch").json()["id"]
    locked_2 = client.post(
        f"/api/planning/blocks/{block_id_2}/lock",
        json={"locked_start": "2099-08-16T20:00:00", "locked_end": "2099-08-16T22:00:00"},
        headers=auth_header(admin),
    )
    assert locked_2.json()["color"] is None


def test_view_preference_round_trip_and_validation(client, admin):
    _set(client, admin, "planning_enabled", "true")
    event_id = _create_event(client, admin)
    member = _member(client)

    # No preference saved yet.
    initial = client.get(f"/api/planning/events/{event_id}", headers=auth_header(member))
    assert initial.json()["my_schedule_view"] is None

    saved = client.patch(
        "/api/planning/view-preference", json={"view": "calendar"}, headers=auth_header(member)
    )
    assert saved.status_code == 200

    after = client.get(f"/api/planning/events/{event_id}", headers=auth_header(member))
    assert after.json()["my_schedule_view"] == "calendar"

    rejected = client.patch(
        "/api/planning/view-preference", json={"view": "weekly"}, headers=auth_header(member)
    )
    assert rejected.status_code == 422
