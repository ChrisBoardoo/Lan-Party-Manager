"""Who may change a tournament's teams, and when (S7 of the 2026-09-24 security review).

The four team routes used to check only that the caller was signed in: any member
could rename, empty or delete any team of any tournament — including a finished one,
where deleting a team nulls it out of its matches and rewrites the bracket, the Hall
of Fame and per-game stats. Now: the tournament's organizer or an admin, and only
while the tournament is still `pending` (before brackets are generated).
"""

import pytest

from conftest import auth_header, login, make_user, register


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


def _member(client, username):
    uid = make_user(username)
    return uid, login(client, username)


def _organizer(client, username):
    """A member who ticked "tournament organizer" on their own profile — the real flow."""
    uid, token = _member(client, username)
    client.put(
        f"/api/users/{uid}", json={"is_tournament_organizer": True}, headers=auth_header(token)
    ).raise_for_status()
    return uid, token


def _tournament(client, token):
    resp = client.post(
        "/api/tournaments/",
        json={"game_name": "Rocket League", "bracket_type": "single_elimination", "max_team_size": 2},
        headers=auth_header(token),
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _add_team(client, token, tid, name):
    return client.post(
        f"/api/tournaments/{tid}/teams",
        json={"team_name": name, "members": [{"player_name": name}]},
        headers=auth_header(token),
    )


def _all_team_calls(client, token, tid, team_id):
    """Status code of each of the four team routes, in order: add, update, seed, delete."""
    h = auth_header(token)
    return [
        _add_team(client, token, tid, "Intruders").status_code,
        client.put(
            f"/api/tournaments/{tid}/teams/{team_id}",
            json={"team_name": "Renamed", "members": []},
            headers=h,
        ).status_code,
        client.patch(f"/api/tournaments/{tid}/teams/{team_id}/seed", params={"seed": 1}, headers=h).status_code,
        client.delete(f"/api/tournaments/{tid}/teams/{team_id}", headers=h).status_code,
    ]


def test_a_member_cannot_touch_someone_elses_teams(client, admin):
    tid = _tournament(client, admin)
    team_id = _add_team(client, admin, tid, "Alpha").json()["id"]
    _, member = _member(client, "prankster")

    assert _all_team_calls(client, member, tid, team_id) == [403, 403, 403, 403]

    teams = client.get(f"/api/tournaments/{tid}", headers=auth_header(admin)).json()["teams"]
    assert [t["team_name"] for t in teams] == ["Alpha"]


def test_an_organizer_manages_their_own_tournament_but_not_others(client, admin):
    _, organizer = _organizer(client, "orga")
    own = _tournament(client, organizer)
    team_id = _add_team(client, organizer, own, "Alpha").json()["id"]
    assert _all_team_calls(client, organizer, own, team_id) == [201, 200, 200, 200]

    other = _tournament(client, admin)
    other_team = _add_team(client, admin, other, "Beta").json()["id"]
    assert _all_team_calls(client, organizer, other, other_team) == [403, 403, 403, 403]


def test_an_admin_manages_any_tournament(client, admin):
    _, organizer = _organizer(client, "orga")
    tid = _tournament(client, organizer)
    team_id = _add_team(client, organizer, tid, "Alpha").json()["id"]

    assert _all_team_calls(client, admin, tid, team_id) == [201, 200, 200, 200]


def test_teams_lock_once_brackets_exist(client, admin):
    """Even for an admin: a finished bracket must not be rewritable by deleting a team."""
    tid = _tournament(client, admin)
    first = _add_team(client, admin, tid, "Alpha").json()["id"]
    _add_team(client, admin, tid, "Beta").raise_for_status()
    client.post(f"/api/tournaments/{tid}/generate-brackets", headers=auth_header(admin)).raise_for_status()

    assert _all_team_calls(client, admin, tid, first) == [409, 409, 409, 409]


def test_unknown_tournament_is_404(client, admin):
    assert _add_team(client, admin, 9999, "Ghost").status_code == 404
