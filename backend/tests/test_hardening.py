"""Hardening from the 2026-10 review: roles, usernames, activity visibility,
rate-limit buckets, invite codes, and the treasury's default event."""

from datetime import date, timedelta
from types import SimpleNamespace

import database
import event_utils
import models
from conftest import auth_header, login, make_user
from limiter import client_key


def _audit(action):
    s = database.SessionLocal()
    try:
        return [a.details for a in s.query(models.AuditLog).filter_by(action=action).all()]
    finally:
        s.close()


# ── roles ──────────────────────────────────────────────────────────────────────

def test_the_last_admin_cannot_demote_themselves(client):
    uid = make_user("admin", role="admin")
    token = login(client, "admin")
    resp = client.put(f"/api/users/{uid}/role", params={"role": "user"}, headers=auth_header(token))
    assert resp.status_code == 400


def test_role_changes_are_audited(client):
    make_user("admin", role="admin")
    bob = make_user("bob")
    token = login(client, "admin")
    assert client.put(f"/api/users/{bob}/role", params={"role": "treasurer"}, headers=auth_header(token)).status_code == 200
    assert _audit("role_changed") == ["User: bob — user → treasurer"]


# ── usernames ──────────────────────────────────────────────────────────────────

def test_username_uniqueness_ignores_case(client):
    uid = make_user("alice")
    make_user("Bob")
    token = login(client, "alice")
    resp = client.put(f"/api/users/{uid}", json={"username": "BOB"}, headers=auth_header(token))
    assert resp.status_code == 400


def test_deleted_user_prefix_is_reserved(client):
    uid = make_user("alice")
    token = login(client, "alice")
    resp = client.put(f"/api/users/{uid}", json={"username": "deleted_user_7"}, headers=auth_header(token))
    assert resp.status_code == 422  # refused by the schema's username check


# ── activity ───────────────────────────────────────────────────────────────────

def test_cannot_react_to_someone_elses_targeted_entry(client):
    alice, bob, cara = make_user("alice"), make_user("bob"), make_user("cara")
    s = database.SessionLocal()
    try:
        entry = models.ActivityLog(user_id=alice, action="chat_mention", description="mentioned you",
                                   recipient_user_id=bob)
        s.add(entry)
        s.commit()
        entry_id = entry.id
    finally:
        s.close()
    cara_t, bob_t = login(client, "cara"), login(client, "bob")
    body = {"emoji": "🔥"}
    assert client.post(f"/api/activity/{entry_id}/react", json=body, headers=auth_header(cara_t)).status_code == 404
    assert client.post(f"/api/activity/{entry_id}/react", json=body, headers=auth_header(bob_t)).status_code == 200


# ── rate-limit buckets ─────────────────────────────────────────────────────────

def _req(host):
    return SimpleNamespace(client=SimpleNamespace(host=host), headers={}, scope={})


def test_ipv6_clients_are_bucketed_by_their_64():
    assert client_key(_req("2001:db8:1:2:aaaa::1")) == client_key(_req("2001:db8:1:2:bbbb::9"))
    assert client_key(_req("2001:db8:1:3::1")) != client_key(_req("2001:db8:1:2::1"))
    assert client_key(_req("203.0.113.7")) == "203.0.113.7"


# ── invite codes ───────────────────────────────────────────────────────────────

def _event_with_invite(start, end, code="ABCDEF"):
    s = database.SessionLocal()
    try:
        admin = s.query(models.User).filter_by(role="admin").first()
        ev = models.LanEvent(title="LAN", start_date=start, end_date=end, created_by=admin.id)
        s.add(ev)
        s.flush()
        s.add(models.EventInvite(event_id=ev.id, code=code, created_by=admin.id))
        s.commit()
        return ev.id
    finally:
        s.close()


def test_invite_code_of_a_finished_event_no_longer_works(client):
    make_user("admin", role="admin")
    _event_with_invite(date.today() - timedelta(days=10), date.today() - timedelta(days=8), code="OLDCODE")
    assert client.get("/api/events/invite/validate/OLDCODE").json()["valid"] is False
    _event_with_invite(date.today() + timedelta(days=3), date.today() + timedelta(days=5), code="NEWCODE")
    assert client.get("/api/events/invite/validate/NEWCODE").json()["valid"] is True


def test_new_invite_codes_are_ten_characters(client):
    import router_events
    s = database.SessionLocal()
    try:
        assert len(router_events._generate_invite_code(s)) == 10
    finally:
        s.close()


# ── treasury default event ─────────────────────────────────────────────────────

def test_treasury_stays_on_the_lan_that_just_ended(client):
    make_user("admin", role="admin")
    s = database.SessionLocal()
    try:
        admin = s.query(models.User).first().id
        today = date.today()
        just_ended = models.LanEvent(title="October", start_date=today - timedelta(days=6),
                                     end_date=today - timedelta(days=2), created_by=admin)
        next_year = models.LanEvent(title="Next", start_date=today + timedelta(days=300),
                                    end_date=today + timedelta(days=303), created_by=admin)
        s.add_all([just_ended, next_year])
        s.commit()
        assert event_utils.treasury_default_event(s).title == "October"
        assert event_utils.current_event(s).title == "Next"
    finally:
        s.close()
