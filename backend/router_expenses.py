from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import User, Expense, LanEvent, SettlementPayment
from schemas import ExpenseCreate, ExpenseOut
from activity import add_audit
from auth import require_treasurer as _require_treasurer_role
from prorata import calculate_prorata
from event_utils import event_prorata_inputs, treasury_default_event
from router_settings import require_feature

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
    return calculate_prorata(event, rsvps, expenses, payments, current_user.id)


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


# ── Settlement "payment sent" (self-service, any member) ────────────────────────
# A debtor marks/reverses only their OWN debt line (from_user_id == themselves),
# except that a treasurer records it for a debtor who can't log in any more
# (deactivated or deleted, still in a started LAN's split): nobody else could.
# Marking records the amount of the line as it stands right now; the split then
# counts it, so anything that changes later (a late receipt, new dates) shows
# up as what is still owed instead of silently relabelling the old line.

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
    event = db.query(LanEvent).filter(LanEvent.id == data.event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    # Take the write lock before reading what is owed: two clicks at once
    # otherwise both see the line unpaid, and the second one either breaks on
    # the unique pair (500) or adds the amount a second time. Serialized, the
    # second computes the split after the first committed and finds the line
    # paid (400). SQLite only; another engine keeps its default isolation.
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    rsvps, expenses, payments = event_prorata_inputs(db, event)
    result = calculate_prorata(event, rsvps, expenses, payments, current_user.id)
    line = next(
        (
            l for l in result["settlements"]
            if not l["paid"] and l["from_user_id"] == debtor.id and l["to_user_id"] == data.to_user_id
        ),
        None,
    )
    if line is None:
        raise HTTPException(400, "Nothing is owed on this line")

    existing = (
        db.query(SettlementPayment)
        .filter(
            SettlementPayment.event_id == data.event_id,
            SettlementPayment.from_user_id == debtor.id,
            SettlementPayment.to_user_id == data.to_user_id,
        )
        .first()
    )
    # One row per pair (unique constraint): a second transfer to the same
    # person adds up into it.
    if existing:
        existing.amount = round((existing.amount or 0) + line["amount"], 2)
    else:
        db.add(SettlementPayment(
            event_id=data.event_id,
            from_user_id=debtor.id,
            to_user_id=data.to_user_id,
            amount=line["amount"],
        ))
    _audit_on_behalf(db, current_user, debtor, data, f"payment of {line['amount']:.2f} € recorded")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This payment was just recorded")
    return {"ok": True, "paid": True, "amount": line["amount"]}


@router.delete("/settlements/mark")
def unmark_settlement(
    data: SettlementMark,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("treasury")),
):
    debtor = _settlement_debtor(db, data, current_user)
    removed = db.query(SettlementPayment).filter(
        SettlementPayment.event_id == data.event_id,
        SettlementPayment.from_user_id == debtor.id,
        SettlementPayment.to_user_id == data.to_user_id,
    ).delete()
    if removed:
        _audit_on_behalf(db, current_user, debtor, data, "recorded payment reversed")
    db.commit()
    return {"ok": True, "paid": False}
