"""Tests for self-service match score reporting — propose-then-confirm.

A participant reports a score from their own device; the organizer confirms
(applying it + advancing the bracket) or rejects it. The live score is never
touched until confirmation.
"""

import pytest

from conftest import register, login, auth_header, make_user


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


def _member(client, username):
    uid = make_user(username, role="user")
    return uid, login(client, username)


def _setup_match(client, admin, p1_id, p2_id, bracket="single_elimination"):
    """A 2-player individual tournament with one match, both players assigned."""
    t = client.post(
        "/api/tournaments/",
        json={"game_name": "Smash", "bracket_type": bracket, "event_type": "individual", "max_team_size": 1},
        headers=auth_header(admin),
    ).json()
    tid = t["id"]
    for name, uid in (("Alice", p1_id), ("Bob", p2_id)):
        client.post(
            f"/api/tournaments/{tid}/teams",
            json={"team_name": name, "members": [{"player_name": name, "user_id": uid}]},
            headers=auth_header(admin),
        ).raise_for_status()
    client.post(f"/api/tournaments/{tid}/generate-brackets", headers=auth_header(admin)).raise_for_status()
    match = client.get(f"/api/tournaments/{tid}", headers=auth_header(admin)).json()["matches"][0]
    return tid, match


def test_participant_reports_then_organizer_confirms(client, admin):
    p1_id, p1 = _member(client, "alice")
    p2_id, p2 = _member(client, "bob")
    tid, match = _setup_match(client, admin, p1_id, p2_id)
    mid = match["id"]

    # A player reports — only the reported_* fields change; live score stays 0/0.
    reported = client.post(
        f"/api/tournaments/{tid}/matches/{mid}/report",
        json={"score_a": 3, "score_b": 1}, headers=auth_header(p1),
    )
    assert reported.status_code == 200
    body = reported.json()
    assert body["reported_score_a"] == 3 and body["reported_score_b"] == 1
    assert body["reported_by"] == p1_id
    assert body["score_a"] == 0 and body["status"] != "completed"

    # Organizer confirms — it becomes the live score, winner resolves, report clears.
    confirmed = client.post(f"/api/tournaments/{tid}/matches/{mid}/confirm", headers=auth_header(admin))
    assert confirmed.status_code == 200
    cb = confirmed.json()
    assert cb["score_a"] == 3 and cb["score_b"] == 1
    assert cb["status"] == "completed"
    assert cb["winner_id"] == match["team_a_id"]
    assert cb["reported_by"] is None and cb["reported_score_a"] is None


def test_non_participant_cannot_report(client, admin):
    p1_id, _ = _member(client, "alice")
    p2_id, _ = _member(client, "bob")
    _outsider_id, outsider = _member(client, "carol")
    tid, match = _setup_match(client, admin, p1_id, p2_id)
    resp = client.post(
        f"/api/tournaments/{tid}/matches/{match['id']}/report",
        json={"score_a": 1, "score_b": 0}, headers=auth_header(outsider),
    )
    assert resp.status_code == 403


def test_confirm_requires_a_pending_report(client, admin):
    p1_id, _ = _member(client, "alice")
    p2_id, _ = _member(client, "bob")
    tid, match = _setup_match(client, admin, p1_id, p2_id)
    resp = client.post(f"/api/tournaments/{tid}/matches/{match['id']}/confirm", headers=auth_header(admin))
    assert resp.status_code == 400


def test_reporter_can_reject_own_report(client, admin):
    p1_id, p1 = _member(client, "alice")
    p2_id, _ = _member(client, "bob")
    tid, match = _setup_match(client, admin, p1_id, p2_id)
    mid = match["id"]
    client.post(f"/api/tournaments/{tid}/matches/{mid}/report", json={"score_a": 2, "score_b": 2}, headers=auth_header(p1)).raise_for_status()

    rejected = client.delete(f"/api/tournaments/{tid}/matches/{mid}/report", headers=auth_header(p1))
    assert rejected.status_code == 200
    assert rejected.json()["reported_by"] is None
    # ...and a third party can't clear someone's report.
    _c_id, carol = _member(client, "carol")
    client.post(f"/api/tournaments/{tid}/matches/{mid}/report", json={"score_a": 1, "score_b": 0}, headers=auth_header(p1)).raise_for_status()
    assert client.delete(f"/api/tournaments/{tid}/matches/{mid}/report", headers=auth_header(carol)).status_code == 403


def test_knockout_draw_is_rejected_but_round_robin_allows_it(client, admin):
    p1_id, p1 = _member(client, "alice")
    p2_id, _ = _member(client, "bob")

    # Single-elimination: a draw can't advance → confirm is refused.
    tid, match = _setup_match(client, admin, p1_id, p2_id, bracket="single_elimination")
    mid = match["id"]
    client.post(f"/api/tournaments/{tid}/matches/{mid}/report", json={"score_a": 2, "score_b": 2}, headers=auth_header(p1)).raise_for_status()
    assert client.post(f"/api/tournaments/{tid}/matches/{mid}/confirm", headers=auth_header(admin)).status_code == 400

    # Round-robin: a draw is legitimate → confirm succeeds with no winner.
    rid, rmatch = _setup_match(client, admin, p1_id, p2_id, bracket="round_robin")
    rmid = rmatch["id"]
    client.post(f"/api/tournaments/{rid}/matches/{rmid}/report", json={"score_a": 1, "score_b": 1}, headers=auth_header(p1)).raise_for_status()
    ok = client.post(f"/api/tournaments/{rid}/matches/{rmid}/confirm", headers=auth_header(admin))
    assert ok.status_code == 200
    assert ok.json()["status"] == "completed"
    assert ok.json()["winner_id"] is None


def test_cannot_report_completed_match(client, admin):
    p1_id, p1 = _member(client, "alice")
    p2_id, _ = _member(client, "bob")
    tid, match = _setup_match(client, admin, p1_id, p2_id)
    mid = match["id"]
    client.post(f"/api/tournaments/{tid}/matches/{mid}/report", json={"score_a": 3, "score_b": 0}, headers=auth_header(p1)).raise_for_status()
    client.post(f"/api/tournaments/{tid}/matches/{mid}/confirm", headers=auth_header(admin)).raise_for_status()
    # Match is now completed → further reports are refused.
    assert client.post(
        f"/api/tournaments/{tid}/matches/{mid}/report", json={"score_a": 1, "score_b": 0}, headers=auth_header(p1)
    ).status_code == 400
