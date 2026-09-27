"""A member never receives another member's email or phone (S6 of the 2026-09-24
security review).

The UI already hid them — the roster is UserPublic, a profile shows the email only to
its owner or an admin, the phone only reaches the debtor in the pro-rata. But seven
responses nested the full UserOut, so both went out in clear to every member through
the raw API, including the activity feed's WebSocket. The UI never displayed them,
which is how it went unnoticed.
"""

import typing

from pydantic import BaseModel

import schemas
from conftest import auth_header, login, make_user, register

# The only responses allowed to nest the full UserOut: admin-only ones, since an admin
# sees every member's email anyway.
ADMIN_ONLY = {"AuditLogOut"}


def _nests_user_out(annotation) -> bool:
    if annotation is schemas.UserOut:
        return True
    return any(_nests_user_out(arg) for arg in typing.get_args(annotation))


def test_no_response_nests_the_full_user():
    offenders = [
        f"{name}.{field}"
        for name, model in vars(schemas).items()
        if isinstance(model, type) and issubclass(model, BaseModel) and name not in ADMIN_ONLY
        for field, info in model.model_fields.items()
        if _nests_user_out(info.annotation)
    ]
    assert not offenders, f"nest UserPublic instead of UserOut in: {offenders}"


def test_activity_feed_leaks_no_contact_details(client):
    """The widest leak: every member reads the feed, and it names whoever acted."""
    register(client, "founder", "founder@example.com")
    admin = login(client, "founder")
    admin_id = client.get("/api/auth/me", headers=auth_header(admin)).json()["id"]
    client.put(
        f"/api/users/{admin_id}", json={"phone": "+33 6 12 34 56 78"}, headers=auth_header(admin)
    ).raise_for_status()
    client.post(
        "/api/tournaments/", json={"game_name": "Quake", "max_team_size": 1}, headers=auth_header(admin)
    ).raise_for_status()

    make_user("member")
    member = login(client, "member")
    for path in ("/api/activity/", "/api/tournaments/"):
        body = client.get(path, headers=auth_header(member)).text
        assert "founder" in body, path  # the entry is there…
        assert "founder@example.com" not in body, path  # …without the contact details
        assert "+33 6 12 34 56 78" not in body, path
