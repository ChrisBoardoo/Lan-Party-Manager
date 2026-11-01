import json
from collections import defaultdict
from datetime import date
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


def _transfer_cents(p) -> Optional[int]:
    """A transfer's amount in cents: `amount_cents` on a models.Transfer, or the
    float `amount` of a settlement_payments row from 1.3.4 → 1.4.1 (still
    accepted, e.g. by unit tests). None = an amount-less legacy flag."""
    cents = getattr(p, "amount_cents", None)
    if cents is not None:
        return int(cents)
    amount = getattr(p, "amount", None)
    return None if amount is None else _cents(amount)


def _normalize_payments(payments: Optional[Iterable]) -> Tuple[List[Any], List[Tuple[int, int, Optional[int]]]]:
    """Split `payments` into recorded transfers (with an amount) and legacy
    "paid" markers (a debtor/creditor pair without one, from before amounts
    were recorded — also accepted as bare (from, to) tuples)."""
    recorded, legacy = [], []
    for p in payments or ():
        if isinstance(p, tuple):
            legacy.append((p[0], p[1], None))
        elif _transfer_cents(p) is None:
            legacy.append((p.from_user_id, p.to_user_id, getattr(p, "id", None)))
        else:
            recorded.append(p)
    return recorded, legacy


def _history_line(users: Dict[int, Any], p, viewer_id: Optional[int]) -> dict:
    """One recorded transfer, as the "already paid" part of the settlement:
    when it happened, the note, and who entered it (the debtor clicking
    "payment sent", or the treasurer/an admin for them)."""
    line = _line(users, p.from_user_id, p.to_user_id, _transfer_cents(p), viewer_id, True, getattr(p, "id", None))
    recorder = getattr(p, "recorder", None)
    recorded_by = getattr(p, "recorded_by", None)
    transferred_on = getattr(p, "transferred_on", None)
    line.update({
        "transfer_id": getattr(p, "id", None) if hasattr(p, "amount_cents") else None,
        "transferred_on": transferred_on.isoformat() if transferred_on else None,
        "note": getattr(p, "note", None),
        "recorded_by_user_id": recorded_by,
        "recorded_by_username": getattr(recorder, "username", None),
        "on_behalf": recorded_by is not None and recorded_by != p.from_user_id,
    })
    return line


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
        # A debtor who can't log in any more can't record their own payment;
        # the treasurer records it for them (router_expenses.mark_settlement).
        "from_inactive": not getattr(debtor, "is_active", True),
        "amount": cents / 100,
        "paid": paid,
        "payment_id": payment_id,
    }


def greedy_lines(balances: Dict[int, int]) -> List[List[int]]:
    """Greedy minimal-transaction settlement over what's still owed, as
    [from_user_id, to_user_id, cents]. `balances` maps user_id -> net cents
    (fronted + sent - share - received); positive = creditor, negative = debtor."""
    creditors = [[uid, bal] for uid, bal in sorted(balances.items(), key=lambda x: (-x[1], x[0])) if bal > 0]
    debtors = [[uid, -bal] for uid, bal in sorted(balances.items(), key=lambda x: (x[1], x[0])) if bal < 0]
    lines: List[List[int]] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        pay = min(debtors[i][1], creditors[j][1])
        lines.append([debtors[i][0], creditors[j][0], pay])
        debtors[i][1] -= pay
        creditors[j][1] -= pay
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return lines


def impute_transfers(
    frozen_lines: List[List[int]],
    transfers: List[Tuple[int, int, int]],
    paid_before: Iterable[int] = (),
) -> List[List[int]]:
    """Replay the transfers made since the plan was frozen onto its lines, so a
    payment only moves the lines of the people it concerns (treso2.0.md § 2.3
    bis; prototype md/2.features/treso2.0_plan_fige_prototype.py):

    1. a transfer A -> B first pays down the plan line A -> B;
    2. what's left shrinks A's other lines (largest first): their creditors are
       now short; if A owed nothing more, it's owed back to A;
    3. B received money that isn't B's: B's debtors who haven't paid anything
       yet are redirected (largest line first); what they can't absorb, B
       passes on or gives back;
    4. only that residual goes through the greedy, merged into existing pairs,
       and a pair left in both directions is netted.

    The balances never depend on this: it only changes *who pays whom*.
    `paid_before`: members who had already paid something (never redirected)."""
    lines = [list(l) for l in frozen_lines]
    payers = set(paid_before) | {a for a, _, _ in transfers}
    residual: Dict[int, int] = defaultdict(int)
    for a, b, x in transfers:
        for ln in lines:
            if ln[0] == a and ln[1] == b and ln[2] > 0 and x > 0:
                used = min(ln[2], x)
                ln[2] -= used
                x -= used
        if x == 0:
            continue
        left = x
        for ln in sorted((l for l in lines if l[0] == a and l[2] > 0), key=lambda l: -l[2]):
            used = min(ln[2], left)
            ln[2] -= used
            residual[ln[1]] += used
            left -= used
        residual[a] += left
        left = x
        for ln in sorted((l for l in lines if l[1] == b and l[2] > 0 and l[0] not in payers), key=lambda l: -l[2]):
            used = min(ln[2], left)
            ln[2] -= used
            residual[ln[0]] -= used
            left -= used
        residual[b] -= left
    for f, t, x in greedy_lines({u: v for u, v in residual.items() if v}):
        for ln in lines:
            if ln[0] == f and ln[1] == t:
                ln[2] += x
                break
        else:
            lines.append([f, t, x])
    net: Dict[Tuple[int, int], int] = {}
    for f, t, x in lines:
        if x <= 0:
            continue
        if (t, f) in net:
            back = net[(t, f)]
            if back >= x:
                net[(t, f)] = back - x
            else:
                del net[(t, f)]
                net[(f, t)] = x - back
        else:
            net[(f, t)] = net.get((f, t), 0) + x
    return [[f, t, x] for (f, t), x in net.items() if x > 0]


def plan_fingerprint(base_balances: Dict[int, int]) -> str:
    """What a frozen plan was computed on: everyone's fronted - share, before
    any transfer. A changed expense, stay or split makes a frozen plan stale."""
    return json.dumps(sorted([uid, bal] for uid, bal in base_balances.items() if bal), separators=(",", ":"))


def _load(value):
    return json.loads(value) if isinstance(value, str) else value


def _transfer_date(p) -> Optional[date]:
    return getattr(p, "transferred_on", None)


def _frozen_applies(frozen, fingerprint: str, recorded: List[Any]) -> bool:
    """A frozen plan is used only while it still describes this split: same
    base, none of the transfers it counted has been deleted, and no transfer
    entered since is dated before it was frozen (that one was made against an
    older plan — a catch-up — and calls for a recompute)."""
    if frozen is None or frozen.fingerprint != fingerprint:
        return False
    baked = set(_load(frozen.baked_transfer_ids))
    if not baked <= {getattr(p, "id", None) for p in recorded}:
        return False
    return not any(
        getattr(p, "id", None) not in baked and _transfer_date(p) is not None and _transfer_date(p) < frozen.frozen_on
        for p in recorded
    )


def _labels(
    lines: List[List[int]], frozen_lines: List[List[int]], unbaked: List[Tuple[int, int, int]]
) -> Dict[Tuple[int, int], str]:
    """Why a line differs from the frozen plan, for the UI: a debtor sent
    elsewhere ("redirected"), someone holding money that isn't theirs
    ("pass_on"), or an overpayment to give back ("give_back")."""
    frozen = {(f, t): c for f, t, c in frozen_lines}
    payees = {b for _, b, _ in unbaked}
    returns = {(b, a) for a, b, _ in unbaked}
    labels: Dict[Tuple[int, int], str] = {}
    for f, t, c in lines:
        if (f, t) in frozen and c <= frozen[(f, t)]:
            continue
        labels[(f, t)] = "give_back" if (f, t) in returns else "pass_on" if f in payees else "redirected"
    return labels


def _base(event: LanEvent, rsvps: List[EventRSVP], expenses: List) -> Dict[str, Any]:
    """The split itself — shares by person-nights and who fronted what — before
    any transfer."""
    total_cents = sum(_cents(e.amount) for e in expenses)

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
            # A deleted member can only be taken out of the split, not given
            # new dates (router_events.adjust_rsvp).
            "deleted": getattr(users[uid], "deleted_at", None) is not None,
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

    base_balances: Dict[int, int] = {
        uid: paid_by_user.get(uid, 0) - share_cents.get(uid, 0)
        for uid in set(share_cents) | set(paid_by_user)
    }
    return {
        "users": users,
        "shares": shares,
        "base_balances": base_balances,
        "total_cents": total_cents,
        "total_person_nights": total_person_nights,
    }


def settlement_state(
    event: LanEvent,
    rsvps: List[EventRSVP],
    expenses: List,
    payments: Optional[Iterable] = None,
    frozen=None,
) -> Dict[str, Any]:
    """Everything the settlement is computed from, shared by the read (GET
    /prorata) and the writes (router_expenses), so both see the same plan.
    `frozen`: the event's models.SettlementPlan, if any. `lines` is the plan
    shown — the frozen one with the transfers since imputed on it while it
    still applies, else the greedy over what's still owed."""
    base = _base(event, rsvps, expenses)
    users = base["users"]
    balances = dict(base["base_balances"])
    recorded, legacy = _normalize_payments(payments)
    for p in recorded:
        cents = _transfer_cents(p)
        balances[p.from_user_id] = balances.get(p.from_user_id, 0) + cents
        balances[p.to_user_id] = balances.get(p.to_user_id, 0) - cents
        for uid, attr in ((p.from_user_id, "from_user"), (p.to_user_id, "to_user")):
            if uid not in users and getattr(p, attr, None) is not None:
                users[uid] = getattr(p, attr)

    fingerprint = plan_fingerprint(base["base_balances"])
    applies = _frozen_applies(frozen, fingerprint, recorded)
    labels: Dict[Tuple[int, int], str] = {}
    if applies:
        frozen_lines = _load(frozen.lines)
        baked = set(_load(frozen.baked_transfer_ids))
        unbaked = [
            (p.from_user_id, p.to_user_id, _transfer_cents(p)) for p in recorded if getattr(p, "id", None) not in baked
        ]
        paid_before = {p.from_user_id for p in recorded if getattr(p, "id", None) in baked}
        lines = impute_transfers(frozen_lines, unbaked, paid_before)
        labels = _labels(lines, frozen_lines, unbaked)
    else:
        lines = greedy_lines(balances)
    return {
        **base,
        "balances": balances,
        "recorded": recorded,
        "legacy": legacy,
        "fingerprint": fingerprint,
        "frozen_applies": applies,
        "frozen_on": frozen.frozen_on if applies else None,
        "lines": lines,
        "labels": labels,
    }


def _build_settlement(state: Dict[str, Any], viewer_id: Optional[int]) -> List[dict]:
    """The plan's lines still to pay, then one line per recorded transfer. A
    legacy "paid" marker on a pair flags the matching line, as it always did."""
    users = state["users"]
    legacy_pairs = {(f, t): pid for f, t, pid in state["legacy"]}
    out: List[dict] = []
    for f, t, cents in state["lines"]:
        legacy_id = legacy_pairs.get((f, t), "absent")
        paid = legacy_id != "absent"
        line = _line(users, f, t, cents, viewer_id, paid, legacy_id if paid else None)
        line["label"] = state["labels"].get((f, t))
        out.append(line)
    return out + [_history_line(users, p, viewer_id) for p in state["recorded"]]


def calculate_prorata(
    event: LanEvent,
    rsvps: List[EventRSVP],
    expenses: List,
    payments: Optional[Iterable] = None,
    viewer_id: Optional[int] = None,
    frozen=None,
) -> Dict[str, Any]:
    """Split an event's expenses by person-nights and work out who still owes
    whom. `payments` are the transfers (and pre-1.3.4 "paid" flags): they
    count in the balances, so a receipt added or a date changed afterwards
    shows what's *still* owed instead of re-labelling the old line as paid.
    `frozen`: the event's frozen plan (models.SettlementPlan), if any."""
    state = settlement_state(event, rsvps, expenses, payments, frozen)
    return {
        "total_expenses": state["total_cents"] / 100,
        "event_id": event.id,
        "event_title": event.title,
        "event_start": event.start_date.isoformat(),
        "event_end": event.end_date.isoformat(),
        "total_nights": (event.end_date - event.start_date).days,
        "total_person_nights": state["total_person_nights"],
        "shares": state["shares"],
        "settlements": _build_settlement(state, viewer_id),
        # The plan shown is frozen (lines only move for the people a transfer
        # concerns) or freshly computed — the UI says which.
        "plan": {
            "frozen": state["frozen_applies"],
            "frozen_on": state["frozen_on"].isoformat() if state["frozen_on"] else None,
        },
    }
