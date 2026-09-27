"""Unit tests for the who-owes-whom settlement in ``calculate_prorata``.

Like ``test_prorata.py`` these feed lightweight namespaces to the pure function.
The settlement layer adds: per-person net balances (fronted - fair share), a
minimal-transaction settlement list, and phone privacy (creditor phone visible
only to the debtor who owes them)."""

from datetime import date
from types import SimpleNamespace

from prorata import calculate_prorata


def _event(start, end, title="Test LAN", eid=1):
    return SimpleNamespace(id=eid, title=title, start_date=start, end_date=end)


def _user(uid, username=None, phone=None):
    return SimpleNamespace(
        id=uid, username=username or f"user{uid}", avatar_url=None, phone=phone
    )


def _rsvp(user, arrival, departure):
    return SimpleNamespace(
        user_id=user.id, arrival_date=arrival, departure_date=departure, user=user
    )


def _expense(amount, payer):
    return SimpleNamespace(amount=amount, payer=payer, creator=payer)


def test_settlement_nets_to_zero_and_is_minimal():
    # 2 equal nights each -> 50/50 share of 100. Alice fronted all 100.
    alice = _user(1, "alice", phone="+33600000001")
    bob = _user(2, "bob")
    event = _event(date(2026, 8, 1), date(2026, 8, 3))
    rsvps = [
        _rsvp(alice, date(2026, 8, 1), date(2026, 8, 3)),
        _rsvp(bob, date(2026, 8, 1), date(2026, 8, 3)),
    ]
    result = calculate_prorata(event, rsvps, [_expense(100.0, alice)], set(), viewer_id=2)

    # Bob owes his 50 share to Alice, in a single transfer.
    lines = result["settlements"]
    assert len(lines) == 1
    line = lines[0]
    assert line["from_user_id"] == 2 and line["to_user_id"] == 1
    assert line["amount"] == 50.0
    assert line["paid"] is False
    # Bob is the viewer/debtor -> he sees Alice's contact phone.
    assert line["to_phone"] == "+33600000001"


def test_phone_hidden_from_non_debtor_viewer():
    alice = _user(1, "alice", phone="+33600000001")
    bob = _user(2, "bob")
    event = _event(date(2026, 8, 1), date(2026, 8, 3))
    rsvps = [
        _rsvp(alice, date(2026, 8, 1), date(2026, 8, 3)),
        _rsvp(bob, date(2026, 8, 1), date(2026, 8, 3)),
    ]
    # Viewer is Alice (the creditor), NOT the debtor on this line.
    result = calculate_prorata(event, rsvps, [_expense(100.0, alice)], set(), viewer_id=1)
    assert result["settlements"][0]["to_phone"] is None


def test_paid_flag_reflects_marked_pairs():
    alice = _user(1, "alice")
    bob = _user(2, "bob")
    event = _event(date(2026, 8, 1), date(2026, 8, 3))
    rsvps = [
        _rsvp(alice, date(2026, 8, 1), date(2026, 8, 3)),
        _rsvp(bob, date(2026, 8, 1), date(2026, 8, 3)),
    ]
    # Bob (2) -> Alice (1) is marked paid.
    result = calculate_prorata(
        event, rsvps, [_expense(100.0, alice)], {(2, 1)}, viewer_id=2
    )
    assert result["settlements"][0]["paid"] is True


def test_three_way_minimal_transactions():
    # Everyone equal share (nights identical), Alice fronts 90, others 0.
    alice = _user(1, "alice")
    bob = _user(2, "bob")
    cara = _user(3, "cara")
    event = _event(date(2026, 8, 1), date(2026, 8, 2))  # 1 night
    rsvps = [
        _rsvp(alice, date(2026, 8, 1), date(2026, 8, 2)),
        _rsvp(bob, date(2026, 8, 1), date(2026, 8, 2)),
        _rsvp(cara, date(2026, 8, 1), date(2026, 8, 2)),
    ]
    result = calculate_prorata(event, rsvps, [_expense(90.0, alice)], set(), viewer_id=None)

    lines = result["settlements"]
    # Bob and Cara each owe 30 to Alice -> exactly 2 transfers, both to Alice.
    assert len(lines) == 2
    assert all(l["to_user_id"] == 1 for l in lines)
    assert sorted(l["amount"] for l in lines) == [30.0, 30.0]
    # Net check: total settled equals what the debtors underpaid.
    assert round(sum(l["amount"] for l in lines), 2) == 60.0


def test_no_debt_when_everyone_paid_their_share():
    alice = _user(1, "alice")
    bob = _user(2, "bob")
    event = _event(date(2026, 8, 1), date(2026, 8, 3))
    rsvps = [
        _rsvp(alice, date(2026, 8, 1), date(2026, 8, 3)),
        _rsvp(bob, date(2026, 8, 1), date(2026, 8, 3)),
    ]
    # Each fronts exactly their 50 share.
    result = calculate_prorata(
        event, rsvps, [_expense(50.0, alice), _expense(50.0, bob)], set()
    )
    assert result["settlements"] == []
