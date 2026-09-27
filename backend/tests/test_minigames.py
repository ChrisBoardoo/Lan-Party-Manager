"""Tests for mini-game runs, score validation, and the leaderboard.

The validation rules are the point of this file: every gate in
``minigames_registry.validate_submission`` and every guard in ``router_minigames``
has a test that proves it rejects, because a leaderboard nobody trusts is worse
than no leaderboard.
"""

from datetime import datetime, timedelta

import pytest

import database
import models
from conftest import auth_header, login, make_user, register


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    return login(client, "founder")


@pytest.fixture
def enabled(client, admin):
    """Mini-games are opt-in; turn them on for the tests that need them."""
    resp = client.put(
        "/api/settings/minigames_enabled",
        json={"value": "true"},
        headers=auth_header(admin),
    )
    resp.raise_for_status()
    return admin


@pytest.fixture
def player(client, enabled):
    make_user("player")
    return login(client, "player")


def start_run(client, token, game="neon-survivor"):
    resp = client.post("/api/minigames/runs", json={"game": game}, headers=auth_header(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def submit(client, token, run_token, score, **details):
    return client.post(
        f"/api/minigames/runs/{run_token}/submit",
        json={"score": score, "details": details},
        headers=auth_header(token),
    )


def _backdate_run(run_token, seconds):
    """Move a run's start time into the past so a long run can be tested instantly."""
    session = database.SessionLocal()
    try:
        run = session.query(models.MiniGameRun).filter(models.MiniGameRun.token == run_token).first()
        run.started_at = datetime.utcnow() - timedelta(seconds=seconds)
        session.commit()
    finally:
        session.close()


# ── Feature flag ──────────────────────────────────────────────────────────────

def test_disabled_by_default(client, admin):
    cfg = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert cfg["minigames_enabled"] is False


def test_non_admin_blocked_while_disabled(client, admin):
    make_user("bystander")
    token = login(client, "bystander")
    resp = client.get("/api/minigames/games", headers=auth_header(token))
    assert resp.status_code == 404


def test_enabled_flag_opens_it(client, player):
    resp = client.get("/api/minigames/games", headers=auth_header(player))
    assert resp.status_code == 200
    slugs = [g["slug"] for g in resp.json()]
    assert "neon-survivor" in slugs


def test_registry_describes_the_metric(client, player):
    games = client.get("/api/minigames/games", headers=auth_header(player)).json()
    neon = next(g for g in games if g["slug"] == "neon-survivor")
    assert neon["metric"] == "seconds_survived"
    assert neon["max_score"] == 3600
    assert neon["higher_is_better"] is True


# ── Happy path ────────────────────────────────────────────────────────────────

def test_submit_accepted_and_appears_on_board(client, player):
    run = start_run(client, player)
    _backdate_run(run, 200)

    resp = submit(client, player, run, 180, kills=400, wave=7, level=12)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["personal_best"] is True
    assert body["rank"] == 1
    assert body["score"]["details"] == {"kills": 400, "wave": 7, "level": 12}

    board = client.get(
        "/api/minigames/leaderboard", params={"game": "neon-survivor"}, headers=auth_header(player)
    ).json()
    assert len(board) == 1
    assert board[0]["score"] == 180
    assert board[0]["user"]["username"] == "player"


def test_run_past_ten_minutes_is_accepted(client, player):
    """Regression: the final boss spawns at 600s and victory waits for it to die, so
    every run that reaches it ends past 10 minutes. The old 600s ceiling rejected them."""
    run = start_run(client, player)
    _backdate_run(run, 720)

    resp = submit(client, player, run, 700, kills=2500, wave=24, level=30)
    assert resp.status_code == 200, resp.text
    assert resp.json()["score"]["score"] == 700


def test_my_best_is_null_before_any_run(client, player):
    resp = client.get(
        "/api/minigames/me/best", params={"game": "neon-survivor"}, headers=auth_header(player)
    )
    assert resp.status_code == 200
    assert resp.json() is None


def test_personal_best_only_reported_when_improved(client, player):
    first = start_run(client, player)
    _backdate_run(first, 300)
    assert submit(client, player, first, 250, wave=9).json()["personal_best"] is True

    second = start_run(client, player)
    _backdate_run(second, 300)
    body = submit(client, player, second, 100, wave=4).json()
    assert body["personal_best"] is False

    best = client.get(
        "/api/minigames/me/best", params={"game": "neon-survivor"}, headers=auth_header(player)
    ).json()
    assert best["score"] == 250


def test_board_keeps_one_row_per_player(client, player):
    for score in (120, 300, 200):
        run = start_run(client, player)
        _backdate_run(run, 600)
        assert submit(client, player, run, score, wave=1 + score // 30).status_code == 200

    board = client.get(
        "/api/minigames/leaderboard", params={"game": "neon-survivor"}, headers=auth_header(player)
    ).json()
    assert len(board) == 1
    assert board[0]["score"] == 300


def test_board_is_sorted_best_first(client, enabled):
    scores = {"alice": 400, "bob": 120, "carol": 260}
    for name, score in scores.items():
        make_user(name)
        token = login(client, name)
        run = start_run(client, token)
        _backdate_run(run, 600)
        assert submit(client, token, run, score, wave=1 + score // 30).status_code == 200

    board = client.get(
        "/api/minigames/leaderboard", params={"game": "neon-survivor"}, headers=auth_header(enabled)
    ).json()
    assert [row["user"]["username"] for row in board] == ["alice", "carol", "bob"]


def test_personal_best_lands_in_the_activity_feed(client, player):
    run = start_run(client, player)
    _backdate_run(run, 200)
    submit(client, player, run, 150, wave=6)

    feed = client.get("/api/activity/", headers=auth_header(player)).json()
    entries = feed["items"] if isinstance(feed, dict) else feed
    best = next(e for e in entries if e["action"] == "minigame_best")
    # Same format as the leaderboard card next to it on the Hub: 150s reads 2:30,
    # not the raw 150 under the game's slug.
    assert best["description"] == "New personal best on Neon Survivor: 2:30"


# ── Validation: the gates that must reject ────────────────────────────────────

def test_score_above_the_games_ceiling_is_rejected(client, player):
    """Backdated well inside the token TTL, so this proves the ceiling rejects it —
    not the expiry guard, and not the elapsed-time check."""
    run = start_run(client, player)
    _backdate_run(run, 3600)
    resp = submit(client, player, run, 99999, wave=3334)
    assert resp.status_code == 400
    assert "maximum" in resp.json()["detail"]


def test_score_beyond_real_elapsed_time_is_rejected(client, player):
    """The core anti-forgery check: claim 400s one second after opening the run."""
    run = start_run(client, player)
    resp = submit(client, player, run, 400, wave=14)
    assert resp.status_code == 400
    assert "elapsed" in resp.json()["detail"]


def test_negative_score_is_rejected(client, player):
    run = start_run(client, player)
    resp = submit(client, player, run, -5)
    assert resp.status_code == 400


def test_impossible_wave_for_the_time_is_rejected(client, player):
    """wave is a pure function of the score in NeonSurvivor, so this pairing is forged."""
    run = start_run(client, player)
    _backdate_run(run, 200)
    resp = submit(client, player, run, 120, wave=90)
    assert resp.status_code == 400
    assert "wave" in resp.json()["detail"]


def test_implausible_kill_count_is_rejected(client, player):
    run = start_run(client, player)
    _backdate_run(run, 200)
    resp = submit(client, player, run, 120, kills=99999, wave=5)
    assert resp.status_code == 400
    assert "kills" in resp.json()["detail"]


def test_token_cannot_be_reused(client, player):
    run = start_run(client, player)
    _backdate_run(run, 300)
    assert submit(client, player, run, 200, wave=7).status_code == 200

    again = submit(client, player, run, 250, wave=9)
    assert again.status_code == 409


def test_rejected_submission_still_burns_the_token(client, player):
    """Otherwise a cheat just retries with a better-shaped payload on the same run."""
    run = start_run(client, player)
    _backdate_run(run, 300)
    assert submit(client, player, run, 250, wave=99).status_code == 400

    retry = submit(client, player, run, 250, wave=9)
    assert retry.status_code == 409


def test_another_players_token_is_not_usable(client, player, enabled):
    make_user("thief")
    thief = login(client, "thief")

    run = start_run(client, player)
    _backdate_run(run, 300)
    resp = submit(client, thief, run, 250, wave=9)
    assert resp.status_code == 404


def test_unknown_token_is_rejected(client, player):
    resp = submit(client, player, "not-a-real-token", 100)
    assert resp.status_code == 404


def test_expired_run_is_rejected(client, player):
    run = start_run(client, player)
    _backdate_run(run, int(timedelta(hours=13).total_seconds()))
    resp = submit(client, player, run, 300, wave=11)
    assert resp.status_code == 410


def test_unknown_game_is_rejected(client, player):
    resp = client.post(
        "/api/minigames/runs", json={"game": "not-a-game"}, headers=auth_header(player)
    )
    assert resp.status_code == 404


def test_unknown_detail_fields_are_dropped(client, player):
    """A tampered client must not be able to grow the row with arbitrary keys."""
    run = start_run(client, player)
    _backdate_run(run, 200)
    resp = submit(client, player, run, 150, wave=6, junk="x" * 5000, another=1)
    assert resp.status_code == 200
    assert resp.json()["score"]["details"] == {"wave": 6}


# ── Admin backstop ────────────────────────────────────────────────────────────

def test_admin_can_delete_an_outlier(client, player, enabled):
    run = start_run(client, player)
    _backdate_run(run, 300)
    score_id = submit(client, player, run, 250, wave=9).json()["score"]["id"]

    resp = client.delete(f"/api/minigames/scores/{score_id}", headers=auth_header(enabled))
    assert resp.status_code == 200

    board = client.get(
        "/api/minigames/leaderboard", params={"game": "neon-survivor"}, headers=auth_header(enabled)
    ).json()
    assert board == []


def test_member_cannot_delete_a_score(client, player, enabled):
    run = start_run(client, player)
    _backdate_run(run, 300)
    score_id = submit(client, player, run, 250, wave=9).json()["score"]["id"]

    resp = client.delete(f"/api/minigames/scores/{score_id}", headers=auth_header(player))
    assert resp.status_code == 403


# ── Derived badge ─────────────────────────────────────────────────────────────
#
# Exercised through badges.user_badges directly rather than the HTTP endpoint: that
# route is gated behind the *recap* feature, which is a different flag and not what
# these assert.

def _badge_codes(user_id):
    from badges import user_badges

    session = database.SessionLocal()
    try:
        return {a.code for a in user_badges(session, user_id)}
    finally:
        session.close()


def test_leader_earns_the_arcade_champion_badge(client, enabled):
    """Derived on read like every other badge — no achievements table involved."""
    user_id = make_user("leader")
    token = login(client, "leader")

    run = start_run(client, token)
    _backdate_run(run, 300)
    assert submit(client, token, run, 250, wave=9).status_code == 200

    assert "arcade_champion" in _badge_codes(user_id)


def test_runner_up_does_not_earn_the_badge(client, enabled):
    leader_id = make_user("leader")
    second_id = make_user("second")

    for name, score in (("leader", 400), ("second", 120)):
        token = login(client, name)
        run = start_run(client, token)
        _backdate_run(run, 600)
        assert submit(client, token, run, score, wave=1 + score // 30).status_code == 200

    assert "arcade_champion" in _badge_codes(leader_id)
    assert "arcade_champion" not in _badge_codes(second_id)


def test_no_badge_while_the_feature_is_off(client, admin):
    """The flag gates the badge too, so turning mini-games off doesn't leave a
    dangling achievement on someone's profile."""
    user_id = make_user("loner")
    assert "arcade_champion" not in _badge_codes(user_id)


# ── Registry: the clock gate must not apply to non-duration metrics ────────────
#
# Regression guard. The wall-clock bound was originally applied to every
# higher-is-better game, which is only correct when `score` literally counts seconds.
# A points-based game legitimately scores thousands in a few minutes, so the same rule
# would have rejected every honest run of it.

def test_clock_bound_only_applies_when_score_is_a_duration():
    from minigames_registry import MiniGameSpec, validate_submission

    points_game = MiniGameSpec(
        slug="points-game", metric="points", max_score=20000,
        score_is_elapsed_seconds=False,
    )
    # 7000 points after 300s: nonsense for a duration, normal for points.
    assert validate_submission(points_game, 7000, {}, elapsed_seconds=300) is None

    duration_game = MiniGameSpec(
        slug="duration-game", metric="seconds_survived", max_score=20000,
        score_is_elapsed_seconds=True,
    )
    err = validate_submission(duration_game, 7000, {}, elapsed_seconds=300)
    assert err is not None and "elapsed" in err


def test_check_receives_elapsed_time_so_duration_floors_can_be_game_specific():
    """Duration floors are never game-agnostic — "N waves need N x 10s" depends on the
    run's claimed progress. So `check` gets elapsed_seconds and owns the rule, instead
    of a flat per-game minimum that would reject an honest early loss."""
    from minigames_registry import MiniGameSpec, validate_submission

    seen = {}

    def check(score, details, elapsed_seconds):
        seen["elapsed"] = elapsed_seconds
        stages = details.get("stages")
        if stages is not None and elapsed_seconds < stages * 10:
            return f"{stages} stages cannot have been reached in {int(elapsed_seconds)}s"
        return None

    spec = MiniGameSpec(slug="slow-game", metric="points", max_score=20000, check=check)

    err = validate_submission(spec, 5000, {"stages": 20}, elapsed_seconds=40)
    assert err is not None and "cannot have been reached" in err
    assert seen["elapsed"] == 40

    # The same game, an honest short run: accepted, not caught by a blanket floor.
    assert validate_submission(spec, 300, {"stages": 2}, elapsed_seconds=45) is None


def test_neon_survivor_still_bounded_by_the_clock():
    """The existing game must keep the protection the flag was extracted from."""
    from minigames_registry import GAMES, validate_submission

    spec = GAMES["neon-survivor"]
    assert spec.score_is_elapsed_seconds is True
    err = validate_submission(spec, 400, {"wave": 14}, elapsed_seconds=1)
    assert err is not None and "elapsed" in err
