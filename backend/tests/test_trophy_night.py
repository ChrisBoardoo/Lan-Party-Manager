"""Trophy night — /api/trophies/events/{id}/open-votes, /close-votes, /nudge,
/api/trophies/ballot, and the kiosk's turnout.

The rules pinned here:
- only an admin runs the night; it only touches what each step is for (vote-mode
  drafts to open, open votes to close), never direct-mode or revealed trophies;
- notifications go to this LAN's attendees only, one targeted entry each, never
  to the admin who clicked, never to a member who isn't coming;
- a reminder goes only to the attendees who still have a vote to cast;
- the ballot gives a member their own open votes and who they may vote for
  (attendees minus themselves), and nothing about anyone else's ballot;
- the kiosk shows counts, never names.
"""
import database
import models
from conftest import auth_header

from test_trophies import _edition, _h, _set, _trophy, _vote, crew  # noqa: F401  (crew is a fixture)


def _open(client, crew, who="founder", **body):
    return client.post(f"/api/trophies/events/{crew['event_id']}/open-votes", json=body, headers=_h(crew, who))


def _close(client, crew, who="founder"):
    return client.post(f"/api/trophies/events/{crew['event_id']}/close-votes", headers=_h(crew, who))


def _nudge(client, crew, who="founder"):
    return client.post(f"/api/trophies/events/{crew['event_id']}/nudge", headers=_h(crew, who))


def _ballot(client, crew, who):
    resp = client.get("/api/trophies/ballot", headers=_h(crew, who))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _notes(action):
    s = database.SessionLocal()
    try:
        return [(a.recipient_user_id, a.user_id, a.entity_id, a.description)
                for a in s.query(models.ActivityLog).filter_by(action=action).order_by(models.ActivityLog.id)]
    finally:
        s.close()


def _night(client, crew, count=2):
    """`count` vote-mode drafts, plus one direct-mode draft that must stay put."""
    ids = [_edition(client, crew, _trophy(client, crew, name=f"Trophy {i}", emoji="🏆")["id"])["id"] for i in range(count)]
    direct = _edition(client, crew, _trophy(client, crew, name="Organizer's pick")["id"], mode="direct")["id"]
    return ids, direct


def test_trophy_night_is_admin_only(client, crew):
    _night(client, crew)
    assert _open(client, crew, who="alice").status_code == 403
    assert _close(client, crew, who="alice").status_code == 403
    assert _nudge(client, crew, who="alice").status_code == 403


def test_open_votes_opens_every_vote_draft_and_notifies_the_attendees(client, crew):
    ids, direct = _night(client, crew)
    resp = _open(client, crew, post_to_discord=False)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["changed"] == 2 and body["notified"] == 3  # alice, bob, carol — not the founder, not dave
    status = {e["id"]: e["status"] for e in body["editions"]}
    assert [status[i] for i in ids] == ["voting", "voting"] and status[direct] == "draft"

    notes = _notes("trophy_vote_open")
    ids_by_name = crew["ids"]
    assert sorted(r for r, *_ in notes) == sorted(ids_by_name[n] for n in ("alice", "bob", "carol"))
    assert all(actor == ids_by_name["founder"] and ev == crew["event_id"] for _, actor, ev, _ in notes)

    # Targeted: dave's feed doesn't carry it, alice's does.
    dave_feed = client.get("/api/activity/", headers=_h(crew, "dave")).json()
    alice_feed = client.get("/api/activity/", headers=_h(crew, "alice")).json()
    assert not [a for a in dave_feed if a["action"] == "trophy_vote_open"]
    assert len([a for a in alice_feed if a["action"] == "trophy_vote_open"]) == 1

    # Nothing left to open.
    assert _open(client, crew).status_code == 400


def test_open_votes_can_stay_silent(client, crew):
    _night(client, crew)
    body = _open(client, crew, notify=False).json()
    assert body["changed"] == 2 and body["notified"] == 0
    assert _notes("trophy_vote_open") == []


def test_close_votes_proposes_winners_including_ties(client, crew):
    (a, b), _ = _night(client, crew)
    _open(client, crew, notify=False)
    _vote(client, crew, a, "alice", "bob").raise_for_status()
    _vote(client, crew, a, "carol", "bob").raise_for_status()
    _vote(client, crew, b, "alice", "carol").raise_for_status()
    _vote(client, crew, b, "carol", "alice").raise_for_status()

    body = _close(client, crew).json()
    assert body["changed"] == 2
    by_id = {e["id"]: e for e in body["editions"]}
    assert by_id[a]["status"] == by_id[b]["status"] == "closed"
    assert [w["username"] for w in by_id[a]["winners"]] == ["bob"]
    assert sorted(w["username"] for w in by_id[b]["winners"]) == ["alice", "carol"]
    # Members still don't see the winners before the reveal.
    assert all(e["winners"] == [] for e in client.get(
        f"/api/trophies/events/{crew['event_id']}", headers=_h(crew, "alice")).json())
    assert _close(client, crew).status_code == 400


def test_nudge_reaches_only_the_attendees_with_a_vote_left(client, crew):
    (a, b), _ = _night(client, crew)
    assert _nudge(client, crew).status_code == 400  # nothing open yet
    _open(client, crew, notify=False)
    for e in (a, b):
        _vote(client, crew, e, "alice", "bob").raise_for_status()
    _vote(client, crew, a, "bob", "alice").raise_for_status()

    assert _nudge(client, crew).json()["notified"] == 2
    notes = {r: d for r, _, _, d in _notes("trophy_vote_nudge")}
    ids = crew["ids"]
    # bob has one left, carol two; alice is done, the founder never nudges himself, dave isn't coming.
    assert notes == {ids["bob"]: "1 trophy vote still waiting for you", ids["carol"]: "2 trophy votes still waiting for you"}


def test_ballot_gives_my_open_votes_and_who_i_can_vote_for(client, crew):
    assert _ballot(client, crew, "alice") is None  # nothing open anywhere
    (a, b), _ = _night(client, crew)
    _open(client, crew, notify=False)
    _vote(client, crew, a, "alice", "bob").raise_for_status()
    _vote(client, crew, a, "carol", "alice").raise_for_status()

    ballot = _ballot(client, crew, "alice")
    assert ballot["event_id"] == crew["event_id"] and ballot["nudge_id"] is None
    assert [e["id"] for e in ballot["editions"]] == [a, b]
    assert [e["my_vote"] for e in ballot["editions"]] == [crew["ids"]["bob"], None]
    # Attendees minus herself; dave isn't coming.
    assert [n["username"] for n in ballot["nominees"]] == ["bob", "carol", "founder"]
    # Secret: a member sees turnout, never totals or winners.
    assert all(e["tally"] is None and e["winners"] == [] for e in ballot["editions"])

    # Not coming = no ballot.
    assert _ballot(client, crew, "dave") is None

    # A reminder shows up as a new nudge_id, so the modal pops again.
    _nudge(client, crew)  # alice still has b to vote on
    assert _ballot(client, crew, "alice")["nudge_id"] is not None

    _close(client, crew)
    assert _ballot(client, crew, "alice") is None


def test_ballot_respects_the_feature_flag(client, crew):
    _set(client, crew["tok"]["founder"], "trophies_enabled", "false")
    assert client.get("/api/trophies/ballot", headers=_h(crew, "alice")).status_code == 404


def test_kiosk_shows_the_turnout_without_names(client, crew):
    _set(client, crew["tok"]["founder"], "kiosk_enabled", "true")
    token = client.post("/api/kiosk/admin/token", headers=_h(crew, "founder")).json()["token"]

    def summary():
        return client.get("/api/kiosk/summary", headers={"X-Kiosk-Token": token}).json()

    (a, b), _ = _night(client, crew)
    assert summary()["trophy_vote"] is None
    _open(client, crew, notify=False)
    _vote(client, crew, a, "alice", "bob").raise_for_status()
    _vote(client, crew, b, "alice", "carol").raise_for_status()
    _vote(client, crew, a, "bob", "carol").raise_for_status()

    tv = summary()["trophy_vote"]
    assert tv["eligible"] == 4 and tv["done"] == 1  # only alice voted on both
    assert [(t["edition_id"], t["voters"]) for t in tv["trophies"]] == [(a, 2), (b, 1)]
    assert set(tv["trophies"][0]) == {"edition_id", "name", "emoji", "image_url", "voters"}

    _close(client, crew)
    assert summary()["trophy_vote"] is None


def test_activity_feed_breaks_same_second_ties_by_id(client, crew):
    # A reveal with co-winners writes one trophy_awarded row per winner in the
    # same transaction, so with the same created_at (one-second resolution).
    # The desktop app takes the feed's first item as its "last seen" id: if
    # that's the lower id of the tie, the other row counts as new on every
    # poll and its toast fires every 30 s, forever.
    from datetime import datetime

    s = database.SessionLocal()
    try:
        same = datetime(2026, 10, 17, 23, 30, 0)
        for name in ("alice", "bob"):
            s.add(models.ActivityLog(user_id=crew["ids"]["founder"], action="trophy_awarded",
                                     description="🏆 Clutch", created_at=same))
        s.commit()
        top = max(a.id for a in s.query(models.ActivityLog).all())
    finally:
        s.close()
    feed = client.get("/api/activity/", headers=_h(crew, "alice")).json()
    assert feed[0]["id"] == top
