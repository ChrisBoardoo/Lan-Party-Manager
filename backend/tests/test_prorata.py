"""Unit tests for the flagship pro-rata cost split (``prorata.calculate_prorata``).

The function is pure and duck-typed, so we feed it lightweight namespaces rather
than persisted ORM rows — this keeps the tests fast and focused on the maths.
"""

from datetime import date
from types import SimpleNamespace

from prorata import calculate_prorata


def _event(start, end, title="Test LAN", eid=1):
    return SimpleNamespace(id=eid, title=title, start_date=start, end_date=end)


def _rsvp(user_id, arrival, departure, username=None, avatar_url=None):
    user = SimpleNamespace(username=username or f"user{user_id}", avatar_url=avatar_url)
    return SimpleNamespace(
        user_id=user_id, arrival_date=arrival, departure_date=departure, user=user
    )


def _expense(amount):
    return SimpleNamespace(amount=amount)


def test_even_split_two_people():
    event = _event(date(2026, 8, 1), date(2026, 8, 3))  # 2 nights total
    rsvps = [
        _rsvp(1, date(2026, 8, 1), date(2026, 8, 3)),  # 2 nights
        _rsvp(2, date(2026, 8, 1), date(2026, 8, 3)),  # 2 nights
    ]
    result = calculate_prorata(event, rsvps, [_expense(100.0)])

    assert result["total_expenses"] == 100.0
    assert result["total_person_nights"] == 4
    shares = {s["user_id"]: s for s in result["shares"]}
    assert shares[1]["nights"] == 2
    assert shares[1]["percentage"] == 50.0
    assert shares[1]["amount"] == 50.0
    assert shares[2]["amount"] == 50.0


def test_uneven_split_by_nights():
    event = _event(date(2026, 8, 1), date(2026, 8, 5))  # 4 nights total
    rsvps = [
        _rsvp(1, date(2026, 8, 1), date(2026, 8, 5)),  # 4 nights
        _rsvp(2, date(2026, 8, 4), date(2026, 8, 5)),  # 1 night
    ]
    result = calculate_prorata(event, rsvps, [_expense(100.0)])

    shares = {s["user_id"]: s for s in result["shares"]}
    assert shares[1]["nights"] == 4
    assert shares[2]["nights"] == 1
    assert result["total_person_nights"] == 5
    assert shares[1]["amount"] == 80.0
    assert shares[2]["amount"] == 20.0


def test_dates_clamp_to_event_window():
    """Someone who books outside the event window is clamped to it —
    they can't accrue nights before the event starts or after it ends."""
    event = _event(date(2026, 8, 1), date(2026, 8, 3))  # 2 nights
    rsvps = [
        # Claims Jul 30 -> Aug 10, but only Aug 1 -> Aug 3 counts (2 nights).
        _rsvp(1, date(2026, 7, 30), date(2026, 8, 10)),
    ]
    result = calculate_prorata(event, rsvps, [_expense(50.0)])

    assert result["shares"][0]["nights"] == 2
    assert result["shares"][0]["amount"] == 50.0


def test_zero_person_nights_no_division_error():
    """Everyone attends zero nights -> no ZeroDivisionError, all shares 0."""
    event = _event(date(2026, 8, 1), date(2026, 8, 1))  # 0 nights
    rsvps = [_rsvp(1, date(2026, 8, 1), date(2026, 8, 1))]
    result = calculate_prorata(event, rsvps, [_expense(40.0)])

    assert result["total_person_nights"] == 0
    assert result["shares"][0]["nights"] == 0
    assert result["shares"][0]["percentage"] == 0.0
    assert result["shares"][0]["amount"] == 0.0


def test_rsvp_without_dates_is_excluded():
    event = _event(date(2026, 8, 1), date(2026, 8, 3))
    rsvps = [
        _rsvp(1, date(2026, 8, 1), date(2026, 8, 3)),  # counts
        _rsvp(2, None, None),                          # excluded
        _rsvp(3, date(2026, 8, 1), None),              # excluded (partial)
    ]
    result = calculate_prorata(event, rsvps, [_expense(100.0)])

    assert len(result["shares"]) == 1
    assert result["shares"][0]["user_id"] == 1
    assert result["shares"][0]["amount"] == 100.0


def test_shares_sorted_by_nights_desc():
    event = _event(date(2026, 8, 1), date(2026, 8, 5))
    rsvps = [
        _rsvp(1, date(2026, 8, 4), date(2026, 8, 5)),  # 1 night
        _rsvp(2, date(2026, 8, 1), date(2026, 8, 5)),  # 4 nights
        _rsvp(3, date(2026, 8, 3), date(2026, 8, 5)),  # 2 nights
    ]
    result = calculate_prorata(event, rsvps, [_expense(0.0)])

    assert [s["nights"] for s in result["shares"]] == [4, 2, 1]


def test_amounts_sum_to_total():
    event = _event(date(2026, 8, 1), date(2026, 8, 4))  # 3 nights
    rsvps = [
        _rsvp(1, date(2026, 8, 1), date(2026, 8, 4)),  # 3
        _rsvp(2, date(2026, 8, 2), date(2026, 8, 4)),  # 2
        _rsvp(3, date(2026, 8, 3), date(2026, 8, 4)),  # 1
    ]
    result = calculate_prorata(event, rsvps, [_expense(33.33), _expense(66.67)])

    total_allocated = round(sum(s["amount"] for s in result["shares"]), 2)
    # Rounding per-share can drift by a cent or two; assert it's within tolerance.
    assert abs(total_allocated - result["total_expenses"]) <= 0.05
    assert result["total_expenses"] == 100.0
