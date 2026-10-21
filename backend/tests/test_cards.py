"""Cards & boosters — /api/cards (cards.py, cards_rules.py).

The rules pinned here:
- the feature flag gates members; switching it on starts the count (cards_since),
  nothing is paid out for before it (no backfill);
- a booster's content is drawn at grant time and hidden until it's opened;
  opening twice returns the same cards; only the owner opens;
- size follows the pool (the LAN's attendees, owner excluded), never the same
  member twice, never the owner;
- at most one Epic, always the last card, at the source's rate;
- grants are idempotent: attendance once per LAN from its first day (withheld,
  never redrawn, while the member is taken out of it), one per trophy
  won (taken back if unopened when the reveal is undone), one per XP level above
  the base level;
- buying spends XP from a balance (earned − spent) without lowering the level;
- faces are snapshots: an avatar change doesn't touch them, a deletion removes
  the photo; there is no opt-out (decided 2026-10-18).
"""
import os
from datetime import date, datetime, timedelta, timezone

import pytest

import cards
import database
import models
import uploads
from cards_rules import BOOSTER_PRICE_XP, EPIC_RATES, booster_size
from conftest import auth_header, login, make_user, run_concurrently


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _today():
    """The app's today (instance timezone, UTC by default), not the test
    machine's: between midnight and 02:00 in Paris they differ by a day."""
    from event_utils import local_today

    s = database.SessionLocal()
    try:
        return local_today(s)
    finally:
        s.close()


def _set(client, token, key, value):
    resp = client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(token))
    assert resp.status_code == 200, resp.text
    return resp


@pytest.fixture
def lan(client):
    """founder (admin) + 8 members, all "in" at a LAN that ended yesterday;
    nina is a member who wasn't there. Cards on, counting from a week ago."""
    names = ["founder", "alice", "bob", "carol", "dan", "eve", "fay", "gus", "hal"]
    ids = {n: make_user(n, role="admin" if n == "founder" else "user") for n in names}
    ids["nina"] = make_user("nina")
    s = database.SessionLocal()
    try:
        end = _today() - timedelta(days=1)
        event = models.LanEvent(title="LAN #2", start_date=end - timedelta(days=4), end_date=end,
                                created_by=ids["founder"])
        s.add(event)
        s.flush()
        for n in names:
            s.add(models.EventRSVP(event_id=event.id, user_id=ids[n], status="in",
                                   arrival_date=event.start_date, departure_date=event.end_date))
        s.commit()
        event_id = event.id
    finally:
        s.close()
    tok = {n: login(client, n) for n in ids}
    _set(client, tok["founder"], "cards_enabled", "true")
    _set(client, tok["founder"], "cards_since", (_today() - timedelta(days=7)).isoformat())
    return {"ids": ids, "tok": tok, "event_id": event_id}


def _h(lan, who):
    return auth_header(lan["tok"][who])


def _me(client, lan, who):
    resp = client.get("/api/cards/me", headers=_h(lan, who))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _open(client, lan, who, booster_id):
    return client.post(f"/api/cards/boosters/{booster_id}/open", headers=_h(lan, who))


def _collection(client, lan, viewer, owner):
    resp = client.get(f"/api/cards/collection/{lan['ids'][owner]}", headers=_h(lan, viewer))
    assert resp.status_code == 200, resp.text
    return resp.json()


class _Rng:
    """Stands in for cards._rng: sample() keeps the pool's order, random()
    returns what the test wants (0 = Epic every time, 0.99 = never)."""

    def __init__(self, roll):
        self.roll = roll

    def sample(self, pool, k):
        return list(pool)[:k]

    def random(self):
        return self.roll


def _reveal_trophy(lan, winners, *, revealed_at=None, name="Clutch"):
    s = database.SessionLocal()
    try:
        t = models.Trophy(name=name, emoji="🎯", created_by=lan["ids"]["founder"])
        s.add(t)
        s.flush()
        e = models.EventTrophy(event_id=lan["event_id"], trophy_id=t.id, mode="direct", status="revealed",
                               revealed_at=revealed_at or datetime.utcnow())
        s.add(e)
        s.flush()
        for w in winners:
            s.add(models.EventTrophyWinner(event_trophy_id=e.id, user_id=lan["ids"][w]))
        s.commit()
        return e.id
    finally:
        s.close()


# ── Rules ─────────────────────────────────────────────────────────────────────

def test_booster_size_follows_the_pool():
    assert [booster_size(n) for n in (0, 1, 2, 10, 11, 19, 20, 29, 30, 49, 50, 99, 100, 250)] == \
        [0, 1, 2, 2, 3, 3, 4, 4, 5, 5, 8, 8, 10, 10]


def test_epic_rates_are_by_source_and_within_one_to_ten_percent():
    assert EPIC_RATES == {"attendance": 0.08, "xp_level": 0.06, "trophy": 0.10, "purchase": 0.05}
    assert all(0.01 <= r <= 0.10 for r in EPIC_RATES.values())


# ── Flag & start date ─────────────────────────────────────────────────────────

def test_feature_off_hides_cards_from_members(client, lan):
    _set(client, lan["tok"]["founder"], "cards_enabled", "false")
    assert client.get("/api/cards/me", headers=_h(lan, "alice")).status_code == 404
    # Admins pass the gate but get nothing while it's off.
    assert _me(client, lan, "founder")["boosters"] == []


def test_first_switch_on_starts_the_count_today(client):
    admin = make_user("boss", role="admin")
    tok = login(client, "boss")
    _set(client, tok, "cards_enabled", "true")
    s = database.SessionLocal()
    try:
        assert s.query(models.AppSetting).filter_by(key="cards_since").one().value == _today().isoformat()
    finally:
        s.close()
    assert client.get("/api/settings/public-config", headers=auth_header(tok)).json()["cards_enabled"] is True
    assert client.put("/api/settings/cards_since", json={"value": "yesterday"},
                      headers=auth_header(tok)).status_code == 400
    assert admin


def test_no_backfill_for_a_lan_over_before_the_switch_on(client, lan):
    _set(client, lan["tok"]["founder"], "cards_since", _today().isoformat())
    assert _me(client, lan, "alice")["boosters"] == []


# ── Attendance boosters ───────────────────────────────────────────────────────

def test_attendance_booster_once_per_lan_and_drawn_from_the_others(client, lan):
    first = _me(client, lan, "alice")["boosters"]
    assert len(first) == 1
    b = first[0]
    # 9 attendees, alice excluded: a pool of 8 → 2 cards. Content never shown before opening.
    assert b["source_type"] == "attendance" and b["size"] == 2 and b["epic_rate"] == EPIC_RATES["attendance"]
    assert "cards" not in b
    assert _me(client, lan, "alice")["boosters"] == first  # idempotent
    # nina wasn't there.
    assert _me(client, lan, "nina")["boosters"] == []

    opened = _open(client, lan, "alice", b["id"]).json()
    members = [c["face"]["user_id"] for c in opened["cards"]]
    assert len(set(members)) == 2 and lan["ids"]["alice"] not in members
    assert lan["ids"]["nina"] not in members
    assert [c["slot"] for c in opened["cards"]] == [1, 2]
    assert sorted(opened["new_member_ids"]) == sorted(members)


def _move_lan(lan, start, end):
    s = database.SessionLocal()
    try:
        event = s.get(models.LanEvent, lan["event_id"])
        event.start_date, event.end_date = start, end
        s.commit()
    finally:
        s.close()


def test_from_the_lans_first_day_not_before(client, lan):
    _move_lan(lan, _today() + timedelta(days=1), _today() + timedelta(days=4))
    assert _me(client, lan, "alice")["boosters"] == []
    _move_lan(lan, _today(), _today() + timedelta(days=3))
    assert [b["source_type"] for b in _me(client, lan, "alice")["boosters"]] == ["attendance"]


def _attendance(client, lan, who, status):
    """The treasurer's way, the only one once the LAN has started."""
    end = _today() - timedelta(days=1)
    body = {"status": status}
    if status == "in":
        body.update(arrival_date=(end - timedelta(days=4)).isoformat(), departure_date=end.isoformat())
    resp = client.put(f"/api/events/{lan['event_id']}/rsvps/{lan['ids'][who]}", json=body, headers=_h(lan, "founder"))
    assert resp.status_code == 200, resp.text


def test_taken_out_and_back_in_finds_the_same_booster_never_a_second(client, lan):
    [b] = _me(client, lan, "alice")["boosters"]
    _attendance(client, lan, "alice", "out")
    assert _me(client, lan, "alice")["boosters"] == []
    assert _open(client, lan, "alice", b["id"]).status_code == 409
    _attendance(client, lan, "alice", "in")
    assert _me(client, lan, "alice")["boosters"] == [b]  # the same booster, the same draw
    for _ in range(2):
        _attendance(client, lan, "alice", "out")
        _attendance(client, lan, "alice", "in")
    assert _me(client, lan, "alice")["boosters"] == [b]
    s = database.SessionLocal()
    try:
        assert s.query(models.CardBooster).filter_by(
            owner_id=lan["ids"]["alice"], source_type="attendance").count() == 1
    finally:
        s.close()
    assert _open(client, lan, "alice", b["id"]).status_code == 200


def test_an_opened_attendance_booster_stays_once_taken_out(client, lan):
    [b] = _me(client, lan, "alice")["boosters"]
    drawn = [c["id"] for c in _open(client, lan, "alice", b["id"]).json()["cards"]]
    _attendance(client, lan, "alice", "out")
    assert [c["id"] for c in _open(client, lan, "alice", b["id"]).json()["cards"]] == drawn
    owned = {c["id"] for m in _collection(client, lan, "alice", "alice")["members"] for c in m["cards"]}
    assert set(drawn) <= owned


# ── Opening ───────────────────────────────────────────────────────────────────

def test_opening_reveals_the_same_cards_every_time_and_only_for_the_owner(client, lan):
    b = _me(client, lan, "alice")["boosters"][0]
    assert _collection(client, lan, "alice", "alice")["total_cards"] == 1  # signature only: still sealed
    assert _open(client, lan, "bob", b["id"]).status_code == 404
    first = _open(client, lan, "alice", b["id"]).json()
    again = _open(client, lan, "alice", b["id"]).json()
    assert [c["id"] for c in first["cards"]] == [c["id"] for c in again["cards"]]
    assert _me(client, lan, "alice")["boosters"] == []
    assert _collection(client, lan, "alice", "alice")["total_cards"] == 3


def test_epic_is_always_the_last_card_and_announced(client, lan, monkeypatch):
    monkeypatch.setattr(cards, "_rng", _Rng(0.0))
    b = _me(client, lan, "alice")["boosters"][0]
    got = _open(client, lan, "alice", b["id"]).json()["cards"]
    assert [c["rarity"] for c in got] == ["common", "epic"]
    feed = client.get("/api/activity/", headers=_h(lan, "bob")).json()
    assert [a["action"] for a in feed].count("card_epic_pulled") == 1
    _open(client, lan, "alice", b["id"])  # replay: no second announcement
    feed = client.get("/api/activity/", headers=_h(lan, "bob")).json()
    assert [a["action"] for a in feed].count("card_epic_pulled") == 1


def test_no_epic_above_the_rate(client, lan, monkeypatch):
    monkeypatch.setattr(cards, "_rng", _Rng(0.99))
    b = _me(client, lan, "alice")["boosters"][0]
    assert {c["rarity"] for c in _open(client, lan, "alice", b["id"]).json()["cards"]} == {"common"}


def test_epic_draw_uses_the_rate(monkeypatch, client, lan):
    # Just under the attendance rate: Epic. At it: not.
    monkeypatch.setattr(cards, "_rng", _Rng(EPIC_RATES["attendance"] - 1e-9))
    b = _me(client, lan, "alice")["boosters"][0]
    assert _open(client, lan, "alice", b["id"]).json()["cards"][-1]["rarity"] == "epic"
    monkeypatch.setattr(cards, "_rng", _Rng(EPIC_RATES["attendance"]))
    b = _me(client, lan, "bob")["boosters"][0]
    assert _open(client, lan, "bob", b["id"]).json()["cards"][-1]["rarity"] == "common"


# ── Signature card ────────────────────────────────────────────────────────────

def test_signature_card_is_mine_and_never_in_a_booster(client, lan):
    col = _collection(client, lan, "alice", "alice")
    [me] = [m for m in col["members"] if m["user_id"] == lan["ids"]["alice"]]
    assert [c["kind"] for c in me["cards"]] == ["signature"]
    # The completion counter ignores my own card: 9 active others, none collected yet.
    assert col["collected"] == 0 and col["crew_size"] == 9


# ── Trophies ──────────────────────────────────────────────────────────────────

def test_trophy_booster_and_its_take_back(client, lan):
    edition = _reveal_trophy(lan, ["alice", "bob"])
    sources = sorted(b["source_type"] for b in _me(client, lan, "alice")["boosters"])
    assert sources == ["attendance", "trophy"]
    trophy_b = next(b for b in _me(client, lan, "alice")["boosters"] if b["source_type"] == "trophy")
    assert trophy_b["epic_rate"] == EPIC_RATES["trophy"]
    bob_trophy = next(b for b in _me(client, lan, "bob")["boosters"] if b["source_type"] == "trophy")
    _open(client, lan, "bob", bob_trophy["id"])

    # Un-reveal: alice's unopened booster goes, bob's opened one stays.
    resp = client.patch(f"/api/trophies/editions/{edition}", json={"status": "draft"}, headers=_h(lan, "founder"))
    assert resp.status_code == 200, resp.text
    s = database.SessionLocal()
    try:
        left = {(b.owner_id, b.opened_at is not None)
                for b in s.query(models.CardBooster).filter_by(source_type="trophy").all()}
    finally:
        s.close()
    assert left == {(lan["ids"]["bob"], True)}
    assert [b["source_type"] for b in _me(client, lan, "alice")["boosters"]] == ["attendance"]


def test_trophy_revealed_before_the_switch_on_gives_nothing(client, lan):
    _reveal_trophy(lan, ["alice"], revealed_at=datetime.utcnow() - timedelta(days=30))
    assert [b["source_type"] for b in _me(client, lan, "alice")["boosters"]] == ["attendance"]


def test_start_day_is_a_local_day_for_a_ceremony_past_midnight(client, lan):
    # Paris is ahead of UTC: a reveal at 00:30 local on the start day is stored
    # on the previous UTC day, and must count; one at 23:30 the evening before
    # must not.
    from zoneinfo import ZoneInfo

    paris = ZoneInfo("Europe/Paris")
    _set(client, lan["tok"]["founder"], "app_timezone", "Europe/Paris")
    day = datetime.now(paris).date()
    _set(client, lan["tok"]["founder"], "cards_since", day.isoformat())

    def utc(d, hour, minute):
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=paris).astimezone(timezone.utc).replace(tzinfo=None)

    _reveal_trophy(lan, ["alice"], revealed_at=utc(day, 0, 30), name="After midnight")
    _reveal_trophy(lan, ["bob"], revealed_at=utc(day - timedelta(days=1), 23, 30), name="Evening before")
    assert "trophy" in [b["source_type"] for b in _me(client, lan, "alice")["boosters"]]
    assert "trophy" not in [b["source_type"] for b in _me(client, lan, "bob")["boosters"]]


def test_winner_removed_after_the_reveal_loses_the_unopened_booster(client, lan):
    edition = _reveal_trophy(lan, ["alice"])
    assert "trophy" in [b["source_type"] for b in _me(client, lan, "alice")["boosters"]]
    resp = client.put(f"/api/trophies/editions/{edition}/winners",
                      json={"winners": [{"user_id": lan["ids"]["bob"]}]}, headers=_h(lan, "founder"))
    assert resp.status_code == 200, resp.text
    assert "trophy" not in [b["source_type"] for b in _me(client, lan, "alice")["boosters"]]
    assert "trophy" in [b["source_type"] for b in _me(client, lan, "bob")["boosters"]]


# ── XP: level-up boosters and purchases ───────────────────────────────────────

def test_level_up_boosters_start_above_the_base_level(client, lan):
    _set(client, lan["tok"]["founder"], "xp_enabled", "true")
    _set(client, lan["tok"]["founder"], "trophies_enabled", "true")  # trophy XP counts only then
    # The LAN that ended yesterday: 100 XP, level 2.
    assert "xp_level" not in [b["source_type"] for b in _me(client, lan, "alice")["boosters"]]  # base = 2
    _reveal_trophy(lan, ["alice"], name="New")  # 150 XP: level 3
    got = [b for b in _me(client, lan, "alice")["boosters"] if b["source_type"] == "xp_level"]
    assert len(got) == 1 and got[0]["epic_rate"] == EPIC_RATES["xp_level"]
    assert len([b for b in _me(client, lan, "alice")["boosters"] if b["source_type"] == "xp_level"]) == 1


def test_buying_spends_the_balance_not_the_level(client, lan):
    _set(client, lan["tok"]["founder"], "xp_enabled", "true")
    _set(client, lan["tok"]["founder"], "trophies_enabled", "true")
    assert _me(client, lan, "nina")["xp_balance"] == 0  # wasn't at the LAN
    assert client.post("/api/cards/boosters/buy", headers=_h(lan, "nina")).status_code == 400
    assert _me(client, lan, "alice")["xp_balance"] == 100  # the LAN that ended yesterday
    before = client.get(f"/api/xp/users/{lan['ids']['alice']}", headers=_h(lan, "alice")).json()

    resp = client.post("/api/cards/boosters/buy", headers=_h(lan, "alice"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["xp_balance"] == 100 - BOOSTER_PRICE_XP
    bought = [b for b in body["boosters"] if b["source_type"] == "purchase"]
    assert len(bought) == 1 and bought[0]["epic_rate"] == EPIC_RATES["purchase"]
    after = client.get(f"/api/xp/users/{lan['ids']['alice']}", headers=_h(lan, "alice")).json()
    assert (after["total"], after["level"]) == (before["total"], before["level"])
    assert client.post("/api/cards/boosters/buy", headers=_h(lan, "alice")).status_code == 400


def test_no_purchase_without_xp(client, lan):
    me = _me(client, lan, "alice")
    assert me["xp_balance"] is None and me["booster_price"] == BOOSTER_PRICE_XP
    assert client.post("/api/cards/boosters/buy", headers=_h(lan, "alice")).status_code == 400


# ── Faces ─────────────────────────────────────────────────────────────────────

def _give_avatar(user_id, name="avatar_x.webp"):
    path = os.path.join(uploads.UPLOAD_DIR, name)
    with open(path, "wb") as f:
        f.write(b"RIFF....WEBPfake")
    s = database.SessionLocal()
    try:
        s.get(models.User, user_id).avatar_url = f"/uploads/{name}"
        s.commit()
    finally:
        s.close()
    return path


def _bob_card(client, lan, monkeypatch):
    """Open alice's booster with bob drawn first."""
    order = [lan["ids"]["bob"], lan["ids"]["carol"]]

    class Rng(_Rng):
        def sample(self, pool, k):
            by_id = {u.id: u for u in pool}
            return [by_id[i] for i in order][:k]

    monkeypatch.setattr(cards, "_rng", Rng(0.99))
    b = _me(client, lan, "alice")["boosters"][0]
    return _open(client, lan, "alice", b["id"]).json()["cards"][0]


def test_face_is_a_copy_that_outlives_an_avatar_change(client, lan, monkeypatch):
    original = _give_avatar(lan["ids"]["bob"])
    card = _bob_card(client, lan, monkeypatch)
    url = card["face"]["image_url"]
    assert url.startswith("/uploads/cards/") and url != "/uploads/avatar_x.webp"
    os.remove(original)  # what save_image_upload does to the old avatar
    assert os.path.exists(os.path.join(uploads.UPLOAD_DIR, "cards", os.path.basename(url)))
    face = _collection(client, lan, "alice", "alice")["members"]
    bob = next(m for m in face if m["user_id"] == lan["ids"]["bob"])
    assert bob["cards"][0]["face"]["image_url"] == url
    assert card["face"]["event_title"] == "LAN #2" and card["face"]["edition_size"] == 9


def test_there_is_no_opt_out(client, lan, monkeypatch):
    _give_avatar(lan["ids"]["bob"])
    url = _bob_card(client, lan, monkeypatch)["face"]["image_url"]
    resp = client.put(f"/api/users/{lan['ids']['bob']}", json={"cards_opt_out": True}, headers=_h(lan, "bob"))
    assert resp.status_code == 200 and "cards_opt_out" not in resp.json()
    assert os.path.exists(os.path.join(uploads.UPLOAD_DIR, "cards", os.path.basename(url)))
    bob = next(m for m in _collection(client, lan, "alice", "alice")["members"] if m["user_id"] == lan["ids"]["bob"])
    assert bob["image_url"] == url


def test_deletion_takes_the_photo_off(client, lan, monkeypatch):
    _give_avatar(lan["ids"]["bob"])
    url = _bob_card(client, lan, monkeypatch)["face"]["image_url"]
    assert client.delete(f"/api/users/{lan['ids']['bob']}", headers=_h(lan, "founder")).status_code == 200
    assert not os.path.exists(os.path.join(uploads.UPLOAD_DIR, "cards", os.path.basename(url)))
    bob = next(m for m in _collection(client, lan, "alice", "alice")["members"] if m["user_id"] == lan["ids"]["bob"])
    assert bob["departed"] is True and bob["image_url"] is None and bob["username"].startswith("deleted_user_")


# ── Races: a double click, two tabs (D-1, D-7 of the 2026-10-20 review) ───────

def _purchases(user_id):
    s = database.SessionLocal()
    try:
        return s.query(models.CardBooster).filter(
            models.CardBooster.owner_id == user_id, models.CardBooster.source_type == "purchase",
        ).count()
    finally:
        s.close()


def _buy(client, lan, who):
    return lambda: client.post("/api/cards/boosters/buy", headers=_h(lan, who))


def _xp_on(client, lan):
    _set(client, lan["tok"]["founder"], "xp_enabled", "true")
    _set(client, lan["tok"]["founder"], "trophies_enabled", "true")


def test_two_purchases_at_once_pay_for_one_booster(client, lan):
    _xp_on(client, lan)
    assert _me(client, lan, "alice")["xp_balance"] == 100
    statuses = sorted(r.status_code for r in run_concurrently(_buy(client, lan, "alice"), _buy(client, lan, "alice")))
    # 409 when they really raced (the loser gives its booster back), 400 when
    # the second one simply came after; never two boosters for one price.
    assert statuses[0] == 200 and statuses[1] in (400, 409), statuses
    assert _purchases(lan["ids"]["alice"]) == 1
    assert _me(client, lan, "alice")["xp_balance"] == 0


def test_purchases_at_once_respect_the_weekly_cap(client, lan):
    _xp_on(client, lan)
    for i in range(6):  # 6 trophies: +300 XP on top of the LAN's 100
        _reveal_trophy(lan, ["alice"], name=f"Trophy {i}")
    assert _me(client, lan, "alice")["xp_balance"] == 400
    assert client.post("/api/cards/boosters/buy", headers=_h(lan, "alice")).status_code == 200
    statuses = [r.status_code for r in run_concurrently(*[_buy(client, lan, "alice")] * 3)]
    assert statuses.count(200) == 1 and all(s in (200, 400, 409) for s in statuses), statuses
    assert _purchases(lan["ids"]["alice"]) == 2
    assert _me(client, lan, "alice")["purchases_left"] == 0


def test_purchases_at_once_on_undrawn_faces_never_500(client, lan):
    # bob never opened LPM: no face exists for anyone he may draw, so three
    # purchases at once race on uq_card_face as well as on the balance — and
    # with XP for two boosters, the two losers of the first draw race again
    # on their second attempt (the audit saw 200, 200, 500 here).
    _xp_on(client, lan)
    for i in range(6):
        _reveal_trophy(lan, ["bob"], name=f"Trophy {i}")
    statuses = [r.status_code for r in run_concurrently(*[_buy(client, lan, "bob")] * 3)]
    assert all(s in (200, 400, 409) for s in statuses), statuses
    assert statuses.count(200) == 2 and _purchases(lan["ids"]["bob"]) == 2


def test_opening_at_once_announces_the_epic_once(client, lan, monkeypatch):
    monkeypatch.setattr(cards, "_rng", _Rng(0.0))
    b = _me(client, lan, "alice")["boosters"][0]
    results = run_concurrently(lambda: _open(client, lan, "alice", b["id"]), lambda: _open(client, lan, "alice", b["id"]))
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json()["cards"] == results[1].json()["cards"]
    feed = client.get("/api/activity/", headers=_h(lan, "bob")).json()
    assert [a["action"] for a in feed].count("card_epic_pulled") == 1
