"""Best-effort Open Graph link preview for the Craving Chat — "paste a link,
get a WhatsApp-style card" per crew feedback. Fetched server-side (not from
the viewer's browser, which would mean CORS problems and a different result
per viewer) and cached on the message row, so every viewer sees the same
preview and it's only ever fetched once per message.

Fetching a URL a user pasted is inherently untrusted-input territory —
mitigated here, not eliminated:

  * scheme restricted to http/https
  * the resolved IP is checked against private/loopback/link-local/reserved/
    multicast ranges before connecting — blocks the classic "paste
    http://192.168.1.1/admin and read the response back as a preview" SSRF
    against the box's own LAN (this app is self-hosted, so "the LAN" is a
    real, sensitive network here, not just a cloud metadata endpoint)
  * response size, content-type, and redirect count are all capped
  * any failure (timeout, blocked host, non-HTML, no usable OG tags) just
    means no preview — never an error surfaced back to the sender

Residual limitation: the safety check resolves DNS once before connecting; a
DNS-rebinding attack (the domain resolves to a public IP at check time, a
private one at actual connect time) isn't fully closed by this. Acceptable
for a self-hosted app used by a trusted-ish crew, not a hardened multi-tenant
service — revisit with a pinned-IP transport if that threat model changes.
"""
import ipaddress
import re
import socket
from typing import Optional
from urllib.parse import urlparse

import httpx

FETCH_TIMEOUT = 4.0
MAX_BODY_BYTES = 512 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; LPMLinkPreview/1.0; +self-hosted)"

URL_RE = re.compile(r"https?://[^\s<>\"]+")
_TRAILING_PUNCT = ".,!?;:'\")]"


def first_url(text: str) -> Optional[str]:
    """The first http(s) URL in a message, trailing punctuation stripped —
    mirrors the frontend's own linkify() so both agree on what "the link" is."""
    m = URL_RE.search(text)
    return m.group(0).rstrip(_TRAILING_PUNCT) if m else None


def _is_safe_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


def _meta(html: str, prop: str) -> Optional[str]:
    escaped = re.escape(prop)
    for pattern in (
        rf'<meta[^>]+(?:property|name)=["\']{escaped}["\'][^>]+content=["\']([^"\']*)["\']',
        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{escaped}["\']',
    ):
        m = re.search(pattern, html, re.IGNORECASE)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def fetch_preview(url: str) -> Optional[dict]:
    """Returns {url, title, description, image_url, site_name} or None if
    the URL is unsafe/unreachable/has nothing worth showing. Never raises —
    every failure mode is a None return, since a chat message must never
    fail to send just because its link's preview couldn't be built."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if not _is_safe_public_host(parsed.hostname):
            return None

        with httpx.Client(
            timeout=FETCH_TIMEOUT, follow_redirects=True, max_redirects=3,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return None
            if "text/html" not in resp.headers.get("content-type", ""):
                return None
            html = resp.text[:MAX_BODY_BYTES]

        title = _meta(html, "og:title")
        if not title:
            m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            title = m.group(1).strip() if m else None
        description = _meta(html, "og:description") or _meta(html, "description")
        image_url = _meta(html, "og:image")
        site_name = _meta(html, "og:site_name")

        if not title and not description and not image_url:
            return None

        return {
            "url": url,
            "title": title[:200] if title else None,
            "description": description[:400] if description else None,
            "image_url": image_url,
            "site_name": site_name[:80] if site_name else None,
        }
    except Exception:
        return None
