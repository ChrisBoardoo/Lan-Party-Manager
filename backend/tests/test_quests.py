"""Monthly contract — /api/quests (quests.py).

The rules pinned here:
- the feature needs XP on; while it's off the endpoint is a 404 for everyone,
  admins included, and nothing is drawn;
- a month's objectives are drawn once, among the available ones, and kept;
  last month's come back only to fill up;
- each objective counts the month's facts, in the instance timezone; meeting
  `required` of them pays xp.QUEST_XP, once per month;
- the announcement of the 1st goes out once.
"""
import json
from datetime import date, datetime, timedelta

import pytest

import database
import models
import quests
from conftest import auth_header, login, make_user
from xp import QUEST_XP, user_xp


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _add(*rows):
    s = database.SessionLocal()
    try:
        s.add_all(rows)
        s.commit()
        return [r.id if hasattr(r, "id") else None for r in rows]
    finally:
        s.close()


def _db(fn):
    s = database.SessionLocal()
    try:
        return fn(s)
    finally:
        s.close()


def _today():
    from event_utils import local_today

    return _db(local_today)


def _month():
    return quests.month_key(_today())


def _last_month():
    first, _ = quests.month_days(_month())
    return quests.month_key(first - timedelta(days=1))


def _start():
    """This month's first instant, as the naive UTC the app stores."""
    return _db(lambda s: quests.month_window(s, _month())[0])


def _set(client, token, key, value):
    resp = client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(token))
    assert resp.status_code == 200, resp.text


@pytest.fixture
def crew(client):
    ids = {n: make_user(n, role="admin" if n == "founder" else "user") for n in ("founder", "alice", "bob")}
    tok = {n: login(client, n) for n in ids}
    _set(client, tok["founder"], "xp_enabled", "true")
    _set(client, tok["founder"], "quests_enabled", "true")
    # Off unless a test needs it: with no LAN it's never available anyway, but
    # the tests that create a LAN would otherwise get a chat objective too.
    _set(client, tok["founder"], "craving_chat_enabled", "false")
    return {"ids": ids, "tok": tok}


class _InOrder:
    """Stands in for quests._rng: shuffles nothing."""

    def shuffle(self, seq):
        pass


def _contract(*objs, month=None, required=2):
    """Store a month's contract as given, skipping the draw."""
    _add(models.MonthlyContract(month=month or _month(), objectives=json.dumps(list(objs)), required=required))


def _current(client, crew, who):
    resp = client.get("/api/quests/current", headers=auth_header(crew["tok"][who]))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _quest_xp(uid):
    lines = {line.code: line for line in _db(lambda s: user_xp(s, uid)).breakdown}
    line = lines.get("quest")
    return (line.count, line.xp) if line else (0, 0)


def _lan(crew, start_in_days, length=4):
    start = _today() + timedelta(days=start_in_days)
    (eid,) = _add(models.LanEvent(title="LAN #3", start_date=start, end_date=start + timedelta(days=length),
                                  created_by=crew["ids"]["founder"]))
    return eid


def _block(crew, event_id):
    (bid,) = _add(models.ScheduleBlock(event_id=event_id, game="CS2", status="proposed",
                                       created_by=crew["ids"]["founder"]))
    return bid


def _score(uid, at):
    return models.MiniGameScore(user_id=uid, game="neon-survivor", mode="solo", score=100, created_at=at)


# ── Months ────────────────────────────────────────────────────────────────────

def test_months_wrap_the_year():
    assert quests.month_days("2026-12") == (date(2026, 12, 1), date(2027, 1, 1))
    assert quests.month_days("2027-02") == (date(2027, 2, 1), date(2027, 3, 1))
    assert quests.month_key(date(2027, 3, 17)) == "2027-03"


# ── Gate ──────────────────────────────────────────────────────────────────────

def test_off_for_everyone_without_xp_or_while_off(client):
    make_user("founder", role="admin")
    make_user("alice")
    tok = {n: login(client, n) for n in ("founder", "alice")}
    _set(client, tok["founder"], "quests_enabled", "true")  # XP still off
    for who in tok.values():
        assert client.get("/api/quests/current", headers=auth_header(who)).status_code == 404
    assert client.get("/api/settings/public-config", headers=auth_header(tok["alice"])).json()["quests_enabled"] is False

    _set(client, tok["founder"], "xp_enabled", "true")
    _set(client, tok["founder"], "quests_enabled", "false")
    assert client.get("/api/quests/current", headers=auth_header(tok["founder"])).status_code == 404
    assert _db(lambda s: s.query(models.MonthlyContract).count()) == 0  # nothing drawn while off

    _set(client, tok["founder"], "quests_enabled", "true")
    assert client.get("/api/quests/current", headers=auth_header(tok["alice"])).status_code == 200
    assert client.get("/api/settings/public-config", headers=auth_header(tok["alice"])).json()["quests_enabled"] is True


# ── The draw ──────────────────────────────────────────────────────────────────

def test_drawn_once_among_the_available_and_kept(client, crew, monkeypatch):
    monkeypatch.setattr(quests, "_rng", _InOrder())
    assert _current(client, crew, "alice")["objectives"] == []  # nothing available: no contract
    s = _db(lambda s: s.get(models.MonthlyContract, _month()))
    assert s.required == 0 and _current(client, crew, "alice")["done"] is False

    # A month with nothing drawn stays empty, even once something is available.
    _set(client, crew["tok"]["founder"], "minigames_enabled", "true")
    assert _current(client, crew, "alice")["objectives"] == []


def test_fewer_available_means_fewer_required(client, crew, monkeypatch):
    monkeypatch.setattr(quests, "_rng", _InOrder())
    _set(client, crew["tok"]["founder"], "minigames_enabled", "true")
    body = _current(client, crew, "alice")
    assert [o["code"] for o in body["objectives"]] == ["minigame"] and body["required"] == 1

    _set(client, crew["tok"]["founder"], "lol_stats_enabled", "true")  # too late for this month
    assert [o["code"] for o in _current(client, crew, "bob")["objectives"]] == ["minigame"]


def test_last_months_objectives_come_back_only_to_fill_up(client, crew, monkeypatch):
    monkeypatch.setattr(quests, "_rng", _InOrder())
    for key in ("minigames_enabled", "lol_stats_enabled", "planning_enabled"):
        _set(client, crew["tok"]["founder"], key, "true")
    lan = _lan(crew, 10)
    _block(crew, lan)
    _contract({"code": "lol_squad", "target": 5}, {"code": "minigame", "target": 3},
              {"code": "planning_vote", "target": 1}, month=_last_month())

    body = _current(client, crew, "alice")
    # Fresh first (rsvp_next), then last month's in catalogue order.
    assert [o["code"] for o in body["objectives"]] == ["rsvp_next", "lol_squad", "minigame"]
    assert body["objectives"][0]["event_title"] == "LAN #3" and body["required"] == 2


def test_the_next_lans_rsvp_is_asked_once(client, crew, monkeypatch):
    monkeypatch.setattr(quests, "_rng", _InOrder())
    lan = _lan(crew, 10)
    _contract({"code": "rsvp_next", "target": 1, "event_id": lan}, month=_last_month(), required=1)
    assert _current(client, crew, "alice")["objectives"] == []


def test_chat_is_asked_only_with_a_room_open_long_enough(client, crew, monkeypatch):
    monkeypatch.setattr(quests, "_rng", _InOrder())
    _set(client, crew["tok"]["founder"], "craving_chat_enabled", "true")
    _set(client, crew["tok"]["founder"], "craving_chat_always_open", "true")
    _lan(crew, 10)  # always open: its room is open from now on
    assert "chat_days" in [o["code"] for o in _current(client, crew, "alice")["objectives"]]


# ── Progress and XP ───────────────────────────────────────────────────────────

def test_two_of_three_pays_once_a_month(client, crew):
    alice, bob = crew["ids"]["alice"], crew["ids"]["bob"]
    block = _block(crew, _lan(crew, 10))
    start = _start()
    _contract({"code": "minigame", "target": 3}, {"code": "planning_vote", "target": 1},
              {"code": "lol_squad", "target": 5})
    _contract({"code": "minigame", "target": 3}, month=_last_month(), required=1)
    _add(
        *[_score(alice, start + timedelta(hours=h)) for h in (1, 2, 3)],
        models.BlockVote(block_id=block, user_id=alice, slot_start=datetime(2027, 3, 17, 20), created_at=start),
        *[_score(alice, start - timedelta(hours=h)) for h in (1, 2, 3)],  # last month: met too
        *[_score(bob, start + timedelta(hours=h)) for h in (1, 2, 3)],  # one objective out of two
        *[_score(bob, start - timedelta(days=2, hours=h)) for h in (1, 2)],  # last month: two runs only
    )

    body = _current(client, crew, "alice")
    assert [(o["code"], o["progress"], o["done"]) for o in body["objectives"]] == [
        ("minigame", 3, True), ("planning_vote", 1, True), ("lol_squad", 0, False),
    ]
    assert body["done"] is True and body["xp"] == QUEST_XP
    assert _quest_xp(alice) == (2, 2 * QUEST_XP)  # this month and last month

    assert _current(client, crew, "bob")["done"] is False
    assert _quest_xp(bob) == (0, 0)


def test_quest_xp_stops_with_the_feature(client, crew):
    alice = crew["ids"]["alice"]
    _contract({"code": "minigame", "target": 1}, required=1)
    _add(_score(alice, _start() + timedelta(hours=1)))
    assert _quest_xp(alice) == (1, QUEST_XP)
    _set(client, crew["tok"]["founder"], "quests_enabled", "false")
    assert _quest_xp(alice) == (0, 0)


def test_lol_squad_counts_games_with_another_member(client, crew):
    alice, bob = crew["ids"]["alice"], crew["ids"]["bob"]
    _contract({"code": "lol_squad", "target": 5}, required=1)
    at = _start() + timedelta(hours=1)
    m1, m2, m3, old = _add(*[models.LolMatch(riot_game_id=f"EUW1_{n}", created_at=at) for n in (1, 2, 3)],
                           models.LolMatch(riot_game_id="EUW1_0", created_at=at - timedelta(days=2)))

    def player(match, uid, name):
        return models.LolMatchPlayer(match_id=match, user_id=uid, riot_id=f"{name}#EUW", riot_id_key=f"{name}#euw")

    _add(
        player(m1, alice, "a"), player(m1, bob, "b"),  # crew together
        player(m2, alice, "a"), player(m2, None, "stranger"),  # alice with no one from the crew
        player(m3, alice, "a"), player(m3, bob, "b"),
        player(old, alice, "a"), player(old, bob, "b"),  # last month
    )
    assert _current(client, crew, "alice")["objectives"][0]["progress"] == 2
    assert _current(client, crew, "bob")["objectives"][0]["progress"] == 2


def test_chat_days_are_local_days_with_a_message_that_counts(client, crew):
    alice = crew["ids"]["alice"]
    _add(models.AppSetting(key="app_timezone", value="Europe/Paris"))
    (eid,) = _add(models.LanEvent(title="LAN", start_date=_today(), end_date=_today(),
                                  created_by=crew["ids"]["founder"]))
    _contract({"code": "chat_days", "target": 5}, required=1)
    start = _start()  # local midnight on the 1st: 22:00 or 23:00 UTC the day before

    def msg(hours, text):
        return models.ChatMessage(event_id=eid, user_id=alice, content=text, created_at=start + timedelta(hours=hours))

    _add(
        msg(-0.5, "le mois dernier"),  # before the month
        msg(23.5, "un message"),  # local day 1, late evening
        msg(24.5, "un autre message"),  # local day 2 — the same UTC day as the one above
        msg(48.5, "un autre message"),  # day 3: the same message again, doesn't count
        msg(49, "ok"),  # day 3: too short
    )
    assert _current(client, crew, "alice")["objectives"][0]["progress"] == 2


def test_rsvp_next_counts_an_answer_given_any_time(client, crew):
    lan = _lan(crew, 10)
    _contract({"code": "rsvp_next", "target": 1, "event_id": lan}, required=1)
    _add(models.EventRSVP(event_id=lan, user_id=crew["ids"]["alice"], status="out"))
    assert _current(client, crew, "alice")["done"] is True
    assert _current(client, crew, "bob")["done"] is False


# ── The announcement ──────────────────────────────────────────────────────────

def test_the_announcement_goes_out_once(client, crew, monkeypatch):
    sent = []
    monkeypatch.setattr(quests, "send_discord_message", lambda db, content: sent.append(content) or True)
    quests.announce_monthly_contract()
    assert sent == []  # nothing available: no contract to announce

    _db(lambda s: (s.query(models.MonthlyContract).delete(), s.commit()))
    _set(client, crew["tok"]["founder"], "minigames_enabled", "true")
    quests.announce_monthly_contract()
    quests.announce_monthly_contract()
    assert len(sent) == 1
    assert "Contrat du mois" in sent[0] and "mini-jeu" in sent[0] and "1 objectif sur 1" in sent[0]


def test_no_announcement_while_off(client, crew, monkeypatch):
    sent = []
    monkeypatch.setattr(quests, "send_discord_message", lambda db, content: sent.append(content) or True)
    _set(client, crew["tok"]["founder"], "minigames_enabled", "true")
    _set(client, crew["tok"]["founder"], "quests_enabled", "false")
    quests.announce_monthly_contract()
    assert sent == [] and _db(lambda s: s.query(models.MonthlyContract).count()) == 0
