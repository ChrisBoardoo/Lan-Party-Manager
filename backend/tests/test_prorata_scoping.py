"""The pro-rata split is scoped to one event's expenses.

This used to be an unfiltered ``query(Expense).all()``: every event's split
silently included every other event's spending, while still being labelled with
one event's id and title. On a single-event box that's invisible, which is how
it survived — the moment a second event exists, both report the same inflated
total and the settlement graph is wrong for both.

These tests fail against that old behaviour.
"""

from datetime import date

import database
import models
from conftest import auth_header, login, make_user


def _event(session, title, start, end, created_by):
    event = models.LanEvent(title=title, start_date=start, end_date=end, created_by=created_by)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _seed_two_events(founder_id, bob_id):
    """Two events, each with its own expense and the same two attendees.

    August: 100 fronted by the founder. September: 400 fronted by Bob. Each
    split should see only its own money.
    """
    session = database.SessionLocal()
    try:
        august = _event(session, "August LAN", date(2026, 8, 1), date(2026, 8, 3), founder_id)
        september = _event(session, "September LAN", date(2026, 9, 1), date(2026, 9, 3), founder_id)

        for event, start, end in ((august, date(2026, 8, 1), date(2026, 8, 3)),
                                  (september, date(2026, 9, 1), date(2026, 9, 3))):
            for uid in (founder_id, bob_id):
                session.add(models.EventRSVP(
                    event_id=event.id, user_id=uid, status="in",
                    arrival_date=start, departure_date=end,
                ))

        session.add(models.Expense(
            description="August venue", amount=100.0, category="general",
            date=date(2026, 8, 1), created_by=founder_id, paid_by=founder_id,
            event_id=august.id,
        ))
        session.add(models.Expense(
            description="September venue", amount=400.0, category="general",
            date=date(2026, 9, 1), created_by=bob_id, paid_by=bob_id,
            event_id=september.id,
        ))
        session.commit()
        return august.id, september.id
    finally:
        session.close()


def _prorata(client, token, event_id):
    resp = client.get(f"/api/expenses/prorata?event_id={event_id}", headers=auth_header(token))
    assert resp.status_code == 200
    return resp.json()


def test_split_sees_only_its_own_events_expenses(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    august_id, september_id = _seed_two_events(founder_id, bob_id)
    token = login(client, "founder")

    august = _prorata(client, token, august_id)
    september = _prorata(client, token, september_id)

    # Before the fix both of these were 500.0 — the global total.
    assert august["total_expenses"] == 100.0
    assert september["total_expenses"] == 400.0
    assert august["event_id"] == august_id
    assert september["event_id"] == september_id


def test_shares_derive_from_the_scoped_total(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    august_id, _ = _seed_two_events(founder_id, bob_id)
    token = login(client, "founder")

    shares = {s["user_id"]: s for s in _prorata(client, token, august_id)["shares"]}

    # Equal stays, so an even split of August's 100 alone.
    assert shares[founder_id]["amount"] == 50.0
    assert shares[bob_id]["amount"] == 50.0


def test_settlement_derives_from_the_scoped_total(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    august_id, september_id = _seed_two_events(founder_id, bob_id)
    token = login(client, "founder")

    # August: founder fronted 100, both owe 50 -> Bob owes the founder 50.
    lines = _prorata(client, token, august_id)["settlements"]
    assert len(lines) == 1
    assert (lines[0]["from_user_id"], lines[0]["to_user_id"]) == (bob_id, founder_id)
    assert lines[0]["amount"] == 50.0

    # September: Bob fronted 400 -> the founder owes Bob 200. The direction
    # flips, which it could not do when both events shared one global total.
    lines = _prorata(client, token, september_id)["settlements"]
    assert len(lines) == 1
    assert (lines[0]["from_user_id"], lines[0]["to_user_id"]) == (founder_id, bob_id)
    assert lines[0]["amount"] == 200.0


def test_untagged_expense_counts_towards_no_split(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    august_id, september_id = _seed_two_events(founder_id, bob_id)

    session = database.SessionLocal()
    try:
        session.add(models.Expense(
            description="Cables, bought whenever", amount=999.0, category="general",
            date=date(2026, 7, 15), created_by=founder_id, paid_by=founder_id,
            event_id=None,
        ))
        session.commit()
    finally:
        session.close()

    token = login(client, "founder")
    assert _prorata(client, token, august_id)["total_expenses"] == 100.0
    assert _prorata(client, token, september_id)["total_expenses"] == 400.0


def test_unassigned_count_surfaces_untagged_expenses(client):
    founder_id = make_user("founder", role="admin")
    make_user("bob")
    token = login(client, "founder")

    assert client.get("/api/expenses/unassigned-count", headers=auth_header(token)).json()["count"] == 0

    session = database.SessionLocal()
    try:
        session.add(models.Expense(
            description="Cables", amount=20.0, category="general",
            date=date(2026, 7, 15), created_by=founder_id, event_id=None,
        ))
        session.commit()
    finally:
        session.close()

    assert client.get("/api/expenses/unassigned-count", headers=auth_header(token)).json()["count"] == 1
