"""Deactivating or deleting a member should remove them from event attendee
lists (past and current alike) and — for events that haven't concluded yet —
from the pro-rata split, while a *past* event's split stays exactly as it
was. A full deletion also frees the username/email for reuse.

Reported after testing the desktop app against a real crew: a deactivated
member kept showing up as an event attendee (their RSVP row was untouched —
only their ability to log in was), and there was no way to fully delete a
test/throwaway account at all. The attendee-list and capacity fixes key off
`User.is_active` alone — deletion deliberately never touches EventRSVP rows,
since a past event's cost split is settled history keyed on those same rows.
"""
from datetime import date

import database
import models
from conftest import auth_header, login, make_user


def _event_with_attendees(founder_id, other_id):
    session = database.SessionLocal()
    try:
        event = models.LanEvent(
            title="LAN", start_date=date(2026, 8, 1), end_date=date(2026, 8, 3),
            created_by=founder_id,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        for uid in (founder_id, other_id):
            session.add(models.EventRSVP(
                event_id=event.id, user_id=uid, status="in",
                arrival_date=date(2026, 8, 1), departure_date=date(2026, 8, 3),
            ))
        session.commit()
        return event.id
    finally:
        session.close()


def _attendee_ids(client, token, event_id):
    resp = client.get(f"/api/events/{event_id}", headers=auth_header(token))
    assert resp.status_code == 200
    return {a["user_id"] for a in resp.json()["attendees"]}


def test_deactivated_member_disappears_from_attendee_list(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    founder_token = login(client, "founder")
    event_id = _event_with_attendees(founder_id, bob_id)

    assert _attendee_ids(client, founder_token, event_id) == {founder_id, bob_id}

    resp = client.put(f"/api/users/{bob_id}/deactivate", headers=auth_header(founder_token))
    assert resp.status_code == 200

    assert _attendee_ids(client, founder_token, event_id) == {founder_id}


def test_deactivated_member_freed_capacity_slot(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    founder_token = login(client, "founder")

    session = database.SessionLocal()
    try:
        event = models.LanEvent(
            title="Small LAN", start_date=date(2026, 8, 1), end_date=date(2026, 8, 3),
            created_by=founder_id, capacity=2,
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        for uid in (founder_id, bob_id):
            session.add(models.EventRSVP(
                event_id=event.id, user_id=uid, status="in",
                arrival_date=date(2026, 8, 1), departure_date=date(2026, 8, 3),
            ))
        session.commit()
        event_id = event.id
    finally:
        session.close()

    charlie_id = make_user("charlie")
    charlie_token = login(client, "charlie")
    # Full at capacity 2 — a third RSVP is rejected.
    resp = client.post(
        f"/api/events/{event_id}/rsvp",
        json={"arrival_date": "2026-08-01", "departure_date": "2026-08-03"},
        headers=auth_header(charlie_token),
    )
    assert resp.status_code == 400

    client.put(f"/api/users/{bob_id}/deactivate", headers=auth_header(founder_token))

    # Deactivating bob should free his capacity slot.
    resp = client.post(
        f"/api/events/{event_id}/rsvp",
        json={"arrival_date": "2026-08-01", "departure_date": "2026-08-03"},
        headers=auth_header(charlie_token),
    )
    assert resp.status_code == 200


def test_admin_cannot_deactivate_or_delete_self(client):
    founder_id = make_user("founder", role="admin")
    founder_token = login(client, "founder")

    assert client.put(
        f"/api/users/{founder_id}/deactivate", headers=auth_header(founder_token)
    ).status_code == 400
    assert client.delete(
        f"/api/users/{founder_id}", headers=auth_header(founder_token)
    ).status_code == 400


def test_delete_user_removes_from_attendees_and_scrubs_identity(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob", password="password123")
    bob_token = login(client, "bob", password="password123")
    founder_token = login(client, "founder")
    event_id = _event_with_attendees(founder_id, bob_id)

    resp = client.delete(f"/api/users/{bob_id}", headers=auth_header(founder_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == f"deleted_user_{bob_id}"
    assert body["email"] == f"deleted_user_{bob_id}@deleted.invalid"
    assert body["is_active"] is False
    assert body["deleted_at"] is not None

    assert _attendee_ids(client, founder_token, event_id) == {founder_id}

    # bob's pre-deletion token no longer authenticates anything (inactive account).
    resp = client.get("/api/auth/me", headers=auth_header(bob_token))
    assert resp.status_code == 401


def test_deleted_member_username_and_email_are_free_for_reuse(client):
    founder_id = make_user("founder", role="admin")
    founder_token = login(client, "founder")

    event_resp = client.post(
        "/api/events/",
        json={"title": "LAN", "start_date": "2026-08-01", "end_date": "2026-08-03"},
        headers=auth_header(founder_token),
    )
    event_id = event_resp.json()["id"]
    code = client.post(
        f"/api/events/{event_id}/invite", headers=auth_header(founder_token)
    ).json()["code"]

    resp = client.post(
        "/api/auth/register",
        json={
            "username": "bob", "email": "bob@example.com", "password": "password123",
            "invite_code": code, "arrival_date": "2026-08-01", "departure_date": "2026-08-02",
        },
    )
    assert resp.status_code == 201
    bob_id = resp.json()["id"]

    client.delete(f"/api/users/{bob_id}", headers=auth_header(founder_token))

    # A fresh registration can now reuse "bob" / "bob@example.com" — the
    # deleted row's identity fields were scrubbed, not just its status flipped.
    # A used-once invite code still has seats (event has no capacity cap set).
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "bob", "email": "bob@example.com", "password": "password456",
            "invite_code": code, "arrival_date": "2026-08-01", "departure_date": "2026-08-02",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["username"] == "bob"
    assert resp.json()["id"] != bob_id  # a genuinely new row, not the old one reactivated


def test_deleted_member_hidden_from_the_hub_roster_even_for_admins(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    founder_token = login(client, "founder")

    ids = {u["id"] for u in client.get("/api/users/", headers=auth_header(founder_token)).json()}
    assert ids == {founder_id, bob_id}

    client.delete(f"/api/users/{bob_id}", headers=auth_header(founder_token))

    # An admin still sees a merely-deactivated account (to be able to
    # reactivate it) but never a deleted one — it has no identity left worth
    # showing in the live crew list.
    ids = {u["id"] for u in client.get("/api/users/", headers=auth_header(founder_token)).json()}
    assert ids == {founder_id}


def test_deleted_users_history_endpoint_is_admin_only(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    founder_token = login(client, "founder")
    bob_token = login(client, "bob")

    assert client.get("/api/users/deleted", headers=auth_header(bob_token)).status_code == 403

    client.delete(f"/api/users/{bob_id}", headers=auth_header(founder_token))

    resp = client.get("/api/users/deleted", headers=auth_header(founder_token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == bob_id
    assert body[0]["deleted_username"] == "bob"
    assert body[0]["deleted_at"] is not None


def test_cannot_delete_an_already_deleted_account(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    founder_token = login(client, "founder")

    client.delete(f"/api/users/{bob_id}", headers=auth_header(founder_token))
    resp = client.delete(f"/api/users/{bob_id}", headers=auth_header(founder_token))
    assert resp.status_code == 400


def _event_with_expense(founder_id, bob_id, start, end):
    """An event both attended, each fronting an expense — enough to build a
    real pro-rata split with both a debtor and a creditor side."""
    session = database.SessionLocal()
    try:
        event = models.LanEvent(title="LAN", start_date=start, end_date=end, created_by=founder_id)
        session.add(event)
        session.commit()
        session.refresh(event)

        for uid in (founder_id, bob_id):
            session.add(models.EventRSVP(
                event_id=event.id, user_id=uid, status="in",
                arrival_date=start, departure_date=end,
            ))
        session.add(models.Expense(
            description="Venue", amount=100.0, category="general",
            date=start, created_by=founder_id, paid_by=founder_id, event_id=event.id,
        ))
        session.commit()
        return event.id
    finally:
        session.close()


def _prorata_user_ids(client, token, event_id):
    resp = client.get(f"/api/expenses/prorata?event_id={event_id}", headers=auth_header(token))
    assert resp.status_code == 200
    return {s["user_id"] for s in resp.json()["shares"]}


def test_deleted_member_excluded_from_a_current_events_prorata(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    founder_token = login(client, "founder")
    # Clearly in the future regardless of when this test runs.
    event_id = _event_with_expense(founder_id, bob_id, date(2030, 8, 1), date(2030, 8, 3))

    assert _prorata_user_ids(client, founder_token, event_id) == {founder_id, bob_id}

    client.delete(f"/api/users/{bob_id}", headers=auth_header(founder_token))

    assert _prorata_user_ids(client, founder_token, event_id) == {founder_id}


def test_deleted_members_past_event_prorata_is_kept_as_is(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    founder_token = login(client, "founder")
    # Clearly concluded regardless of when this test runs.
    event_id = _event_with_expense(founder_id, bob_id, date(2020, 8, 1), date(2020, 8, 3))

    assert _prorata_user_ids(client, founder_token, event_id) == {founder_id, bob_id}

    client.delete(f"/api/users/{bob_id}", headers=auth_header(founder_token))

    # A past event's split is settled history — deleting bob later must not
    # retroactively reshuffle it.
    assert _prorata_user_ids(client, founder_token, event_id) == {founder_id, bob_id}
