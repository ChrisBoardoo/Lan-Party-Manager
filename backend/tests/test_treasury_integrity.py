"""Treasury integrity: bounded amounts, real events, audited writes, and event
date changes / deletions that don't silently rewrite or lose the money."""

from datetime import date, timedelta

import pytest

import database
import models
from conftest import auth_header, login, make_user


def _event(start=date(2026, 10, 14), end=date(2026, 10, 18)):
    s = database.SessionLocal()
    try:
        admin = s.query(models.User).filter(models.User.role == "admin").first()
        ev = models.LanEvent(title="LAN", start_date=start, end_date=end, created_by=admin.id)
        s.add(ev)
        s.commit()
        return ev.id
    finally:
        s.close()


def _expense(client, token, **overrides):
    body = {"description": "Pizza", "amount": 60, "date": "2026-10-14", **overrides}
    return client.post("/api/expenses/", json=body, headers=auth_header(token))


def _audit_actions():
    s = database.SessionLocal()
    try:
        return [a.action for a in s.query(models.AuditLog).order_by(models.AuditLog.id).all()]
    finally:
        s.close()


@pytest.mark.parametrize("amount", ["inf", "Infinity", 1e308, 100_000.01, 0.001, 0, -5, True])
def test_unusable_amounts_are_refused(client, amount):
    make_user("tess", role="admin")
    token = login(client, "tess")
    assert _expense(client, token, amount=amount).status_code == 422


def test_amount_is_stored_in_cents(client):
    make_user("tess", role="admin")
    token = login(client, "tess")
    resp = _expense(client, token, amount=12.345)
    assert resp.status_code == 201 and resp.json()["amount"] == 12.35


def test_expense_must_point_at_an_existing_event(client):
    make_user("tess", role="admin")
    token = login(client, "tess")
    assert _expense(client, token, event_id=9999).status_code == 400


def test_every_expense_write_is_audited(client):
    make_user("tess", role="admin")
    token = login(client, "tess")
    eid = _event()
    expense_id = _expense(client, token, event_id=eid).json()["id"]
    body = {"description": "Pizza", "amount": 90, "date": "2026-10-14", "event_id": eid}
    assert client.put(f"/api/expenses/{expense_id}", json=body, headers=auth_header(token)).status_code == 200
    assert client.delete(f"/api/expenses/{expense_id}", headers=auth_header(token)).status_code == 200
    assert _audit_actions() == ["expense_created", "expense_updated", "expense_deleted"]
    s = database.SessionLocal()
    try:
        updated = s.query(models.AuditLog).filter_by(action="expense_updated").one().details
    finally:
        s.close()
    assert "60.00 €" in updated and "90.00 €" in updated


def test_event_end_before_start_is_refused_on_update(client):
    make_user("admin", role="admin")
    token = login(client, "admin")
    eid = _event()
    resp = client.put(f"/api/events/{eid}", json={"end_date": "2026-10-01"}, headers=auth_header(token))
    assert resp.status_code == 400


def test_postponing_an_event_moves_the_rsvps_with_it(client):
    make_user("admin", role="admin")
    token = login(client, "admin")
    uid = make_user("bob")
    eid = _event()
    s = database.SessionLocal()
    try:
        s.add(models.EventRSVP(event_id=eid, user_id=uid, status="in",
                               arrival_date=date(2026, 10, 15), departure_date=date(2026, 10, 17)))
        s.commit()
    finally:
        s.close()

    resp = client.put(
        f"/api/events/{eid}", json={"start_date": "2026-10-21", "end_date": "2026-10-25"},
        headers=auth_header(token),
    )
    assert resp.status_code == 200
    s = database.SessionLocal()
    try:
        rsvp = s.query(models.EventRSVP).filter_by(event_id=eid, user_id=uid).one()
        assert (rsvp.arrival_date, rsvp.departure_date) == (date(2026, 10, 22), date(2026, 10, 24))
    finally:
        s.close()
    assert "event_dates_changed" in _audit_actions()


def test_deleting_an_event_hands_its_expenses_back_as_unassigned(client):
    make_user("admin", role="admin")
    token = login(client, "admin")
    eid = _event()
    _expense(client, token, event_id=eid, amount=300)
    assert client.delete(f"/api/events/{eid}", headers=auth_header(token)).status_code == 200
    count = client.get("/api/expenses/unassigned-count", headers=auth_header(token)).json()["count"]
    assert count == 1
