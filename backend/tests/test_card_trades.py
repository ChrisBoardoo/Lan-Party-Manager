"""Card trades — /api/cards/trades, /listings, /trade-suggestions (card_trades.py).

The rules pinned here (lot C, md/2.features/cards/cards_v2_quetes_presence_echanges.md §3):
- a card type is (face, rarity); you give duplicates only and keep one of each
  type; an Epic alone isn't a duplicate, even next to a common of the same face;
- only seen cards count: an unopened booster's cards, the signature, a card of
  the receiver — all refused with the same 400, so the refusal leaks nothing;
- 1 to 3 cards a side; nothing is reserved, everything is checked again
  (serialized) on accept: an offer that became impossible is cancelled;
- offers lapse after 7 days, on read; pending offers sent are capped;
- the recipient answers, the proposer cancels, nobody else sees the offer;
- listings close once their author has no duplicate left;
- the feature flag gates members (404), and needs cards on.
"""
import threading
from datetime import datetime, timedelta

import pytest

import card_trades
import database
import models
from conftest import auth_header, login, make_user, run_concurrently


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _set(client, token, key, value):
    resp = client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(token))
    assert resp.status_code == 200, resp.text


@pytest.fixture
def crew(client):
    """founder (admin), alice, bob, carol, dan at one LAN, each with a face in
    it. Cards and trading on. `deal(owner, face_of, n, rarity, opened, kind)`
    puts cards straight into a member's hands."""
    names = ["founder", "alice", "bob", "carol", "dan"]
    ids = {n: make_user(n, role="admin" if n == "founder" else "user") for n in names}
    s = database.SessionLocal()
    try:
        today = datetime.utcnow().date()
        event = models.LanEvent(title="LAN #2", start_date=today - timedelta(days=5),
                                end_date=today - timedelta(days=1), created_by=ids["founder"])
        s.add(event)
        s.flush()
        faces = {}
        for n in names:
            face = models.CardFace(event_id=event.id, user_id=ids[n], username=n)
            s.add(face)
            s.flush()
            faces[n] = face.id
        s.commit()
        event_id = event.id
    finally:
        s.close()
    tok = {n: login(client, n) for n in names}
    _set(client, tok["founder"], "cards_enabled", "true")
    _set(client, tok["founder"], "cards_trading_enabled", "true")

    def deal(owner, face_of, n=1, rarity="common", opened=True, kind="pulled"):
        """`n` cards of `face_of`'s face to `owner`, in one booster (none for a
        signature)."""
        s = database.SessionLocal()
        try:
            booster = None
            if kind == "pulled":
                booster = models.CardBooster(
                    owner_id=ids[owner], source_type="purchase", source_id=None, event_id=event_id, size=n,
                    epic_rate=0.05, opened_at=datetime.utcnow() if opened else None,
                )
                s.add(booster)
                s.flush()
            made = []
            for slot in range(1, n + 1):
                card = models.Card(owner_id=ids[owner], face_id=faces[face_of], rarity=rarity, kind=kind,
                                   slot=slot, booster_id=booster.id if booster else None)
                s.add(card)
                s.flush()
                made.append(card.id)
            s.commit()
            return made
        finally:
            s.close()

    return {"ids": ids, "tok": tok, "faces": faces, "event_id": event_id, "deal": deal}


@pytest.fixture
def swap(crew):
    """alice holds 2× dan, bob holds 2× carol: a trade both can make."""
    return {"alice_dan": crew["deal"]("alice", "dan", 2), "bob_carol": crew["deal"]("bob", "carol", 2)}


def _h(crew, who):
    return auth_header(crew["tok"][who])


def _propose(client, crew, who, to, give, take, **extra):
    return client.post("/api/cards/trades", json={"recipient_id": crew["ids"][to], "give": give, "take": take, **extra},
                       headers=_h(crew, who))


def _answer(client, crew, who, trade_id, verb="accept"):
    return client.post(f"/api/cards/trades/{trade_id}/{verb}", headers=_h(crew, who))


def _trades(client, crew, who):
    resp = client.get("/api/cards/trades", headers=_h(crew, who))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _owner_of(card_id):
    s = database.SessionLocal()
    try:
        return s.get(models.Card, card_id).owner_id
    finally:
        s.close()


# ── Flag ──────────────────────────────────────────────────────────────────────

def test_flag_off_hides_trading_from_members(client, crew):
    _set(client, crew["tok"]["founder"], "cards_trading_enabled", "false")
    for path in ("/api/cards/trades", "/api/cards/listings", "/api/cards/trade-suggestions"):
        assert client.get(path, headers=_h(crew, "alice")).status_code == 404
    assert client.get("/api/cards/me", headers=_h(crew, "alice")).json()["trades_pending"] is None
    # Trading needs the cards on as well.
    _set(client, crew["tok"]["founder"], "cards_trading_enabled", "true")
    _set(client, crew["tok"]["founder"], "cards_enabled", "false")
    assert client.get("/api/cards/trades", headers=_h(crew, "alice")).status_code == 404


# ── The duplicate rule ────────────────────────────────────────────────────────

def test_collection_shows_what_can_be_traded(client, crew):
    crew["deal"]("alice", "bob", 3)
    crew["deal"]("alice", "carol", 1, rarity="epic")
    crew["deal"]("alice", "carol", 1)
    col = client.get(f"/api/cards/collection/{crew['ids']['alice']}", headers=_h(crew, "bob")).json()
    types = {(t["face_id"], t["rarity"]): t for t in col["types"]}
    bob = types[(crew["faces"]["bob"], "common")]
    assert (bob["count"], bob["tradable"], len(bob["card_ids"])) == (3, 2, 2)
    # An Epic alone isn't a duplicate, even next to a common of the same member.
    assert types[(crew["faces"]["carol"], "epic")]["tradable"] == 0
    assert types[(crew["faces"]["carol"], "common")]["tradable"] == 0


def test_refused_cards_all_get_the_same_answer(client, crew, swap):
    lone = crew["deal"]("alice", "bob", 1, rarity="epic")       # not a duplicate
    hidden = crew["deal"]("alice", "carol", 3, opened=False)    # unopened booster
    sig = crew["deal"]("alice", "alice", 1, kind="signature")   # her signature
    bobs_face = crew["deal"]("alice", "bob", 2)                 # bob would receive himself
    hers_at_bob = crew["deal"]("bob", "alice", 2)               # alice would receive herself
    take = swap["bob_carol"][:1]
    answers = [
        _propose(client, crew, "alice", "bob", lone, take),
        _propose(client, crew, "alice", "bob", hidden[:1], take),
        _propose(client, crew, "alice", "bob", sig, take),
        _propose(client, crew, "alice", "bob", bobs_face[:1], take),
        _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], hers_at_bob[:1]),
        _propose(client, crew, "alice", "bob", swap["alice_dan"][:1] * 2, take),
        _propose(client, crew, "alice", "bob", swap["alice_dan"], take),  # her last dan too
    ]
    assert [r.status_code for r in answers] == [400] * len(answers)
    assert len({r.json()["detail"] for r in answers}) == 1
    # The same cards, sound, go through.
    assert _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], take).status_code == 200


def test_sides_hold_one_to_three_cards(client, crew, swap):
    assert _propose(client, crew, "alice", "bob", [], swap["bob_carol"][:1]).status_code == 422
    five = crew["deal"]("alice", "dan", 5)
    assert _propose(client, crew, "alice", "bob", five[:4], swap["bob_carol"][:1]).status_code == 422


# ── Offer → answer ────────────────────────────────────────────────────────────

def test_accepting_swaps_the_cards(client, crew, swap):
    give, take = swap["alice_dan"][:1], swap["bob_carol"][:1]
    offer = _propose(client, crew, "alice", "bob", give, take, note="deal?")
    assert offer.status_code == 200, offer.text
    trade = offer.json()
    assert trade["status"] == "pending" and trade["note"] == "deal?"
    assert [c["id"] for c in trade["give"]] == give and [c["id"] for c in trade["take"]] == take
    assert [t["id"] for t in _trades(client, crew, "bob")["received"]] == [trade["id"]]
    assert [t["id"] for t in _trades(client, crew, "alice")["sent"]] == [trade["id"]]
    assert client.get("/api/cards/me", headers=_h(crew, "bob")).json()["trades_pending"] == 1
    # Nobody else sees it, nor answers it.
    assert _trades(client, crew, "carol") == {"received": [], "sent": [], "history": []}
    assert _answer(client, crew, "carol", trade["id"]).status_code == 404
    assert _answer(client, crew, "alice", trade["id"]).status_code == 403

    resp = _answer(client, crew, "bob", trade["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    assert _owner_of(give[0]) == crew["ids"]["bob"] and _owner_of(take[0]) == crew["ids"]["alice"]
    # Provenance: the card says where it came from.
    col = client.get(f"/api/cards/collection/{crew['ids']['alice']}", headers=_h(crew, "alice")).json()
    got = next(c for m in col["members"] for c in m["cards"] if c["id"] == take[0])
    assert got["acquired_from"] == "bob" and got["acquired_at"] is not None
    assert _trades(client, crew, "alice")["history"][0]["status"] == "accepted"
    assert _answer(client, crew, "bob", trade["id"]).status_code == 409


def test_notifications_go_to_the_other_side_and_epics_to_everyone(client, crew, swap):
    epics = crew["deal"]("bob", "dan", 2, rarity="epic")
    trade = _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], epics[:1]).json()
    assert _answer(client, crew, "bob", trade["id"]).status_code == 200
    s = database.SessionLocal()
    try:
        rows = {r.action: r for r in s.query(models.ActivityLog).filter(models.ActivityLog.action.like("card_trade%"))}
    finally:
        s.close()
    assert rows["card_trade_offered"].recipient_user_id == crew["ids"]["bob"]
    assert rows["card_trade_accepted"].recipient_user_id == crew["ids"]["alice"]
    assert rows["card_trade_epic"].recipient_user_id is None


def test_a_trade_of_commons_stays_out_of_the_public_feed(client, crew, swap):
    trade = _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], swap["bob_carol"][:1]).json()
    _answer(client, crew, "bob", trade["id"])
    s = database.SessionLocal()
    try:
        assert s.query(models.ActivityLog).filter(models.ActivityLog.action == "card_trade_epic").count() == 0
    finally:
        s.close()


def test_decline_and_cancel_belong_to_their_side(client, crew, swap):
    t1 = _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], swap["bob_carol"][:1]).json()
    assert _answer(client, crew, "alice", t1["id"], "decline").status_code == 403
    assert _answer(client, crew, "bob", t1["id"], "decline").json()["status"] == "declined"
    t2 = _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], swap["bob_carol"][:1]).json()
    assert _answer(client, crew, "bob", t2["id"], "cancel").status_code == 403
    out = _answer(client, crew, "alice", t2["id"], "cancel").json()
    assert (out["status"], out["closed_reason"]) == ("cancelled", "proposer")


def test_the_same_offer_twice_is_refused(client, crew, swap):
    give, take = swap["alice_dan"][:1], swap["bob_carol"][:1]
    assert _propose(client, crew, "alice", "bob", give, take).status_code == 200
    assert _propose(client, crew, "alice", "bob", give, take).status_code == 409


def test_an_offer_that_became_impossible_is_cancelled(client, crew, swap):
    """Two offers on bob's one spare carol: the first accepted, the second
    can't go through any more."""
    dan = crew["deal"]("dan", "alice", 2)
    first = _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], swap["bob_carol"][:1]).json()
    second = _propose(client, crew, "dan", "bob", dan[:1], swap["bob_carol"][1:]).json()
    assert _answer(client, crew, "bob", first["id"]).status_code == 200
    assert _answer(client, crew, "bob", second["id"]).status_code == 409
    closed = _trades(client, crew, "dan")["history"][0]
    assert (closed["status"], closed["closed_reason"]) == ("cancelled", "unavailable")
    assert _owner_of(swap["bob_carol"][1]) == crew["ids"]["bob"]


def test_two_accepts_at_once_move_a_card_once(client, crew, swap, monkeypatch):
    """bob's one spare carol in two offers, both accepted in the same instant
    (two tabs): one goes through, the other is 409.

    The gate makes the race real: each accept waits, right after its checks,
    for the other one to have checked too. With the write lock the second
    accept can't even start checking, the gate times out, and it then finds
    the card gone; without the lock both pass and the card moves twice."""
    dan = crew["deal"]("dan", "alice", 2)
    first = _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], swap["bob_carol"][:1]).json()
    second = _propose(client, crew, "dan", "bob", dan[:1], swap["bob_carol"][:1]).json()

    real_check = card_trades.check_offer
    gate = threading.Barrier(2, timeout=2)

    def check_then_wait(*args, **kwargs):
        result = real_check(*args, **kwargs)
        try:
            gate.wait()
        except threading.BrokenBarrierError:
            pass
        return result

    monkeypatch.setattr(card_trades, "check_offer", check_then_wait)
    results = run_concurrently(
        lambda: _answer(client, crew, "bob", first["id"]).status_code,
        lambda: _answer(client, crew, "bob", second["id"]).status_code,
    )
    assert sorted(results) == [200, 409]
    s = database.SessionLocal()
    try:
        assert s.query(models.Card).filter(models.Card.owner_id == crew["ids"]["bob"],
                                           models.Card.face_id == crew["faces"]["carol"]).count() == 1
    finally:
        s.close()


def test_offers_lapse_after_a_week(client, crew, swap):
    trade = _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], swap["bob_carol"][:1]).json()
    s = database.SessionLocal()
    try:
        s.get(models.CardTrade, trade["id"]).expires_at = datetime.utcnow() - timedelta(minutes=1)
        s.commit()
    finally:
        s.close()
    assert client.get("/api/cards/me", headers=_h(crew, "bob")).json()["trades_pending"] == 0
    assert _answer(client, crew, "bob", trade["id"]).status_code == 409
    assert _trades(client, crew, "alice")["history"][0]["status"] == "expired"


def test_pending_offers_are_capped(client, crew, swap, monkeypatch):
    monkeypatch.setattr(card_trades, "TRADE_PENDING_MAX", 1)
    assert _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], swap["bob_carol"][:1]).status_code == 200
    assert _propose(client, crew, "alice", "bob", swap["alice_dan"][1:], swap["bob_carol"][:1]).status_code == 400


def test_a_departed_member_cancels_their_offers(client, crew, swap):
    trade = _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], swap["bob_carol"][:1]).json()
    s = database.SessionLocal()
    try:
        s.get(models.User, crew["ids"]["alice"]).is_active = False
        s.commit()
    finally:
        s.close()
    assert _trades(client, crew, "bob")["history"][0]["closed_reason"] == "unavailable"
    assert _answer(client, crew, "bob", trade["id"]).status_code == 409


# ── Market ────────────────────────────────────────────────────────────────────

def test_listings_need_a_duplicate_and_close_when_it_goes(client, crew, swap):
    crew["deal"]("alice", "carol", 1)
    face_carol, face_dan = crew["faces"]["carol"], crew["faces"]["dan"]
    assert client.post("/api/cards/listings", json={"face_id": face_carol, "rarity": "common"},
                       headers=_h(crew, "alice")).status_code == 400
    resp = client.post("/api/cards/listings", json={"face_id": face_dan, "rarity": "common", "note": "vs Epic"},
                       headers=_h(crew, "alice"))
    assert resp.status_code == 200, resp.text
    listing = resp.json()
    assert listing["mine"] and listing["viewer_count"] == 2 and listing["card"]["id"] in swap["alice_dan"]
    assert client.post("/api/cards/listings", json={"face_id": face_dan, "rarity": "common"},
                       headers=_h(crew, "alice")).status_code == 409
    col = client.get(f"/api/cards/collection/{crew['ids']['alice']}", headers=_h(crew, "alice")).json()
    assert next(t for t in col["types"] if t["face_id"] == face_dan)["listed"] is True
    seen = client.get("/api/cards/listings", headers=_h(crew, "carol")).json()
    assert [(l["id"], l["mine"], l["viewer_count"], l["note"]) for l in seen] == [(listing["id"], False, 0, "vs Epic")]
    assert client.delete(f"/api/cards/listings/{listing['id']}", headers=_h(crew, "carol")).status_code == 403

    # carol answers the listing; once it's accepted, alice has no duplicate left.
    gift = crew["deal"]("carol", "bob", 2)
    trade = _propose(client, crew, "carol", "alice", gift[:1], [listing["card"]["id"]], listing_id=listing["id"])
    assert trade.status_code == 200, trade.text
    assert _answer(client, crew, "alice", trade.json()["id"]).status_code == 200
    assert client.get("/api/cards/listings", headers=_h(crew, "carol")).json() == []


def test_a_listing_is_closed_by_its_author(client, crew, swap):
    listing = client.post("/api/cards/listings", json={"face_id": crew["faces"]["dan"], "rarity": "common"},
                          headers=_h(crew, "alice")).json()
    assert client.delete(f"/api/cards/listings/{listing['id']}", headers=_h(crew, "alice")).status_code == 200
    assert client.get("/api/cards/listings", headers=_h(crew, "bob")).json() == []


def test_suggestions_pair_what_each_side_is_missing(client, crew, swap):
    sugg = client.get("/api/cards/trade-suggestions", headers=_h(crew, "alice")).json()
    assert [s["member"]["username"] for s in sugg] == ["bob"]
    assert [c["face"]["username"] for c in sugg[0]["they_give"]] == ["carol"]
    assert [c["face"]["username"] for c in sugg[0]["i_give"]] == ["dan"]
    # A duplicate of bob's own face is no use to bob.
    crew["deal"]("alice", "bob", 2)
    sugg = client.get("/api/cards/trade-suggestions", headers=_h(crew, "alice")).json()
    assert [c["face"]["username"] for c in sugg[0]["i_give"]] == ["dan"]


# ── Monthly contract ──────────────────────────────────────────────────────────

def test_an_accepted_trade_counts_for_both_sides(client, crew, swap):
    trade = _propose(client, crew, "alice", "bob", swap["alice_dan"][:1], swap["bob_carol"][:1]).json()
    _answer(client, crew, "bob", trade["id"])
    s = database.SessionLocal()
    try:
        counted = card_trades.accepted_by_member(s, datetime.utcnow() - timedelta(days=1),
                                                 datetime.utcnow() + timedelta(days=1))
    finally:
        s.close()
    assert counted == {crew["ids"]["alice"]: 1, crew["ids"]["bob"]: 1}
