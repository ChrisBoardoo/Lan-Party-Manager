"""Cards & boosters endpoints — /api/cards. The rules live in cards.py and
cards_rules.py; this only maps them to HTTP. Gated by the `cards` feature
(admins pass, as everywhere, but get no grants while it's off)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import cards
from cards_rules import BOOSTER_PRICE_XP, PURCHASES_PER_WEEK
from database import get_db
from models import User
from router_settings import is_feature_enabled, require_feature
from schemas import BoosterOpenOut, CardsMeOut, CollectionOut

router = APIRouter()


def _grant_and_commit(db: Session, user: User) -> None:
    """ensure_grants, committed. Two tabs opening LPM at once can race on the
    unique constraints: the loser rolls back and runs again, which then finds
    the winner's grants and adds nothing."""
    for attempt in range(2):
        try:
            cards.ensure_grants(db, user)
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            if attempt:
                raise


def _me(db: Session, user: User) -> CardsMeOut:
    unopened = cards.unopened_boosters(db, user)
    balance = cards.xp_balance(db, user)
    left, next_at = cards.purchase_allowance(db, user) if balance is not None else (None, None)
    return CardsMeOut(
        boosters=[cards.booster_out(b) for b in unopened],
        xp_balance=balance,
        booster_price=BOOSTER_PRICE_XP,
        purchases_per_week=PURCHASES_PER_WEEK,
        purchases_left=left,
        next_purchase_at=next_at,
    )


@router.get("/me", response_model=CardsMeOut)
def my_cards(db: Session = Depends(get_db), user: User = Depends(require_feature("cards"))):
    """My unopened boosters, after granting whatever I've earned since my last
    visit. The Hub polls this for its "boosters to open" banner."""
    _grant_and_commit(db, user)
    return _me(db, user)


@router.post("/boosters/buy", response_model=CardsMeOut)
def buy(db: Session = Depends(get_db), user: User = Depends(require_feature("cards"))):
    """Buy a booster with spendable XP. Doesn't open it."""
    if not is_feature_enabled(db, "cards"):
        raise HTTPException(400, "Cards are not enabled")
    cards.buy_booster(db, user)
    db.commit()
    return _me(db, user)


@router.post("/boosters/{booster_id}/open", response_model=BoosterOpenOut)
def open_booster(booster_id: int, db: Session = Depends(get_db), user: User = Depends(require_feature("cards"))):
    """Reveal a booster's cards, in slot order (an Epic is always last).
    Calling it again returns the same cards."""
    booster = cards.open_booster(db, user, booster_id)
    db.commit()
    view = cards.CardView(db)
    return BoosterOpenOut(
        booster=cards.booster_out(booster),
        cards=[view.card(c) for c in sorted(booster.cards, key=lambda c: c.slot)],
        new_member_ids=cards.new_member_ids(db, booster),
    )


@router.get("/collection/{user_id}", response_model=CollectionOut)
def get_collection(user_id: int, db: Session = Depends(get_db), viewer: User = Depends(require_feature("cards"))):
    """A member's collection — readable by the whole crew: the showcase is what
    gets people talking between two LANs. Only cards that have been revealed."""
    owner = db.query(User).filter(User.id == user_id).first()
    if owner is None or owner.deleted_at is not None:
        raise HTTPException(404, "User not found")
    if owner.id == viewer.id:
        _grant_and_commit(db, viewer)  # my signature card shows up on my first visit
    return cards.collection(db, owner)
