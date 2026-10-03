"""Guest WiFi — admin settings, who may read the password, and the kiosk.

The password is the one setting here that ordinary members get to read, so the
tests pin down exactly who: admins, and members with an "in" RSVP to the current
event. It must never ride along in /public-config, which every member can fetch.
"""
from datetime import date, timedelta

import database
import models
from conftest import auth_header, login, make_user


def _set(client, admin, key, value):
    resp = client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(admin))
    resp.raise_for_status()


def _configure(client, admin, ssid="LAN-Invites", password="Pizza;Froide42", security="WPA"):
    _set(client, admin, "wifi_ssid", ssid)
    _set(client, admin, "wifi_password", password)
    _set(client, admin, "wifi_security", security)


def _current_event(created_by):
    """An event running from today, so current_event() picks it."""
    session = database.SessionLocal()
    try:
        today = date.today()
        event = models.LanEvent(
            title="October LAN", start_date=today, end_date=today + timedelta(days=2), created_by=created_by
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event.id
    finally:
        session.close()


def _rsvp(event_id, user_id, status="in"):
    session = database.SessionLocal()
    try:
        session.add(models.EventRSVP(event_id=event_id, user_id=user_id, status=status))
        session.commit()
    finally:
        session.close()


def _setup(client):
    admin_id = make_user("founder", role="admin")
    admin = login(client, "founder")
    return admin_id, admin


def test_admin_reads_wifi(client):
    _, admin = _setup(client)
    _configure(client, admin)
    resp = client.get("/api/settings/wifi", headers=auth_header(admin))
    assert resp.status_code == 200
    assert resp.json() == {
        "ssid": "LAN-Invites", "password": "Pizza;Froide42", "security": "WPA", "hidden": False,
        "event_id": None,  # no event exists yet
    }


def test_null_when_no_ssid(client):
    _, admin = _setup(client)
    resp = client.get("/api/settings/wifi", headers=auth_header(admin))
    assert resp.status_code == 200
    assert resp.json() is None


def test_attendee_of_current_event_reads_wifi(client):
    admin_id, admin = _setup(client)
    _configure(client, admin)
    bob_id = make_user("bob")
    event_id = _current_event(admin_id)
    _rsvp(event_id, bob_id)
    resp = client.get("/api/settings/wifi", headers=auth_header(login(client, "bob")))
    assert resp.status_code == 200
    assert resp.json()["password"] == "Pizza;Froide42"
    assert resp.json()["event_id"] == event_id


def test_non_attendee_gets_404(client):
    admin_id, admin = _setup(client)
    _configure(client, admin)
    make_user("carol")  # no RSVP at all
    event_id = _current_event(admin_id)
    dave_id = make_user("dave")  # RSVP'd, but "out"
    _rsvp(event_id, dave_id, status="out")
    assert client.get("/api/settings/wifi", headers=auth_header(login(client, "carol"))).status_code == 404
    assert client.get("/api/settings/wifi", headers=auth_header(login(client, "dave"))).status_code == 404


def test_member_with_no_event_at_all_gets_404(client):
    _, admin = _setup(client)
    _configure(client, admin)
    make_user("bob")
    assert client.get("/api/settings/wifi", headers=auth_header(login(client, "bob"))).status_code == 404


def test_password_never_in_public_config(client):
    _, admin = _setup(client)
    _configure(client, admin)
    body = client.get("/api/settings/public-config", headers=auth_header(admin)).json()
    assert "Pizza;Froide42" not in str(body)
    assert not any(k.startswith("wifi") for k in body)


def test_open_network_drops_the_password(client):
    _, admin = _setup(client)
    _configure(client, admin, security="nopass")
    body = client.get("/api/settings/wifi", headers=auth_header(admin)).json()
    assert body["security"] == "nopass"
    assert body["password"] is None


def test_hidden_flag(client):
    _, admin = _setup(client)
    _configure(client, admin)
    _set(client, admin, "wifi_hidden", "true")
    assert client.get("/api/settings/wifi", headers=auth_header(admin)).json()["hidden"] is True


def test_rejects_unknown_security(client):
    _, admin = _setup(client)
    resp = client.put("/api/settings/wifi_security", json={"value": "WPA9"}, headers=auth_header(admin))
    assert resp.status_code == 400


def test_non_admin_cannot_write_wifi(client):
    _setup(client)
    make_user("bob")
    resp = client.put(
        "/api/settings/wifi_password", json={"value": "x"}, headers=auth_header(login(client, "bob"))
    )
    assert resp.status_code == 403


def test_kiosk_summary_carries_wifi_and_join_url(client):
    _, admin = _setup(client)
    _configure(client, admin)
    _set(client, admin, "app_base_url", "https://lan.example.com/")
    _set(client, admin, "kiosk_enabled", "true")
    token = client.post("/api/kiosk/admin/token", headers=auth_header(admin)).json()["token"]
    body = client.get("/api/kiosk/summary", headers={"X-Kiosk-Token": f"{token}"}).json()
    assert body["wifi"]["ssid"] == "LAN-Invites"
    assert body["wifi"]["password"] == "Pizza;Froide42"
    assert body["join_url"] == "https://lan.example.com"


def test_kiosk_summary_without_wifi(client):
    _, admin = _setup(client)
    _set(client, admin, "kiosk_enabled", "true")
    token = client.post("/api/kiosk/admin/token", headers=auth_header(admin)).json()["token"]
    body = client.get("/api/kiosk/summary", headers={"X-Kiosk-Token": f"{token}"}).json()
    assert body["wifi"] is None
    assert body["join_url"] is None
