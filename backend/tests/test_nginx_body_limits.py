"""frontend/nginx.conf caps request bodies at 1 MB, except for the upload routes it
lists in one regex location (S11 of the 2026-09-24 security review).

That list is the fragile part: a new upload endpoint that isn't added to it works in
`uvicorn --reload` and in every test here, then 413s behind nginx in production. These
tests read the real nginx.conf and the real app's routes so that can't happen silently.
"""

import re
from pathlib import Path

import main

NGINX_CONF = Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf"


def _conf() -> str:
    return NGINX_CONF.read_text(encoding="utf-8")


def _upload_location() -> re.Pattern:
    match = re.search(r"location ~ (\^/api/\S+) \{\s*client_max_body_size 110m;", _conf())
    assert match, "no 110m upload location found in frontend/nginx.conf"
    return re.compile(match.group(1))


def _upload_routes() -> list[str]:
    """Every route taking a multipart body — i.e. an UploadFile parameter.

    Read from the OpenAPI schema rather than `app.routes`: FastAPI 0.141 wraps each
    `include_router` in an `_IncludedRouter`, so `app.routes` doesn't list them."""
    return sorted(
        path
        for path, operations in main.app.openapi()["paths"].items()
        for operation in operations.values()
        if "multipart/form-data" in operation.get("requestBody", {}).get("content", {})
    )


def _concrete(path: str) -> str:
    """/api/users/{user_id}/avatar -> /api/users/1/avatar"""
    return re.sub(r"\{[^}]+\}", "1", path)


def test_the_default_cap_is_small():
    assert re.search(r"^\s*client_max_body_size 1m;", _conf(), re.MULTILINE)
    assert "client_max_body_size 110m;" in _conf()


def test_every_upload_route_is_let_through():
    routes = _upload_routes()
    # Guards the guard: if route discovery broke, the loop below would pass vacuously.
    assert "/api/media/upload" in routes and len(routes) >= 8

    location = _upload_location()
    missing = [p for p in routes if not location.fullmatch(_concrete(p))]
    assert not missing, f"add these upload routes to the regex location in frontend/nginx.conf: {missing}"


def test_json_routes_stay_capped():
    location = _upload_location()
    for path in ("/api/auth/login", "/api/users/1/avatar/rotate", "/api/lol/matches", "/api/chat/1/messages"):
        assert not location.fullmatch(path), path
