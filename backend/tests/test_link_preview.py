"""Tests for link_preview.py — the Craving Chat's Open Graph unfurl.

No real network calls: `_is_safe_public_host` on an IP literal resolves
instantly (no DNS lookup needed), so the SSRF guard is fully testable
offline, and `fetch_preview` short-circuits before ever opening a socket for
every case exercised here (bad scheme, blocked host).
"""
from link_preview import _is_safe_public_host, fetch_preview, first_url


def test_first_url_extracts_and_strips_trailing_punctuation():
    assert first_url("check this out: https://example.com/page.") == "https://example.com/page"
    assert first_url("no link here") is None
    assert first_url("(see https://example.com/x)") == "https://example.com/x"
    assert first_url("plain text https://a.com then https://b.com") == "https://a.com"


def test_safe_public_host_rejects_private_loopback_and_link_local():
    assert _is_safe_public_host("127.0.0.1") is False
    assert _is_safe_public_host("localhost") is False
    assert _is_safe_public_host("10.0.0.5") is False
    assert _is_safe_public_host("192.168.1.1") is False
    assert _is_safe_public_host("169.254.1.1") is False  # link-local
    assert _is_safe_public_host("0.0.0.0") is False


def test_safe_public_host_accepts_a_public_ip_literal():
    # A literal IP needs no real DNS lookup, so this stays network-free.
    assert _is_safe_public_host("8.8.8.8") is True


def test_fetch_preview_rejects_non_http_scheme_without_any_network_call():
    assert fetch_preview("ftp://example.com/file") is None
    assert fetch_preview("javascript:alert(1)") is None


def test_fetch_preview_rejects_ssrf_targets_without_any_network_call():
    assert fetch_preview("http://127.0.0.1:8000/admin") is None
    assert fetch_preview("http://169.254.169.254/latest/meta-data/") is None  # cloud metadata endpoint shape
    assert fetch_preview("http://localhost/") is None
