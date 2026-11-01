"""Card trades — swapping duplicates within the crew (lot C, decided by
CrossWax on 2026-10-19: md/2.features/cards/cards_v2_quetes_presence_echanges.md
§3). The HTTP side is router_cards.py.

The rules:
- a card *type* is (face, rarity), and duplicates are identical: what's traded
  is one of my copies of a type, never a particular card;
- only cards that have been seen count (cards.owned_cards: the signature and
  the cards of opened boosters) — an unopened booster's cards don't exist yet,
  for trading as for showing;
- the signature card is never traded;
- you only give duplicates: for every type, you keep at least one;
- nobody receives a card of themselves. A face without a member (the Souvenir
  cards to come, md/2.features/cards/cards_souvenirs_implementation.md) is
  nobody's;
- 1 to 3 cards on each side, so no gifts;
- nothing is reserved while an offer is pending: everything is checked again,
  serialized, when it's accepted. An offer that became impossible is cancelled
  the next time it's read, and one nobody answered lapses after
  TRADE_EXPIRY_DAYS, also on read;
- no XP for a trade (two friends could bounce a card back and forth for
  ever): an accepted trade only counts towards the monthly contract's `trade`
  objective (quests.py).
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from activity import add_activity
from cards_rules import (
    LISTINGS_OPEN_MAX, TRADE_EXPIRY_DAYS, TRADE_MAX_CARDS_PER_SIDE, TRADE_PENDING_MAX,
)
from models import Card, CardBooster, CardListing, CardTrade, CardTradeItem, User

CardType = Tuple[int, str]  # (face_id, rarity)
Holding = Dict[CardType, List[Card]]

# Shown for any card that fails the checks: which rule broke would tell the
# proposer something about cards they can't see (an unopened booster's).
INVALID_CARDS = "These cards can't be traded"
# How many closed trades the history shows.
HISTORY_LIMIT = 50
# Suggestions shown, and cards prefilled on each side of one.
SUGGESTIONS_MAX = 3


def lock(db: Session) -> None:
    """Serialize the write (router_expenses._lock): two accepts at once that
    involve the same card both pass their checks otherwise. SQLite only."""
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def card_type(card: Card) -> CardType:
    return (card.face_id, card.rarity)


def _active(user: Optional[User]) -> bool:
    return user is not None and user.deleted_at is None and bool(user.is_active)


def _is_card_of(card: Card, user_id: int) -> bool:
    """A card showing this member. A face without a member is nobody's."""
    return card.face is not None and card.face.user_id is not None and card.face.user_id == user_id


# ── Holdings ──────────────────────────────────────────────────────────────────

class Holdings:
    """Members' seen cards by type, loaded once per request (one query for
    any number of members)."""

    def __init__(self, db: Session):
        self.db = db
        self._by_user: Dict[int, Holding] = {}

    def load(self, user_ids: Iterable[int]) -> None:
        missing = [uid for uid in set(user_ids) if uid not in self._by_user]
        if not missing:
            return
        rows = (
            self.db.query(Card)
            .options(joinedload(Card.face))
            .outerjoin(CardBooster, CardBooster.id == Card.booster_id)
            .filter(Card.owner_id.in_(missing))
            .filter((Card.booster_id.is_(None)) | (CardBooster.opened_at.isnot(None)))
            .order_by(Card.id)
            .all()
        )
        for uid in missing:
            self._by_user[uid] = defaultdict(list)
        for card in rows:
            self._by_user[card.owner_id][card_type(card)].append(card)

    def of(self, user_id: int) -> Holding:
        self.load([user_id])
        return self._by_user[user_id]


def tradable(holding: Holding) -> Dict[CardType, List[Card]]:
    """The copies a member may give, by type: every copy but one, and never
    the signature card."""
    out: Dict[CardType, List[Card]] = {}
    for t, cards in holding.items():
        spare = [c for c in cards if c.kind != "signature"][: max(len(cards) - 1, 0)]
        if spare:
            out[t] = spare
    return out


def _side_ok(holding: Holding, card_ids: Sequence[int], receiver_id: int, cards_by_id: Dict[int, Card]) -> bool:
    """These cards can go from the holding's owner to `receiver_id`: owned,
    seen, none is a signature or a card of the receiver, and the giver keeps
    at least one of each type."""
    owned = {c.id: c for cards in holding.values() for c in cards}
    giving: Dict[CardType, int] = defaultdict(int)
    for cid in card_ids:
        card = owned.get(cid)
        if card is None or card.kind == "signature" or _is_card_of(card, receiver_id):
            return False
        giving[card_type(card)] += 1
        cards_by_id[cid] = card
    return all(n <= len(holding[t]) - 1 for t, n in giving.items())


def check_offer(
    holdings: Holdings, proposer_id: int, recipient_id: int, give: Sequence[int], take: Sequence[int],
) -> Optional[Dict[int, Card]]:
    """The offer's cards by id if it can go through as it stands, else None."""
    if not (1 <= len(give) <= TRADE_MAX_CARDS_PER_SIDE and 1 <= len(take) <= TRADE_MAX_CARDS_PER_SIDE):
        return None
    if len(set(give)) != len(give) or len(set(take)) != len(take) or set(give) & set(take):
        return None
    holdings.load([proposer_id, recipient_id])
    cards_by_id: Dict[int, Card] = {}
    if not _side_ok(holdings.of(proposer_id), give, recipient_id, cards_by_id):
        return None
    if not _side_ok(holdings.of(recipient_id), take, proposer_id, cards_by_id):
        return None
    return cards_by_id


# ── Offers ────────────────────────────────────────────────────────────────────

def sides(trade: CardTrade) -> Tuple[List[int], List[int]]:
    """(the proposer's card ids, the recipient's card ids)."""
    give = [i.card_id for i in trade.items if i.from_user_id == trade.proposer_id]
    take = [i.card_id for i in trade.items if i.from_user_id == trade.recipient_id]
    return give, take


def _close(trade: CardTrade, status: str, reason: Optional[str] = None, at: Optional[datetime] = None) -> None:
    trade.status = status
    trade.closed_reason = reason
    trade.decided_at = at or datetime.utcnow()


def settle(db: Session, trades: Iterable[CardTrade], holdings: Optional[Holdings] = None) -> bool:
    """Close the pending offers that lapsed or became impossible. Returns
    whether anything changed; the caller commits."""
    pending = [t for t in trades if t.status == "pending"]
    if not pending:
        return False
    holdings = holdings or Holdings(db)
    holdings.load({uid for t in pending for uid in (t.proposer_id, t.recipient_id)})
    now = datetime.utcnow()
    changed = False
    for t in pending:
        if t.expires_at <= now:
            _close(t, "expired", at=t.expires_at)
            changed = True
        elif not (_active(t.proposer) and _active(t.recipient)) or check_offer(
            holdings, t.proposer_id, t.recipient_id, *sides(t),
        ) is None:
            _close(t, "cancelled", "unavailable", now)
            changed = True
    return changed


def propose(
    db: Session, proposer: User, recipient_id: int, give: List[int], take: List[int],
    listing_id: Optional[int] = None, note: Optional[str] = None,
) -> CardTrade:
    """Send an offer: `give` from the proposer's cards, `take` from the
    recipient's. The caller has taken the lock and commits."""
    recipient = db.get(User, recipient_id)
    if recipient is None or recipient.id == proposer.id or not _active(recipient):
        raise HTTPException(400, "Choose another member")
    holdings = Holdings(db)
    sent = db.query(CardTrade).filter(CardTrade.proposer_id == proposer.id, CardTrade.status == "pending").all()
    settle(db, sent, holdings)
    sent = [t for t in sent if t.status == "pending"]
    if len(sent) >= TRADE_PENDING_MAX:
        raise HTTPException(400, f"At most {TRADE_PENDING_MAX} offers waiting for an answer")
    cards_by_id = check_offer(holdings, proposer.id, recipient.id, give, take)
    if cards_by_id is None:
        raise HTTPException(400, INVALID_CARDS)
    if listing_id is not None:
        listing = db.get(CardListing, listing_id)
        if (
            listing is None or listing.closed_at is not None or listing.owner_id != recipient.id
            or (listing.face_id, listing.rarity) not in {card_type(cards_by_id[c]) for c in take}
        ):
            raise HTTPException(400, "This listing is no longer open")
    # A second click on "Send", or the same offer again: one is enough.
    wanted = (sorted(give), sorted(take))
    for t in sent:
        give_t, take_t = sides(t)
        if t.recipient_id == recipient.id and (sorted(give_t), sorted(take_t)) == wanted:
            raise HTTPException(409, "You already sent this offer")
    trade = CardTrade(
        proposer_id=proposer.id, recipient_id=recipient.id, listing_id=listing_id, status="pending",
        note=(note or "").strip() or None, expires_at=datetime.utcnow() + timedelta(days=TRADE_EXPIRY_DAYS),
    )
    for cid in give:
        trade.items.append(CardTradeItem(card_id=cid, from_user_id=proposer.id))
    for cid in take:
        trade.items.append(CardTradeItem(card_id=cid, from_user_id=recipient.id))
    db.add(trade)
    db.flush()
    add_activity(db, proposer.id, "card_trade_offered", "offered you a card trade", "card_trade", trade.id,
                 recipient_user_id=recipient.id)
    return trade


def _get_pending(db: Session, trade_id: int, user: User, role: str) -> CardTrade:
    """The offer, if `user` is its `role` ("proposer" | "recipient") and it's
    still pending; a lapsed one is closed (and committed) on the way."""
    trade = db.get(CardTrade, trade_id)
    if trade is None or user.id not in (trade.proposer_id, trade.recipient_id):
        raise HTTPException(404, "Trade not found")
    if getattr(trade, f"{role}_id") != user.id:
        raise HTTPException(403, "Not your offer to answer" if role == "recipient" else "Not your offer")
    if trade.status == "pending" and trade.expires_at <= datetime.utcnow():
        _close(trade, "expired", at=trade.expires_at)
        db.commit()
    if trade.status != "pending":
        raise HTTPException(409, "This offer is closed")
    return trade


def accept(db: Session, trade_id: int, user: User) -> CardTrade:
    """Swap the cards, checked again from scratch. The caller has taken the
    lock and commits; an offer that became impossible is cancelled and
    committed here, then 409."""
    trade = _get_pending(db, trade_id, user, "recipient")
    proposer = trade.proposer
    give, take = sides(trade)
    cards_by_id = None
    if _active(proposer) and _active(user):
        cards_by_id = check_offer(Holdings(db), trade.proposer_id, trade.recipient_id, give, take)
    if cards_by_id is None:
        _close(trade, "cancelled", "unavailable")
        db.commit()
        raise HTTPException(409, "This offer is no longer possible: a card has moved since")
    now = datetime.utcnow()
    for cid in give:
        cards_by_id[cid].owner_id = trade.recipient_id
        cards_by_id[cid].acquired_at = now
    for cid in take:
        cards_by_id[cid].owner_id = trade.proposer_id
        cards_by_id[cid].acquired_at = now
    _close(trade, "accepted", at=now)
    db.flush()
    close_stale_listings(db, [trade.proposer_id, trade.recipient_id])
    add_activity(db, user.id, "card_trade_accepted", "accepted your card trade", "card_trade", trade.id,
                 recipient_user_id=trade.proposer_id)
    if any(cards_by_id[c].rarity == "epic" for c in give + take):
        # The one trade the whole crew hears about: an Epic changing hands.
        add_activity(db, user.id, "card_trade_epic", f"traded an Epic card with {proposer.username}",
                     "card_trade", trade.id)
    return trade


def decline(db: Session, trade_id: int, user: User) -> CardTrade:
    trade = _get_pending(db, trade_id, user, "recipient")
    _close(trade, "declined")
    add_activity(db, user.id, "card_trade_declined", "declined your card trade", "card_trade", trade.id,
                 recipient_user_id=trade.proposer_id)
    return trade


def cancel(db: Session, trade_id: int, user: User) -> CardTrade:
    trade = _get_pending(db, trade_id, user, "proposer")
    _close(trade, "cancelled", "proposer")
    return trade


def my_trades(db: Session, user: User) -> Dict[str, List[CardTrade]]:
    """Offers received and sent (pending), and the history — after closing
    what lapsed or became impossible. The caller commits."""
    mine = (
        db.query(CardTrade)
        .filter((CardTrade.proposer_id == user.id) | (CardTrade.recipient_id == user.id))
        .order_by(CardTrade.created_at.desc(), CardTrade.id.desc())
        .all()
    )
    settle(db, mine)
    pending = [t for t in mine if t.status == "pending"]
    closed = sorted(
        (t for t in mine if t.status != "pending"),
        key=lambda t: (t.decided_at or t.created_at or datetime.min, t.id), reverse=True,
    )
    return {
        "received": [t for t in pending if t.recipient_id == user.id],
        "sent": [t for t in pending if t.proposer_id == user.id],
        "history": closed[:HISTORY_LIMIT],
    }


def pending_received(db: Session, user_id: int) -> int:
    """For the Hub banner: offers waiting for my answer. Cheap, so not
    settled — one that became impossible still counts until the page that
    lists them closes it."""
    return (
        db.query(CardTrade)
        .filter(CardTrade.recipient_id == user_id, CardTrade.status == "pending",
                CardTrade.expires_at > datetime.utcnow())
        .count()
    )


def accepted_by_member(db: Session, start: datetime, end: datetime) -> Dict[int, int]:
    """Accepted trades per member, either side, decided in [start, end) — the
    monthly contract's `trade` objective."""
    out: Dict[int, int] = defaultdict(int)
    rows = (
        db.query(CardTrade.proposer_id, CardTrade.recipient_id)
        .filter(CardTrade.status == "accepted", CardTrade.decided_at >= start, CardTrade.decided_at < end)
        .all()
    )
    for proposer_id, recipient_id in rows:
        out[proposer_id] += 1
        out[recipient_id] += 1
    return dict(out)


# ── Market (listings) ─────────────────────────────────────────────────────────

def close_stale_listings(db: Session, owner_ids: Iterable[int], holdings: Optional[Holdings] = None) -> None:
    """Close the open listings whose author left or no longer has a duplicate
    of that type. The caller commits."""
    owner_ids = list(set(owner_ids))
    if not owner_ids:
        return
    listings = (
        db.query(CardListing)
        .filter(CardListing.owner_id.in_(owner_ids), CardListing.closed_at.is_(None))
        .all()
    )
    if not listings:
        return
    holdings = holdings or Holdings(db)
    holdings.load(owner_ids)
    now = datetime.utcnow()
    for listing in listings:
        spare = tradable(holdings.of(listing.owner_id)).get((listing.face_id, listing.rarity))
        if not spare or not _active(listing.owner):
            listing.closed_at = now


def open_listings(db: Session, holdings: Holdings) -> List[CardListing]:
    """Every open listing, after closing the stale ones. The caller commits."""
    listings = db.query(CardListing).filter(CardListing.closed_at.is_(None)).all()
    close_stale_listings(db, [l.owner_id for l in listings], holdings)
    return sorted(
        (l for l in listings if l.closed_at is None),
        key=lambda l: (l.created_at or datetime.min, l.id), reverse=True,
    )


def create_listing(db: Session, owner: User, face_id: int, rarity: str, note: Optional[str]) -> CardListing:
    """The caller has taken the lock and commits."""
    holdings = Holdings(db)
    if not tradable(holdings.of(owner.id)).get((face_id, rarity)):
        raise HTTPException(400, "You have no duplicate of this card")
    close_stale_listings(db, [owner.id], holdings)
    mine = (
        db.query(CardListing)
        .filter(CardListing.owner_id == owner.id, CardListing.closed_at.is_(None))
        .all()
    )
    if any(l.face_id == face_id and l.rarity == rarity for l in mine):
        raise HTTPException(409, "This card is already listed")
    if len(mine) >= LISTINGS_OPEN_MAX:
        raise HTTPException(400, f"At most {LISTINGS_OPEN_MAX} open listings")
    listing = CardListing(owner_id=owner.id, face_id=face_id, rarity=rarity, note=(note or "").strip() or None)
    db.add(listing)
    db.flush()
    return listing


def close_listing(db: Session, listing_id: int, user: User) -> None:
    listing = db.get(CardListing, listing_id)
    if listing is None or listing.closed_at is not None:
        raise HTTPException(404, "Listing not found")
    if listing.owner_id != user.id:
        raise HTTPException(403, "Not your listing")
    listing.closed_at = datetime.utcnow()


def listed_types(db: Session, owner_id: int) -> set:
    return set(
        db.query(CardListing.face_id, CardListing.rarity)
        .filter(CardListing.owner_id == owner_id, CardListing.closed_at.is_(None))
        .all()
    )


# ── Suggestions ───────────────────────────────────────────────────────────────

def suggestions(db: Session, viewer: User) -> List[dict]:
    """The members with whom a trade would suit both sides: their duplicates
    I have no copy of, against my duplicates they have no copy of (and none
    showing the one who'd receive it). The best three, by the smaller side."""
    members = [u for u in db.query(User).filter(User.id != viewer.id).all() if _active(u)]
    holdings = Holdings(db)
    holdings.load([viewer.id] + [m.id for m in members])
    mine = holdings.of(viewer.id)
    my_spare = tradable(mine)
    out = []
    for m in members:
        theirs = holdings.of(m.id)
        they_give = [
            cards[0] for t, cards in tradable(theirs).items()
            if not mine.get(t) and not _is_card_of(cards[0], viewer.id)
        ]
        i_give = [
            cards[0] for t, cards in my_spare.items()
            if not theirs.get(t) and not _is_card_of(cards[0], m.id)
        ]
        if they_give and i_give:
            out.append({"user": m, "they_give": they_give, "i_give": i_give})
    out.sort(key=lambda s: (-min(len(s["they_give"]), len(s["i_give"])),
                            -(len(s["they_give"]) + len(s["i_give"])), s["user"].username.lower()))
    return out[:SUGGESTIONS_MAX]
