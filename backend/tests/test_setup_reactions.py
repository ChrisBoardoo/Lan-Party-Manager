"""Reactions on a member's rig — the media-reaction semantics pointed at My Setup.

POST /api/setup/{user_id}/react is deliberately the one router_setup write that
names another user: the row it writes belongs to the caller (their reaction),
never the owner. These tests also pin the privacy rule that the public share
payload carries no reactions.
"""
import database
import models
from conftest import auth_header, login, make_user


def _enable(client, admin_token, value="true"):
    resp = client.put(
        "/api/settings/setup_enabled", json={"value": value}, headers=auth_header(admin_token)
    )
    resp.raise_for_status()


def _save_setup(client, token, cpu="Ryzen 7 7800X3D"):
    resp = client.put(
        "/api/setup/me",
        json={"components": {"cpu": cpu}, "custom_fields": []},
        headers=auth_header(token),
    )
    assert resp.status_code == 200
    return resp.json()


def _react(client, token, user_id, emoji="🔥"):
    return client.post(f"/api/setup/{user_id}/react", json={"emoji": emoji}, headers=auth_header(token))


def _crew(client):
    """Admin owner with a saved setup + a plain member, feature on."""
    owner_id = make_user("founder", role="admin")
    make_user("bob")
    owner_token = login(client, "founder")
    bob_token = login(client, "bob")
    _enable(client, owner_token)
    _save_setup(client, owner_token)
    return owner_id, owner_token, bob_token


# ── Reacting ──────────────────────────────────────────────────────────────────

def test_reacting_then_reacting_again_toggles_it_off(client):
    owner_id, _, bob_token = _crew(client)

    body = _react(client, bob_token, owner_id).json()
    assert body["reaction_total"] == 1
    assert body["reactions"] == [{"emoji": "🔥", "count": 1, "mine": True, "users": ["bob"]}]

    body = _react(client, bob_token, owner_id).json()
    assert body["reaction_total"] == 0
    assert body["reactions"] == []


def test_another_members_reaction_counts_but_is_not_mine(client):
    owner_id, owner_token, bob_token = _crew(client)

    _react(client, owner_token, owner_id)  # reacting to your own rig is allowed
    _react(client, bob_token, owner_id)

    seen_by_bob = client.get(f"/api/setup/{owner_id}", headers=auth_header(bob_token)).json()
    assert seen_by_bob["reaction_total"] == 2
    # users is who reacted, oldest first — it's what the hover tooltip shows.
    assert seen_by_bob["reactions"] == [{"emoji": "🔥", "count": 2, "mine": True, "users": ["founder", "bob"]}]

    _react(client, bob_token, owner_id)  # bob un-reacts
    seen_by_bob = client.get(f"/api/setup/{owner_id}", headers=auth_header(bob_token)).json()
    assert seen_by_bob["reactions"] == [{"emoji": "🔥", "count": 1, "mine": False, "users": ["founder"]}]


def test_distinct_emoji_are_counted_separately_and_ordered_by_count(client):
    owner_id, owner_token, bob_token = _crew(client)

    _react(client, bob_token, owner_id, "🔥")
    _react(client, bob_token, owner_id, "😂")
    body = _react(client, owner_token, owner_id, "😂").json()

    assert body["reaction_total"] == 3
    assert [r["emoji"] for r in body["reactions"]] == ["😂", "🔥"]


def test_an_emoji_outside_the_set_is_rejected(client):
    owner_id, _, bob_token = _crew(client)
    assert _react(client, bob_token, owner_id, "🍕").status_code == 400


def test_reacting_to_a_missing_user_is_404(client):
    _, _, bob_token = _crew(client)
    assert _react(client, bob_token, 999).status_code == 404


def test_reacting_to_a_user_with_no_saved_setup_is_404(client):
    make_user("founder", role="admin")
    bob_id = make_user("bob")
    owner_token = login(client, "founder")
    _enable(client, owner_token)
    assert _react(client, owner_token, bob_id).status_code == 404


def test_member_cannot_react_while_the_feature_is_off(client):
    owner_id, owner_token, bob_token = _crew(client)
    _enable(client, owner_token, value="false")
    assert _react(client, bob_token, owner_id).status_code == 404


# ── Privacy ───────────────────────────────────────────────────────────────────

def test_shared_payload_carries_no_reactions(client):
    """The share token view stays minimal — reactions (and their mine flag,
    which is meaningless without a session) never reach the public URL."""
    owner_id, owner_token, bob_token = _crew(client)
    _react(client, bob_token, owner_id)

    token = client.post("/api/setup/me/share", headers=auth_header(owner_token)).json()["token"]
    shared = client.get("/api/setup/shared", headers={"X-Setup-Token": token})
    assert shared.status_code == 200
    assert "reactions" not in shared.json()
    assert "reaction_total" not in shared.json()


def test_deleting_nothing_but_the_reaction_rows_on_toggle_off(client):
    """A toggle-off deletes exactly the caller's row for that emoji."""
    owner_id, owner_token, bob_token = _crew(client)
    _react(client, owner_token, owner_id)
    _react(client, bob_token, owner_id)
    _react(client, bob_token, owner_id)  # off again

    session = database.SessionLocal()
    try:
        rows = session.query(models.SetupReaction).all()
        assert len(rows) == 1
        assert rows[0].emoji == "🔥"
    finally:
        session.close()
