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


def _organizer(client, username, admin):
    """A member an admin made "tournament organizer" from their player page —
    the real flow since 1.4.1 (D-2 of the 2026-10-20 review: self-service let a
    member run a fake tournament during a LAN and pay himself the XP)."""
    uid, token = _member(client, username)
    client.put(
        f"/api/users/{uid}", json={"is_tournament_organizer": True}, headers=auth_header(admin)
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
    _, organizer = _organizer(client, "orga", admin)
    own = _tournament(client, organizer)
    team_id = _add_team(client, organizer, own, "Alpha").json()["id"]
    assert _all_team_calls(client, organizer, own, team_id) == [201, 200, 200, 200]

    other = _tournament(client, admin)
    other_team = _add_team(client, admin, other, "Beta").json()["id"]
    assert _all_team_calls(client, organizer, other, other_team) == [403, 403, 403, 403]


def test_an_admin_manages_any_tournament(client, admin):
    _, organizer = _organizer(client, "orga", admin)
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


def test_a_member_cannot_make_themselves_organizer(client, admin):
    uid, member = _member(client, "ambitious")
    h = auth_header(member)
    assert client.put(f"/api/users/{uid}", json={"is_tournament_organizer": True}, headers=h).status_code == 403
    # Sending back the unchanged value (an older profile form) is fine.
    assert client.put(f"/api/users/{uid}", json={"is_tournament_organizer": False, "phone": "06"}, headers=h).status_code == 200
    assert client.post(
        "/api/tournaments/", json={"game_name": "Fake 1v1", "bracket_type": "single_elimination", "max_team_size": 1},
        headers=h,
    ).status_code == 403
    # An admin grants it, and only then can the member create a tournament.
    assert client.put(f"/api/users/{uid}", json={"is_tournament_organizer": True}, headers=auth_header(admin)).status_code == 200
    assert _tournament(client, member) > 0
    # A member can't take it off an admin's hands either (nor off their own).
    assert client.put(f"/api/users/{uid}", json={"is_tournament_organizer": False}, headers=h).status_code == 403


def test_a_team_cannot_name_an_unknown_or_inactive_account(client, admin):
    tid = _tournament(client, admin)
    h = auth_header(admin)
    ghost = {"team_name": "Ghosts", "members": [{"player_name": "nobody", "user_id": 9999}]}
    assert client.post(f"/api/tournaments/{tid}/teams", json=ghost, headers=h).status_code == 400
    gone_id, _ = _member(client, "gone")
    client.put(f"/api/users/{gone_id}/deactivate", headers=h).raise_for_status()
    inactive = {"team_name": "Gone", "members": [{"player_name": "gone", "user_id": gone_id}]}
    assert client.post(f"/api/tournaments/{tid}/teams", json=inactive, headers=h).status_code == 400
    assert client.put(f"/api/tournaments/{tid}/teams", json={"teams": [ghost]}, headers=h).status_code == 400
    # Guests without an account stay free-text names.
    assert _add_team(client, admin, tid, "Guests").status_code == 201
    live_id, _ = _member(client, "live")
    ok = {"team_name": "Live", "members": [{"player_name": "live", "user_id": live_id}]}
    assert client.post(f"/api/tournaments/{tid}/teams", json=ok, headers=h).status_code == 201


def test_brackets_cannot_be_regenerated_once_the_tournament_started(client, admin):
    """Regenerating used to delete every match of a running or finished tournament
    (Q-6 of the 2026-10-20 review): scores, played_at, the XP and Hall of Fame
    derived from them — with no journal and no way back."""
    tid = _tournament(client, admin)
    h = auth_header(admin)
    _add_team(client, admin, tid, "Alpha").raise_for_status()
    _add_team(client, admin, tid, "Beta").raise_for_status()
    client.post(f"/api/tournaments/{tid}/generate-brackets", headers=h).raise_for_status()
    before = [m["id"] for m in client.get(f"/api/tournaments/{tid}", headers=h).json()["matches"]]
    assert before
    assert client.post(f"/api/tournaments/{tid}/generate-brackets", headers=h).status_code == 409
    assert [m["id"] for m in client.get(f"/api/tournaments/{tid}", headers=h).json()["matches"]] == before
