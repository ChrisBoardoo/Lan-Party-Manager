"""The hidden costs the 2026-10-20 review measured (Q-1, Q-7), pinned so they
don't come back: the XP ledger is built once per request, and the kiosk, the
Hall of Fame and the events list don't do a query per row.

Query counts are compared between a small and a larger dataset rather than
asserted as absolute numbers: an N+1 shows as a count that grows with N.
"""
from datetime import date, datetime, timedelta

import database
import models
import xp
from conftest import auth_header, count_queries, login, make_user, register


def _add(*rows):
    s = database.SessionLocal()
    try:
        s.add_all(rows)
        s.commit()
        return [r.id for r in rows]
    finally:
        s.close()


def _set(client, token, key, value):
    client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(token)).raise_for_status()


def _tournaments(n, member_ids, organizer, event_id=None):
    """n completed single-elimination tournaments, 4 teams of 2 members, 3 matches."""
    s = database.SessionLocal()
    try:
        for i in range(n):
            t = models.Tournament(game_name=f"Game {i}", organizer_id=organizer, event_id=event_id,
                                  bracket_type="single_elimination", status="completed", max_team_size=2)
            s.add(t)
            s.flush()
            teams = []
            for k in range(4):
                team = models.Team(tournament_id=t.id, team_name=f"T{i}-{k}")
                s.add(team)
                s.flush()
                for uid in member_ids[(2 * k) % len(member_ids):(2 * k) % len(member_ids) + 2]:
                    s.add(models.TeamMember(team_id=team.id, player_name=f"u{uid}", user_id=uid))
                teams.append(team)
            at = datetime(2026, 10, 15, 20)
            s.add(models.Match(tournament_id=t.id, round="semifinal", round_number=1, match_number=1,
                               team_a_id=teams[0].id, team_b_id=teams[1].id, winner_id=teams[0].id,
                               status="completed", score_a=1, score_b=0, played_at=at))
            s.add(models.Match(tournament_id=t.id, round="semifinal", round_number=1, match_number=2,
                               team_a_id=teams[2].id, team_b_id=teams[3].id, winner_id=teams[2].id,
                               status="completed", score_a=1, score_b=0, played_at=at))
            s.add(models.Match(tournament_id=t.id, round="final", round_number=2, match_number=1,
                               team_a_id=teams[0].id, team_b_id=teams[2].id, winner_id=teams[0].id,
                               status="completed", score_a=1, score_b=0, played_at=at))
        s.commit()
    finally:
        s.close()


# ── Q-7: no query per row ─────────────────────────────────────────────────────

def test_kiosk_summary_does_not_grow_with_the_number_of_tournaments(client):
    register(client, "founder", "founder@example.com")
    admin = login(client, "founder")
    members = [make_user(f"m{i}") for i in range(8)]
    _set(client, admin, "kiosk_enabled", "true")
    token = client.post("/api/kiosk/admin/token", headers=auth_header(admin)).json()["token"]

    def summary():
        with count_queries() as q:
            r = client.get("/api/kiosk/summary", headers={"X-Kiosk-Token": token})
        assert r.status_code == 200, r.text
        return q.n

    _tournaments(2, members, organizer=1)
    small = summary()
    _tournaments(8, members, organizer=1)
    large = summary()
    assert large - small <= 2, (small, large)  # 84 queries for 8 tournaments before 1.4.1


def test_hall_of_fame_is_not_a_query_per_member(client):
    register(client, "founder", "founder@example.com")
    admin = login(client, "founder")
    few = [make_user(f"a{i}") for i in range(4)]
    _tournaments(1, few, organizer=1)
    with count_queries() as q:
        assert client.get("/api/tournaments/hall-of-fame", headers=auth_header(admin)).status_code == 200
    small = q.n
    many = [make_user(f"b{i}") for i in range(16)]
    _tournaments(2, many, organizer=1)
    with count_queries() as q:
        body = client.get("/api/tournaments/hall-of-fame", headers=auth_header(admin)).json()
    assert len(body) == 10  # the top 10 of 20 members
    assert q.n - small <= 1, (small, q.n)


def test_events_list_is_not_three_queries_per_event(client):
    register(client, "founder", "founder@example.com")
    admin = login(client, "founder")
    members = [make_user(f"m{i}") for i in range(5)]

    def events(n, start):
        for i in range(n):
            (eid,) = _add(models.LanEvent(title=f"LAN {start + i}", start_date=date(2027, 1, 1) + timedelta(days=30 * (start + i)),
                                          end_date=date(2027, 1, 3) + timedelta(days=30 * (start + i)), created_by=1))
            _add(*[models.EventRSVP(event_id=eid, user_id=uid, status="in") for uid in members])

    events(2, 0)
    with count_queries() as q:
        assert len(client.get("/api/events/", headers=auth_header(admin)).json()) == 2
    small = q.n
    events(8, 2)
    with count_queries() as q:
        body = client.get("/api/events/", headers=auth_header(admin)).json()
    assert len(body) == 10 and all(e["rsvp_count"] == 5 for e in body)
    assert q.n - small <= 1, (small, q.n)


# ── Q-1: one ledger per request, and a cache that drops on writes ─────────────

def test_cards_me_and_buy_build_the_xp_ledger_once(client, monkeypatch):
    register(client, "founder", "founder@example.com")
    admin = login(client, "founder")
    for name in ("alice", "bob", "carol"):
        make_user(name)
    (eid,) = _add(models.LanEvent(title="LAN", start_date=date.today() - timedelta(days=5),
                                  end_date=date.today() - timedelta(days=1), created_by=1))
    _add(*[models.EventRSVP(event_id=eid, user_id=uid, status="in") for uid in (1, 2, 3, 4)])
    _set(client, admin, "xp_enabled", "true")
    _set(client, admin, "cards_enabled", "true")
    _set(client, admin, "cards_since", (date.today() - timedelta(days=30)).isoformat())

    builds = {"n": 0}
    real = xp._build_ledger

    def counting(db):
        builds["n"] += 1
        return real(db)

    monkeypatch.setattr(xp, "_build_ledger", counting)
    alice = login(client, "alice")
    assert client.get("/api/cards/me", headers=auth_header(alice)).status_code == 200
    assert builds["n"] == 1, builds  # grants + balance, one build (was 2–3)
    builds["n"] = 0
    assert client.post("/api/cards/boosters/buy", headers=auth_header(alice)).status_code == 200
    assert builds["n"] == 1, builds


def test_the_ledger_cache_serves_within_the_ttl_and_drops_on_a_write(client, monkeypatch):
    make_user("alice")
    (eid,) = _add(models.LanEvent(title="LAN", start_date=date.today(), end_date=date.today(), created_by=1))
    monkeypatch.setattr(xp, "LEDGER_TTL_S", 30.0)
    xp.invalidate_ledger()
    s = database.SessionLocal()
    try:
        first = xp.build_ledger(s)
        assert xp.build_ledger(s) is first  # fresh: served from the cache
        # A chat message is the one XP source with no activity row: the cache
        # key (max id, count) catches it.
        s.add(models.ChatMessage(event_id=eid, user_id=1, content="hello there"))
        s.commit()
        second = xp.build_ledger(s)
        assert second is not first
        assert xp.build_ledger(s) is second
        xp.invalidate_ledger()  # what add_activity and the settings do
        assert xp.build_ledger(s) is not second
    finally:
        s.close()
        xp.invalidate_ledger()
