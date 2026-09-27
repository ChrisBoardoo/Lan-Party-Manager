"""Tests for the single-source feature-flag logic in ``/api/settings/public-config``.

Encodes the rules documented in ``router_settings.get_public_config``:
  * new opt-in features (sponsors, prizes) default OFF,
  * treasury defaults ON,
  * enabling prizes hides treasury everywhere.
"""

import pytest

from conftest import register, login, auth_header


@pytest.fixture
def admin(client):
    register(client, "founder", "founder@example.com")
    token = login(client, "founder")
    return token


def _set(client, token, key, value):
    resp = client.put(
        f"/api/settings/{key}", json={"value": value}, headers=auth_header(token)
    )
    resp.raise_for_status()
    return resp


def _config(client, token):
    resp = client.get("/api/settings/public-config", headers=auth_header(token))
    assert resp.status_code == 200
    return resp.json()


def test_defaults(client, admin):
    cfg = _config(client, admin)
    assert cfg["currency"] == "€"
    assert cfg["treasury_enabled"] is True
    assert cfg["sponsors_enabled"] is False
    assert cfg["prizes_enabled"] is False
    assert cfg["recap_enabled"] is False
    assert cfg["streams_enabled"] is True


def test_streams_explicit_off(client, admin):
    _set(client, admin, "streams_enabled", "false")
    assert _config(client, admin)["streams_enabled"] is False


def test_recap_toggle(client, admin):
    _set(client, admin, "recap_enabled", "true")
    assert _config(client, admin)["recap_enabled"] is True


def test_enabling_prizes_hides_treasury(client, admin):
    _set(client, admin, "prizes_enabled", "true")
    cfg = _config(client, admin)
    assert cfg["prizes_enabled"] is True
    assert cfg["treasury_enabled"] is False  # prizes takes treasury's place


def test_treasury_explicit_off(client, admin):
    _set(client, admin, "treasury_enabled", "false")
    cfg = _config(client, admin)
    assert cfg["treasury_enabled"] is False


def test_sponsors_toggle(client, admin):
    _set(client, admin, "sponsors_enabled", "true")
    assert _config(client, admin)["sponsors_enabled"] is True


def test_currency_reflected(client, admin):
    _set(client, admin, "currency", "$")
    assert _config(client, admin)["currency"] == "$"


def test_public_config_requires_auth(client):
    assert client.get("/api/settings/public-config").status_code == 401
