"""Per-game player stats — the pure counting rules, then the API around them.

The pure half feeds duck-typed namespaces, like test_tournament_stats. The API
half checks what the pure half can't: tournaments getting linked to the shared
catalog on create/update, the route order (/games and /stats/* must not be
swallowed by /{tid}), the event filter, and admin-only access to "unlinked".
"""
from types import SimpleNamespace

import database
import models
from conftest import auth_header, login, make_user
from tournament_stats import leaderboard_key, match_result, player_game_records


# ── Pure: counting rules ──────────────────────────────────────────────────────

def _team(tid, members=()):
    return SimpleNamespace(
        id=tid, team_name=f"T{tid}", color=None, seed=None,
        members=[SimpleNamespace(player_name=f"p{u}" if u else "guest", user_id=u) for u in members],
    )


def _match(a, b, score_a, score_b, *, status="completed", winner_id=None, rn=1):
    return SimpleNamespace(
        team_a_id=a, team_b_id=b, score_a=score_a, score_b=score_b, status=status,
        winner_id=winner_id, round_number=rn, played_at=None,
    )


def _t(game_id, teams, matches, *, bracket="round_robin", status="completed"):
    return SimpleNamespace(game_id=game_id, bracket_type=bracket, status=status, teams=teams, matches=matches)


def _by_user(records, game_id=1):
    return {r.user_id: r for r in records if r.game_id == game_id}


def test_team_result_credits_every_linked_member():
    t = _t(1, [_team(1, [10, 11]), _team(2, [20, 21])], [_match(1, 2, 3, 1)])
    recs = _by_user(player_game_records([t]))
    assert (recs[10].wins, recs[11].wins, recs[20].losses, recs[21].losses) == (1, 1, 1, 1)
    assert all(r.played == 1 for r in recs.values())


def test_unlinked_players_are_ignored():
    t = _t(1, [_team(1, [10, None]), _team(2, [None])], [_match(1, 2, 1, 0)])
    assert set(_by_user(player_game_records([t]))) == {10}


def test_byes_and_pending_matches_do_not_count():
    t = _t(1, [_team(1, [10]), _team(2, [20])], [
        _match(1, None, 0, 0),                    # bye: no opponent
        _match(1, 2, 0, 0, status="pending"),     # not played yet
        _match(1, 2, 2, 1),
    ])
    recs = _by_user(player_game_records([t]))
    assert recs[10].played == 1 and recs[20].played == 1


def test_draws_are_counted():
    t = _t(1, [_team(1, [10]), _team(2, [20])], [_match(1, 2, 2, 2)])
    recs = _by_user(player_game_records([t]))
    assert (recs[10].draws, recs[10].wins, recs[10].losses) == (1, 0, 0)


def test_bracket_winner_click_beats_a_0_0_score():
    # The organizer clicked the winner and never typed a score: not a draw.
    m = _match(1, 2, 0, 0, winner_id=2)
    assert match_result(m) == (2, 1)
    t = _t(1, [_team(1, [10]), _team(2, [20])], [m], bracket="single_elimination")
    recs = _by_user(player_game_records([t]))
    assert recs[20].wins == 1 and recs[10].losses == 1 and recs[10].draws == 0


def test_titles_need_a_completed_tournament_but_matches_do_not():
    teams = [_team(1, [10]), _team(2, [20])]
    unfinished = _t(1, teams, [_match(1, 2, 1, 0)], status="pending")
    recs = _by_user(player_game_records([unfinished]))
    assert recs[10].wins == 1 and recs[10].titles == 0

    finished = _t(1, teams, [_match(1, 2, 1, 0)], status="completed")
    assert _by_user(player_game_records([finished]))[10].titles == 1


def test_tournaments_without_a_game_are_skipped_and_games_stay_separate():
    teams = [_team(1, [10]), _team(2, [20])]
    recs = player_game_records([
        _t(None, teams, [_match(1, 2, 1, 0)]),
        _t(1, teams, [_match(1, 2, 1, 0)]),
        _t(2, teams, [_match(1, 2, 0, 1)]),
    ])
    assert _by_user(recs, 1)[10].wins == 1
    assert _by_user(recs, 2)[10].losses == 1
    assert {r.game_id for r in recs} == {1, 2}


def test_tournaments_played_counts_participation_even_without_matches():
    t = _t(1, [_team(1, [10]), _team(2, [20])], [], status="pending")
    assert _by_user(player_game_records([t]))[10].tournaments == 1


def test_win_rate_needs_three_matches():
    teams = [_team(1, [10]), _team(2, [20])]
    two = _by_user(player_game_records([_t(1, teams, [_match(1, 2, 1, 0), _match(1, 2, 1, 0)])]))
    assert two[10].win_rate is None
    three = _by_user(player_game_records([_t(1, teams, [_match(1, 2, 1, 0)] * 2 + [_match(1, 2, 0, 1)])]))
    assert round(three[10].win_rate, 3) == 0.667


def test_leaderboard_orders_by_wins_then_rate():
    teams = [_team(1, [10]), _team(2, [20]), _team(3, [30])]
    t = _t(1, teams, [
        _match(1, 2, 1, 0), _match(1, 3, 1, 0), _match(1, 2, 0, 1),   # 10: 2W 1L
        _match(2, 3, 1, 0), _match(2, 3, 1, 0),                       # 20: 3W 1L
    ])
    order = [r.user_id for r in sorted(player_game_records([t]), key=leaderboard_key)]
    assert order[:2] == [20, 10]


# ── API ───────────────────────────────────────────────────────────────────────

def _admin(client):
    make_user("founder", role="admin")
    return login(client, "founder")


def _game(name):
    s = database.SessionLocal()
    try:
        g = models.Game(name=name, genre="MOBA", default_max_players=10)
        s.add(g)
        s.commit()
        s.refresh(g)
        return g.id
    finally:
        s.close()


def _create(client, token, **body):
    body.setdefault("bracket_type", "round_robin")
    resp = client.post("/api/tournaments/", json=body, headers=auth_header(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _play(client, token, tid, users_a, users_b, score_a, score_b):
    """Two one-team-each sides, generate, then complete the single match."""
    for name, users in (("A", users_a), ("B", users_b)):
        client.post(
            f"/api/tournaments/{tid}/teams",
            json={"team_name": name, "members": [{"player_name": f"u{u}", "user_id": u} for u in users]},
            headers=auth_header(token),
        ).raise_for_status()
    client.post(f"/api/tournaments/{tid}/generate-brackets", headers=auth_header(token)).raise_for_status()
    match = client.get(f"/api/tournaments/{tid}", headers=auth_header(token)).json()["matches"][0]
    client.put(
        f"/api/tournaments/{tid}/matches/{match['id']}",
        json={"score_a": score_a, "score_b": score_b, "status": "completed"},
        headers=auth_header(token),
    ).raise_for_status()


def test_create_links_a_catalog_game_by_id(client):
    admin = _admin(client)
    lol = _game("League of Legends")
    t = _create(client, admin, game_name="whatever", game_id=lol)
    assert t["game_id"] == lol and t["game_name"] == "League of Legends"


def test_create_resolves_a_typed_name_case_insensitively(client):
    admin = _admin(client)
    lol = _game("League of Legends")
    t = _create(client, admin, game_name="  league of LEGENDS ")
    assert t["game_id"] == lol and t["game_name"] == "League of Legends"


def test_create_adds_an_unknown_game_as_custom(client):
    admin = _admin(client)
    t = _create(client, admin, game_name="Bomberman 64")
    s = database.SessionLocal()
    try:
        g = s.query(models.Game).filter(models.Game.id == t["game_id"]).one()
        assert g.name == "Bomberman 64" and g.is_custom
    finally:
        s.close()


def test_create_rejects_an_unknown_game_id(client):
    admin = _admin(client)
    resp = client.post(
        "/api/tournaments/", json={"game_name": "x", "game_id": 999}, headers=auth_header(admin)
    )
    assert resp.status_code == 404


def test_update_attaches_a_legacy_tournament(client):
    admin = _admin(client)
    lol = _game("League of Legends")
    s = database.SessionLocal()
    try:
        legacy = models.Tournament(game_name="LoL", organizer_id=1)
        s.add(legacy)
        s.commit()
        tid = legacy.id
    finally:
        s.close()

    unlinked = client.get("/api/tournaments/stats/unlinked", headers=auth_header(admin)).json()
    assert [u["id"] for u in unlinked] == [tid]

    resp = client.put(f"/api/tournaments/{tid}", json={"game_id": lol}, headers=auth_header(admin))
    assert resp.json()["game_id"] == lol and resp.json()["game_name"] == "League of Legends"
    assert client.get("/api/tournaments/stats/unlinked", headers=auth_header(admin)).json() == []


def test_unlinked_is_admin_only(client):
    _admin(client)
    make_user("bob")
    resp = client.get("/api/tournaments/stats/unlinked", headers=auth_header(login(client, "bob")))
    assert resp.status_code == 403


def test_game_picker_orders_played_games_first(client):
    admin = _admin(client)
    _game("Age of Empires II")
    lol = _game("League of Legends")
    _create(client, admin, game_name="x", game_id=lol)
    games = client.get("/api/tournaments/games", headers=auth_header(admin)).json()
    assert games[0]["id"] == lol and games[0]["tournament_count"] == 1
    assert games[1]["name"] == "Age of Empires II" and games[1]["tournament_count"] == 0


def test_stats_end_to_end(client):
    admin = _admin(client)
    alice, bob = make_user("alice"), make_user("bob")
    lol = _game("League of Legends")
    t = _create(client, admin, game_name="x", game_id=lol)
    _play(client, admin, t["id"], [alice], [bob], 2, 1)

    overview = client.get("/api/tournaments/stats/games", headers=auth_header(admin)).json()
    assert overview == [{
        "game_id": lol, "name": "League of Legends", "genre": "MOBA", "tournaments": 1, "matches": 1,
        "players": 2, "leader": {"user_id": alice, "username": "alice", "avatar_url": None, "wins": 1},
    }]

    detail = client.get(f"/api/tournaments/stats/games/{lol}", headers=auth_header(admin)).json()
    assert [(p["username"], p["wins"], p["losses"], p["titles"]) for p in detail["players"]] == [
        ("alice", 1, 0, 1), ("bob", 0, 1, 0),
    ]

    mine = client.get(f"/api/users/{alice}/game-stats", headers=auth_header(admin)).json()
    assert mine == [{
        "game_id": lol, "name": "League of Legends", "played": 1, "wins": 1, "losses": 0, "draws": 0,
        "win_rate": None, "tournaments": 1, "titles": 1,
    }]


def test_stats_event_filter(client):
    admin = _admin(client)
    alice, bob = make_user("alice"), make_user("bob")
    lol = _game("League of Legends")
    s = database.SessionLocal()
    try:
        from datetime import date
        ev = models.LanEvent(title="LAN", start_date=date(2026, 10, 13), end_date=date(2026, 10, 15), created_by=1)
        s.add(ev)
        s.commit()
        event_id = ev.id
    finally:
        s.close()
    t = _create(client, admin, game_name="x", game_id=lol, event_id=event_id)
    _play(client, admin, t["id"], [alice], [bob], 1, 0)

    in_event = client.get(f"/api/tournaments/stats/games?event_id={event_id}", headers=auth_header(admin)).json()
    other = client.get(f"/api/tournaments/stats/games?event_id={event_id + 1}", headers=auth_header(admin)).json()
    assert len(in_event) == 1 and other == []


def test_overview_skips_games_without_a_played_match(client):
    admin = _admin(client)
    _create(client, admin, game_name="x", game_id=_game("Rocket League"))  # no teams, no matches
    assert client.get("/api/tournaments/stats/games", headers=auth_header(admin)).json() == []


def test_stats_detail_404_for_unknown_game(client):
    admin = _admin(client)
    assert client.get("/api/tournaments/stats/games/999", headers=auth_header(admin)).status_code == 404


def test_user_game_stats_404_for_unknown_user(client):
    admin = _admin(client)
    assert client.get("/api/users/999/game-stats", headers=auth_header(admin)).status_code == 404
