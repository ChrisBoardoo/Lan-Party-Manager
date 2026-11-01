"""Game time — /api/gametime: the desktop app's heartbeats, the sessions they
build, and what a LAN's page reads back (totals, members, heatmap, now playing)."""
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

import database
import models
import router_gametime
from conftest import register, login, auth_header, make_user


def _lan(user_ids, *, start=-1, end=1, status="in"):
    today = date.today()
    s = database.SessionLocal()
    try:
        event = models.LanEvent(
            title="LAN", start_date=today + timedelta(days=start), end_date=today + timedelta(days=end),
            created_by=1,
        )
        s.add(event)
        s.commit()
        for uid in user_ids:
            s.add(models.EventRSVP(event_id=event.id, user_id=uid, status=status))
        s.commit()
        return event.id
    finally:
        s.close()


@pytest.fixture
def crew(client):
    register(client, "founder", "founder@example.com")  # first user = admin (id 1)
    admin = login(client, "founder")
    client.put("/api/settings/gametime_enabled", json={"value": "true"},
               headers=auth_header(admin)).raise_for_status()
    ids, tokens = {}, {}
    for name in ("cross", "bob"):
        ids[name] = make_user(name)
        tokens[name] = login(client, name)
    event_id = _lan(ids.values())
    return SimpleNamespace(admin=admin, ids=ids, tokens=tokens, event_id=event_id)


def _beat(client, token, *games, visible=True):
    body = {"games": [{"key": k, "name": n} for k, n in games], "visible": visible}
    return client.post("/api/gametime/heartbeat", json=body, headers=auth_header(token))


def _sessions(**filters):
    s = database.SessionLocal()
    try:
        return s.query(models.GameSession).filter_by(**filters).order_by(models.GameSession.id).all()
    finally:
        s.close()


def _shift(minutes, **filters):
    """Move sessions back in time, as if their heartbeats had come earlier."""
    s = database.SessionLocal()
    try:
        for gs in s.query(models.GameSession).filter_by(**filters).all():
            gs.started_at -= timedelta(minutes=minutes)
            gs.last_seen_at -= timedelta(minutes=minutes)
        s.commit()
    finally:
        s.close()


def _stats(client, token, event_id):
    r = client.get(f"/api/gametime/events/{event_id}", headers=auth_header(token))
    r.raise_for_status()
    return r.json()


CS2 = ("exe:cs2", "Counter-Strike 2")
LOL = ("exe:lol", "League of Legends")


# ── The flag ─────────────────────────────────────────────────────────────────

def test_feature_is_off_by_default(client):
    register(client, "founder", "founder@example.com")
    make_user("cross")
    token = login(client, "cross")
    assert _beat(client, token, CS2).status_code == 404
    status = client.get("/api/gametime/status", headers=auth_header(token)).json()
    assert status == {"enabled": False, "lan_in_progress": False}


def test_an_admin_heartbeat_is_refused_with_the_feature_off(client):
    """Admins pass require_feature everywhere else; here they must not, or an
    admin's app would count with the feature turned off."""
    register(client, "founder", "founder@example.com")
    admin = login(client, "founder")
    assert _beat(client, admin, CS2).status_code == 404
    assert _sessions() == []


def test_status_during_and_outside_a_lan(client, crew):
    status = client.get("/api/gametime/status", headers=auth_header(crew.tokens["cross"])).json()
    assert status == {"enabled": True, "lan_in_progress": True}
    s = database.SessionLocal()
    try:
        s.query(models.EventRSVP).filter(models.EventRSVP.user_id == crew.ids["cross"]).update({"status": "out"})
        s.commit()
    finally:
        s.close()
    status = client.get("/api/gametime/status", headers=auth_header(crew.tokens["cross"])).json()
    assert status == {"enabled": True, "lan_in_progress": False}


def test_endpoints_need_a_login(client):
    assert client.get("/api/gametime/status").status_code == 401
    assert client.get("/api/gametime/catalog").status_code == 401
    assert client.post("/api/gametime/heartbeat", json={"games": []}).status_code == 401


# ── Heartbeats and sessions ──────────────────────────────────────────────────

def test_first_heartbeat_opens_a_session_under_the_running_lan(client, crew):
    r = _beat(client, crew.tokens["cross"], CS2)
    assert r.status_code == 200
    assert r.json() == {"counted": 1, "event_id": crew.event_id}
    [gs] = _sessions()
    assert (gs.user_id, gs.event_id, gs.game_key, gs.game_name) == (crew.ids["cross"], crew.event_id, *CS2)
    assert gs.started_at == gs.last_seen_at


def test_next_heartbeat_extends_the_session_on_the_server_clock(client, crew):
    _beat(client, crew.tokens["cross"], CS2)
    _shift(2)  # the first heartbeat came two minutes ago
    _beat(client, crew.tokens["cross"], CS2)
    [gs] = _sessions()
    played = gs.last_seen_at - gs.started_at
    assert timedelta(minutes=2) - timedelta(seconds=5) <= played <= timedelta(minutes=2, seconds=5)


def test_a_gap_longer_than_three_minutes_starts_a_new_session(client, crew):
    _beat(client, crew.tokens["cross"], CS2)
    _shift(10)
    _beat(client, crew.tokens["cross"], CS2)
    assert len(_sessions()) == 2


def test_heartbeats_closer_than_twenty_seconds_are_not_written(client, crew):
    _beat(client, crew.tokens["cross"], CS2)
    [before] = _sessions()
    _beat(client, crew.tokens["cross"], CS2)
    [after] = _sessions()
    assert after.last_seen_at == before.last_seen_at


def test_a_flood_of_heartbeats_adds_no_time(client, crew):
    for _ in range(20):
        _beat(client, crew.tokens["cross"], CS2).raise_for_status()
    [gs] = _sessions()
    assert gs.last_seen_at - gs.started_at < timedelta(seconds=5)


def test_two_games_at_once_are_two_sessions_and_duplicates_count_once(client, crew):
    r = _beat(client, crew.tokens["cross"], CS2, LOL, CS2)
    assert r.json()["counted"] == 2
    assert sorted(gs.game_key for gs in _sessions()) == ["exe:cs2", "exe:lol"]


def test_outside_a_lan_the_session_has_no_event(client, crew):
    s = database.SessionLocal()
    try:
        s.query(models.LanEvent).update({"start_date": date.today() + timedelta(days=5),
                                         "end_date": date.today() + timedelta(days=7)})
        s.commit()
    finally:
        s.close()
    assert _beat(client, crew.tokens["cross"], CS2).json() == {"counted": 1, "event_id": None}
    assert _stats(client, crew.tokens["cross"], crew.event_id)["total_seconds"] == 0


def test_a_lan_starting_mid_game_starts_a_new_session(client, crew):
    s = database.SessionLocal()
    try:
        s.query(models.EventRSVP).filter(models.EventRSVP.user_id == crew.ids["cross"]).update({"status": "out"})
        s.commit()
        _beat(client, crew.tokens["cross"], CS2)
        _shift(1)
        s.query(models.EventRSVP).filter(models.EventRSVP.user_id == crew.ids["cross"]).update({"status": "in"})
        s.commit()
    finally:
        s.close()
    _beat(client, crew.tokens["cross"], CS2)
    assert [gs.event_id for gs in _sessions()] == [None, crew.event_id]


@pytest.mark.parametrize("game", [
    {"key": "CS2", "name": "x"},            # upper case
    {"key": "exe cs2", "name": "x"},        # space
    {"key": "", "name": "x"},
    {"key": "a" * 65, "name": "x"},
    {"key": "exe:cs2", "name": ""},
    {"key": "exe:cs2", "name": "x" * 81},
])
def test_malformed_games_are_422(client, crew, game):
    r = client.post("/api/gametime/heartbeat", json={"games": [game]}, headers=auth_header(crew.tokens["cross"]))
    assert r.status_code == 422


def test_more_than_three_games_is_422(client, crew):
    games = [(f"exe:g{i}", f"Game {i}") for i in range(4)]
    assert _beat(client, crew.tokens["cross"], *games).status_code == 422


def test_names_lose_control_characters_and_extra_spaces(client, crew):
    _beat(client, crew.tokens["cross"], ("exe:x", "  Star\u0007   Citizen\n "))
    assert _sessions()[0].game_name == "Star Citizen"


def test_a_name_with_nothing_printable_is_not_counted(client, crew):
    assert _beat(client, crew.tokens["cross"], ("exe:x", "\u0007\u0008")).json()["counted"] == 0
    assert _sessions() == []


def test_a_game_links_to_the_catalog_but_never_creates_a_row(client, crew):
    s = database.SessionLocal()
    try:
        s.add(models.Game(name="Counter-Strike 2 / CS:S", is_custom=False))
        s.commit()
        cs_id = s.query(models.Game.id).filter_by(name="Counter-Strike 2 / CS:S").scalar()
    finally:
        s.close()
    _beat(client, crew.tokens["cross"], CS2, ("steam:999", "Some Indie Game"))
    by_key = {gs.game_key: gs for gs in _sessions()}
    assert by_key["exe:cs2"].game_id == cs_id  # through the served list's `catalog` name
    assert by_key["steam:999"].game_id is None
    s = database.SessionLocal()
    try:
        assert s.query(models.Game).count() == 1
    finally:
        s.close()


# ── What a LAN reads back ────────────────────────────────────────────────────

def _played(user_id, event_id, key, name, start, minutes, visible=True):
    s = database.SessionLocal()
    try:
        s.add(models.GameSession(
            user_id=user_id, event_id=event_id, game_key=key, game_name=name, visible=visible,
            started_at=start, last_seen_at=start + timedelta(minutes=minutes),
        ))
        s.commit()
    finally:
        s.close()


def test_event_totals_members_and_longest(client, crew):
    t0 = datetime(2026, 10, 15, 18, 0)
    _played(crew.ids["cross"], crew.event_id, *CS2, t0, 120)
    _played(crew.ids["cross"], crew.event_id, *CS2, t0 + timedelta(hours=3), 60)
    _played(crew.ids["cross"], crew.event_id, *LOL, t0, 30)
    _played(crew.ids["bob"], crew.event_id, *LOL, t0, 90)
    _played(crew.ids["bob"], None, *LOL, t0, 500)  # outside the LAN: not counted here

    out = _stats(client, crew.tokens["bob"], crew.event_id)
    assert out["total_seconds"] == (120 + 60 + 30 + 90) * 60
    assert [(g["game_name"], g["seconds"], g["players"]) for g in out["games"]] == [
        ("Counter-Strike 2", 180 * 60, 1),
        ("League of Legends", 120 * 60, 2),
    ]
    assert [(m["username"], m["seconds"]) for m in out["members"]] == [("cross", 210 * 60), ("bob", 90 * 60)]
    assert [g["game_name"] for g in out["members"][0]["games"]] == ["Counter-Strike 2", "League of Legends"]
    assert out["longest"] == {"user_id": crew.ids["cross"], "username": "cross",
                              "game_name": "Counter-Strike 2", "seconds": 120 * 60}


def test_heatmap_cuts_sessions_at_local_hours(client, crew):
    s = database.SessionLocal()
    try:
        s.add(models.AppSetting(key="app_timezone", value="Europe/Paris"))
        s.commit()
    finally:
        s.close()
    # 22:30 → 00:15 UTC on 15/10 = 00:30 → 02:15 in Paris (UTC+2) on 16/10.
    _played(crew.ids["cross"], crew.event_id, *CS2, datetime(2026, 10, 15, 22, 30), 105)
    out = _stats(client, crew.tokens["cross"], crew.event_id)
    assert [(c["day"], c["hour"], c["seconds"]) for c in out["heatmap"]] == [
        ("2026-10-16", 0, 30 * 60),
        ("2026-10-16", 1, 60 * 60),
        ("2026-10-16", 2, 15 * 60),
    ]
    assert sum(c["seconds"] for c in out["heatmap"]) == out["total_seconds"]


def test_now_playing_lists_recent_visible_sessions_only(client, crew):
    now = datetime.utcnow()
    _played(crew.ids["cross"], crew.event_id, *CS2, now - timedelta(minutes=30), 29)
    _played(crew.ids["bob"], crew.event_id, *LOL, now - timedelta(minutes=30), 29, visible=False)
    _played(crew.ids["bob"], crew.event_id, *CS2, now - timedelta(hours=3), 60)  # over
    out = _stats(client, crew.tokens["cross"], crew.event_id)
    assert [(p["username"], p["game_name"]) for p in out["now_playing"]] == [("cross", "Counter-Strike 2")]
    # Hidden from "now playing", still counted.
    assert out["total_seconds"] == (29 + 29 + 60) * 60


def test_hiding_takes_effect_on_the_next_heartbeat(client, crew):
    _beat(client, crew.tokens["cross"], CS2)
    _shift(1)
    _beat(client, crew.tokens["cross"], CS2, visible=False)
    assert _stats(client, crew.tokens["cross"], crew.event_id)["now_playing"] == []


def test_event_stats_are_404_with_the_feature_off_except_for_admins(client, crew):
    client.put("/api/settings/gametime_enabled", json={"value": "false"},
               headers=auth_header(crew.admin)).raise_for_status()
    r = client.get(f"/api/gametime/events/{crew.event_id}", headers=auth_header(crew.tokens["cross"]))
    assert r.status_code == 404
    assert client.get(f"/api/gametime/events/{crew.event_id}", headers=auth_header(crew.admin)).status_code == 200


def test_unknown_event_is_404(client, crew):
    r = client.get("/api/gametime/events/999", headers=auth_header(crew.tokens["cross"]))
    assert r.status_code == 404


def test_deleting_the_event_keeps_its_sessions_outside_any_lan(client, crew):
    _beat(client, crew.tokens["cross"], CS2)
    client.delete(f"/api/events/{crew.event_id}", headers=auth_header(crew.admin)).raise_for_status()
    [gs] = _sessions()
    assert gs.event_id is None


# ── The served list ──────────────────────────────────────────────────────────

def test_catalog_is_served_and_its_keys_pass_the_heartbeat_check(client, crew):
    out = client.get("/api/gametime/catalog", headers=auth_header(crew.tokens["cross"])).json()
    assert out["games"] and out["ignore_exes"] and out["ignore_steam_apps"]
    keys = [g["key"] for g in out["games"]]
    assert len(keys) == len(set(keys))
    exes = [e.lower() for g in out["games"] for e in g["exes"]]
    assert len(exes) == len(set(exes)), "one executable, one game"
    for g in out["games"]:
        assert _beat(client, crew.tokens["cross"], (g["key"], g["name"])).status_code == 200


def test_catalog_names_exist_in_the_seed():
    """A `catalog` name that isn't in the seed would silently never link."""
    with open(router_gametime.CATALOG_PATH.parent / "games_catalog_seed.json", encoding="utf-8") as f:
        seed = {g["name"] for g in json.load(f)}
    for g in router_gametime.load_catalog()["games"]:
        if g.get("catalog"):
            assert g["catalog"] in seed, g
