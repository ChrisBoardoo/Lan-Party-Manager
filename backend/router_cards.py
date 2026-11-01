"""Cards & boosters endpoints — /api/cards. The rules live in cards.py and
cards_rules.py; this only maps them to HTTP. Gated by the `cards` feature
(admins pass, as everywhere, but get no grants while it's off)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from typing import List

import card_trades
import cards
from cards_rules import BOOSTER_PRICE_XP, PURCHASES_PER_WEEK
from database import get_db
from models import CardTrade, User
from router_settings import is_feature_enabled, require_feature
from schemas import (
    BoosterOpenOut, CardsMeOut, CollectionOut, ListingCreate, ListingOut, TradeCreate, TradeOut, TradesOut,
    TradeSuggestionOut,
)

router = APIRouter()

# Attempts on a unique-constraint race (uq_card_face, see _grant_and_commit).
RETRIES = 4


def _grant_and_commit(db: Session, user: User, ledger=None) -> None:
    """ensure_grants, committed. Two tabs opening LPM at once can race on the
    unique constraints: the loser rolls back and runs again, which then finds
    the winner's grants and adds nothing. Three or four at once (a LAN's first
    morning) can lose twice in a row on the faces, hence the attempts."""
    for attempt in range(RETRIES):
        try:
            cards.ensure_grants(db, user, ledger)
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            if attempt == RETRIES - 1:
                raise


def _me(db: Session, user: User, ledger=None) -> CardsMeOut:
    unopened = cards.unopened_boosters(db, user)
    balance = cards.xp_balance(db, user, ledger)
    left, next_at = cards.purchase_allowance(db, user) if balance is not None else (None, None)
    return CardsMeOut(
        boosters=[cards.booster_out(b) for b in unopened],
        xp_balance=balance,
        booster_price=BOOSTER_PRICE_XP,
        purchases_per_week=PURCHASES_PER_WEEK,
        purchases_left=left,
        next_purchase_at=next_at,
        trades_pending=card_trades.pending_received(db, user.id) if is_feature_enabled(db, "cards_trading") else None,
    )


@router.get("/me", response_model=CardsMeOut)
def my_cards(db: Session = Depends(get_db), user: User = Depends(require_feature("cards"))):
    """My unopened boosters, after granting whatever I've earned since my last
    visit. The Hub polls this for its "boosters to open" banner."""
    ledger = cards.xp_ledger(db)  # one build for the grants and the balance
    _grant_and_commit(db, user, ledger)
    return _me(db, user, ledger)


@router.post("/boosters/buy", response_model=CardsMeOut)
def buy(db: Session = Depends(get_db), user: User = Depends(require_feature("cards"))):
    """Buy a booster with spendable XP. Doesn't open it."""
    if not is_feature_enabled(db, "cards"):
        raise HTTPException(400, "Cards are not enabled")
    # Same race as _grant_and_commit on the faces (uq_card_face): two purchases
    # at once that draw a member nobody had drawn yet. The loser runs again and
    # finds the face — or, more likely, finds its XP already spent (400).
    ledger = cards.xp_ledger(db)  # earned XP doesn't change with a purchase
    for attempt in range(RETRIES):
        try:
            cards.buy_booster(db, user, ledger)
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if attempt == RETRIES - 1:
                raise
    return _me(db, user, ledger)


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


# ── Trades (card_trades.py) ───────────────────────────────────────────────────
# Gated by `cards_trading` (which needs `cards`). Every write takes the write
# lock first: an accept re-checks the cards and moves them in one go, and two
# at once that involve the same card would otherwise both pass their checks.

def _member(user: User) -> dict:
    return {"id": user.id, "username": user.username, "avatar_url": user.avatar_url}


def _trade_out(view: cards.CardView, trade: CardTrade) -> dict:
    by_id = {i.card_id: i.card for i in trade.items}
    give, take = card_trades.sides(trade)
    return {
        "id": trade.id,
        "status": trade.status,
        "closed_reason": trade.closed_reason,
        "note": trade.note,
        "created_at": trade.created_at,
        "decided_at": trade.decided_at,
        "expires_at": trade.expires_at,
        "listing_id": trade.listing_id,
        "proposer": _member(trade.proposer),
        "recipient": _member(trade.recipient),
        "give": [view.card(by_id[c]) for c in give],
        "take": [view.card(by_id[c]) for c in take],
    }


@router.get("/trades", response_model=TradesOut)
def list_trades(db: Session = Depends(get_db), user: User = Depends(require_feature("cards_trading"))):
    """My offers: received and sent (pending), and the history. Offers that
    lapsed or became impossible are closed on the way."""
    mine = card_trades.my_trades(db, user)
    db.commit()
    view = cards.CardView(db)
    return {key: [_trade_out(view, t) for t in trades] for key, trades in mine.items()}


@router.post("/trades", response_model=TradeOut)
def propose_trade(data: TradeCreate, db: Session = Depends(get_db), user: User = Depends(require_feature("cards_trading"))):
    card_trades.lock(db)
    trade = card_trades.propose(db, user, data.recipient_id, data.give, data.take, data.listing_id, data.note)
    db.commit()
    db.refresh(trade)
    return _trade_out(cards.CardView(db), trade)


def _answer(db: Session, trade: CardTrade) -> dict:
    db.commit()
    db.refresh(trade)
    return _trade_out(cards.CardView(db), trade)


@router.post("/trades/{trade_id}/accept", response_model=TradeOut)
def accept_trade(trade_id: int, db: Session = Depends(get_db), user: User = Depends(require_feature("cards_trading"))):
    """The cards change hands, after every rule is checked again. 409 when the
    offer can't go through any more (it's then cancelled)."""
    card_trades.lock(db)
    return _answer(db, card_trades.accept(db, trade_id, user))


@router.post("/trades/{trade_id}/decline", response_model=TradeOut)
def decline_trade(trade_id: int, db: Session = Depends(get_db), user: User = Depends(require_feature("cards_trading"))):
    card_trades.lock(db)
    return _answer(db, card_trades.decline(db, trade_id, user))


@router.post("/trades/{trade_id}/cancel", response_model=TradeOut)
def cancel_trade(trade_id: int, db: Session = Depends(get_db), user: User = Depends(require_feature("cards_trading"))):
    card_trades.lock(db)
    return _answer(db, card_trades.cancel(db, trade_id, user))


@router.get("/listings", response_model=List[ListingOut])
def list_listings(db: Session = Depends(get_db), user: User = Depends(require_feature("cards_trading"))):
    """The crew's market. Listings whose author no longer has a duplicate of
    that type are closed on the way."""
    holdings = card_trades.Holdings(db)
    listings = card_trades.open_listings(db, holdings)
    db.commit()
    mine = holdings.of(user.id)
    view = cards.CardView(db)
    out = []
    for listing in listings:
        spare = card_trades.tradable(holdings.of(listing.owner_id)).get((listing.face_id, listing.rarity))
        if not spare:
            continue
        out.append({
            "id": listing.id,
            "owner": _member(listing.owner),
            "card": view.card(spare[-1]),
            "note": listing.note,
            "created_at": listing.created_at,
            "mine": listing.owner_id == user.id,
            "viewer_count": len(mine.get((listing.face_id, listing.rarity), [])),
        })
    return out


@router.post("/listings", response_model=ListingOut)
def create_listing(data: ListingCreate, db: Session = Depends(get_db), user: User = Depends(require_feature("cards_trading"))):
    card_trades.lock(db)
    listing = card_trades.create_listing(db, user, data.face_id, data.rarity, data.note)
    db.commit()
    db.refresh(listing)
    held = card_trades.Holdings(db).of(user.id)
    spare = card_trades.tradable(held)[(listing.face_id, listing.rarity)]
    return {
        "id": listing.id,
        "owner": _member(user),
        "card": cards.CardView(db).card(spare[-1]),
        "note": listing.note,
        "created_at": listing.created_at,
        "mine": True,
        "viewer_count": len(held[(listing.face_id, listing.rarity)]),
    }


@router.delete("/listings/{listing_id}")
def delete_listing(listing_id: int, db: Session = Depends(get_db), user: User = Depends(require_feature("cards_trading"))):
    card_trades.lock(db)
    card_trades.close_listing(db, listing_id, user)
    db.commit()
    return {"ok": True}


@router.get("/trade-suggestions", response_model=List[TradeSuggestionOut])
def trade_suggestions(db: Session = Depends(get_db), user: User = Depends(require_feature("cards_trading"))):
    view = cards.CardView(db)
    return [
        {
            "member": _member(s["user"]),
            "they_give": [view.card(c) for c in s["they_give"]],
            "i_give": [view.card(c) for c in s["i_give"]],
        }
        for s in card_trades.suggestions(db, user)
    ]
