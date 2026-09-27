"""League of Legends stats — /api/lol, plus its hooks elsewhere (the Riot
ID back-fill in PUT /users/{id}, Arena's per-game overview, event deletion)."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import database
import models
import router_lol
from conftest import register, login, auth_header, make_user
from lol_payloads import capture, player


def _lan(user_ids, *, start=-1, end=1, status="in"):
    """An event running from today+start to today+end, with these RSVPs."""
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


def _set_riot_id(client, token, user_id, riot_id):
    client.put(f"/api/users/{user_id}", json={"riot_id": riot_id}, headers=auth_header(token)).raise_for_status()


@pytest.fixture
def crew(client):
    register(client, "founder", "founder@example.com")  # first user = admin (id 1)
    admin = login(client, "founder")
    client.put("/api/settings/lol_stats_enabled", json={"value": "true"},
               headers=auth_header(admin)).raise_for_status()
    ids, tokens = {}, {}
    for name in ("cross", "bob", "carol"):
        ids[name] = make_user(name)
        tokens[name] = login(client, name)
    _set_riot_id(client, tokens["cross"], ids["cross"], "Cross#EUW")
    _set_riot_id(client, tokens["bob"], ids["bob"], "Bob#EUW")
    event_id = _lan(ids.values())
    return SimpleNamespace(admin=admin, ids=ids, tokens=tokens, event_id=event_id)


def _post(client, token, body):
    return client.post("/api/lol/matches", json=body, headers=auth_header(token))


def _stats(client, token, **params):
    r = client.get("/api/lol/stats", params=params, headers=auth_header(token))
    r.raise_for_status()
    return r.json()


def _custom_5v5(game_id=9001):
    return capture(
        game_id,
        [player("Cross", kills=10, deaths=2, assists=8, damage=32000, champion="Jinx"),
         player("Stranger", kills=3, deaths=3, assists=3, damage=10000)],
        [player("Bob", kills=2, deaths=7, assists=4, damage=15000),
         player("Carol", kills=5, deaths=5, assists=5, damage=20000)],
        is_custom=True,
    )


# ── Capture ──────────────────────────────────────────────────────────────────

def test_feature_is_off_by_default(client):
    register(client, "founder", "founder@example.com")
    make_user("cross")
    token = login(client, "cross")
    assert _post(client, token, _custom_5v5()).status_code == 404
    assert client.get("/api/lol/stats", headers=auth_header(token)).status_code == 404


def test_public_config_reports_the_flag(client, crew):
    config = client.get("/api/settings/public-config", headers=auth_header(crew.tokens["bob"])).json()
    assert config["lol_stats_enabled"] is True


def test_capture_stores_the_game(client, crew):
    r = _post(client, crew.tokens["cross"], _custom_5v5())
    assert r.status_code == 201
    assert r.json()["created"] is True

    stats = _stats(client, crew.tokens["bob"], event_id=crew.event_id)
    assert stats["matches"] == 1
    by_name = {p["username"]: p for p in stats["players"]}
    assert set(by_name) == {"cross", "bob"}  # carol hasn't set her Riot ID yet
    cross = by_name["cross"]
    assert (cross["games"], cross["wins"], cross["kills"], cross["deaths"], cross["assists"]) == (1, 1, 10, 2, 8)
    assert cross["kda"] == 9.0
    assert cross["avg_damage"] == 32000
    assert by_name["bob"]["wins"] == 0


def test_the_same_game_sent_by_every_player_is_kept_once(client, crew):
    first = _post(client, crew.tokens["cross"], _custom_5v5())
    again = _post(client, crew.tokens["bob"], _custom_5v5())
    assert again.status_code == 200
    assert again.json() == {"match_id": first.json()["match_id"], "created": False}
    assert _stats(client, crew.tokens["bob"])["matches"] == 1


def test_simultaneous_sends_do_not_fail(client, crew, monkeypatch):
    """Another app's insert landing between our duplicate check and our own
    insert must end as "already have it", not a 500."""
    real = router_lol._lan_in_progress

    def racing(db, user):
        event = real(db, user)
        s = database.SessionLocal()
        try:
            s.add(models.LolMatch(event_id=event.id, riot_game_id="9001", submitted_by=crew.ids["bob"]))
            s.commit()
        finally:
            s.close()
        return event

    monkeypatch.setattr(router_lol, "_lan_in_progress", racing)
    r = _post(client, crew.tokens["cross"], _custom_5v5(9001))
    assert r.status_code == 200
    assert r.json()["created"] is False


def test_sender_needs_a_riot_id(client, crew):
    r = _post(client, crew.tokens["carol"], _custom_5v5())
    assert r.status_code == 400


def test_sender_must_have_played_the_game(client, crew):
    body = capture(1, [player("Someone")], [player("Else")])
    assert _post(client, crew.tokens["cross"], body).status_code == 403


def _matches(client, crew):
    return client.get("/api/lol/matches", headers=auth_header(crew.admin)).json()


def test_a_game_outside_a_lan_counts_globally_only(client, crew):
    s = database.SessionLocal()
    try:
        s.query(models.LanEvent).filter(models.LanEvent.id == crew.event_id).update(
            {"start_date": date.today() - timedelta(days=10), "end_date": date.today() - timedelta(days=8)})
        s.commit()
    finally:
        s.close()
    assert _post(client, crew.tokens["cross"], _custom_5v5()).status_code == 201

    assert [m["event_id"] for m in _matches(client, crew)] == [None]
    assert _stats(client, crew.tokens["bob"])["matches"] == 1
    assert _stats(client, crew.tokens["bob"], event_id=crew.event_id)["matches"] == 0


def test_a_lan_the_sender_is_not_attending_does_not_claim_the_game(client, crew):
    s = database.SessionLocal()
    try:
        s.query(models.EventRSVP).filter(models.EventRSVP.user_id == crew.ids["cross"]).update({"status": "out"})
        s.commit()
    finally:
        s.close()
    assert _post(client, crew.tokens["cross"], _custom_5v5()).status_code == 201
    assert [m["event_id"] for m in _matches(client, crew)] == [None]


# ── What the desktop app asks before watching the League client ──────────────

def _status(client, token):
    r = client.get("/api/lol/capture-status", headers=auth_header(token))
    r.raise_for_status()
    return r.json()


def test_capture_status_during_a_lan(client, crew):
    assert _status(client, crew.tokens["cross"]) == {"enabled": True, "lan_in_progress": True}


def test_capture_status_outside_a_lan(client, crew):
    s = database.SessionLocal()
    try:
        s.query(models.EventRSVP).filter(models.EventRSVP.user_id == crew.ids["cross"]).update({"status": "out"})
        s.commit()
    finally:
        s.close()
    assert _status(client, crew.tokens["cross"]) == {"enabled": True, "lan_in_progress": False}


def test_capture_status_reports_the_flag_even_to_an_admin(client, crew):
    """Admins bypass require_feature everywhere else — here they must not, or
    an admin's desktop app would capture with the feature turned off."""
    client.put("/api/settings/lol_stats_enabled", json={"value": "false"},
               headers=auth_header(crew.admin)).raise_for_status()
    assert _status(client, crew.admin)["enabled"] is False
    assert _status(client, crew.tokens["cross"])["enabled"] is False


def test_capture_status_needs_a_login(client, crew):
    assert client.get("/api/lol/capture-status").status_code == 401


def test_a_resend_after_the_lan_still_answers_already_have_it(client, crew):
    _post(client, crew.tokens["cross"], _custom_5v5()).raise_for_status()
    s = database.SessionLocal()
    try:
        s.query(models.LanEvent).update({"end_date": date.today() - timedelta(days=1),
                                         "start_date": date.today() - timedelta(days=3)})
        s.commit()
    finally:
        s.close()
    r = _post(client, crew.tokens["bob"], _custom_5v5())
    assert r.status_code == 200 and r.json()["created"] is False


def test_unreadable_block_is_422(client, crew):
    assert _post(client, crew.tokens["cross"], {"eog": {"hello": "world"}}).status_code == 422


def test_capture_lands_on_the_running_lan(client, crew):
    _lan([crew.ids["cross"]], start=-30, end=-28)  # an older LAN
    match_id = _post(client, crew.tokens["cross"], _custom_5v5()).json()["match_id"]
    matches = client.get("/api/lol/matches", headers=auth_header(crew.admin)).json()
    assert [(m["id"], m["event_id"]) for m in matches] == [(match_id, crew.event_id)]


# ── Who gets stored ──────────────────────────────────────────────────────────

def test_custom_game_keeps_unclaimed_players_for_later(client, crew):
    _post(client, crew.tokens["cross"], _custom_5v5()).raise_for_status()
    _set_riot_id(client, crew.tokens["carol"], crew.ids["carol"], "carol#euw")

    by_name = {p["username"]: p for p in _stats(client, crew.tokens["carol"])["players"]}
    assert by_name["carol"]["kills"] == 5


def test_matchmade_game_never_stores_strangers(client, crew):
    body = capture(
        9100, [player("Cross", kills=4), player("Stranger", kills=12)], [player("Carol", kills=6)],
        is_custom=False, game_mode="ARAM",
    )
    _post(client, crew.tokens["cross"], body).raise_for_status()
    match = client.get("/api/lol/matches", headers=auth_header(crew.admin)).json()[0]
    assert [p["riot_id"] for p in match["players"]] == ["Cross#EUW"]
    assert match["category"] == "aram"

    # Carol wasn't a member yet when it was captured: nothing to back-fill.
    _set_riot_id(client, crew.tokens["carol"], crew.ids["carol"], "Carol#EUW")
    assert {p["username"] for p in _stats(client, crew.tokens["carol"])["players"]} == {"cross"}


def test_an_already_claimed_line_is_not_taken_over(client, crew):
    """Bob's games stay Bob's even if another member later claims his old Riot ID."""
    _post(client, crew.tokens["cross"], _custom_5v5()).raise_for_status()
    _set_riot_id(client, crew.tokens["bob"], crew.ids["bob"], "BobNewName#EUW")
    _set_riot_id(client, crew.tokens["carol"], crew.ids["carol"], "Bob#EUW")
    by_name = {p["username"]: p for p in _stats(client, crew.tokens["carol"])["players"]}
    assert by_name["bob"]["games"] == 1
    assert "carol" not in by_name


# ── Stats ────────────────────────────────────────────────────────────────────

def test_category_filter(client, crew):
    _post(client, crew.tokens["cross"], _custom_5v5(1)).raise_for_status()
    aram = capture(2, [player("Cross", kills=20)], [player("Bob")], is_custom=False, game_mode="ARAM")
    _post(client, crew.tokens["cross"], aram).raise_for_status()

    assert _stats(client, crew.tokens["bob"])["matches"] == 2
    assert _stats(client, crew.tokens["bob"], category="custom")["matches"] == 1
    aram_stats = _stats(client, crew.tokens["bob"], category="aram")
    assert aram_stats["matches"] == 1
    assert {p["username"]: p["kills"] for p in aram_stats["players"]}["cross"] == 20
    assert _stats(client, crew.tokens["bob"], category="matchmade")["matches"] == 0
    assert client.get("/api/lol/stats", params={"category": "urf"},
                      headers=auth_header(crew.tokens["bob"])).status_code == 422


def test_event_filter(client, crew):
    _post(client, crew.tokens["cross"], _custom_5v5()).raise_for_status()
    other_event = _lan([], start=-60, end=-58)
    assert _stats(client, crew.tokens["bob"], event_id=other_event)["matches"] == 0
    assert _stats(client, crew.tokens["bob"], event_id=crew.event_id)["matches"] == 1


def test_records(client, crew):
    _post(client, crew.tokens["cross"], _custom_5v5()).raise_for_status()
    records = {r["kind"]: r for r in _stats(client, crew.tokens["bob"])["records"]}
    assert (records["kills"]["username"], records["kills"]["value"], records["kills"]["champion"]) == ("cross", 10, "Jinx")
    assert records["damage"]["value"] == 32000
    assert records["assists"]["username"] == "cross"  # 8, the Stranger's line never counts


def test_stats_report_the_catalog_game(client, crew):
    _post(client, crew.tokens["cross"], _custom_5v5()).raise_for_status()
    stats = _stats(client, crew.tokens["bob"])
    games = client.get("/api/tournaments/games", headers=auth_header(crew.tokens["bob"])).json()
    lol = next(g for g in games if g["name"] == "League of Legends")
    assert stats["game_id"] == lol["id"]


# ── Match history & clean-up ─────────────────────────────────────────────────

def test_match_list(client, crew):
    _post(client, crew.tokens["cross"], _custom_5v5()).raise_for_status()
    (match,) = client.get("/api/lol/matches", headers=auth_header(crew.tokens["bob"])).json()
    assert match["category"] == "custom"
    assert match["submitted_by"] == "cross"
    assert match["duration_s"] == 1800
    names = {p["riot_id"]: p["username"] for p in match["players"]}
    assert names == {"Cross#EUW": "cross", "Stranger#EUW": None, "Bob#EUW": "bob", "Carol#EUW": None}


def test_admin_deletes_a_game(client, crew):
    match_id = _post(client, crew.tokens["cross"], _custom_5v5()).json()["match_id"]
    assert client.delete(f"/api/lol/matches/{match_id}", headers=auth_header(crew.tokens["cross"])).status_code == 403
    assert client.delete(f"/api/lol/matches/{match_id}", headers=auth_header(crew.admin)).status_code == 200
    assert _stats(client, crew.tokens["bob"])["matches"] == 0
    assert client.delete(f"/api/lol/matches/{match_id}", headers=auth_header(crew.admin)).status_code == 404


def test_deleting_the_event_keeps_its_games_in_the_global_stats(client, crew):
    _post(client, crew.tokens["cross"], _custom_5v5()).raise_for_status()
    client.delete(f"/api/events/{crew.event_id}", headers=auth_header(crew.admin)).raise_for_status()
    assert _stats(client, crew.tokens["bob"])["matches"] == 1
    assert [m["event_id"] for m in _matches(client, crew)] == [None]
    s = database.SessionLocal()
    try:
        assert s.query(models.LolMatchPlayer).count() == 4  # a custom game keeps all four lines
    finally:
        s.close()


# ── Arena > Stats by game stays tournaments-only ─────────────────────────────

def test_captures_stay_out_of_the_arena_overview(client, crew):
    """Captured games have their own tab on the Games page (/api/lol/stats);
    Arena's per-game overview only counts tournament matches."""
    _post(client, crew.tokens["cross"], _custom_5v5(1)).raise_for_status()
    _post(client, crew.tokens["cross"], _custom_5v5(2)).raise_for_status()

    overview = client.get("/api/tournaments/stats/games", headers=auth_header(crew.tokens["bob"]))
    assert overview.json() == []
    assert _stats(client, crew.tokens["bob"])["matches"] == 2


def test_remakes_are_not_counted(client, crew):
    body = _custom_5v5()
    body["eog"]["gameEndedInEarlySurrender"] = True
    r = _post(client, crew.tokens["cross"], body)
    assert r.status_code == 422
    assert _stats(client, crew.tokens["bob"])["matches"] == 0
