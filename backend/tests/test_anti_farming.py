"""Anti-farming (decided 2026-10-18): XP has to be earned at a LAN, and boosters
bought with it are capped — so a fake tournament or a spam burst between two
LANs can't be turned into a stack of boosters.

The rules pinned here:
- a match's decision time is recorded when it's finalized, cleared if reopened;
- tournament XP counts only for matches decided at a LAN (its own LAN when the
  tournament has one, any LAN otherwise; legacy undated matches only when the
  tournament belongs to a LAN), the champion bonus likewise;
- one account plays for one team of a tournament, never two; an account found
  on both sides of a match earns nothing from it;
- photo XP counts only photos attached to a LAN and uploaded during it or in the
  week after; an upload can't name a LAN that doesn't exist;
- chat messages under 3 characters, or repeating the author's previous one,
  don't count;
- at most two boosters bought per rolling week.
"""
from datetime import date, datetime, timedelta
from types import SimpleNamespace as NS

import database
import models
from conftest import auth_header, login, make_user
from xp import (
    CHAT_MESSAGES_PER_DAY_CAP, _Ledger, add_tournament_xp, counted_chat_messages, decided_at_a_lan, user_xp,
)

LAN1 = (datetime(2026, 10, 14), datetime(2026, 10, 20))
LAN2 = (datetime(2026, 12, 1), datetime(2026, 12, 4))
WINDOWS = {1: LAN1, 2: LAN2}


def _add(*rows):
    s = database.SessionLocal()
    try:
        s.add_all(rows)
        s.commit()
        return [r.id for r in rows]
    finally:
        s.close()


def _set(client, token, key, value):
    resp = client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(token))
    assert resp.status_code == 200, resp.text


def _xp(uid):
    s = database.SessionLocal()
    try:
        return {line.code: line.xp for line in user_xp(s, uid).breakdown}
    finally:
        s.close()


# ── The LAN rule (pure) ───────────────────────────────────────────────────────

def test_decided_at_a_lan():
    during1, during2, between = datetime(2026, 10, 16, 21), datetime(2026, 12, 2, 12), datetime(2026, 11, 10, 20)
    # Its own LAN, when it has one.
    assert decided_at_a_lan(1, during1, WINDOWS)
    assert not decided_at_a_lan(1, during2, WINDOWS)  # during another LAN than its own
    assert not decided_at_a_lan(1, between, WINDOWS)
    # Any LAN, when it has none.
    assert decided_at_a_lan(None, during2, WINDOWS)
    assert not decided_at_a_lan(None, between, WINDOWS)
    # The window's edges: first instant in, end excluded.
    assert decided_at_a_lan(1, LAN1[0], WINDOWS) and not decided_at_a_lan(1, LAN1[1], WINDOWS)
    # Undated (decided before timestamps): only a LAN's own tournament.
    assert decided_at_a_lan(1, None, WINDOWS)
    assert not decided_at_a_lan(None, None, WINDOWS)


def _t(event_id, played_at, teams, winner=1, status="completed"):
    return NS(
        event_id=event_id, bracket_type="single_elimination", status=status, teams=teams,
        matches=[NS(round="final", round_number=1, team_a_id=1, team_b_id=2, winner_id=winner,
                    score_a=0, score_b=0, status="completed", played_at=played_at)],
    )


def _team(tid, *uids):
    return NS(id=tid, team_name=f"T{tid}", color=None, seed=None, members=[NS(user_id=u) for u in uids])


def test_a_fake_tournament_between_lans_pays_nothing():
    ledger = _Ledger()
    add_tournament_xp(ledger, [_t(None, datetime(2026, 11, 10, 20), [_team(1, 7), _team(2, 8)])], WINDOWS)
    assert ledger.rows == {}
    add_tournament_xp(ledger, [_t(None, datetime(2026, 10, 16, 20), [_team(1, 7), _team(2, 8)])], WINDOWS)
    assert {code: v[1] for code, v in ledger.rows[7].items()} == {"match_final": 100, "tournament_win": 50}


def test_an_account_on_both_sides_wins_nothing_from_that_match():
    ledger = _Ledger()
    add_tournament_xp(ledger, [_t(1, datetime(2026, 10, 16, 20), [_team(1, 7, 9), _team(2, 7)])], WINDOWS)
    assert "match_final" not in ledger.rows.get(7, {})
    assert ledger.rows[9]["match_final"] == [1, 100]


# ── Recording when a match was decided ────────────────────────────────────────

def _tournament(admin, event_id=None):
    (tid,) = _add(models.Tournament(game_name="CS2", organizer_id=admin, event_id=event_id, status="final"))
    a, b = _add(models.Team(tournament_id=tid, team_name="A"), models.Team(tournament_id=tid, team_name="B"))
    (mid,) = _add(models.Match(tournament_id=tid, round="final", round_number=1, team_a_id=a, team_b_id=b))
    return tid, a, b, mid


def _played_at(mid):
    s = database.SessionLocal()
    try:
        return s.get(models.Match, mid).played_at
    finally:
        s.close()


def test_finalizing_records_when_and_reopening_clears_it(client):
    admin = make_user("boss", role="admin")
    tok = login(client, "boss")
    tid, a, _b, mid = _tournament(admin)
    url = f"/api/tournaments/{tid}/matches/{mid}"
    before = datetime.utcnow() - timedelta(seconds=5)
    assert client.put(url, json={"status": "completed", "winner_id": a}, headers=auth_header(tok)).status_code == 200
    first = _played_at(mid)
    assert first is not None and first >= before
    # A later score fix keeps the original time.
    client.put(url, json={"score_a": 2}, headers=auth_header(tok))
    assert _played_at(mid) == first
    # Reopened: it will be decided again.
    client.put(url, json={"status": "in_progress"}, headers=auth_header(tok))
    assert _played_at(mid) is None


def test_confirming_a_reported_score_records_when_too(client):
    admin = make_user("boss", role="admin")
    tok = login(client, "boss")
    tid, a, _b, mid = _tournament(admin)
    s = database.SessionLocal()
    try:
        m = s.get(models.Match, mid)
        m.reported_score_a, m.reported_score_b, m.reported_at = 3, 1, datetime.utcnow()
        s.commit()
    finally:
        s.close()
    resp = client.post(f"/api/tournaments/{tid}/matches/{mid}/confirm", headers=auth_header(tok))
    assert resp.status_code == 200, resp.text
    assert _played_at(mid) is not None


def test_a_match_decided_now_counts_only_if_a_lan_is_on(client):
    admin = make_user("boss", role="admin")
    tok = login(client, "boss")
    player = make_user("farmer")
    tid, a, _b, mid = _tournament(admin)
    _add(models.TeamMember(team_id=a, player_name="farmer", user_id=player))
    client.put(f"/api/tournaments/{tid}/matches/{mid}", json={"status": "completed", "winner_id": a},
               headers=auth_header(tok))
    assert _xp(player) == {}  # no LAN at all: a fake tournament
    today = date.today()
    _add(models.LanEvent(title="LAN", start_date=today - timedelta(days=1), end_date=today + timedelta(days=1),
                         created_by=admin))
    assert _xp(player) == {"match_final": 100, "tournament_win": 50}  # the final closed the tournament


# ── One team per player ───────────────────────────────────────────────────────

def test_a_player_can_only_be_on_one_team(client):
    admin = make_user("boss", role="admin")
    tok = login(client, "boss")
    alice = make_user("alice")
    (tid,) = _add(models.Tournament(game_name="CS2", organizer_id=admin, status="pending"))
    h = auth_header(tok)
    me = {"player_name": "alice", "user_id": alice}
    team_a = client.post(f"/api/tournaments/{tid}/teams", json={"team_name": "A", "members": [me]}, headers=h)
    assert team_a.status_code == 201, team_a.text
    # Not in a second team, nor twice in one.
    assert client.post(f"/api/tournaments/{tid}/teams", json={"team_name": "B", "members": [me]}, headers=h).status_code == 400
    assert client.post(f"/api/tournaments/{tid}/teams", json={"team_name": "C", "members": [me, me]}, headers=h).status_code == 400
    team_b = client.post(f"/api/tournaments/{tid}/teams", json={"team_name": "B", "members": [{"player_name": "guest"}]}, headers=h)
    assert team_b.status_code == 201
    # Editing team B to add her: refused; editing team A with her still in it: fine.
    bid, aid = team_b.json()["id"], team_a.json()["id"]
    assert client.put(f"/api/tournaments/{tid}/teams/{bid}", json={"team_name": "B", "members": [me]}, headers=h).status_code == 400
    assert client.put(f"/api/tournaments/{tid}/teams/{aid}", json={"team_name": "A2", "members": [me]}, headers=h).status_code == 200


# ── Photos ────────────────────────────────────────────────────────────────────

def _photo(uid, event_id, at):
    return models.MediaItem(filename="f", original_name="f", file_type="image", mime_type="image/png", file_size=1,
                            url="/u/f", event_id=event_id, uploaded_by=uid, created_at=at)


def test_photos_count_at_their_lan_and_the_week_after():
    uid = make_user("snap")
    (eid,) = _add(models.LanEvent(title="LAN", start_date=date(2026, 10, 14), end_date=date(2026, 10, 18), created_by=uid))
    _add(
        _photo(uid, eid, datetime(2026, 10, 16, 12)),   # during: counts
        _photo(uid, eid, datetime(2026, 10, 25, 12)),   # 7 days after the end: counts
        _photo(uid, eid, datetime(2026, 10, 26, 12)),   # 8 days after: doesn't
        _photo(uid, eid, datetime(2026, 10, 1, 12)),    # before the LAN: doesn't
        _photo(uid, None, datetime(2026, 10, 16, 12)),  # no LAN: doesn't
    )
    assert _xp(uid) == {"photo": 4}


def test_an_upload_cant_name_a_lan_that_doesnt_exist(client):
    make_user("snap")
    tok = login(client, "snap")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    resp = client.post("/api/media/upload", data={"event_id": "999"}, files={"file": ("x.png", png, "image/png")},
                       headers=auth_header(tok))
    assert resp.status_code == 400 and resp.json()["detail"] == "Event not found"


# ── Chat ──────────────────────────────────────────────────────────────────────

def test_short_and_repeated_messages_dont_count():
    t = datetime(2026, 10, 16, 20)
    rows = [
        (1, t, "gg"),             # too short
        (1, t, "  ok  "),          # too short once trimmed
        (1, t, "bien joué"),       # counts
        (1, t, "Bien  joué"),      # same once normalized: doesn't
        (1, t, "trop fort"),       # counts
        (1, t, "bien joué"),       # not a repeat of the *previous* one: counts
        (2, t, "bien joué"),       # another author: counts
    ]
    assert counted_chat_messages(rows) == {1: 3, 2: 1}


def test_the_daily_cap_still_applies():
    t = datetime(2026, 10, 16, 20)
    rows = [(1, t, f"message {i}") for i in range(CHAT_MESSAGES_PER_DAY_CAP + 15)]
    assert counted_chat_messages(rows) == {1: CHAT_MESSAGES_PER_DAY_CAP}


# ── Two purchases a week ──────────────────────────────────────────────────────

def test_at_most_two_boosters_bought_a_week(client):
    admin = make_user("boss", role="admin")
    tok = login(client, "boss")
    buyer, other = make_user("buyer"), make_user("other")
    btok = login(client, "buyer")
    today = date.today()
    (eid,) = _add(models.LanEvent(title="LAN", start_date=today - timedelta(days=2), end_date=today + timedelta(days=1),
                                  created_by=admin))
    _add(*[models.EventRSVP(event_id=eid, user_id=u, status="in") for u in (buyer, other)])
    # 400 XP of photos (50 at 2 XP, at four LANs running now): four boosters' worth.
    now = datetime.utcnow()
    _add(*[_photo(buyer, eid, now) for _ in range(50)])
    for n in range(3):
        (more,) = _add(models.LanEvent(title=f"LAN {n}", start_date=today - timedelta(days=2),
                                       end_date=today + timedelta(days=1), created_by=admin))
        _add(*[_photo(buyer, more, now) for _ in range(50)], models.EventRSVP(event_id=more, user_id=other, status="in"))
    for key in ("cards_enabled", "xp_enabled"):
        _set(client, tok, key, "true")

    h = auth_header(btok)
    me = client.get("/api/cards/me", headers=h).json()
    assert (me["purchases_per_week"], me["purchases_left"], me["next_purchase_at"]) == (2, 2, None)
    first_buy = client.post("/api/cards/boosters/buy", headers=h)
    assert first_buy.status_code == 200, first_buy.text
    second = client.post("/api/cards/boosters/buy", headers=h).json()
    assert second["purchases_left"] == 0 and second["next_purchase_at"] is not None
    third = client.post("/api/cards/boosters/buy", headers=h)
    assert third.status_code == 400 and third.json()["detail"] == "Weekly purchase limit reached"

    # A week later the first slot is free again.
    s = database.SessionLocal()
    try:
        first = s.query(models.CardBooster).filter_by(owner_id=buyer, source_type="purchase").order_by(models.CardBooster.id).first()
        first.granted_at = datetime.utcnow() - timedelta(days=8)
        s.commit()
    finally:
        s.close()
    assert client.get("/api/cards/me", headers=h).json()["purchases_left"] == 1
    assert client.post("/api/cards/boosters/buy", headers=h).status_code == 200
