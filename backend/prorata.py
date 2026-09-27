from typing import List, Dict, Any, Set, Tuple, Optional
from models import LanEvent, EventRSVP


def _build_settlement(
    balances: Dict[int, float],
    users: Dict[int, Any],
    paid_pairs: Set[Tuple[int, int]],
    viewer_id: Optional[int],
) -> List[dict]:
    """Greedy minimal-transaction settlement. `balances` maps user_id -> net
    (paid_total - fair_share); positive = creditor, negative = debtor. Returns
    a list of who-owes-whom lines with the fewest transfers."""
    creditors = sorted(
        ((uid, bal) for uid, bal in balances.items() if bal > 0.005),
        key=lambda x: x[1],
        reverse=True,
    )
    debtors = sorted(
        ((uid, -bal) for uid, bal in balances.items() if bal < -0.005),
        key=lambda x: x[1],
        reverse=True,
    )

    lines: List[dict] = []
    i = j = 0
    creditors = [list(c) for c in creditors]  # mutable [uid, remaining]
    debtors = [list(d) for d in debtors]
    while i < len(debtors) and j < len(creditors):
        d_uid, d_amt = debtors[i]
        c_uid, c_amt = creditors[j]
        pay = round(min(d_amt, c_amt), 2)
        if pay > 0:
            debtor = users.get(d_uid)
            creditor = users.get(c_uid)
            lines.append({
                "from_user_id": d_uid,
                "from_username": getattr(debtor, "username", "?"),
                "to_user_id": c_uid,
                "to_username": getattr(creditor, "username", "?"),
                # Reveal the creditor's contact phone only to the debtor who owes them.
                "to_phone": getattr(creditor, "phone", None) if viewer_id == d_uid else None,
                "amount": pay,
                "paid": (d_uid, c_uid) in paid_pairs,
            })
        debtors[i][1] = round(d_amt - pay, 2)
        creditors[j][1] = round(c_amt - pay, 2)
        if debtors[i][1] <= 0.005:
            i += 1
        if creditors[j][1] <= 0.005:
            j += 1

    return lines


def calculate_prorata(
    event: LanEvent,
    rsvps: List[EventRSVP],
    expenses: List,
    paid_pairs: Optional[Set[Tuple[int, int]]] = None,
    viewer_id: Optional[int] = None,
) -> Dict[str, Any]:
    paid_pairs = paid_pairs or set()
    total_amount = round(sum(e.amount for e in expenses), 2)
    total_event_nights = (event.end_date - event.start_date).days

    # Registry of every person involved (attendees + anyone who fronted an
    # expense), so phones/usernames are available for the settlement.
    users: Dict[int, Any] = {}

    person_data: Dict[int, dict] = {}
    for rsvp in rsvps:
        if not rsvp.arrival_date or not rsvp.departure_date:
            continue
        arrival = max(rsvp.arrival_date, event.start_date)
        departure = min(rsvp.departure_date, event.end_date)
        nights = max(0, (departure - arrival).days)
        person_data[rsvp.user_id] = {
            "user": rsvp.user,
            "nights": nights,
        }
        users[rsvp.user_id] = rsvp.user

    total_person_nights = sum(v["nights"] for v in person_data.values())

    shares = []
    share_by_user: Dict[int, float] = {}
    for user_id, data in person_data.items():
        nights = data["nights"]
        user = data["user"]
        if total_person_nights > 0:
            percentage = round(nights / total_person_nights * 100, 1)
            amount = round(nights / total_person_nights * total_amount, 2)
        else:
            percentage = 0.0
            amount = 0.0
        share_by_user[user_id] = amount

        shares.append({
            "user_id": user_id,
            "username": user.username,
            "avatar_url": user.avatar_url,
            "nights": nights,
            "percentage": percentage,
            "amount": amount,
        })

    shares.sort(key=lambda x: x["nights"], reverse=True)

    # How much each person actually fronted. paid_by falls back to the creator
    # for legacy rows. Use the SAME expense set that feeds `total_amount`, so
    # net balances (paid - share) sum to zero.
    paid_by_user: Dict[int, float] = {}
    for e in expenses:
        payer = getattr(e, "payer", None) or getattr(e, "creator", None)
        if payer is None or getattr(payer, "id", None) is None:
            continue
        paid_by_user[payer.id] = round(paid_by_user.get(payer.id, 0.0) + e.amount, 2)
        users.setdefault(payer.id, payer)

    balances: Dict[int, float] = {}
    for uid in set(share_by_user) | set(paid_by_user):
        balances[uid] = round(paid_by_user.get(uid, 0.0) - share_by_user.get(uid, 0.0), 2)

    settlements = _build_settlement(balances, users, paid_pairs, viewer_id)

    return {
        "total_expenses": total_amount,
        "event_id": event.id,
        "event_title": event.title,
        "event_start": event.start_date.isoformat(),
        "event_end": event.end_date.isoformat(),
        "total_nights": total_event_nights,
        "total_person_nights": total_person_nights,
        "shares": shares,
        "settlements": settlements,
    }
