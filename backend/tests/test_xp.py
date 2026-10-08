"""Crew XP, derived on read.

Like the badges, every source is asserted both ways: it pays when the fact is
there, and it doesn't when the fact is missing (a bye, a draw, a closed trophy,
a video, an unlinked player). XP that fires on nothing is noise.
"""
from datetime import date, datetime
from types import SimpleNamespace as NS

import database
import models
from conftest import auth_header, login, make_user
from xp import (
    LEVEL_STEP_AFTER,
    _Ledger,
    add_tournament_xp,
    crew_xp,
    level_progress,
    title_for,
    user_xp,
)


# ── levels ────────────────────────────────────────────────────────────────────

def test_level_progress_boundaries():
    assert level_progress(0) == (1, 0, 50)
    assert level_progress(49) == (1, 0, 50)
    assert level_progress(50) == (2, 50, 150)
    assert level_progress(2999) == (9, 2300, 3000)
    assert level_progress(3000) == (10, 3000, 3000 + LEVEL_STEP_AFTER)
    assert level_progress(3000 + LEVEL_STEP_AFTER) == (11, 3800, 4600)
    assert level_progress(-5) == (1, 0, 50)


def test_titles_by_band():
    assert [title_for(n) for n in (1, 2, 3, 5, 7, 9, 10, 25)] == [
        "recruit", "recruit", "regular", "pillar", "veteran", "veteran", "legend", "legend",
    ]


# ── tournaments (duck-typed, no session) ──────────────────────────────────────

def _team(tid, *user_ids):
    return NS(id=tid, team_name=f"T{tid}", color=None, seed=None, members=[NS(user_id=u) for u in user_ids])


def _match(rnd, a, b, winner=None, score=(0, 0), status="completed", rn=1):
    return NS(
        round=rnd, round_number=rn, team_a_id=a, team_b_id=b, winner_id=winner,
        score_a=score[0], score_b=score[1], status=status, played_at=None,
    )


def _lines(ledger, uid):
    return {code: tuple(v) for code, v in ledger.rows.get(uid, {}).items()}


def test_bracket_pays_by_stage_plus_champion_bonus():
    # 4 teams; team 1 (users 1+2) wins semi + final, team 3 (user 3) wins the other semi.
    t = NS(
        bracket_type="single_elimination", status="completed",
        teams=[_team(1, 1, 2), _team(2, 4), _team(3, 3), _team(4, None)],
        matches=[
            _match("semifinal", 1, 2, winner=1),
            _match("semifinal", 3, 4, winner=3),
            _match("final", 1, 3, winner=1, rn=2),
        ],
    )
    ledger = _Ledger()
    add_tournament_xp(ledger, [t])

    assert _lines(ledger, 1) == {"match_semifinal": (1, 60), "match_final": (1, 100), "tournament_win": (1, 50)}
    assert _lines(ledger, 2) == _lines(ledger, 1)
    assert _lines(ledger, 3) == {"match_semifinal": (1, 60)}
    assert _lines(ledger, 4) == {}
    assert ledger.summary(1).total == 210


def test_bye_draw_pending_and_unlinked_pay_nothing():
    t = NS(
        bracket_type="round_robin", status="round_robin",
        teams=[_team(1, 1), _team(2, 2), _team(3, None)],
        matches=[
            _match("quarterfinal", 1, None, winner=1),               # bye: no opponent
            _match("round_1", 1, 2, score=(2, 2)),                   # draw
            _match("round_2", 1, 2, score=(3, 0), status="in_progress"),  # not decided
            _match("round_3", 3, 2, score=(1, 0)),                   # winner has no account
        ],
    )
    ledger = _Ledger()
    add_tournament_xp(ledger, [t])
    assert ledger.rows == {}


def test_round_robin_win_pays_the_flat_rate_and_no_bonus_until_completed():
    t = NS(
        bracket_type="round_robin", status="round_robin",
        teams=[_team(1, 1), _team(2, 2)],
        matches=[_match("round_1", 1, 2, score=(2, 0))],
    )
    ledger = _Ledger()
    add_tournament_xp(ledger, [t])
    assert _lines(ledger, 1) == {"match_other": (1, 15)}

    t.status = "completed"
    ledger = _Ledger()
    add_tournament_xp(ledger, [t])
    assert _lines(ledger, 1) == {"match_other": (1, 15), "tournament_win": (1, 50)}


def test_breakdown_order_and_zero_lines_hidden():
    ledger = _Ledger()
    ledger.add(1, "avatar", 10)
    ledger.add(1, "match_final", 100)
    ledger.add(1, "chat", 0, 12)  # under one step: counted, worth nothing yet
    s = ledger.summary(1)
    assert [line.code for line in s.breakdown] == ["match_final", "avatar"]
    assert (s.total, s.level, s.title) == (110, 2, "recruit")


# ── database sources ──────────────────────────────────────────────────────────

def _add(*rows):
    session = database.SessionLocal()
    try:
        session.add_all(rows)
        session.commit()
        return [r.id for r in rows]
    finally:
        session.close()


def _event(created_by):
    (eid,) = _add(models.LanEvent(
        title="LAN", start_date=date(2026, 10, 14), end_date=date(2026, 10, 18), created_by=created_by,
    ))
    return eid


def _media(uid, event_id, file_type="image"):
    return models.MediaItem(
        filename="f", original_name="f", file_type=file_type, mime_type="image/jpeg",
        file_size=1, url="/u/f", event_id=event_id, uploaded_by=uid,
    )


def _setting(key, value):
    _add(models.AppSetting(key=key, value=value))


def _summary(uid):
    session = database.SessionLocal()
    try:
        return user_xp(session, uid)
    finally:
        session.close()


def test_photos_capped_per_event_and_videos_ignored():
    uid = make_user("snap")
    e1, e2 = _event(uid), _event(uid)
    _add(*[_media(uid, e1) for _ in range(55)], *[_media(uid, e2) for _ in range(3)], _media(uid, e1, "video"))
    lines = {line.code: line for line in _summary(uid).breakdown}
    assert (lines["photo"].count, lines["photo"].xp) == (53, 106)


def test_chat_pays_per_step_with_a_daily_cap():
    uid = make_user("talker")
    eid = _event(uid)

    def msgs(n, day):
        return [
            models.ChatMessage(event_id=eid, user_id=uid, content="gg", created_at=datetime(2026, 10, day, 20, 0))
            for _ in range(n)
        ]

    _add(*msgs(29, 1))
    assert _summary(uid).breakdown == []  # 29 messages: not a full step yet

    # Day 1: 29 + 71 = 100 → capped at 60. Day 2: 25. Counted 85 → 2 steps.
    _add(*msgs(71, 1), *msgs(25, 2))
    lines = {line.code: line for line in _summary(uid).breakdown}
    assert (lines["chat"].count, lines["chat"].xp) == (85, 10)


def test_avatar_pays_once():
    uid = make_user("pic")
    assert _summary(uid).total == 0
    session = database.SessionLocal()
    try:
        session.get(models.User, uid).avatar_url = "/uploads/avatars/pic.jpg"
        session.commit()
    finally:
        session.close()
    assert [(l.code, l.xp) for l in _summary(uid).breakdown] == [("avatar", 10)]


def test_trophies_count_when_revealed_and_the_feature_is_on():
    uid = make_user("champ")
    eid = _event(uid)
    (trophy_id,) = _add(models.Trophy(name="Golden Rage-Quit"))
    (other_trophy,) = _add(models.Trophy(name="MVP"))
    revealed, closed = _add(
        models.EventTrophy(event_id=eid, trophy_id=trophy_id, mode="direct", status="revealed"),
        models.EventTrophy(event_id=eid, trophy_id=other_trophy, mode="vote", status="closed"),
    )
    _add(
        models.EventTrophyWinner(event_trophy_id=revealed, user_id=uid),
        models.EventTrophyWinner(event_trophy_id=closed, user_id=uid),
    )

    assert _summary(uid).total == 0  # trophies feature off: nothing leaks
    _setting("trophies_enabled", "true")
    assert [(l.code, l.count, l.xp) for l in _summary(uid).breakdown] == [("trophy", 1, 50)]


def test_crew_xp_ranks_best_first():
    a, b = make_user("a"), make_user("b")
    eid = _event(a)
    _add(*[_media(b, eid) for _ in range(5)])
    session = database.SessionLocal()
    try:
        users = session.query(models.User).order_by(models.User.id).all()
        assert [(s.user_id, s.total) for s in crew_xp(session, users)] == [(b, 10), (a, 0)]
    finally:
        session.close()


# ── API ───────────────────────────────────────────────────────────────────────

def test_endpoints_are_gated_but_admins_pass(client):
    make_user("boss", role="admin")
    uid = make_user("member")
    member = auth_header(login(client, "member"))
    admin = auth_header(login(client, "boss"))

    assert client.get("/api/xp/crew", headers=member).status_code == 404
    assert client.get(f"/api/xp/users/{uid}", headers=member).status_code == 404
    assert client.get("/api/xp/crew", headers=admin).status_code == 200
    assert client.get("/api/settings/public-config", headers=member).json()["xp_enabled"] is False

    _setting("xp_enabled", "true")
    assert client.get("/api/settings/public-config", headers=member).json()["xp_enabled"] is True
    body = client.get(f"/api/xp/users/{uid}", headers=member).json()
    assert body == {
        "user_id": uid, "total": 0, "level": 1, "level_floor": 0, "next_level_at": 50,
        "title": "recruit", "breakdown": [],
    }
    assert client.get("/api/xp/users/9999", headers=member).status_code == 404


def test_crew_leaves_out_deactivated_and_deleted_members(client):
    make_user("boss", role="admin")
    gone, deleted = make_user("gone"), make_user("deleted")
    _setting("xp_enabled", "true")
    session = database.SessionLocal()
    try:
        session.get(models.User, gone).is_active = False
        session.get(models.User, deleted).deleted_at = datetime(2026, 10, 1)
        session.commit()
    finally:
        session.close()

    body = client.get("/api/xp/crew", headers=auth_header(login(client, "boss"))).json()
    assert [row["username"] for row in body] == ["boss"]
    assert set(body[0]) == {"user_id", "username", "avatar_url", "total", "level", "title"}
