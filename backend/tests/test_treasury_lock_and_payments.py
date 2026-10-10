"""Treasury: exact cents, the zero-night case, payments counted as amounts,
attendance locked from the event's first day (treasurer/admin corrections
only), one rule for deactivated members, and the J-10/J-7/J-1 reminders."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import database
import event_utils
import lan_reminders
import models
from conftest import auth_header, login, make_user
from prorata import calculate_prorata


# ── pure calculation ───────────────────────────────────────────────────────────

def _u(uid):
    return SimpleNamespace(id=uid, username=f"u{uid}", avatar_url=None, phone=None)


def _rsvp(user, arrival, departure):
    return SimpleNamespace(user_id=user.id, arrival_date=arrival, departure_date=departure, user=user)


def _exp(amount, payer):
    return SimpleNamespace(amount=amount, payer=payer, creator=payer)


def _pay(frm, to, amount, pid=1):
    return SimpleNamespace(id=pid, from_user_id=frm, to_user_id=to, amount=amount)


EV = SimpleNamespace(id=1, title="LAN", start_date=date(2026, 10, 14), end_date=date(2026, 10, 18))


def _owed(result):
    return sorted((l["from_user_id"], l["to_user_id"], l["amount"]) for l in result["settlements"] if not l["paid"])


def test_shares_add_up_to_the_cent():
    users = [_u(i) for i in range(1, 8)]
    rsvps = [_rsvp(u, EV.start_date, EV.end_date) for u in users]
    result = calculate_prorata(EV, rsvps, [_exp(100.0, users[0])])
    assert round(sum(s["amount"] for s in result["shares"]), 2) == 100.0
    assert round(sum(s["percentage"] for s in result["shares"]), 1) == 100.0
    # What the settlement asks of each debtor matches their own row.
    shares = {s["user_id"]: s["amount"] for s in result["shares"]}
    for frm, to, amount in _owed(result):
        assert amount == shares[frm]


def test_nobody_stays_a_night_means_an_equal_split():
    a, b, c = _u(1), _u(2), _u(3)
    one_day = SimpleNamespace(id=1, title="Day LAN", start_date=date(2026, 10, 14), end_date=date(2026, 10, 14))
    rsvps = [_rsvp(u, one_day.start_date, one_day.end_date) for u in (a, b, c)]
    result = calculate_prorata(one_day, rsvps, [_exp(60.0, a)])
    assert sorted(s["amount"] for s in result["shares"]) == [20.0, 20.0, 20.0]
    assert _owed(result) == [(2, 1, 20.0), (3, 1, 20.0)]


def test_a_late_receipt_shows_what_is_still_owed():
    a, b, c = _u(1), _u(2), _u(3)
    rsvps = [_rsvp(u, EV.start_date, EV.end_date) for u in (a, b, c)]
    # B paid their 100 to A, then a forgotten 60 € receipt (paid by A) comes in.
    result = calculate_prorata(EV, rsvps, [_exp(300.0, a), _exp(60.0, a)], [_pay(2, 1, 100.0)])
    assert _owed(result) == [(2, 1, 20.0), (3, 1, 120.0)]
    paid = [l for l in result["settlements"] if l["paid"]]
    assert [(l["from_user_id"], l["to_user_id"], l["amount"]) for l in paid] == [(2, 1, 100.0)]


def test_dates_changed_after_a_payment():
    a, b, c = _u(1), _u(2), _u(3)
    start, end = EV.start_date, EV.start_date + timedelta(days=3)
    ev = SimpleNamespace(id=1, title="LAN", start_date=start, end_date=end)
    rsvps = [_rsvp(a, start, end), _rsvp(b, start, end), _rsvp(c, start, start + timedelta(days=1))]
    # A fronted 300, C 150; B already sent 150 to A; C then only stayed one night.
    result = calculate_prorata(ev, rsvps, [_exp(300.0, a), _exp(150.0, c)], [_pay(2, 1, 150.0)])
    # Shares 192.86 / 192.86 / 64.28 (the two leftover cents go to the two
    # largest remainders): A and B each still owe C 42.86.
    assert _owed(result) == [(1, 3, 42.86), (2, 3, 42.86)]


def test_legacy_markers_still_flag_their_line():
    a, b = _u(1), _u(2)
    rsvps = [_rsvp(a, EV.start_date, EV.end_date), _rsvp(b, EV.start_date, EV.end_date)]
    legacy = SimpleNamespace(id=9, from_user_id=2, to_user_id=1, amount=None)
    result = calculate_prorata(EV, rsvps, [_exp(100.0, a)], [legacy])
    assert result["settlements"] == [dict(result["settlements"][0], paid=True, payment_id=9)]


# ── API: payments, lock, corrections ───────────────────────────────────────────

def _seed(start_offset=5, nights=3):
    """Admin + bob + cara, an event starting `start_offset` days from today,
    everyone in for the whole event, admin fronted 300."""
    admin = make_user("admin", role="admin")
    bob, cara = make_user("bob"), make_user("cara")
    start = date.today() + timedelta(days=start_offset)
    s = database.SessionLocal()
    try:
        ev = models.LanEvent(title="LAN", start_date=start, end_date=start + timedelta(days=nights), created_by=admin)
        s.add(ev)
        s.flush()
        for uid in (admin, bob, cara):
            s.add(models.EventRSVP(event_id=ev.id, user_id=uid, status="in",
                                   arrival_date=ev.start_date, departure_date=ev.end_date))
        s.add(models.Expense(description="Rent", amount=300.0, category="general", date=start,
                             created_by=admin, paid_by=admin, event_id=ev.id))
        s.commit()
        return ev.id, admin, bob, cara
    finally:
        s.close()


def _prorata(client, token, eid):
    return client.get(f"/api/expenses/prorata?event_id={eid}", headers=auth_header(token)).json()


def test_marking_paid_records_the_amount_and_adds_up(client):
    eid, admin, bob, _ = _seed()
    t = login(client, "bob")
    resp = client.post("/api/expenses/settlements/mark", json={"event_id": eid, "to_user_id": admin},
                       headers=auth_header(t))
    assert resp.status_code == 200 and resp.json()["amount"] == 100.0
    # Nothing left on that line: marking again is refused.
    again = client.post("/api/expenses/settlements/mark", json={"event_id": eid, "to_user_id": admin},
                        headers=auth_header(t))
    assert again.status_code == 400

    # A late receipt: bob owes 20 more, and paying it adds up into the same row.
    s = database.SessionLocal()
    try:
        s.add(models.Expense(description="Ice", amount=60.0, category="general", date=date.today(),
                             created_by=admin, paid_by=admin, event_id=eid))
        s.commit()
    finally:
        s.close()
    owed = [l for l in _prorata(client, t, eid)["settlements"] if l["from_user_id"] == bob and not l["paid"]]
    assert [l["amount"] for l in owed] == [20.0]
    client.post("/api/expenses/settlements/mark", json={"event_id": eid, "to_user_id": admin}, headers=auth_header(t))
    s = database.SessionLocal()
    try:
        assert s.query(models.SettlementPayment).filter_by(event_id=eid, from_user_id=bob).one().amount == 120.0
    finally:
        s.close()


def test_member_can_change_dates_before_the_lan_but_not_once_it_started(client):
    eid, _, bob, _ = _seed(start_offset=5)
    t = login(client, "bob")
    start = date.today() + timedelta(days=5)
    body = {"arrival_date": str(start), "departure_date": str(start + timedelta(days=1))}
    assert client.post(f"/api/events/{eid}/rsvp", json=body, headers=auth_header(t)).status_code == 200

    started, _, _, _ = _seed_started()
    t2 = login(client, "dan")
    assert client.post(f"/api/events/{started}/rsvp", json=body, headers=auth_header(t2)).status_code == 409
    assert client.delete(f"/api/events/{started}/rsvp", headers=auth_header(t2)).status_code == 409
    event = client.get(f"/api/events/{started}", headers=auth_header(t2)).json()
    assert event["attendance_locked"] is True


def _seed_started():
    """An event that started yesterday, with dan attending."""
    s = database.SessionLocal()
    try:
        admin = s.query(models.User).filter_by(username="admin").first()
        dan = models.User(username="dan", email="dan@example.com", hashed_password=admin.hashed_password)
        s.add(dan)
        start = date.today() - timedelta(days=1)
        ev = models.LanEvent(title="Running LAN", start_date=start, end_date=start + timedelta(days=3),
                             created_by=admin.id)
        s.add(ev)
        s.flush()
        s.add(models.EventRSVP(event_id=ev.id, user_id=dan.id, status="in",
                               arrival_date=ev.start_date, departure_date=ev.end_date))
        s.commit()
        return ev.id, admin.id, dan.id, None
    finally:
        s.close()


def test_treasurer_adjusts_a_member_after_the_start_and_it_is_traced(client):
    _seed()
    eid, admin, dan, _ = _seed_started()
    s = database.SessionLocal()
    try:
        s.add(models.User(username="tess", email="tess@example.com", role="treasurer",
                          hashed_password=s.get(models.User, admin).hashed_password))
        s.commit()
    finally:
        s.close()
    member_t, tess_t = login(client, "bob"), login(client, "tess")
    start = date.today() - timedelta(days=1)
    body = {"status": "in", "arrival_date": str(start), "departure_date": str(start + timedelta(days=1))}

    assert client.put(f"/api/events/{eid}/rsvps/{dan}", json=body, headers=auth_header(member_t)).status_code == 403
    resp = client.put(f"/api/events/{eid}/rsvps/{dan}", json=body, headers=auth_header(tess_t))
    assert resp.status_code == 200 and resp.json()["changed"] is True

    s = database.SessionLocal()
    try:
        rsvp = s.query(models.EventRSVP).filter_by(event_id=eid, user_id=dan).one()
        assert (rsvp.arrival_date, rsvp.departure_date) == (start, start + timedelta(days=1))
        assert s.query(models.AuditLog).filter_by(action="rsvp_adjusted").count() == 1
        note = s.query(models.ActivityLog).filter_by(action="rsvp_adjusted").one()
        assert note.recipient_user_id == dan
    finally:
        s.close()


def test_admin_removes_a_member_from_an_upcoming_lan_and_keeps_their_account(client):
    # The roster's "remove attendance": the member drops out of this event
    # only, instead of losing their account.
    eid, _, bob, _ = _seed(start_offset=4)
    admin_t = login(client, "admin")

    resp = client.put(f"/api/events/{eid}/rsvps/{bob}", json={"status": "out"}, headers=auth_header(admin_t))
    assert resp.status_code == 200 and resp.json()["changed"] is True

    event = client.get(f"/api/events/{eid}", headers=auth_header(admin_t)).json()
    assert bob not in {a["user_id"] for a in event["attendees"]}
    assert event["rsvp_count"] == 2
    assert bob not in {s["user_id"] for s in _prorata(client, admin_t, eid)["shares"]}

    s = database.SessionLocal()
    try:
        assert s.get(models.User, bob).is_active is True
        assert s.query(models.AuditLog).filter_by(action="rsvp_adjusted").count() == 1
        assert s.query(models.ActivityLog).filter_by(action="rsvp_adjusted").one().recipient_user_id == bob
    finally:
        s.close()
    # Their account still works.
    assert login(client, "bob")


def test_deactivated_member_counts_once_the_lan_started_and_not_before(client):
    upcoming, _, _, cara = _seed(start_offset=5)
    running, _, dan, _ = _seed_started()
    s = database.SessionLocal()
    try:
        s.get(models.User, cara).is_active = False
        s.get(models.User, dan).is_active = False
        s.commit()
        rsvps, _, _ = event_utils.event_prorata_inputs(s, s.get(models.LanEvent, upcoming))
        assert cara not in {r.user_id for r in rsvps}
        rsvps, _, _ = event_utils.event_prorata_inputs(s, s.get(models.LanEvent, running))
        assert dan in {r.user_id for r in rsvps}
    finally:
        s.close()


# ── countdown reminders ────────────────────────────────────────────────────────

def test_countdown_reminds_attendees_and_undecided_once(client, monkeypatch):
    sent = []
    monkeypatch.setattr(lan_reminders, "send_email", lambda db, to, subject, body: sent.append((to, subject)))
    eid, admin, bob, cara = _seed(start_offset=7)
    undecided = make_user("eve")
    out = make_user("olaf")
    s = database.SessionLocal()
    try:
        s.query(models.EventRSVP).filter_by(event_id=eid, user_id=cara).one().status = "out"
        s.add(models.EventRSVP(event_id=eid, user_id=out, status="out"))
        s.commit()
    finally:
        s.close()

    lan_reminders.send_lan_countdown_reminders()
    lan_reminders.send_lan_countdown_reminders()  # same day again: nothing new

    s = database.SessionLocal()
    try:
        notes = s.query(models.ActivityLog).filter_by(action="lan_countdown").all()
        assert sorted(n.recipient_user_id for n in notes) == sorted([admin, bob, undecided])
        assert all("Your next LAN is about to start" in n.description for n in notes)
    finally:
        s.close()
    assert len(sent) == 3 and all(subject.startswith("LAN PARTY MANAGER") for _, subject in sent)


@pytest.mark.parametrize("offset,expected", [(10, True), (1, True), (5, False)])
def test_countdown_only_fires_on_j10_j7_j1(client, monkeypatch, offset, expected):
    monkeypatch.setattr(lan_reminders, "send_email", lambda *a: True)
    _seed(start_offset=offset)
    lan_reminders.send_lan_countdown_reminders()
    s = database.SessionLocal()
    try:
        assert (s.query(models.ActivityLog).filter_by(action="lan_countdown").count() > 0) is expected
    finally:
        s.close()
