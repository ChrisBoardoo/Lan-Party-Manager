"""Trophies — /api/trophies.

The rules that matter, each pinned by a test:
- the feature flag gates members (admins pass, to prepare before enabling);
- drafts are admin-only; winners stay hidden from members until the reveal;
- voting: attendees only, one ballot each (changeable), never for yourself,
  only for an attendee, only while the vote is open;
- the ballot is secret — no response pairs a voter with a nominee, and members
  never see totals;
- most votes wins, a tie makes co-winners, zero votes makes nobody;
- every transition is enforced server-side;
- history is archived, never erased: an awarded trophy can't be deleted.
"""
from datetime import date, timedelta

import pytest

import database
import models
from conftest import auth_header, login, make_user


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def crew(client):
    """An admin, three attendees (alice, bob, carol) of a running event, and
    dave, a member who isn't coming. Trophies enabled."""
    ids = {"founder": make_user("founder", role="admin")}
    for name in ("alice", "bob", "carol", "dave"):
        ids[name] = make_user(name)
    tokens = {name: login(client, name) for name in ids}
    s = database.SessionLocal()
    try:
        today = date.today()
        event = models.LanEvent(
            title="October LAN", start_date=today, end_date=today + timedelta(days=2), created_by=ids["founder"],
        )
        s.add(event)
        s.commit()
        for name in ("founder", "alice", "bob", "carol"):
            s.add(models.EventRSVP(event_id=event.id, user_id=ids[name], status="in"))
        s.commit()
        event_id = event.id
    finally:
        s.close()
    _set(client, tokens["founder"], "trophies_enabled", "true")
    return {"ids": ids, "tok": tokens, "event_id": event_id}


def _set(client, token, key, value):
    client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(token)).raise_for_status()


def _h(crew, name):
    return auth_header(crew["tok"][name])


def _trophy(client, crew, name="Golden Rage-Quit", emoji="😤"):
    resp = client.post("/api/trophies/", json={"name": name, "emoji": emoji}, headers=_h(crew, "founder"))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _edition(client, crew, trophy_id, mode="vote"):
    resp = client.post(
        f"/api/trophies/events/{crew['event_id']}", json={"trophy_id": trophy_id, "mode": mode},
        headers=_h(crew, "founder"),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _status(client, crew, edition_id, status):
    return client.patch(
        f"/api/trophies/editions/{edition_id}", json={"status": status}, headers=_h(crew, "founder"),
    )


def _vote(client, crew, edition_id, voter, nominee):
    return client.post(
        f"/api/trophies/editions/{edition_id}/vote", json={"nominee_id": crew["ids"][nominee]}, headers=_h(crew, voter),
    )


def _list(client, crew, who):
    resp = client.get(f"/api/trophies/events/{crew['event_id']}", headers=_h(crew, who))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _voting_edition(client, crew):
    e = _edition(client, crew, _trophy(client, crew)["id"])
    _status(client, crew, e["id"], "voting").raise_for_status()
    return e["id"]


# ── Feature flag & cabinet ────────────────────────────────────────────────────

def test_feature_off_hides_it_from_members_not_admins(client, crew):
    _set(client, crew["tok"]["founder"], "trophies_enabled", "false")
    assert client.get(f"/api/trophies/events/{crew['event_id']}", headers=_h(crew, "alice")).status_code == 404
    assert client.get(f"/api/trophies/events/{crew['event_id']}", headers=_h(crew, "founder")).status_code == 200


def test_public_config_exposes_the_flag(client, crew):
    body = client.get("/api/settings/public-config", headers=_h(crew, "alice")).json()
    assert body["trophies_enabled"] is True


def test_cabinet_is_admin_only(client, crew):
    assert client.post("/api/trophies/", json={"name": "x"}, headers=_h(crew, "alice")).status_code == 403
    assert client.get("/api/trophies/", headers=_h(crew, "alice")).status_code == 403


def test_cabinet_crud_and_archive(client, crew):
    t = _trophy(client, crew)
    assert t["name"] == "Golden Rage-Quit" and t["emoji"] == "😤" and t["awarded_count"] == 0
    resp = client.put(
        f"/api/trophies/{t['id']}", json={"description": "Loudest exit", "archived": True}, headers=_h(crew, "founder"),
    )
    assert resp.json()["description"] == "Loudest exit" and resp.json()["archived_at"] is not None
    # An archived trophy can't be put in play…
    resp = client.post(
        f"/api/trophies/events/{crew['event_id']}", json={"trophy_id": t["id"]}, headers=_h(crew, "founder"),
    )
    assert resp.status_code == 400
    # …and a never-awarded one can simply be deleted.
    assert client.delete(f"/api/trophies/{t['id']}", headers=_h(crew, "founder")).status_code == 200


def test_same_trophy_once_per_event(client, crew):
    t = _trophy(client, crew)
    _edition(client, crew, t["id"])
    resp = client.post(
        f"/api/trophies/events/{crew['event_id']}", json={"trophy_id": t["id"]}, headers=_h(crew, "founder"),
    )
    assert resp.status_code == 409


# ── Visibility ────────────────────────────────────────────────────────────────

def test_drafts_are_admin_only(client, crew):
    _edition(client, crew, _trophy(client, crew)["id"])
    assert len(_list(client, crew, "founder")) == 1
    assert _list(client, crew, "alice") == []


# ── Direct mode ───────────────────────────────────────────────────────────────

def test_direct_mode_pick_and_reveal(client, crew):
    e = _edition(client, crew, _trophy(client, crew, "Chef of the LAN", "🍕")["id"], mode="direct")
    resp = client.put(
        f"/api/trophies/editions/{e['id']}/winners",
        json={"winners": [{"user_id": crew["ids"]["carol"], "citation": "Fed 12 people at 3am"}]},
        headers=_h(crew, "founder"),
    )
    assert resp.status_code == 200
    assert _list(client, crew, "alice") == []  # still a draft

    resp = client.post(f"/api/trophies/editions/{e['id']}/reveal", json={}, headers=_h(crew, "founder"))
    assert resp.status_code == 200 and resp.json()["status"] == "revealed"

    [seen] = _list(client, crew, "alice")
    assert [(w["username"], w["citation"]) for w in seen["winners"]] == [("carol", "Fed 12 people at 3am")]

    showcase = client.get(f"/api/trophies/users/{crew['ids']['carol']}", headers=_h(crew, "alice")).json()
    assert [(s["trophy"]["name"], s["event_title"], s["citation"]) for s in showcase] == [
        ("Chef of the LAN", "October LAN", "Fed 12 people at 3am"),
    ]

    s = database.SessionLocal()
    try:
        log = s.query(models.ActivityLog).filter(models.ActivityLog.action == "trophy_awarded").one()
        assert log.user_id == crew["ids"]["carol"] and "Chef of the LAN" in log.description
    finally:
        s.close()


def test_reveal_needs_a_winner(client, crew):
    e = _edition(client, crew, _trophy(client, crew)["id"], mode="direct")
    resp = client.post(f"/api/trophies/editions/{e['id']}/reveal", json={}, headers=_h(crew, "founder"))
    assert resp.status_code == 400


def test_direct_mode_cannot_open_a_vote(client, crew):
    e = _edition(client, crew, _trophy(client, crew)["id"], mode="direct")
    assert _status(client, crew, e["id"], "voting").status_code == 400


# ── Voting rules ──────────────────────────────────────────────────────────────

def test_only_attendees_vote_and_never_for_themselves(client, crew):
    eid = _voting_edition(client, crew)
    assert _vote(client, crew, eid, "dave", "alice").status_code == 403    # not coming
    assert _vote(client, crew, eid, "alice", "alice").status_code == 400   # self-vote
    assert _vote(client, crew, eid, "alice", "dave").status_code == 400    # nominee not coming
    assert _vote(client, crew, eid, "alice", "bob").status_code == 200


def test_one_ballot_each_and_it_can_change(client, crew):
    eid = _voting_edition(client, crew)
    _vote(client, crew, eid, "alice", "bob").raise_for_status()
    body = _vote(client, crew, eid, "alice", "carol").json()
    assert body["voters_count"] == 1 and body["my_vote"] == crew["ids"]["carol"]


def test_no_vote_outside_the_voting_window(client, crew):
    e = _edition(client, crew, _trophy(client, crew)["id"])
    assert _vote(client, crew, e["id"], "alice", "bob").status_code == 400   # draft
    _status(client, crew, e["id"], "voting").raise_for_status()
    _vote(client, crew, e["id"], "alice", "bob").raise_for_status()
    _status(client, crew, e["id"], "closed").raise_for_status()
    assert _vote(client, crew, e["id"], "carol", "bob").status_code == 400   # closed


def test_the_ballot_is_secret(client, crew):
    eid = _voting_edition(client, crew)
    _vote(client, crew, eid, "alice", "bob").raise_for_status()
    _vote(client, crew, eid, "bob", "carol").raise_for_status()

    [as_carol] = _list(client, crew, "carol")
    assert as_carol["my_vote"] is None            # carol hasn't voted; she never sees anyone else's
    assert as_carol["voters_count"] == 2 and as_carol["eligible_count"] == 4
    assert as_carol["tally"] is None and as_carol["winners"] == []

    [as_admin] = _list(client, crew, "founder")   # even the admin gets no totals mid-vote
    assert as_admin["tally"] is None


# ── Closing, ties, reveal ─────────────────────────────────────────────────────

def test_close_elects_the_most_voted_and_members_wait_for_the_reveal(client, crew):
    eid = _voting_edition(client, crew)
    _vote(client, crew, eid, "alice", "bob").raise_for_status()
    _vote(client, crew, eid, "carol", "bob").raise_for_status()
    _vote(client, crew, eid, "bob", "alice").raise_for_status()
    closed = _status(client, crew, eid, "closed").json()
    assert [(w["username"], w["vote_count"]) for w in closed["winners"]] == [("bob", 2)]
    assert [(t["username"], t["votes"]) for t in closed["tally"]] == [("bob", 2), ("alice", 1)]

    [waiting] = _list(client, crew, "alice")
    assert waiting["status"] == "closed" and waiting["winners"] == [] and waiting["tally"] is None

    client.post(f"/api/trophies/editions/{eid}/reveal", json={}, headers=_h(crew, "founder")).raise_for_status()
    [revealed] = _list(client, crew, "alice")
    # Members see who won, not by how much.
    assert [(w["username"], w["vote_count"]) for w in revealed["winners"]] == [("bob", None)]


def test_a_tie_makes_co_winners(client, crew):
    eid = _voting_edition(client, crew)
    _vote(client, crew, eid, "alice", "bob").raise_for_status()
    _vote(client, crew, eid, "bob", "alice").raise_for_status()
    closed = _status(client, crew, eid, "closed").json()
    assert sorted(w["username"] for w in closed["winners"]) == ["alice", "bob"]


def test_no_votes_no_winner(client, crew):
    eid = _voting_edition(client, crew)
    closed = _status(client, crew, eid, "closed").json()
    assert closed["winners"] == []
    assert client.post(f"/api/trophies/editions/{eid}/reveal", json={}, headers=_h(crew, "founder")).status_code == 400


def test_admin_can_break_a_tie_before_the_reveal(client, crew):
    eid = _voting_edition(client, crew)
    _vote(client, crew, eid, "alice", "bob").raise_for_status()
    _vote(client, crew, eid, "bob", "alice").raise_for_status()
    _status(client, crew, eid, "closed").raise_for_status()
    resp = client.put(
        f"/api/trophies/editions/{eid}/winners",
        json={"winners": [{"user_id": crew["ids"]["bob"], "citation": "Tie-break: loudest"}]},
        headers=_h(crew, "founder"),
    )
    assert [(w["username"], w["vote_count"], w["citation"]) for w in resp.json()["winners"]] == [
        ("bob", 1, "Tie-break: loudest"),
    ]


def test_winners_cannot_be_set_mid_vote(client, crew):
    eid = _voting_edition(client, crew)
    resp = client.put(
        f"/api/trophies/editions/{eid}/winners", json={"winners": [{"user_id": crew["ids"]["bob"]}]},
        headers=_h(crew, "founder"),
    )
    assert resp.status_code == 400


def test_reopening_drops_the_proposed_winners(client, crew):
    eid = _voting_edition(client, crew)
    _vote(client, crew, eid, "alice", "bob").raise_for_status()
    _status(client, crew, eid, "closed").raise_for_status()
    reopened = _status(client, crew, eid, "voting").json()
    assert reopened["winners"] == [] and reopened["voters_count"] == 1  # ballots are kept


def test_unreveal_takes_it_back(client, crew):
    eid = _voting_edition(client, crew)
    _vote(client, crew, eid, "alice", "bob").raise_for_status()
    _status(client, crew, eid, "closed").raise_for_status()
    client.post(f"/api/trophies/editions/{eid}/reveal", json={}, headers=_h(crew, "founder")).raise_for_status()
    assert _status(client, crew, eid, "closed").json()["revealed_at"] is None
    assert client.get(f"/api/trophies/users/{crew['ids']['bob']}", headers=_h(crew, "alice")).json() == []


def test_invalid_transitions_are_refused(client, crew):
    e = _edition(client, crew, _trophy(client, crew)["id"])
    assert _status(client, crew, e["id"], "closed").status_code == 400   # draft → closed skips the vote
    resp = client.patch(
        f"/api/trophies/editions/{e['id']}", json={"status": "revealed"}, headers=_h(crew, "founder"),
    )
    assert resp.status_code == 422  # revealing only goes through /reveal


def test_mode_only_changes_in_draft(client, crew):
    eid = _voting_edition(client, crew)
    resp = client.patch(f"/api/trophies/editions/{eid}", json={"mode": "direct"}, headers=_h(crew, "founder"))
    assert resp.status_code == 400


def test_member_cannot_manage_editions(client, crew):
    t = _trophy(client, crew)
    resp = client.post(
        f"/api/trophies/events/{crew['event_id']}", json={"trophy_id": t["id"]}, headers=_h(crew, "alice"),
    )
    assert resp.status_code == 403


# ── History, recap, kiosk, cascades ──────────────────────────────────────────

def _awarded(client, crew, name="Golden Rage-Quit"):
    t = _trophy(client, crew, name)
    e = _edition(client, crew, t["id"], mode="direct")
    client.put(
        f"/api/trophies/editions/{e['id']}/winners", json={"winners": [{"user_id": crew["ids"]["bob"]}]},
        headers=_h(crew, "founder"),
    ).raise_for_status()
    client.post(f"/api/trophies/editions/{e['id']}/reveal", json={}, headers=_h(crew, "founder")).raise_for_status()
    return t, e


def test_an_awarded_trophy_is_archived_not_deleted(client, crew):
    t, _ = _awarded(client, crew)
    assert client.delete(f"/api/trophies/{t['id']}", headers=_h(crew, "founder")).status_code == 409
    [cab] = client.get("/api/trophies/", headers=_h(crew, "founder")).json()
    assert cab["awarded_count"] == 1
    assert cab["last_award"] == {"username": "bob", "event_title": "October LAN"}


def test_recap_lists_revealed_trophies(client, crew):
    _set(client, crew["tok"]["founder"], "recap_enabled", "true")
    _awarded(client, crew)
    _edition(client, crew, _trophy(client, crew, "Still a draft")["id"])
    recap = client.get(f"/api/recap/{crew['event_id']}", headers=_h(crew, "alice")).json()
    assert [(r["trophy"]["name"], [w["username"] for w in r["winners"]]) for r in recap["trophies"]] == [
        ("Golden Rage-Quit", ["bob"]),
    ]


def test_kiosk_carries_revealed_trophies(client, crew):
    _set(client, crew["tok"]["founder"], "kiosk_enabled", "true")
    token = client.post("/api/kiosk/admin/token", headers=_h(crew, "founder")).json()["token"]
    assert client.get("/api/kiosk/summary", headers={"X-Kiosk-Token": f"{token}"}).json()["trophies"] == []
    _, e = _awarded(client, crew)
    [kt] = client.get("/api/kiosk/summary", headers={"X-Kiosk-Token": f"{token}"}).json()["trophies"]
    assert kt["edition_id"] == e["id"] and kt["name"] == "Golden Rage-Quit"
    assert [w["username"] for w in kt["winners"]] == ["bob"]


def test_deleting_the_event_removes_its_editions(client, crew):
    _awarded(client, crew)
    client.delete(f"/api/events/{crew['event_id']}", headers=_h(crew, "founder")).raise_for_status()
    s = database.SessionLocal()
    try:
        assert s.query(models.EventTrophy).count() == 0
        assert s.query(models.EventTrophyWinner).count() == 0
        assert s.query(models.Trophy).count() == 1  # the definition stays in the cabinet
    finally:
        s.close()
