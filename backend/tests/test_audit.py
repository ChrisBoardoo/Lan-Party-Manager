"""GET /api/audit — the one admin endpoint nobody tested (Q-12 of the 2026-10-20
review, already flagged on 2026-09-16). What it must do: admins only, newest
first, the admin's name on each line, paging that holds."""
from conftest import auth_header, login, make_user, register


def _seed(client):
    register(client, "founder", "founder@example.com")  # first user = admin
    admin = login(client, "founder")
    target_id = make_user("target")
    # Two audited admin actions: a role change, then a deactivation.
    client.put(f"/api/users/{target_id}/role", params={"role": "treasurer"}, headers=auth_header(admin)).raise_for_status()
    client.put(f"/api/users/{target_id}/deactivate", headers=auth_header(admin)).raise_for_status()
    return admin


def test_admins_only(client):
    admin = _seed(client)
    make_user("member")
    member = login(client, "member")
    assert client.get("/api/audit/", headers=auth_header(member)).status_code == 403
    assert client.get("/api/audit/").status_code in (401, 403)
    assert client.get("/api/audit/", headers=auth_header(admin)).status_code == 200


def test_lines_carry_the_action_the_admin_and_a_time_newest_first(client):
    admin = _seed(client)
    rows = client.get("/api/audit/", headers=auth_header(admin)).json()
    actions = [r["action"] for r in rows]
    assert "role_changed" in actions and "user_deactivated" in actions
    assert all(r["admin"]["username"] == "founder" for r in rows)
    times = [r["created_at"] for r in rows]
    assert times == sorted(times, reverse=True)  # newest first (ties within a second keep any order)


def test_paging(client):
    admin = _seed(client)
    total = len(client.get("/api/audit/", headers=auth_header(admin)).json())
    assert total >= 2
    first = client.get("/api/audit/?limit=1", headers=auth_header(admin)).json()
    second = client.get("/api/audit/?limit=1&offset=1", headers=auth_header(admin)).json()
    assert len(first) == 1 and len(second) == 1 and first[0]["id"] != second[0]["id"]
    assert client.get("/api/audit/?limit=0", headers=auth_header(admin)).status_code == 422
    assert client.get("/api/audit/?limit=501", headers=auth_header(admin)).status_code == 422
