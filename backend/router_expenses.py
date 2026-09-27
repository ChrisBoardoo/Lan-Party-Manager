from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User, Expense, LanEvent, EventRSVP, SettlementPayment
from schemas import ExpenseCreate, ExpenseOut
from auth import require_treasurer
from prorata import calculate_prorata
from event_utils import current_event, event_prorata_inputs
from router_settings import require_feature

router = APIRouter()

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
        event = current_event(db)

    if not event:
        return _EMPTY_PRORATA

    rsvps, expenses, paid_pairs = event_prorata_inputs(db, event)
    return calculate_prorata(event, rsvps, expenses, paid_pairs, current_user.id)


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
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = db.query(Expense)
    if event_id is not None:
        query = query.filter(Expense.event_id == event_id)
    return query.order_by(Expense.date.desc()).offset(offset).limit(limit).all()


def _validate_payer(db: Session, paid_by):
    if paid_by is not None and not db.query(User).filter(User.id == paid_by).first():
        raise HTTPException(400, "paid_by user not found")


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
    expense = Expense(**payload, created_by=current_user.id)
    db.add(expense)
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
    _validate_payer(db, payload["paid_by"])
    for field, value in payload.items():
        setattr(expense, field, value)
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/{expense_id}")
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_treasurer),
):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(404, "Expense not found")
    db.delete(expense)
    db.commit()
    return {"ok": True}


# ── Settlement "payment sent" markers (self-service, any member) ────────────────
# A debtor marks/reverses only their OWN debt line (from_user_id == themselves).

@router.post("/settlements/mark")
def mark_settlement(
    data: SettlementMark,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("treasury")),
):
    if data.to_user_id == current_user.id:
        raise HTTPException(400, "You cannot owe yourself")
    existing = (
        db.query(SettlementPayment)
        .filter(
            SettlementPayment.event_id == data.event_id,
            SettlementPayment.from_user_id == current_user.id,
            SettlementPayment.to_user_id == data.to_user_id,
        )
        .first()
    )
    if not existing:
        db.add(SettlementPayment(
            event_id=data.event_id,
            from_user_id=current_user.id,
            to_user_id=data.to_user_id,
        ))
        db.commit()
    return {"ok": True, "paid": True}


@router.delete("/settlements/mark")
def unmark_settlement(
    data: SettlementMark,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature("treasury")),
):
    db.query(SettlementPayment).filter(
        SettlementPayment.event_id == data.event_id,
        SettlementPayment.from_user_id == current_user.id,
        SettlementPayment.to_user_id == data.to_user_id,
    ).delete()
    db.commit()
    return {"ok": True, "paid": False}
