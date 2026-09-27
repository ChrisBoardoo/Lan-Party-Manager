"""The post-event recap: aggregation, the feature gate, and the share link.

The share-link tests are the important ones. A recap token is a public URL, so
the rule is absolute: no money reaches it, ever. The kiosk learned this the hard
way (its token used to ride in a query string, and a non-ASCII token 500'd
instead of 401'ing) — those lessons are re-asserted here rather than rediscovered.
"""
from datetime import date, datetime

import database
import models
from conftest import auth_header, login, make_user


def _enable(client, token, feature="recap_enabled"):
    resp = client.put(f"/api/settings/{feature}", json={"value": "true"}, headers=auth_header(token))
    resp.raise_for_status()


def _disable(client, token, feature):
    resp = client.put(f"/api/settings/{feature}", json={"value": "false"}, headers=auth_header(token))
    resp.raise_for_status()


def _event(created_by, title="Summer LAN"):
    session = database.SessionLocal()
    try:
        event = models.LanEvent(
            title=title, start_date=date(2026, 8, 1), end_date=date(2026, 8, 3), created_by=created_by
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event.id
    finally:
        session.close()


def _seed_full_event(founder_id, bob_id):
    """One event with attendance, a finished bracket, an expense and a photo."""
    session = database.SessionLocal()
    try:
        event = models.LanEvent(
            title="Summer LAN", start_date=date(2026, 8, 1), end_date=date(2026, 8, 3),
            created_by=founder_id,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        session.add(models.EventRSVP(
            event_id=event.id, user_id=founder_id, status="in",
            arrival_date=date(2026, 8, 1), departure_date=date(2026, 8, 3),  # 2 nights
        ))
        session.add(models.EventRSVP(
            event_id=event.id, user_id=bob_id, status="in",
            arrival_date=date(2026, 8, 2), departure_date=date(2026, 8, 3),  # 1 night
        ))

        tournament = models.Tournament(
            game_name="Valorant", bracket_type="single_elimination", event_type="team",
            organizer_id=founder_id, event_id=event.id, status="completed",
        )
        session.add(tournament)
        session.commit()
        session.refresh(tournament)

        winners = models.Team(tournament_id=tournament.id, team_name="Winners", color="#f00")
        losers = models.Team(tournament_id=tournament.id, team_name="Losers", color="#00f")
        session.add_all([winners, losers])
        session.commit()
        session.refresh(winners)
        session.refresh(losers)

        session.add(models.TeamMember(team_id=winners.id, player_name="founder", user_id=founder_id))
        session.add(models.TeamMember(team_id=losers.id, player_name="bob", user_id=bob_id))
        session.add(models.Match(
            tournament_id=tournament.id, round="final", round_number=1, match_number=1,
            team_a_id=winners.id, team_b_id=losers.id, score_a=13, score_b=7,
            winner_id=winners.id, status="completed", played_at=datetime(2026, 8, 2, 21, 0),
        ))

        session.add(models.Expense(
            description="Pizza", amount=90.0, category="food", date=date(2026, 8, 2),
            created_by=founder_id, paid_by=founder_id, event_id=event.id,
        ))
        session.add(models.MediaItem(
            filename="p.jpg", original_name="p.jpg", file_type="image", mime_type="image/jpeg",
            file_size=100, url="/uploads/media/p.jpg", event_id=event.id, uploaded_by=bob_id,
        ))
        session.commit()
        return event.id
    finally:
        session.close()


def _recap(client, token, event_id):
    resp = client.get(f"/api/recap/{event_id}", headers=auth_header(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── The gate ──────────────────────────────────────────────────────────────────

def test_member_gets_404_while_the_feature_is_off(client):
    founder_id = make_user("founder", role="admin")
    make_user("bob")
    event_id = _event(founder_id)
    assert client.get(f"/api/recap/{event_id}", headers=auth_header(login(client, "bob"))).status_code == 404


def test_admin_passes_the_gate_so_they_can_configure_it(client):
    founder_id = make_user("founder", role="admin")
    event_id = _event(founder_id)
    assert client.get(f"/api/recap/{event_id}", headers=auth_header(login(client, "founder"))).status_code == 200


def test_member_gets_the_recap_once_enabled(client):
    founder_id = make_user("founder", role="admin")
    make_user("bob")
    event_id = _event(founder_id)
    _enable(client, login(client, "founder"))
    assert client.get(f"/api/recap/{event_id}", headers=auth_header(login(client, "bob"))).status_code == 200


def test_unknown_event_is_404(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    assert client.get("/api/recap/999", headers=auth_header(token)).status_code == 404


# ── Aggregation ───────────────────────────────────────────────────────────────

def test_recap_reflects_the_seeded_event(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    event_id = _seed_full_event(founder_id, bob_id)
    token = login(client, "founder")
    _enable(client, token)

    data = _recap(client, token, event_id)

    assert data["event"]["title"] == "Summer LAN"
    assert data["event"]["nights"] == 2
    assert data["attendance"]["attendee_count"] == 2
    assert data["attendance"]["total_person_nights"] == 3  # 2 + 1
    assert data["attendance"]["longest_stay"] == 2
    assert data["media"]["total"] == 1
    assert data["media"]["photo_count"] == 1
    assert data["shared"] is False

    assert len(data["tournaments"]) == 1
    assert data["tournaments"][0]["champion"]["team_name"] == "Winners"
    assert data["mvp"]["username"] == "founder"
    assert data["mvp"]["wins"] == 1


def test_recap_money_is_present_with_treasury_on(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    event_id = _seed_full_event(founder_id, bob_id)
    token = login(client, "founder")
    _enable(client, token)

    money = _recap(client, token, event_id)["money"]
    assert money["total_expenses"] == 90.0
    assert money["currency"] == "€"
    # Aggregates only — the ledger stays on the Treasury page.
    assert "shares" not in money
    assert "settlements" not in money


def test_recap_money_is_absent_with_treasury_off(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    event_id = _seed_full_event(founder_id, bob_id)
    token = login(client, "founder")
    _enable(client, token)
    _disable(client, token, "treasury_enabled")

    assert _recap(client, token, event_id)["money"] is None


def test_recap_only_counts_its_own_event(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    event_id = _seed_full_event(founder_id, bob_id)
    other_id = _event(founder_id, title="Other LAN")

    session = database.SessionLocal()
    try:
        session.add(models.Expense(
            description="Other", amount=500.0, category="general", date=date(2026, 9, 1),
            created_by=founder_id, paid_by=founder_id, event_id=other_id,
        ))
        session.commit()
    finally:
        session.close()

    token = login(client, "founder")
    _enable(client, token)
    assert _recap(client, token, event_id)["money"]["total_expenses"] == 90.0


# ── Sharing ───────────────────────────────────────────────────────────────────

def _mint(client, token, event_id):
    resp = client.post(f"/api/recap/{event_id}/share", headers=auth_header(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _shared(client, share_token):
    return client.get("/api/recap/shared", headers={"X-Recap-Token": share_token})


def test_shared_recap_never_includes_money(client):
    """The whole point of the rule: a public URL is the internet."""
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    event_id = _seed_full_event(founder_id, bob_id)
    token = login(client, "founder")
    _enable(client, token)

    # Sanity: the authenticated view *does* have money, so absence below is the
    # share rule at work rather than an empty fixture.
    assert _recap(client, token, event_id)["money"] is not None

    share_token = _mint(client, token, event_id)
    resp = _shared(client, share_token)
    assert resp.status_code == 200
    data = resp.json()

    assert data["money"] is None
    assert data["shared"] is True
    assert data["event"]["title"] == "Summer LAN"          # the fun stuff survives
    assert data["tournaments"][0]["champion"]["team_name"] == "Winners"
    assert [b["code"] for b in data["badges"]], "expected non-financial badges to survive"
    assert "snack_sponsor" not in [b["code"] for b in data["badges"]]


def test_shared_recap_leaks_no_emails_or_phones(client):
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    event_id = _seed_full_event(founder_id, bob_id)
    token = login(client, "founder")
    _enable(client, token)
    share_token = _mint(client, token, event_id)

    body = _shared(client, share_token).text
    assert "@example.com" not in body


def test_shared_recap_reaction_tallies_carry_no_usernames(client):
    """Reaction tallies keep their counts on the public link, but the `users`
    lists (who reacted — the hover tooltip) are for logged-in members only:
    hydrate_reactions leaves them empty when viewer_id is None."""
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    event_id = _seed_full_event(founder_id, bob_id)
    token = login(client, "founder")
    _enable(client, token)

    media_id = client.get("/api/media/", headers=auth_header(token)).json()[0]["id"]
    resp = client.post(f"/api/media/{media_id}/react", json={"emoji": "🔥"}, headers=auth_header(token))
    assert resp.status_code == 200

    # Sanity: the authenticated recap names the reactor…
    mine = _recap(client, token, event_id)
    assert mine["media"]["top"][0]["reactions"][0]["users"] == ["founder"]

    # …the public one keeps the count and drops the name.
    share_token = _mint(client, token, event_id)
    data = _shared(client, share_token).json()
    tally = data["media"]["top"][0]["reactions"][0]
    assert tally["count"] == 1
    assert tally["users"] == []


def test_wrong_share_token_is_401(client):
    founder_id = make_user("founder", role="admin")
    event_id = _event(founder_id)
    token = login(client, "founder")
    _enable(client, token)
    _mint(client, token, event_id)

    assert _shared(client, "not-the-token").status_code == 401


def test_missing_share_token_is_401(client):
    make_user("founder", role="admin")
    _enable(client, login(client, "founder"))
    assert client.get("/api/recap/shared").status_code == 401


def test_non_ascii_share_token_is_401_not_500(client):
    """secrets.compare_digest raises TypeError on a non-ASCII *str*, which would
    surface as a 500 rather than a clean 401 — the bug the kiosk shipped.

    The recap token is header-only, and HTTP headers are ASCII by spec, so a
    non-ASCII token can't even reach the endpoint over the wire (httpx refuses to
    encode it). That's the kiosk's real lesson: its token was reachable *because*
    it also accepted ?token= in the query string. The bytes-compare is still
    defence-in-depth for any future caller, so exercise the dependency directly
    where a non-ASCII string is actually expressible.
    """
    import database
    from fastapi import HTTPException
    from router_recap import require_recap_token

    founder_id = make_user("founder", role="admin")
    event_id = _event(founder_id)
    token = login(client, "founder")
    _enable(client, token)
    _mint(client, token, event_id)

    session = database.SessionLocal()
    try:
        try:
            require_recap_token(x_recap_token="tökén-with-ümlauts", db=session)
            raised = None
        except HTTPException as exc:
            raised = exc.status_code
        except TypeError:  # what compare_digest does to a non-ASCII str
            raised = 500
        assert raised == 401
    finally:
        session.close()


def test_share_endpoint_is_404_while_the_feature_is_off(client):
    """Even a valid token must not work when the feature is off — the surface
    stays invisible, exactly like the kiosk."""
    founder_id = make_user("founder", role="admin")
    event_id = _event(founder_id)
    token = login(client, "founder")
    _enable(client, token)
    share_token = _mint(client, token, event_id)

    _disable(client, token, "recap_enabled")
    assert _shared(client, share_token).status_code == 404


def test_revoking_kills_the_link(client):
    founder_id = make_user("founder", role="admin")
    event_id = _event(founder_id)
    token = login(client, "founder")
    _enable(client, token)
    share_token = _mint(client, token, event_id)
    assert _shared(client, share_token).status_code == 200

    assert client.delete(f"/api/recap/{event_id}/share", headers=auth_header(token)).status_code == 200
    assert _shared(client, share_token).status_code == 401


def test_rotating_invalidates_the_old_link(client):
    founder_id = make_user("founder", role="admin")
    event_id = _event(founder_id)
    token = login(client, "founder")
    _enable(client, token)

    first = _mint(client, token, event_id)
    second = _mint(client, token, event_id)
    assert first != second
    assert _shared(client, first).status_code == 401
    assert _shared(client, second).status_code == 200


def test_a_member_cannot_mint_a_share_link(client):
    founder_id = make_user("founder", role="admin")
    make_user("bob")
    event_id = _event(founder_id)
    _enable(client, login(client, "founder"))

    resp = client.post(f"/api/recap/{event_id}/share", headers=auth_header(login(client, "bob")))
    assert resp.status_code == 403


def test_minting_while_disabled_is_404_even_for_an_admin(client):
    """require_feature waves admins through, so admin writes re-check the flag."""
    founder_id = make_user("founder", role="admin")
    event_id = _event(founder_id)
    token = login(client, "founder")
    assert client.post(f"/api/recap/{event_id}/share", headers=auth_header(token)).status_code == 404


def test_get_share_reports_the_current_token(client):
    founder_id = make_user("founder", role="admin")
    event_id = _event(founder_id)
    token = login(client, "founder")
    _enable(client, token)

    before = client.get(f"/api/recap/{event_id}/share", headers=auth_header(token)).json()
    assert before["token"] is None

    minted = _mint(client, token, event_id)
    after = client.get(f"/api/recap/{event_id}/share", headers=auth_header(token)).json()
    assert after["token"] == minted


def test_each_event_gets_its_own_share_token(client):
    founder_id = make_user("founder", role="admin")
    first_id = _event(founder_id, title="First")
    second_id = _event(founder_id, title="Second")
    token = login(client, "founder")
    _enable(client, token)

    first_token = _mint(client, token, first_id)
    second_token = _mint(client, token, second_id)

    assert _shared(client, first_token).json()["event"]["title"] == "First"
    assert _shared(client, second_token).json()["event"]["title"] == "Second"
