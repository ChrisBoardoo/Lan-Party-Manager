import json
import math
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from models import User, Expense, LanEvent, SettlementPayment, SettlementPlan, Transfer
from schemas import ExpenseCreate, ExpenseOut
from activity import add_activity, add_audit
from auth import require_treasurer as _require_treasurer_role
from prorata import calculate_prorata, settlement_state
from event_utils import event_prorata_inputs, local_today, treasury_default_event
from router_settings import DEFAULT_CURRENCY, get_setting, require_feature

router = APIRouter()


def require_treasurer(
    user: User = Depends(_require_treasurer_role),
    _feature: User = Depends(require_feature("treasury")),
) -> User:
    """Treasurer or admin, and the treasury feature on (admins pass anyway):
    writes used to go through with the feature off while reads 404'd."""
    return user

_EMPTY_PRORATA = {
    "total_expenses": 0.0,
    "event_id": None,
    "event_title": None,
    "event_start": None,
    "event_end": None,
    "total_nights": 0,
    "total_person_nights": 0,
    "shares": [],
    "settlements": [],
}


class SettlementMark(BaseModel):
    event_id: int
    to_user_id: int
    # Only for a treasurer recording the payment of a member who can't log in
    # any more (deactivated or deleted); omitted, it's the caller's own line.
    from_user_id: Optional[int] = None


@router.get("/prorata")
def get_prorata(
    event_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("treasury")),
):
    if event_id is not None:
        event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
        if not event:
            raise HTTPException(404, "Event not found")
    else:
        event = treasury_default_event(db)

    if not event:
        return _EMPTY_PRORATA

    rsvps, expenses, payments = event_prorata_inputs(db, event)
    return calculate_prorata(event, rsvps, expenses, payments, current_user.id, frozen=_plan_row(db, event.id))


@router.get("/unassigned-count")
def unassigned_count(
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("treasury")),
):
    """How many expenses aren't tied to an event, and so count towards no split.

    Splits are scoped by event_id, so an untagged expense is invisible in the
    maths. That has to be visible in the UI rather than silently dropped — the
    Treasury page turns this into a banner linking to the edit form.
    """
    return {"count": db.query(Expense).filter(Expense.event_id.is_(None)).count()}


@router.get("/", response_model=list[ExpenseOut])
def get_expenses(
    event_id: int = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("treasury")),
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    query = db.query(Expense)
    if event_id is not None:
        query = query.filter(Expense.event_id == event_id)
    return query.order_by(Expense.date.desc()).offset(offset).limit(limit).all()


def _validate_payer(db: Session, paid_by, current=None):
    """`current` is the expense's payer before an edit: a deleted member can
    stay the payer of what they fronted, but not be picked for a new one."""
    if paid_by is None:
        return
    payer = db.query(User).filter(User.id == paid_by).first()
    if not payer or (payer.deleted_at is not None and paid_by != current):
        raise HTTPException(400, "paid_by user not found")


def _validate_event(db: Session, event_id):
    if event_id is not None and not db.query(LanEvent).filter(LanEvent.id == event_id).first():
        raise HTTPException(400, "event not found")


def _describe(db: Session, expense: Expense) -> str:
    """One line for the audit log: what, how much, who paid, which event."""
    payer = db.query(User.username).filter(User.id == expense.paid_by).scalar() or "?"
    event = (
        db.query(LanEvent.title).filter(LanEvent.id == expense.event_id).scalar()
        if expense.event_id is not None else None
    ) or "no event"
    return f"{expense.description} — {expense.amount:.2f} € paid by {payer} ({event})"


@router.post("/", response_model=ExpenseOut, status_code=201)
def create_expense(
    data: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_treasurer),
):
    payload = data.model_dump()
    # Default the payer to whoever is entering the expense.
    payload["paid_by"] = payload.get("paid_by") or current_user.id
    _validate_payer(db, payload["paid_by"])
    _validate_event(db, payload["event_id"])
    expense = Expense(**payload, created_by=current_user.id)
    db.add(expense)
    db.flush()
    # Every expense moves what everyone owes: keep a trace of who wrote what.
    add_audit(db, current_user.id, "expense_created", _describe(db, expense))
    db.commit()
    db.refresh(expense)
    return expense


@router.put("/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int,
    data: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_treasurer),
):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(404, "Expense not found")
    payload = data.model_dump()
    payload["paid_by"] = payload.get("paid_by") or expense.paid_by or current_user.id
    _validate_payer(db, payload["paid_by"], current=expense.paid_by or expense.created_by)
    _validate_event(db, payload["event_id"])
    before = _describe(db, expense)
    for field, value in payload.items():
        setattr(expense, field, value)
    db.flush()
    add_audit(db, current_user.id, "expense_updated", f"{before} → {_describe(db, expense)}")
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/{expense_id}")
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_treasurer),
):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(404, "Expense not found")
    add_audit(db, current_user.id, "expense_deleted", _describe(db, expense))
    db.delete(expense)
    db.commit()
    return {"ok": True}


# ── Frozen plan, shared by every write (treso2.0.md § 2.3 bis) ───────────────────
# The "who owes whom" plan is frozen at the first transfer: a payment then only
# moves the lines of the people it concerns. It's recomputed (greedy) when the
# split changes (detected by its fingerprint), when a transfer it counted is
# deleted, when a transfer dated before it is entered (a catch-up: made against
# an older plan), or on the treasurer's "recalculate". Every write takes the
# SQLite write lock first, so two writes never freeze two plans.

def _lock(db: Session) -> None:
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _plan_row(db: Session, event_id: int) -> Optional[SettlementPlan]:
    return db.query(SettlementPlan).filter(SettlementPlan.event_id == event_id).first()


def _state(db: Session, event: LanEvent) -> dict:
    rsvps, expenses, payments = event_prorata_inputs(db, event)
    return settlement_state(event, rsvps, expenses, payments, _plan_row(db, event.id))


def _freeze(db: Session, event: LanEvent, state: dict, today: date) -> None:
    """Store the plan `state` shows as the event's frozen plan, from today."""
    row = _plan_row(db, event.id) or SettlementPlan(event_id=event.id)
    row.lines = json.dumps(state["lines"])
    row.baked_transfer_ids = json.dumps(sorted(p.id for p in state["recorded"] if isinstance(p, Transfer)))
    row.fingerprint = state["fingerprint"]
    row.frozen_on = today
    db.add(row)
    db.flush()


def _money(db: Session, cents: int) -> str:
    return f"{cents / 100:.2f} {get_setting(db, 'currency') or DEFAULT_CURRENCY}"


def _username(state: dict, uid: int) -> str:
    return getattr(state["users"].get(uid), "username", "?")


def _owes(state: dict) -> Dict[int, Dict[int, int]]:
    out: Dict[int, Dict[int, int]] = {}
    for f, t, cents in state["lines"]:
        out.setdefault(f, {})[t] = out.get(f, {}).get(t, 0) + cents
    return out


def _notify_plan_changes(db: Session, event: LanEvent, before: dict, after: dict, actor: User, skip: set) -> None:
    """Tell each member whose own payments changed what they now owe. `skip`:
    members the change is already explained to (the payer of the transfer)."""
    was, now = _owes(before), _owes(after)
    for uid in sorted(set(was) | set(now)):
        if uid == actor.id or uid in skip or was.get(uid, {}) == now.get(uid, {}):
            continue
        member = after["users"].get(uid) or before["users"].get(uid)
        if member is None or getattr(member, "deleted_at", None) is not None:
            continue
        owed = now.get(uid, {})
        what = ", ".join(f"{_money(db, c)} to {_username(after, t)}" for t, c in sorted(owed.items())) or "nothing more"
        add_activity(
            db, user_id=actor.id, action="settlement_plan_changed",
            description=f"updated the settlement plan for {event.title}: you now owe {what}",
            entity_type="event", entity_id=event.id, recipient_user_id=uid,
        )


def _record(db: Session, event: LanEvent, items: List[dict], actor: User, before: dict):
    """Write `items` (from_user_id, to_user_id, cents, transferred_on, note) as
    transfers. The caller holds the write lock and computed `before` under it.
    Returns (rows, after, recalculated)."""
    today = local_today(db)
    catch_up = any(it["transferred_on"] < (before["frozen_on"] or today) for it in items)
    if not catch_up and not before["frozen_applies"]:
        # First payment on this plan (or the split changed since): freeze the
        # plan as it was shown, then the payment is imputed on it.
        _freeze(db, event, before, today)
    rows = [
        Transfer(
            event_id=event.id,
            from_user_id=it["from_user_id"],
            to_user_id=it["to_user_id"],
            amount_cents=it["cents"],
            transferred_on=it["transferred_on"],
            note=it.get("note"),
            recorded_by=actor.id,
        )
        for it in items
    ]
    db.add_all(rows)
    db.flush()
    after = _state(db, event)
    if catch_up:
        # Made against an older plan: start again from what is actually owed.
        _freeze(db, event, after, today)
        after = _state(db, event)
    return rows, after, catch_up


def _delete_transfer(db: Session, event: LanEvent, transfer: Transfer, actor: User):
    """Delete one transfer (write lock held). Returns (before, after, recalculated):
    removing a transfer the frozen plan already counted recomputes it."""
    before = _state(db, event)
    plan = _plan_row(db, event.id)
    baked = plan is not None and transfer.id in json.loads(plan.baked_transfer_ids)
    db.delete(transfer)
    db.flush()
    after = _state(db, event)
    if baked:
        _freeze(db, event, after, local_today(db))
        after = _state(db, event)
    return before, after, baked


def _audit_recalculated(db: Session, actor: User, event: LanEvent, reason: str) -> None:
    add_audit(db, actor.id, "settlement_plan_recalculated", f"{event.title}: {reason}")


def _event_or_404(db: Session, event_id: int) -> LanEvent:
    event = db.query(LanEvent).filter(LanEvent.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


# ── Settlement "payment sent" (self-service, any member) ────────────────────────
# A debtor marks/reverses only their OWN debt line (from_user_id == themselves),
# except that a treasurer records it for a debtor who can't log in any more
# (deactivated or deleted, still in a started LAN's split): nobody else could.
# Marking records a transfer of the line's amount as it stands right now, dated
# today; the split then counts it, so anything that changes later (a late
# receipt, new dates) shows up as what is still owed instead of silently
# relabelling the old line.

def _settlement_debtor(db: Session, data: SettlementMark, current_user: User) -> User:
    if data.from_user_id is None or data.from_user_id == current_user.id:
        return current_user
    if current_user.role not in ("treasurer", "admin"):
        raise HTTPException(403, "Treasurer or admin role required")
    debtor = db.query(User).filter(User.id == data.from_user_id).first()
    if not debtor:
        raise HTTPException(404, "User not found")
    if debtor.is_active:
        raise HTTPException(400, "This member records their own payments")
    return debtor


def _audit_on_behalf(db: Session, current_user: User, debtor: User, data: SettlementMark, what: str):
    if debtor.id == current_user.id:
        return
    creditor = db.query(User.username).filter(User.id == data.to_user_id).scalar() or "?"
    event = db.query(LanEvent.title).filter(LanEvent.id == data.event_id).scalar() or "?"
    add_audit(db, current_user.id, "settlement_recorded",
              f"{what}: {debtor.username} → {creditor} ({event})")


@router.post("/settlements/mark")
def mark_settlement(
    data: SettlementMark,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("treasury")),
):
    debtor = _settlement_debtor(db, data, current_user)
    if data.to_user_id == debtor.id:
        raise HTTPException(400, "You cannot owe yourself")
    event = _event_or_404(db, data.event_id)
    # Take the write lock before reading what is owed: two clicks at once
    # otherwise both see the line unpaid and record it twice. Serialized, the
    # second computes the split after the first committed and finds the line
    # paid (400). SQLite only; another engine keeps its default isolation.
    _lock(db)
    before = _state(db, event)
    flagged = {(f, t) for f, t, _ in before["legacy"]}
    cents = next(
        (c for f, t, c in before["lines"] if f == debtor.id and t == data.to_user_id and (f, t) not in flagged),
        None,
    )
    if cents is None:
        raise HTTPException(400, "Nothing is owed on this line")
    _, after, _ = _record(db, event, [{
        "from_user_id": debtor.id, "to_user_id": data.to_user_id, "cents": cents,
        "transferred_on": local_today(db),
    }], current_user, before)
    _audit_on_behalf(db, current_user, debtor, data, f"payment of {cents / 100:.2f} € recorded")
    _notify_plan_changes(db, event, before, after, current_user, skip={debtor.id})
    db.commit()
    return {"ok": True, "paid": True, "amount": cents / 100}


@router.delete("/settlements/mark")
def unmark_settlement(
    data: SettlementMark,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("treasury")),
):
    """Reverses the debtor's latest "payment sent" on this pair (kept for the
    1.4.1 frontend; the 1.4.2 one deletes a transfer by id)."""
    debtor = _settlement_debtor(db, data, current_user)
    event = _event_or_404(db, data.event_id)
    _lock(db)
    query = db.query(Transfer).filter(
        Transfer.event_id == data.event_id,
        Transfer.from_user_id == debtor.id,
        Transfer.to_user_id == data.to_user_id,
    )
    if debtor.id == current_user.id:
        query = query.filter(Transfer.recorded_by == debtor.id)
    latest = query.order_by(Transfer.id.desc()).first()
    removed = 0
    if latest is not None:
        before, after, recalculated = _delete_transfer(db, event, latest, current_user)
        if recalculated:
            _audit_recalculated(db, current_user, event, "a counted payment was reversed")
            _notify_plan_changes(db, event, before, after, current_user, skip={debtor.id})
        removed = 1
    # A pre-1.3.4 "paid" flag on the pair is reversed the same way.
    removed += db.query(SettlementPayment).filter(
        SettlementPayment.event_id == data.event_id,
        SettlementPayment.from_user_id == debtor.id,
        SettlementPayment.to_user_id == data.to_user_id,
    ).delete()
    if removed:
        _audit_on_behalf(db, current_user, debtor, data, "recorded payment reversed")
    db.commit()
    return {"ok": True, "paid": False}


# ── Transfers entered by the treasurer / an admin (Trésorerie 2.0) ───────────────
# Any amount (a partial reimbursement), any two members, the real date (a
# catch-up of what was paid outside the app). Audited, and both members are
# told; anyone whose own payments change because of it is told too.

MAX_TRANSFER = 100_000


class TransferIn(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: float = Field(..., gt=0, le=MAX_TRANSFER)
    transferred_on: date
    note: Optional[str] = Field(None, max_length=200)

    @field_validator("amount")
    @classmethod
    def _to_the_cent(cls, value: float) -> float:
        if not math.isfinite(value) or abs(value * 100 - round(value * 100)) > 1e-6:
            raise ValueError("amount must have at most two decimals")
        return value

    @field_validator("note")
    @classmethod
    def _blank_note(cls, value: Optional[str]) -> Optional[str]:
        return (value or "").strip() or None

    @model_validator(mode="after")
    def _two_members(self):
        # No negative amount: a transfer the other way round is the other way round.
        if self.from_user_id == self.to_user_id:
            raise ValueError("a transfer needs two different members")
        return self


class TransferBatch(BaseModel):
    event_id: int
    transfers: List[TransferIn] = Field(..., min_length=1, max_length=20)
    # The treasurer saw the warning about a member outside this event's split.
    confirm_outside_split: bool = False


class PlanRecalculate(BaseModel):
    event_id: int


def _transfer_out(t: Transfer) -> dict:
    return {
        "id": t.id,
        "event_id": t.event_id,
        "from_user_id": t.from_user_id,
        "to_user_id": t.to_user_id,
        "amount": t.amount_cents / 100,
        "transferred_on": t.transferred_on.isoformat(),
        "note": t.note,
        "recorded_by": t.recorded_by,
    }


@router.post("/transfers", status_code=201)
def record_transfers(
    data: TransferBatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_treasurer),
):
    """Several transfers at once (a catch-up after the LAN is usually a few):
    one plan recompute and one notification per member for the whole batch."""
    event = _event_or_404(db, data.event_id)
    today = local_today(db)
    ids = {t.from_user_id for t in data.transfers} | {t.to_user_id for t in data.transfers}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    if ids - set(users):
        raise HTTPException(400, "User not found")
    if any(t.transferred_on > today for t in data.transfers):
        raise HTTPException(400, "A transfer can't be dated in the future")

    _lock(db)
    before = _state(db, event)
    in_split = {s["user_id"] for s in before["shares"]} | set(before["base_balances"])
    outside = sorted(users[u].username for u in ids - in_split)
    if outside and not data.confirm_outside_split:
        raise HTTPException(400, f"Not in this event's split: {', '.join(outside)}")
    # A double submit replays the same batch: refuse a transfer identical to one
    # entered seconds ago (same pair, amount and date).
    recent = datetime.utcnow() - timedelta(seconds=10)
    for t in data.transfers:
        if db.query(Transfer.id).filter(
            Transfer.event_id == event.id, Transfer.from_user_id == t.from_user_id,
            Transfer.to_user_id == t.to_user_id, Transfer.amount_cents == int(round(t.amount * 100)),
            Transfer.transferred_on == t.transferred_on, Transfer.created_at >= recent,
        ).first():
            raise HTTPException(409, "This transfer was just recorded")

    items = [
        {
            "from_user_id": t.from_user_id, "to_user_id": t.to_user_id, "cents": int(round(t.amount * 100)),
            "transferred_on": t.transferred_on, "note": t.note,
        }
        for t in data.transfers
    ]
    rows, after, recalculated = _record(db, event, items, current_user, before)
    for row in rows:
        payer, payee = users[row.from_user_id], users[row.to_user_id]
        money = _money(db, row.amount_cents)
        note = f", note: {row.note}" if row.note else ""
        add_audit(db, current_user.id, "transfer_recorded",
                  f"{money} {payer.username} → {payee.username} ({event.title}), dated {row.transferred_on}{note}")
        for member in (payer, payee):
            if member.id != current_user.id and member.deleted_at is None:
                add_activity(
                    db, user_id=current_user.id, action="transfer_recorded",
                    description=f"recorded a transfer of {money} from {payer.username} to {payee.username} ({event.title})",
                    entity_type="event", entity_id=event.id, recipient_user_id=member.id,
                )
    if recalculated:
        _audit_recalculated(db, current_user, event, "a transfer dated before the plan was entered")
    _notify_plan_changes(db, event, before, after, current_user, skip={r.from_user_id for r in rows})
    db.commit()
    return {"transfers": [_transfer_out(r) for r in rows], "plan_recalculated": recalculated}


@router.delete("/transfers/{transfer_id}")
def delete_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("treasury")),
):
    """The treasurer or an admin deletes any transfer (a typo is corrected by
    deleting and entering it again); a member only the ones they entered for
    themselves ("payment sent")."""
    transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(404, "Transfer not found")
    is_treasurer = current_user.role in ("treasurer", "admin")
    own = transfer.recorded_by == current_user.id and transfer.from_user_id == current_user.id
    if not (is_treasurer or own):
        raise HTTPException(403, "You can only delete the payments you recorded yourself")
    event = _event_or_404(db, transfer.event_id)
    _lock(db)
    payer = db.query(User).filter(User.id == transfer.from_user_id).first()
    payee = db.query(User).filter(User.id == transfer.to_user_id).first()
    money = _money(db, transfer.amount_cents)
    summary = (f"{money} {getattr(payer, 'username', '?')} → {getattr(payee, 'username', '?')} "
               f"({event.title}), dated {transfer.transferred_on}")
    before, after, recalculated = _delete_transfer(db, event, transfer, current_user)
    add_audit(db, current_user.id, "transfer_deleted", summary)
    for member in (payer, payee):
        if member is not None and member.id != current_user.id and member.deleted_at is None:
            add_activity(
                db, user_id=current_user.id, action="transfer_deleted",
                description=f"deleted the transfer of {summary}",
                entity_type="event", entity_id=event.id, recipient_user_id=member.id,
            )
    if recalculated:
        _audit_recalculated(db, current_user, event, "a counted transfer was deleted")
    _notify_plan_changes(db, event, before, after, current_user, skip={getattr(payer, "id", None)})
    db.commit()
    return {"ok": True, "plan_recalculated": recalculated}


@router.post("/transfers/recalculate")
def recalculate_plan(
    data: PlanRecalculate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_treasurer),
):
    """Start the plan again from what everyone still owes (greedy) — when the
    frozen one has drifted too far from what people actually did."""
    event = _event_or_404(db, data.event_id)
    _lock(db)
    before = _state(db, event)
    rsvps, expenses, payments = event_prorata_inputs(db, event)
    fresh = settlement_state(event, rsvps, expenses, payments, frozen=None)
    _freeze(db, event, fresh, local_today(db))
    after = _state(db, event)
    _audit_recalculated(db, current_user, event, "recalculated by hand")
    _notify_plan_changes(db, event, before, after, current_user, skip=set())
    db.commit()
    return {"ok": True}
