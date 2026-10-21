"""Cards & boosters — the crew collects each other.

Unlike XP and badges (computed on read), a booster can't be derived from other
data: its content is drawn **once, server-side, when it's granted**, and stored.
Opening it only reveals what was drawn — closing the tab mid-animation redraws
nothing, and the API never shows a booster's content before it's opened.

Grants are lazy and idempotent. `ensure_grants` runs when a member looks at
their cards and adds what they've earned since; the unique
(owner, source_type, source_id) makes a second run a no-op. No scheduler, and
no hook in the features that earn boosters — except the trophy endpoints,
which take back an unopened booster when a reveal is undone
(`revoke_trophy_boosters`).

What earns a booster (rules and rates in cards_rules.py), counted from the day
the feature was switched on (`cards_since`) — nothing before it, by decision
(no backfill):
- attendance: one per LAN attended ("in" RSVP), from its first day, to open
  together on site. Attendance is locked from that day (only a treasurer or an
  admin can change it), so the pool is settled. A member taken out of the LAN
  can neither see nor open its booster until put back in; it's never deleted
  nor redrawn, so going out and back in neither stacks boosters nor rerolls
  one (`unopened_boosters`). Once opened, it stays;
- trophy: one per trophy won, from its reveal;
- xp_level: one per XP level reached above the level the member had when
  cards first looked at them (`users.cards_level_base`); XP feature on only;
- purchase: bought with spendable XP (earned − spent; the level is untouched).

A booster belongs to an edition — a LAN — and its cards are drawn from that
LAN's attendees, the owner excluded, never the same member twice. The last
card is Epic with the source's rate. Each member also gets their own card once,
the signature card, which never comes out of a booster.

Faces: a member's photo is copied into uploads/cards/ the first time one of
their cards is drawn for an edition (CardFace), so an avatar change — which
deletes the old file — never changes or breaks the cards already drawn.
"""
import secrets
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from activity import add_activity
from cards_rules import (
    BOOSTER_PRICE_XP, EPIC_RATES, PURCHASE_WINDOW_DAYS, PURCHASES_PER_WEEK, booster_size,
)
from event_utils import local_day_start_utc, local_today
from models import (
    AppSetting, Card, CardBooster, CardFace, EventRSVP, EventTrophy, EventTrophyWinner, LanEvent, User,
)
from router_settings import get_setting, is_feature_enabled
from uploads import copy_upload, remove_upload
from xp import build_ledger, user_xp

# Not random.random(): nobody gets to predict or replay the draws.
_rng = secrets.SystemRandom()

CARDS_SUBDIR = "cards"


# ── Settings ──────────────────────────────────────────────────────────────────

def cards_since(db: Session) -> date:
    """The day the feature was first switched on: grants count from it. Set by
    router_settings when an admin enables cards; written here as today if it
    is missing (an instance enabled before the setting existed)."""
    raw = get_setting(db, "cards_since")
    try:
        if raw:
            return date.fromisoformat(raw)
    except ValueError:
        pass
    today = local_today(db)
    row = db.query(AppSetting).filter(AppSetting.key == "cards_since").first()
    if row:
        row.value = today.isoformat()
    else:
        db.add(AppSetting(key="cards_since", value=today.isoformat()))
    return today


# ── Editions & pools ──────────────────────────────────────────────────────────

def attendees(db: Session, event_id: int) -> List[User]:
    """Who can be drawn in a booster of this LAN: its active "in" attendees."""
    return (
        db.query(User)
        .join(EventRSVP, EventRSVP.user_id == User.id)
        .filter(
            EventRSVP.event_id == event_id,
            EventRSVP.status == "in",
            User.is_active == True,  # noqa: E712
            User.deleted_at.is_(None),
        )
        .order_by(User.id)
        .all()
    )


def latest_edition(db: Session, today: Optional[date] = None) -> Optional[LanEvent]:
    """The edition of boosters that don't come from a LAN (XP level, purchase,
    signature card): the latest LAN that has started, else the next one."""
    today = today or local_today(db)
    started = (
        db.query(LanEvent)
        .filter(LanEvent.start_date <= today)
        .order_by(LanEvent.start_date.desc(), LanEvent.id.desc())
        .first()
    )
    return started or db.query(LanEvent).order_by(LanEvent.start_date, LanEvent.id).first()


class _Levels:
    """Members' XP levels, computed once per request and only if a face needs
    one (the XP ledger walks every tournament, photo and chat message)."""

    def __init__(self, db: Session, ledger=None):
        self.db = db
        self.ledger = ledger  # shared with the caller when it already built one
        self._levels: Optional[Dict[int, int]] = None

    def get(self, user_id: int) -> Optional[int]:
        if not is_feature_enabled(self.db, "xp"):
            return None
        if self._levels is None:
            ledger = self.ledger if self.ledger is not None else build_ledger(self.db)
            users = self.db.query(User.id).filter(User.deleted_at.is_(None)).all()
            self._levels = {uid: ledger.summary(uid).level for (uid,) in users}
        return self._levels.get(user_id)


def _face(db: Session, event: LanEvent, member: User, levels: _Levels) -> CardFace:
    face = db.query(CardFace).filter(CardFace.event_id == event.id, CardFace.user_id == member.id).first()
    if face:
        return face
    image = copy_upload(member.avatar_url, src_subdir=None, dst_subdir=CARDS_SUBDIR,
                        prefix=f"face_{event.id}_{member.id}")
    face = CardFace(event_id=event.id, user_id=member.id, username=member.username,
                    image_url=image, xp_level=levels.get(member.id))
    db.add(face)
    db.flush()  # the session doesn't autoflush: the next draw must see it
    return face


# ── Grants ────────────────────────────────────────────────────────────────────

def _grant(
    db: Session, owner: User, source_type: str, source_id: Optional[int], event: LanEvent,
    levels: _Levels, cost_xp: int = 0,
) -> Optional[CardBooster]:
    """Draw and store a booster, or None if it already exists (same source) or
    there's nobody to collect at that LAN."""
    if source_id is not None and db.query(CardBooster.id).filter(
        CardBooster.owner_id == owner.id,
        CardBooster.source_type == source_type,
        CardBooster.source_id == source_id,
    ).first():
        return None
    pool = [u for u in attendees(db, event.id) if u.id != owner.id]
    size = booster_size(len(pool))
    if size == 0:
        return None
    rate = EPIC_RATES[source_type]
    drawn = _rng.sample(pool, size)
    epic = _rng.random() < rate
    booster = CardBooster(
        owner_id=owner.id, source_type=source_type, source_id=source_id, event_id=event.id,
        size=size, epic_rate=rate, cost_xp=cost_xp,
    )
    for slot, member in enumerate(drawn, start=1):
        booster.cards.append(Card(
            owner_id=owner.id, face=_face(db, event, member, levels), slot=slot, kind="pulled",
            # At most one Epic, always the last card.
            rarity="epic" if epic and slot == size else "common",
        ))
    db.add(booster)
    db.flush()
    return booster


def _ensure_signature(db: Session, owner: User, today: date, levels: _Levels) -> None:
    if db.query(Card.id).filter(Card.owner_id == owner.id, Card.kind == "signature").first():
        return
    event = latest_edition(db, today)
    if event is None:
        return
    db.add(Card(owner_id=owner.id, face=_face(db, event, owner, levels), slot=1, rarity="common", kind="signature"))
    db.flush()


def xp_ledger(db: Session):
    """The XP ledger when XP is on, else None — built once per request and
    handed to ensure_grants / xp_balance / buy_booster (Q-1 of the 2026-10-20
    review: GET /cards/me used to build it two to three times)."""
    return build_ledger(db) if is_feature_enabled(db, "xp") else None


def ensure_grants(db: Session, user: User, ledger=None) -> None:
    """Grant whatever `user` has earned and not received yet. Idempotent; the
    caller commits. Two concurrent runs can race on the unique constraints —
    the routes roll back and run it once more (see router_cards)."""
    if not is_feature_enabled(db, "cards") or user.deleted_at is not None or not user.is_active:
        return
    today = local_today(db)
    since = cards_since(db)
    if ledger is None:
        ledger = xp_ledger(db)
    levels = _Levels(db, ledger)

    _ensure_signature(db, user, today, levels)

    # Attendance: every LAN the member is in, from its first day, unless it was
    # over before the feature started.
    attended = (
        db.query(LanEvent)
        .join(EventRSVP, EventRSVP.event_id == LanEvent.id)
        .filter(
            EventRSVP.user_id == user.id,
            EventRSVP.status == "in",
            LanEvent.end_date >= since,
            LanEvent.start_date <= today,
        )
        .order_by(LanEvent.end_date)
        .all()
    )
    for event in attended:
        _grant(db, user, "attendance", event.id, event, levels)

    # Trophies won, revealed since the feature started. `revealed_at` is UTC and
    # `since` a local day: a ceremony that runs past midnight must still count.
    since_utc = local_day_start_utc(db, since)
    won = (
        db.query(EventTrophy)
        .join(EventTrophyWinner, EventTrophyWinner.event_trophy_id == EventTrophy.id)
        .filter(
            EventTrophyWinner.user_id == user.id,
            EventTrophy.status == "revealed",
            EventTrophy.revealed_at >= since_utc,
        )
        .order_by(EventTrophy.revealed_at)
        .all()
    )
    for edition in won:
        _grant(db, user, "trophy", edition.id, edition.event, levels)

    # XP levels reached above the base level.
    if ledger is not None:
        level = ledger.summary(user.id).level
        if user.cards_level_base is None:
            user.cards_level_base = level  # no payout for levels reached before cards
        elif level > user.cards_level_base:
            event = latest_edition(db, today)
            if event is not None:
                for n in range(user.cards_level_base + 1, level + 1):
                    _grant(db, user, "xp_level", n, event, levels)


def revoke_trophy_boosters(db: Session, edition_id: int, keep_owner_ids: Iterable[int] = ()) -> int:
    """A reveal undone, or a winner removed after it: take back the trophy's
    unopened boosters from whoever no longer won it. An opened booster stays —
    its cards were seen, taking them back would be worse than the mistake."""
    keep = set(keep_owner_ids)
    boosters = (
        db.query(CardBooster)
        .filter(
            CardBooster.source_type == "trophy",
            CardBooster.source_id == edition_id,
            CardBooster.opened_at.is_(None),
        )
        .all()
    )
    n = 0
    for b in boosters:
        if b.owner_id not in keep:
            db.delete(b)
            n += 1
    return n


def scrub_faces(db: Session, user: User) -> None:
    """An account deleted: its photo comes off every card face (the copies are
    deleted) and the faces take the account's anonymized name. The cards stay
    in the others' collections, as "departed".

    There is no opt-out of the cards (decided 2026-10-18): a card shows a
    username and a profile picture — any avatar will do — never anything
    nominative, and being collectable is the point of the feature."""
    for face in db.query(CardFace).filter(CardFace.user_id == user.id).all():
        remove_upload(face.image_url, CARDS_SUBDIR)
        face.image_url = None
        face.username = user.username


# ── XP balance & purchase ─────────────────────────────────────────────────────

def xp_spent(db: Session, user_id: int) -> int:
    return db.query(func.coalesce(func.sum(CardBooster.cost_xp), 0)).filter(CardBooster.owner_id == user_id).scalar()


def xp_balance(db: Session, user: User, ledger=None) -> Optional[int]:
    """Spendable XP: earned − spent on boosters. None when XP is off. Earned XP
    is recomputed on read and can drop (a corrected score, a deleted photo), so
    the balance can go below zero: that blocks purchases, it never takes a
    booster back."""
    if not is_feature_enabled(db, "xp"):
        return None
    return user_xp(db, user.id, ledger).total - xp_spent(db, user.id)


def _recent_purchases(db: Session, user_id: int) -> List[datetime]:
    """When the member bought a booster in the rolling week, oldest first."""
    window_start = datetime.utcnow() - timedelta(days=PURCHASE_WINDOW_DAYS)
    return sorted(
        at for (at,) in db.query(CardBooster.granted_at).filter(
            CardBooster.owner_id == user_id,
            CardBooster.source_type == "purchase",
            CardBooster.granted_at >= window_start,
        ).all()
        if at is not None
    )


def purchase_allowance(db: Session, user: User) -> tuple[int, Optional[datetime]]:
    """(purchases left this rolling week, when the next one frees up if none)."""
    recent = _recent_purchases(db, user.id)
    left = max(0, PURCHASES_PER_WEEK - len(recent))
    next_at = recent[-PURCHASES_PER_WEEK] + timedelta(days=PURCHASE_WINDOW_DAYS) if left == 0 and recent else None
    return left, next_at


def buy_booster(db: Session, user: User, ledger=None) -> CardBooster:
    if not is_feature_enabled(db, "xp"):
        raise HTTPException(400, "XP is not enabled")
    earned = user_xp(db, user.id, ledger).total
    if len(_recent_purchases(db, user.id)) >= PURCHASES_PER_WEEK:
        raise HTTPException(400, "Weekly purchase limit reached")
    if earned - xp_spent(db, user.id) < BOOSTER_PRICE_XP:
        raise HTTPException(400, "Not enough XP")
    event = latest_edition(db)
    if event is None:
        raise HTTPException(400, "No LAN yet")
    booster = _grant(db, user, "purchase", None, event, _Levels(db, ledger), cost_xp=BOOSTER_PRICE_XP)
    if booster is None:
        raise HTTPException(400, "Nobody to collect at this LAN yet")
    # Checked again now that the booster is written (flushed): a purchase that
    # ran at the same moment — a double click, two tabs — wasn't visible to the
    # checks above; it is to these, since our write waited for its commit. The
    # unique constraint can't arbitrate (a purchase has no source_id), so the
    # loser gives its booster back (D-1 of the 2026-10-20 review).
    if earned - xp_spent(db, user.id) < 0:
        db.rollback()
        raise HTTPException(409, "Not enough XP: another purchase went through first")
    if len(_recent_purchases(db, user.id)) > PURCHASES_PER_WEEK:
        db.rollback()
        raise HTTPException(409, "Weekly purchase limit reached by a purchase that went through first")
    return booster


# ── Unopened boosters ─────────────────────────────────────────────────────────

def _attending(db: Session, user_id: int) -> set:
    """The LANs this member is "in" at, right now."""
    return {
        event_id for (event_id,) in db.query(EventRSVP.event_id).filter(
            EventRSVP.user_id == user_id, EventRSVP.status == "in",
        ).all()
    }


def _withheld(booster: CardBooster, attending: set) -> bool:
    """An attendance booster whose owner is no longer in its LAN."""
    return booster.source_type == "attendance" and booster.source_id not in attending


def unopened_boosters(db: Session, user: User) -> List[CardBooster]:
    """The boosters waiting to be opened, oldest first, minus the attendance
    boosters of LANs the member was taken out of (they come back, unchanged,
    if the member is put back in)."""
    attending = _attending(db, user.id)
    boosters = (
        db.query(CardBooster)
        .filter(CardBooster.owner_id == user.id, CardBooster.opened_at.is_(None))
        .order_by(CardBooster.granted_at, CardBooster.id)
        .all()
    )
    return [b for b in boosters if not _withheld(b, attending)]


# ── Opening ───────────────────────────────────────────────────────────────────

def open_booster(db: Session, user: User, booster_id: int) -> CardBooster:
    """Mark the booster opened and return it. Opening again returns the same
    cards: a crash mid-animation neither loses nor redraws anything."""
    booster = db.query(CardBooster).filter(CardBooster.id == booster_id).first()
    if booster is None or booster.owner_id != user.id:
        raise HTTPException(404, "Booster not found")
    if booster.opened_at is None and _withheld(booster, _attending(db, user.id)):
        raise HTTPException(409, "You are no longer attending this LAN")
    if booster.opened_at is None:
        # Claimed in one statement: two opens at the same moment (a double
        # click) both saw opened_at None above; only one changes the row here,
        # and only that one announces the Epic. The other returns the same
        # cards, as a replay does.
        claimed = (
            db.query(CardBooster)
            .filter(CardBooster.id == booster.id, CardBooster.opened_at.is_(None))
            .update({"opened_at": datetime.utcnow()}, synchronize_session=False)
        )
        db.refresh(booster)
        if claimed:
            for card in booster.cards:
                if card.rarity == "epic":
                    # Broadcast: an Epic is an event for the whole crew (Hub feed,
                    # desktop toast). Common cards stay quiet, or the day after a
                    # LAN would drown the feed.
                    add_activity(db, user.id, "card_epic_pulled", f"pulled an Epic card of {card.face.username}",
                                 "card", card.id)
    return booster


# ── Reading ───────────────────────────────────────────────────────────────────

class CardView:
    """Turns stored cards into what the API shows, with the per-edition facts
    computed once per request: card numbers, trophies won, who is gone."""

    def __init__(self, db: Session):
        self.db = db
        self._numbers: Dict[int, List[int]] = {}
        self._trophies: Dict[int, Dict[int, List[str]]] = {}
        self._users: Dict[int, Optional[User]] = {}

    def _edition_ids(self, event_id: int) -> List[int]:
        if event_id not in self._numbers:
            rows = (
                self.db.query(EventRSVP.user_id)
                .filter(EventRSVP.event_id == event_id, EventRSVP.status == "in")
                .order_by(EventRSVP.user_id)
                .all()
            )
            self._numbers[event_id] = [r[0] for r in rows]
        return self._numbers[event_id]

    def _edition_trophies(self, event_id: int) -> Dict[int, List[str]]:
        if event_id not in self._trophies:
            by_user: Dict[int, List[str]] = {}
            rows = (
                self.db.query(EventTrophyWinner.user_id, EventTrophy)
                .join(EventTrophy, EventTrophy.id == EventTrophyWinner.event_trophy_id)
                .filter(EventTrophy.event_id == event_id, EventTrophy.status == "revealed")
                .all()
            )
            for uid, edition in rows:
                by_user.setdefault(uid, []).append(f"{edition.trophy.emoji or '🏆'} {edition.trophy.name}")
            self._trophies[event_id] = by_user
        return self._trophies[event_id]

    def _user(self, user_id: int) -> Optional[User]:
        if user_id not in self._users:
            self._users[user_id] = self.db.query(User).filter(User.id == user_id).first()
        return self._users[user_id]

    def face(self, face: CardFace) -> dict:
        member = self._user(face.user_id)
        departed = member is None or member.deleted_at is not None
        hidden = departed
        ids = self._edition_ids(face.event_id)
        event = face.event
        return {
            "user_id": face.user_id,
            "username": member.username if departed and member else face.username,
            "image_url": None if hidden else face.image_url,
            "xp_level": face.xp_level,
            "event_id": face.event_id,
            "event_title": event.title if event else "",
            "year": event.start_date.year if event else None,
            "number": ids.index(face.user_id) + 1 if face.user_id in ids else None,
            "edition_size": len(ids),
            "trophies": [] if departed else self._edition_trophies(face.event_id).get(face.user_id, []),
            "departed": departed,
        }

    def card(self, card: Card) -> dict:
        booster = card.booster
        return {
            "id": card.id,
            "rarity": card.rarity,
            "kind": card.kind,
            "slot": card.slot,
            "source_type": booster.source_type if booster else "signature",
            "obtained_at": (booster.opened_at if booster else card.created_at),
            "face": self.face(card.face),
        }


def booster_out(booster: CardBooster) -> dict:
    return {
        "id": booster.id,
        "source_type": booster.source_type,
        "event_id": booster.event_id,
        "event_title": booster.event.title if booster.event else "",
        "size": booster.size,
        "epic_rate": booster.epic_rate,
        "granted_at": booster.granted_at,
        "opened_at": booster.opened_at,
    }


def owned_cards(db: Session, owner_id: int, *, exclude_booster: Optional[int] = None) -> List[Card]:
    """A member's cards that have been seen: the signature card and every card
    of an opened booster. Cards of an unopened booster don't exist yet, as far
    as anyone can tell."""
    q = (
        db.query(Card)
        .outerjoin(CardBooster, CardBooster.id == Card.booster_id)
        .filter(Card.owner_id == owner_id)
        .filter((Card.booster_id.is_(None)) | (CardBooster.opened_at.isnot(None)))
    )
    if exclude_booster is not None:
        q = q.filter((Card.booster_id.is_(None)) | (Card.booster_id != exclude_booster))
    return q.all()


def collection(db: Session, owner: User) -> dict:
    """A member's collection, one entry per collected member: Epic first, then
    the most collected. `collected` / `crew_size` is the completion counter
    (active members other than the owner)."""
    view = CardView(db)
    groups: Dict[int, List[dict]] = {}
    for card in owned_cards(db, owner.id):
        groups.setdefault(card.face.user_id, []).append(view.card(card))

    members = []
    for user_id, cards in groups.items():
        cards.sort(key=lambda c: (c["rarity"] != "epic", -(c["face"]["year"] or 0), c["id"]))
        top = cards[0]["face"]
        members.append({
            "user_id": user_id,
            "username": top["username"],
            "image_url": top["image_url"],
            "departed": top["departed"],
            "count": len(cards),
            "epic_count": sum(1 for c in cards if c["rarity"] == "epic"),
            "cards": cards,
        })
    members.sort(key=lambda m: (m["user_id"] != owner.id, -m["epic_count"], -m["count"], m["username"].lower()))

    crew = {
        u.id for u in db.query(User.id).filter(User.deleted_at.is_(None), User.is_active == True).all()  # noqa: E712
    } - {owner.id}
    return {
        "owner_id": owner.id,
        "members": members,
        "collected": len(crew & set(groups)),
        "crew_size": len(crew),
        "total_cards": sum(m["count"] for m in members),
        "epic_cards": sum(m["epic_count"] for m in members),
    }


def new_member_ids(db: Session, booster: CardBooster) -> List[int]:
    """The members of this booster the owner had no card of before it — the
    "New!" tag of the opening's recap."""
    before = {c.face.user_id for c in owned_cards(db, booster.owner_id, exclude_booster=booster.id)}
    return sorted({c.face.user_id for c in booster.cards} - before)

