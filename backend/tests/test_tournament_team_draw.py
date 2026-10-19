"""The random team draw: the browser shuffles the players, then one call replaces
every team of the tournament (PUT /api/tournaments/{id}/teams), and the format and
team size picked in the same modal go through PUT /api/tournaments/{id}. All of it
only while the tournament is pending, by its organizer or an admin."""

from conftest import auth_header, login, make_user


def _setup(client):
    admin = make_user("admin", role="admin")
    players = [make_user(name) for name in ("ana", "ben", "cyd", "dee", "eli")]
    token = login(client, "admin")
    resp = client.post(
        "/api/tournaments/",
        json={"game_name": "League of Legends", "bracket_type": "single_elimination", "max_team_size": 2},
        headers=auth_header(token),
    )
    resp.raise_for_status()
    return resp.json()["id"], admin, players, token


def _team(name, *user_ids):
    return {"team_name": name, "members": [{"player_name": f"u{uid}", "user_id": uid} for uid in user_ids]}


def _teams(client, token, tid):
    t = client.get(f"/api/tournaments/{tid}", headers=auth_header(token)).json()
    return {team["team_name"]: sorted(m["user_id"] for m in team["members"]) for team in t["teams"]}


def test_a_draw_replaces_every_team_and_a_redraw_replaces_it_again(client):
    tid, _, (ana, ben, cyd, dee, eli), token = _setup(client)
    h = auth_header(token)
    client.post(f"/api/tournaments/{tid}/teams", json=_team("Old", ana), headers=h).raise_for_status()

    # Two teams of 2, the fifth player placed by hand on Team 1 (a substitute).
    resp = client.put(
        f"/api/tournaments/{tid}/teams",
        json={"teams": [_team("Team 1", ana, ben, eli), _team("Team 2", cyd, dee)]},
        headers=h,
    )
    assert resp.status_code == 200
    assert _teams(client, token, tid) == {"Team 1": sorted([ana, ben, eli]), "Team 2": sorted([cyd, dee])}

    client.put(
        f"/api/tournaments/{tid}/teams",
        json={"teams": [_team("Team 1", dee, ana), _team("Team 2", ben, cyd)]},
        headers=h,
    ).raise_for_status()
    assert _teams(client, token, tid) == {"Team 1": sorted([ana, dee]), "Team 2": sorted([ben, cyd])}


def test_a_player_drawn_twice_is_refused_and_nothing_changes(client):
    tid, _, (ana, ben, cyd, _, _), token = _setup(client)
    h = auth_header(token)
    client.post(f"/api/tournaments/{tid}/teams", json=_team("Kept", ana), headers=h).raise_for_status()

    resp = client.put(
        f"/api/tournaments/{tid}/teams",
        json={"teams": [_team("Team 1", ana, ben), _team("Team 2", ben, cyd)]},
        headers=h,
    )
    assert resp.status_code == 400
    assert _teams(client, token, tid) == {"Kept": [ana]}


def test_only_the_organizer_or_an_admin_draws_and_only_before_the_brackets(client):
    tid, _, (ana, ben, cyd, dee, _), token = _setup(client)
    body = {"teams": [_team("Team 1", ana, ben), _team("Team 2", cyd, dee)]}

    member = login(client, "ana")
    assert client.put(f"/api/tournaments/{tid}/teams", json=body, headers=auth_header(member)).status_code == 403

    h = auth_header(token)
    client.put(f"/api/tournaments/{tid}/teams", json=body, headers=h).raise_for_status()
    client.post(f"/api/tournaments/{tid}/generate-brackets", headers=h).raise_for_status()
    assert client.put(f"/api/tournaments/{tid}/teams", json=body, headers=h).status_code == 409


def test_format_and_team_size_change_until_the_brackets_are_generated(client):
    tid, _, (ana, ben, cyd, dee, _), token = _setup(client)
    h = auth_header(token)

    resp = client.put(f"/api/tournaments/{tid}", json={"bracket_type": "round_robin", "max_team_size": 5}, headers=h)
    assert resp.status_code == 200
    assert (resp.json()["bracket_type"], resp.json()["max_team_size"]) == ("round_robin", 5)

    assert client.put(f"/api/tournaments/{tid}", json={"bracket_type": "swiss"}, headers=h).status_code == 422
    assert client.put(f"/api/tournaments/{tid}", json={"max_team_size": 11}, headers=h).status_code == 422

    client.put(
        f"/api/tournaments/{tid}/teams",
        json={"teams": [_team("Team 1", ana, ben), _team("Team 2", cyd, dee)]},
        headers=h,
    ).raise_for_status()
    client.post(f"/api/tournaments/{tid}/generate-brackets", headers=h).raise_for_status()
    assert client.put(f"/api/tournaments/{tid}", json={"max_team_size": 3}, headers=h).status_code == 409
    # Renaming the game stays possible.
    assert client.put(f"/api/tournaments/{tid}", json={"game_name": "LoL"}, headers=h).status_code == 200
