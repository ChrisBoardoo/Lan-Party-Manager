"""Endpoint tests for the self-service settlement markers.

A debtor marks/reverses only their OWN who-owes-whom line (the endpoint forces
from_user_id == the caller), and the pro-rata payload reflects the marker."""

from datetime import date

import database
import models
from conftest import login, auth_header, make_user


def _seed_event_with_debt(founder_id, bob_id):
    """Founder fronts a 100 expense; both attend equally -> Bob owes 50 to founder."""
    session = database.SessionLocal()
    try:
        event = models.LanEvent(
            title="Summer LAN",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 3),  # 2 nights
            created_by=founder_id,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        for uid in (founder_id, bob_id):
            session.add(models.EventRSVP(
                event_id=event.id, user_id=uid, status="in",
                arrival_date=date(2026, 8, 1), departure_date=date(2026, 8, 3),
            ))
        session.add(models.Expense(
            description="Venue", amount=100.0, category="general",
            date=date(2026, 8, 1), created_by=founder_id, paid_by=founder_id,
            event_id=event.id,
        ))
        session.commit()
        return event.id
    finally:
        session.close()


def _line(client, token, event_id, from_id, to_id):
    resp = client.get(f"/api/expenses/prorata?event_id={event_id}", headers=auth_header(token))
    assert resp.status_code == 200
    for l in resp.json()["settlements"]:
        if l["from_user_id"] == from_id and l["to_user_id"] == to_id:
            return l
    return None


def test_prorata_reflects_mark_and_reverse(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    event_id = _seed_event_with_debt(founder_id, bob_id)
    bob = login(client, "bob")

    # Bob owes founder 50, initially unpaid, and sees founder's (absent) phone slot.
    line = _line(client, bob, event_id, bob_id, founder_id)
    assert line is not None and line["amount"] == 50.0 and line["paid"] is False

    # Mark sent.
    r = client.post(
        "/api/expenses/settlements/mark",
        json={"event_id": event_id, "to_user_id": founder_id},
        headers=auth_header(bob),
    )
    assert r.status_code == 200 and r.json()["paid"] is True
    assert _line(client, bob, event_id, bob_id, founder_id)["paid"] is True

    # Reverse.
    r = client.request(
        "DELETE", "/api/expenses/settlements/mark",
        json={"event_id": event_id, "to_user_id": founder_id},
        headers=auth_header(bob),
    )
    assert r.status_code == 200 and r.json()["paid"] is False
    assert _line(client, bob, event_id, bob_id, founder_id)["paid"] is False


def test_mark_is_idempotent(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    event_id = _seed_event_with_debt(founder_id, bob_id)
    bob = login(client, "bob")

    for _ in range(2):
        r = client.post(
            "/api/expenses/settlements/mark",
            json={"event_id": event_id, "to_user_id": founder_id},
            headers=auth_header(bob),
        )
        assert r.status_code == 200

    session = database.SessionLocal()
    try:
        count = session.query(models.SettlementPayment).filter(
            models.SettlementPayment.event_id == event_id,
            models.SettlementPayment.from_user_id == bob_id,
            models.SettlementPayment.to_user_id == founder_id,
        ).count()
        assert count == 1  # no duplicate row
    finally:
        session.close()


def test_cannot_owe_yourself(client):
    bob_id = make_user("bob")
    bob = login(client, "bob")
    r = client.post(
        "/api/expenses/settlements/mark",
        json={"event_id": 1, "to_user_id": bob_id},
        headers=auth_header(bob),
    )
    assert r.status_code == 400


def test_mark_requires_auth(client):
    r = client.post(
        "/api/expenses/settlements/mark",
        json={"event_id": 1, "to_user_id": 2},
    )
    assert r.status_code == 401
