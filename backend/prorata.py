from typing import Any, Dict, Iterable, List, Optional, Tuple

from models import LanEvent, EventRSVP

# Everything below runs on integer cents: shares, balances and transfers add up
# exactly, instead of drifting a cent or two per person (100 € split 7 ways used
# to hand out 100.03 €).


def _cents(amount: float) -> int:
    return int(round(amount * 100))


def _split(total: int, weights: Dict[int, int]) -> Dict[int, int]:
    """Split the integer `total` across `weights`' keys in proportion to their
    (integer) weights, largest remainder first, so the parts always add up to
    `total` exactly. Ties go to the lowest key, so the result is stable."""
    weight_sum = sum(weights.values())
    if weight_sum == 0:
        return {k: 0 for k in weights}
    parts = {k: (total * w) // weight_sum for k, w in weights.items()}
    remainders = {k: (total * w) % weight_sum for k, w in weights.items()}
    left = total - sum(parts.values())
    for k in sorted(weights, key=lambda k: (-remainders[k], k))[:left]:
        parts[k] += 1
    return parts


def _normalize_payments(payments: Optional[Iterable]) -> Tuple[List[Any], List[Tuple[int, int, Optional[int]]]]:
    """Split `payments` into recorded transfers (with an amount) and legacy
    "paid" markers (a debtor/creditor pair without one, from before amounts
    were recorded — also accepted as bare (from, to) tuples)."""
    recorded, legacy = [], []
    for p in payments or ():
        if isinstance(p, tuple):
            legacy.append((p[0], p[1], None))
        elif getattr(p, "amount", None) is None:
            legacy.append((p.from_user_id, p.to_user_id, getattr(p, "id", None)))
        else:
            recorded.append(p)
    return recorded, legacy


def _line(users: Dict[int, Any], from_id: int, to_id: int, cents: int, viewer_id: Optional[int],
          paid: bool, payment_id: Optional[int]) -> dict:
    debtor, creditor = users.get(from_id), users.get(to_id)
    return {
        "from_user_id": from_id,
        "from_username": getattr(debtor, "username", "?"),
        "to_user_id": to_id,
        "to_username": getattr(creditor, "username", "?"),
        # Reveal the creditor's contact phone only to the debtor who owes them.
        "to_phone": getattr(creditor, "phone", None) if viewer_id == from_id and not paid else None,
        "amount": cents / 100,
        "paid": paid,
        "payment_id": payment_id,
    }


def _build_settlement(
    balances: Dict[int, int],
    users: Dict[int, Any],
    legacy_pairs: Dict[Tuple[int, int], Optional[int]],
    viewer_id: Optional[int],
) -> List[dict]:
    """Greedy minimal-transaction settlement over what's still owed. `balances`
    maps user_id -> net cents (fronted + sent - share - received); positive =
    creditor, negative = debtor. A legacy "paid" marker on a pair flags the
    matching line, as it always did."""
    creditors = [[uid, bal] for uid, bal in sorted(balances.items(), key=lambda x: (-x[1], x[0])) if bal > 0]
    debtors = [[uid, -bal] for uid, bal in sorted(balances.items(), key=lambda x: (x[1], x[0])) if bal < 0]

    lines: List[dict] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        d_uid, d_amt = debtors[i]
        c_uid, c_amt = creditors[j]
        pay = min(d_amt, c_amt)
        legacy_id = legacy_pairs.get((d_uid, c_uid), "absent")
        paid = legacy_id != "absent"
        lines.append(_line(users, d_uid, c_uid, pay, viewer_id, paid, legacy_id if paid else None))
        debtors[i][1] -= pay
        creditors[j][1] -= pay
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return lines


def calculate_prorata(
    event: LanEvent,
    rsvps: List[EventRSVP],
    expenses: List,
    payments: Optional[Iterable] = None,
    viewer_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Split an event's expenses by person-nights and work out who still owes
    whom. `payments` are the transfers members recorded ("payment sent"), each
    with its amount: they count in the balances, so a receipt added or a date
    changed afterwards shows what's *still* owed instead of re-labelling the
    old line as paid."""
    total_cents = sum(_cents(e.amount) for e in expenses)
    total_event_nights = (event.end_date - event.start_date).days

    # Registry of every person involved (attendees + anyone who fronted an
    # expense), so phones/usernames are available for the settlement.
    users: Dict[int, Any] = {}

    nights_by_user: Dict[int, int] = {}
    stay_by_user: Dict[int, Tuple[str, str]] = {}
    for rsvp in rsvps:
        if not rsvp.arrival_date or not rsvp.departure_date:
            continue
        arrival = max(rsvp.arrival_date, event.start_date)
        departure = min(rsvp.departure_date, event.end_date)
        nights_by_user[rsvp.user_id] = max(0, (departure - arrival).days)
        stay_by_user[rsvp.user_id] = (rsvp.arrival_date.isoformat(), rsvp.departure_date.isoformat())
        users[rsvp.user_id] = rsvp.user

    total_person_nights = sum(nights_by_user.values())
    # Normally the split follows nights. When nobody stays a night at all (a
    # one-day LAN, or everyone came and left the same day), split equally
    # between the attendees — otherwise nobody would owe anything and whoever
    # paid would never be reimbursed.
    weights = nights_by_user if total_person_nights > 0 else {uid: 1 for uid in nights_by_user}
    share_cents = _split(total_cents, weights)
    tenths = _split(1000, weights) if nights_by_user else {}

    shares = [
        {
            "user_id": uid,
            "username": users[uid].username,
            "avatar_url": users[uid].avatar_url,
            "nights": nights_by_user[uid],
            "arrival_date": stay_by_user[uid][0],
            "departure_date": stay_by_user[uid][1],
            "percentage": tenths[uid] / 10,
            "amount": share_cents[uid] / 100,
        }
        for uid in nights_by_user
    ]
    shares.sort(key=lambda x: x["nights"], reverse=True)

    # How much each person actually fronted. paid_by falls back to the creator
    # for legacy rows. Use the SAME expense set that feeds `total_cents`, so
    # net balances (paid - share) sum to zero.
    paid_by_user: Dict[int, int] = {}
    for e in expenses:
        payer = getattr(e, "payer", None) or getattr(e, "creator", None)
        if payer is None or getattr(payer, "id", None) is None:
            continue
        paid_by_user[payer.id] = paid_by_user.get(payer.id, 0) + _cents(e.amount)
        users.setdefault(payer.id, payer)

    balances: Dict[int, int] = {
        uid: paid_by_user.get(uid, 0) - share_cents.get(uid, 0)
        for uid in set(share_cents) | set(paid_by_user)
    }

    recorded, legacy = _normalize_payments(payments)
    history: List[dict] = []
    for p in recorded:
        cents = _cents(p.amount)
        balances[p.from_user_id] = balances.get(p.from_user_id, 0) + cents
        balances[p.to_user_id] = balances.get(p.to_user_id, 0) - cents
        history.append(_line(users, p.from_user_id, p.to_user_id, cents, viewer_id, True, getattr(p, "id", None)))
    legacy_pairs = {(f, t): pid for f, t, pid in legacy}

    settlements = _build_settlement(balances, users, legacy_pairs, viewer_id) + history

    return {
        "total_expenses": total_cents / 100,
        "event_id": event.id,
        "event_title": event.title,
        "event_start": event.start_date.isoformat(),
        "event_end": event.end_date.isoformat(),
        "total_nights": total_event_nights,
        "total_person_nights": total_person_nights,
        "shares": shares,
        "settlements": settlements,
    }
