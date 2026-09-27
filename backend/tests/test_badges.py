"""Derived achievements.

Every badge is computed on read from data another feature already owns, so each
test asserts both the earning condition and — just as important — that the badge
is absent when it hasn't been earned. A badge that always fires is decoration,
not an achievement.
"""
from datetime import date, datetime

import database
import models
from badges import event_badges, user_badges


def _user(username, role="user"):
    from auth import get_password_hash

    session = database.SessionLocal()
    try:
        u = models.User(
            username=username, email=f"{username}@example.com",
            hashed_password=get_password_hash("password123"), role=role,
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        return u.id
    finally:
        session.close()


def _event(created_by, start=date(2026, 8, 1), end=date(2026, 8, 4)):
    session = database.SessionLocal()
    try:
        e = models.LanEvent(title="LAN", start_date=start, end_date=end, created_by=created_by)
        session.add(e)
        session.commit()
        session.refresh(e)
        return e.id
    finally:
        session.close()


def _rsvp(event_id, user_id, arrival, departure):
    session = database.SessionLocal()
    try:
        session.add(models.EventRSVP(
            event_id=event_id, user_id=user_id, status="in",
            arrival_date=arrival, departure_date=departure,
        ))
        session.commit()
    finally:
        session.close()


def _bracket(event_id, organizer_id, *, bracket_type="single_elimination", status="completed"):
    session = database.SessionLocal()
    try:
        t = models.Tournament(
            game_name="Valorant", bracket_type=bracket_type, event_type="team",
            organizer_id=organizer_id, event_id=event_id, status=status,
        )
        session.add(t)
        session.commit()
        session.refresh(t)
        return t.id
    finally:
        session.close()


def _team(tournament_id, name, member_ids):
    session = database.SessionLocal()
    try:
        team = models.Team(tournament_id=tournament_id, team_name=name)
        session.add(team)
        session.commit()
        session.refresh(team)
        for uid in member_ids:
            session.add(models.TeamMember(team_id=team.id, player_name=f"u{uid}", user_id=uid))
        session.commit()
        return team.id
    finally:
        session.close()


def _match(tournament_id, a, b, score_a, score_b, winner_id, played_at, rn=1):
    session = database.SessionLocal()
    try:
        session.add(models.Match(
            tournament_id=tournament_id, round="final", round_number=rn, match_number=1,
            team_a_id=a, team_b_id=b, score_a=score_a, score_b=score_b,
            winner_id=winner_id, status="completed", played_at=played_at,
        ))
        session.commit()
    finally:
        session.close()


def _media(event_id, uploaded_by, n=1):
    session = database.SessionLocal()
    try:
        ids = []
        for i in range(n):
            m = models.MediaItem(
                filename=f"m{uploaded_by}_{i}.jpg", original_name="p.jpg", file_type="image",
                mime_type="image/jpeg", file_size=10, url="/u/p.jpg",
                event_id=event_id, uploaded_by=uploaded_by,
            )
            session.add(m)
            session.commit()
            session.refresh(m)
            ids.append(m.id)
        return ids
    finally:
        session.close()


def _expense(event_id, paid_by, amount):
    session = database.SessionLocal()
    try:
        session.add(models.Expense(
            description="x", amount=amount, category="general", date=date(2026, 8, 2),
            created_by=paid_by, paid_by=paid_by, event_id=event_id,
        ))
        session.commit()
    finally:
        session.close()


def _set_flag(key, value):
    session = database.SessionLocal()
    try:
        session.add(models.AppSetting(key=key, value=value))
        session.commit()
    finally:
        session.close()


def _codes(event_id, *, include_financial=True):
    session = database.SessionLocal()
    try:
        event = session.query(models.LanEvent).filter_by(id=event_id).first()
        awards = event_badges(session, event, include_financial=include_financial)
        return {(a.code, a.user_id): a for a in awards}
    finally:
        session.close()


# ── champion ──────────────────────────────────────────────────────────────────

def test_champion_goes_to_the_winning_teams_members(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    event_id = _event(founder)
    t = _bracket(event_id, founder)
    winners = _team(t, "Winners", [founder])
    losers = _team(t, "Losers", [bob])
    _match(t, winners, losers, 13, 7, winners, datetime(2026, 8, 2, 21, 0))

    awards = _codes(event_id)
    assert ("champion", founder) in awards
    assert ("champion", bob) not in awards


def test_no_champion_without_a_completed_bracket(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    event_id = _event(founder)
    t = _bracket(event_id, founder, status="pending")
    _team(t, "A", [founder])
    _team(t, "B", [bob])

    assert not [k for k in _codes(event_id) if k[0] == "champion"]


def test_a_bracket_from_another_event_earns_nothing_here(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    ours = _event(founder)
    theirs = _event(founder, start=date(2026, 9, 1), end=date(2026, 9, 3))
    t = _bracket(theirs, founder)
    winners = _team(t, "Winners", [founder])
    losers = _team(t, "Losers", [bob])
    _match(t, winners, losers, 13, 7, winners, datetime(2026, 9, 2, 21, 0))

    assert not [k for k in _codes(ours) if k[0] == "champion"]


# ── undefeated ────────────────────────────────────────────────────────────────

def test_undefeated_needs_two_played_and_no_losses(client):
    founder, bob, carol = _user("founder", role="admin"), _user("bob"), _user("carol")
    event_id = _event(founder)
    t = _bracket(event_id, founder, bracket_type="round_robin")
    a = _team(t, "A", [founder])
    b = _team(t, "B", [bob])
    c = _team(t, "C", [carol])
    _match(t, a, b, 2, 0, a, datetime(2026, 8, 2, 20, 0))
    _match(t, a, c, 2, 0, a, datetime(2026, 8, 2, 21, 0))
    _match(t, b, c, 2, 0, b, datetime(2026, 8, 2, 22, 0))

    awards = _codes(event_id)
    assert ("undefeated", founder) in awards   # 2 played, 0 lost
    assert ("undefeated", bob) not in awards   # lost one


def test_a_single_win_is_not_undefeated(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    event_id = _event(founder)
    t = _bracket(event_id, founder)
    a = _team(t, "A", [founder])
    b = _team(t, "B", [bob])
    _match(t, a, b, 1, 0, a, datetime(2026, 8, 2, 20, 0))

    assert not [k for k in _codes(event_id) if k[0] == "undefeated"]


# ── first_blood ───────────────────────────────────────────────────────────────

def test_first_blood_goes_to_the_earliest_match_winner(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    event_id = _event(founder)
    t = _bracket(event_id, founder, bracket_type="round_robin")
    a = _team(t, "A", [founder])
    b = _team(t, "B", [bob])
    _match(t, b, a, 1, 0, b, datetime(2026, 8, 2, 18, 0))   # earliest
    _match(t, a, b, 1, 0, a, datetime(2026, 8, 2, 23, 0))

    awards = _codes(event_id)
    assert ("first_blood", bob) in awards
    assert ("first_blood", founder) not in awards


# ── night_owl ─────────────────────────────────────────────────────────────────

def test_night_owl_goes_to_the_longest_stay(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    event_id = _event(founder)
    _rsvp(event_id, founder, date(2026, 8, 1), date(2026, 8, 4))  # 3 nights
    _rsvp(event_id, bob, date(2026, 8, 3), date(2026, 8, 4))      # 1 night

    awards = _codes(event_id)
    assert ("night_owl", founder) in awards
    assert awards[("night_owl", founder)].value == 3
    assert ("night_owl", bob) not in awards


def test_night_owl_is_shared_on_a_tie(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    event_id = _event(founder)
    _rsvp(event_id, founder, date(2026, 8, 1), date(2026, 8, 4))
    _rsvp(event_id, bob, date(2026, 8, 1), date(2026, 8, 4))

    awards = _codes(event_id)
    assert ("night_owl", founder) in awards
    assert ("night_owl", bob) in awards


def test_night_owl_stay_is_clamped_to_the_event_window(client):
    # Someone who books a week either side didn't stay seven nights at the LAN.
    founder = _user("founder", role="admin")
    event_id = _event(founder, start=date(2026, 8, 1), end=date(2026, 8, 4))
    _rsvp(event_id, founder, date(2026, 7, 20), date(2026, 8, 20))

    assert _codes(event_id)[("night_owl", founder)].value == 3


def test_no_night_owl_when_nobody_stayed_a_night(client):
    founder = _user("founder", role="admin")
    event_id = _event(founder)
    _rsvp(event_id, founder, date(2026, 8, 1), date(2026, 8, 1))  # day tripper

    assert not [k for k in _codes(event_id) if k[0] == "night_owl"]


# ── shutterbug / crowd_pleaser ────────────────────────────────────────────────

def test_shutterbug_goes_to_the_biggest_uploader(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    event_id = _event(founder)
    _media(event_id, bob, n=3)
    _media(event_id, founder, n=1)

    awards = _codes(event_id)
    assert ("shutterbug", bob) in awards
    assert awards[("shutterbug", bob)].value == 3
    assert ("shutterbug", founder) not in awards


def test_no_shutterbug_without_uploads(client):
    founder = _user("founder", role="admin")
    event_id = _event(founder)
    assert not [k for k in _codes(event_id) if k[0] == "shutterbug"]


def test_crowd_pleaser_goes_to_the_most_reacted_items_uploader(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    event_id = _event(founder)
    (bobs_photo,) = _media(event_id, bob, n=1)
    (founders_photo,) = _media(event_id, founder, n=1)

    session = database.SessionLocal()
    try:
        session.add(models.MediaReaction(media_id=bobs_photo, user_id=founder, emoji="😂"))
        session.add(models.MediaReaction(media_id=bobs_photo, user_id=bob, emoji="🔥"))
        session.add(models.MediaReaction(media_id=founders_photo, user_id=bob, emoji="🔥"))
        session.commit()
    finally:
        session.close()

    awards = _codes(event_id)
    assert ("crowd_pleaser", bob) in awards
    assert ("crowd_pleaser", founder) not in awards


def test_no_crowd_pleaser_without_reactions(client):
    founder = _user("founder", role="admin")
    event_id = _event(founder)
    _media(event_id, founder, n=2)
    assert not [k for k in _codes(event_id) if k[0] == "crowd_pleaser"]


# ── quartermaster (gear-gated) ────────────────────────────────────────────────

def test_quartermaster_requires_the_gear_feature(client):
    founder = _user("founder", role="admin")
    event_id = _event(founder)
    session = database.SessionLocal()
    try:
        session.add(models.GearItem(
            event_id=event_id, name="Switch", pledged_by=founder, created_by=founder,
        ))
        session.commit()
    finally:
        session.close()

    assert not [k for k in _codes(event_id) if k[0] == "quartermaster"]

    _set_flag("gear_enabled", "true")
    assert ("quartermaster", founder) in _codes(event_id)


# ── snack_sponsor (financial, gated twice) ────────────────────────────────────

def test_snack_sponsor_goes_to_the_biggest_payer(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    event_id = _event(founder)
    _expense(event_id, founder, 100.0)
    _expense(event_id, bob, 10.0)

    awards = _codes(event_id)
    assert ("snack_sponsor", founder) in awards
    assert ("snack_sponsor", bob) not in awards


def test_snack_sponsor_is_withheld_from_a_shared_recap(client):
    """include_financial=False is what the public share link passes."""
    founder = _user("founder", role="admin")
    event_id = _event(founder)
    _expense(event_id, founder, 100.0)

    assert ("snack_sponsor", founder) in _codes(event_id, include_financial=True)
    assert not [k for k in _codes(event_id, include_financial=False) if k[0] == "snack_sponsor"]


def test_snack_sponsor_respects_the_treasury_flag(client):
    founder = _user("founder", role="admin")
    event_id = _event(founder)
    _expense(event_id, founder, 100.0)
    _set_flag("treasury_enabled", "false")

    assert not [k for k in _codes(event_id) if k[0] == "snack_sponsor"]


# ── all-time (profile) badges ─────────────────────────────────────────────────

def _all_time(user_id):
    session = database.SessionLocal()
    try:
        return {a.code: a for a in user_badges(session, user_id)}
    finally:
        session.close()


def test_veteran_needs_three_attended_events(client):
    founder = _user("founder", role="admin")
    for i in range(2):
        _rsvp(_event(founder), founder, date(2026, 8, 1), date(2026, 8, 2))
    assert "veteran" not in _all_time(founder)

    _rsvp(_event(founder), founder, date(2026, 8, 1), date(2026, 8, 2))
    assert _all_time(founder)["veteran"].value == 3


def test_all_time_champion_counts_wins_across_events(client):
    founder, bob = _user("founder", role="admin"), _user("bob")
    for start in (date(2026, 8, 1), date(2026, 9, 1)):
        event_id = _event(founder, start=start, end=start)
        t = _bracket(event_id, founder)
        winners = _team(t, "W", [founder])
        losers = _team(t, "L", [bob])
        _match(t, winners, losers, 1, 0, winners, datetime(2026, 8, 2, 20, 0))

    assert _all_time(founder)["champion"].value == 2
    assert "champion" not in _all_time(bob)


def test_all_time_shutterbug_has_a_threshold(client):
    founder = _user("founder", role="admin")
    event_id = _event(founder)
    _media(event_id, founder, n=24)
    assert "shutterbug" not in _all_time(founder)

    _media(event_id, founder, n=1)
    assert _all_time(founder)["shutterbug"].value == 25


def test_badges_for_an_unknown_user_are_empty(client):
    assert _all_time(999) == {}
