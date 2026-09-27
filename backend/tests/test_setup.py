"""My Setup: the 14 components, custom fields, photos, and the public share link.

The share-link tests are the ones that matter. Two rules are load-bearing:

  1. **The owner mints their own link — nobody else can, not even an admin.**
     That's enforced by the URL space (every write route is /me), so the test
     asserts the admin route *does not exist* rather than that it 403s.
  2. **A public URL is the internet.** The shared payload asserts on raw JSON
     keys rather than the schema, so adding a field to SetupSharedOut later
     can't silently re-leak an email, a role or a presence timestamp.
"""
import io
import os

from PIL import Image

import database
import models
from conftest import auth_header, login, make_user


def _png(size=(40, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (255, 61, 0)).save(buf, "PNG")
    return buf.getvalue()


def _enable(client, token, key="setup_enabled", value="true"):
    resp = client.put(f"/api/settings/{key}", json={"value": value}, headers=auth_header(token))
    resp.raise_for_status()


def _upload(client, token, name="rig.png"):
    return client.post(
        "/api/setup/me/photos",
        files={"file": (name, _png(), "image/png")},
        headers=auth_header(token),
    )


COMPONENTS = {
    "motherboard": "B650 Tomahawk", "cpu": "Ryzen 7 7800X3D", "cooler": "NH-D15",
    "graphics_card": "RTX 4070", "ram": "32GB DDR5", "power_supply": "750W",
    "fans": "6x Noctua", "storage": "2TB NVMe", "pc_case": "Fractal North",
    "display": "27\" 1440p 165Hz", "keyboard": "Keychron", "mouse": "G Pro",
    "headset": "Arctis", "mic": "SM7B",
}


# ── The gate ──────────────────────────────────────────────────────────────────

def test_member_gets_404_while_the_feature_is_off(client):
    make_user("founder", role="admin")
    make_user("bob")
    assert client.get("/api/setup/me", headers=auth_header(login(client, "bob"))).status_code == 404


def test_admin_passes_the_gate_so_they_can_configure_it(client):
    make_user("founder", role="admin")
    assert client.get("/api/setup/me", headers=auth_header(login(client, "founder"))).status_code == 200


def test_admin_still_cannot_mint_a_link_while_the_feature_is_off(client):
    """require_feature waves admins through, so anything with effect beyond the
    admin's own account re-checks the flag. Minting a public URL for a feature
    the crew switched off is exactly that."""
    make_user("founder", role="admin")
    token = login(client, "founder")
    assert client.post("/api/setup/me/share", headers=auth_header(token)).status_code == 404


def test_turning_the_feature_off_kills_a_live_link(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    share = client.post("/api/setup/me/share", headers=auth_header(token)).json()["token"]
    assert client.get("/api/setup/shared", headers={"X-Setup-Token": share}).status_code == 200

    _enable(client, token, value="false")
    assert client.get("/api/setup/shared", headers={"X-Setup-Token": share}).status_code == 404


# ── Components ────────────────────────────────────────────────────────────────

def test_get_me_returns_an_empty_shape_before_anything_is_saved(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    body = client.get("/api/setup/me", headers=auth_header(token)).json()
    assert body["has_content"] is False
    assert body["components"]["cpu"] is None
    assert body["photos"] == [] and body["custom_fields"] == []


def test_all_fourteen_components_round_trip(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    resp = client.put("/api/setup/me", json={"components": COMPONENTS}, headers=auth_header(token))
    assert resp.status_code == 200
    saved = resp.json()["components"]
    for key, value in COMPONENTS.items():
        assert saved[key] == value, f"{key} did not round-trip"
    assert resp.json()["has_content"] is True


def test_pc_case_round_trips(client):
    """`case` is a SQL reserved word and shadows sqlalchemy.case — the column is
    pc_case, and that rename is exactly the kind of thing that silently breaks."""
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    client.put("/api/setup/me", json={"components": {"pc_case": "Lian Li O11"}}, headers=auth_header(token))
    assert client.get("/api/setup/me", headers=auth_header(token)).json()["components"]["pc_case"] == "Lian Li O11"


def test_blank_components_are_stored_as_null(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    body = client.put("/api/setup/me", json={"components": {"cpu": "   "}}, headers=auth_header(token)).json()
    assert body["components"]["cpu"] is None
    assert body["has_content"] is False


def test_saving_twice_updates_rather_than_duplicating(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    client.put("/api/setup/me", json={"components": {"cpu": "old"}}, headers=auth_header(token))
    client.put("/api/setup/me", json={"components": {"cpu": "new"}}, headers=auth_header(token))

    assert client.get("/api/setup/me", headers=auth_header(token)).json()["components"]["cpu"] == "new"
    session = database.SessionLocal()
    try:
        assert session.query(models.UserSetup).count() == 1
    finally:
        session.close()


# ── Custom fields ─────────────────────────────────────────────────────────────

def test_custom_fields_save_and_keep_their_order(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    resp = client.put("/api/setup/me", json={
        "components": {},
        "custom_fields": [
            {"label": "Chair", "value": "Herman Miller"},
            {"label": "Deskpad", "value": "Big one"},
        ],
    }, headers=auth_header(token))
    fields = resp.json()["custom_fields"]
    assert [f["label"] for f in fields] == ["Chair", "Deskpad"]


def test_custom_fields_are_replaced_wholesale(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    client.put("/api/setup/me", json={
        "components": {}, "custom_fields": [{"label": "Chair", "value": "x"}],
    }, headers=auth_header(token))
    resp = client.put("/api/setup/me", json={
        "components": {}, "custom_fields": [{"label": "Streamdeck", "value": "y"}],
    }, headers=auth_header(token))

    assert [f["label"] for f in resp.json()["custom_fields"]] == ["Streamdeck"]


def test_custom_fields_can_be_cleared(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    client.put("/api/setup/me", json={"components": {}, "custom_fields": [{"label": "Chair"}]}, headers=auth_header(token))
    resp = client.put("/api/setup/me", json={"components": {}, "custom_fields": []}, headers=auth_header(token))
    assert resp.json()["custom_fields"] == []


def test_the_eleventh_custom_field_is_rejected(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    resp = client.put("/api/setup/me", json={
        "components": {},
        "custom_fields": [{"label": f"f{i}", "value": "v"} for i in range(11)],
    }, headers=auth_header(token))
    assert resp.status_code == 400


# ── Photos ────────────────────────────────────────────────────────────────────

def test_a_photo_uploads_and_appears(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    resp = _upload(client, token)
    assert resp.status_code == 200
    photos = resp.json()["photos"]
    assert len(photos) == 1
    assert photos[0]["url"].startswith("/uploads/setup/setup_")
    assert photos[0]["url"].endswith(".webp")  # re-encoded, not stored raw


def test_the_sixth_photo_is_rejected_without_being_written(client, tmp_path):
    """The cap is checked BEFORE the file is read. If it ran afterwards the 6th
    upload would still cost a full buffer and decode before being refused —
    bounding storage but not work."""
    import uploads

    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    for i in range(5):
        assert _upload(client, token, f"r{i}.png").status_code == 200

    setup_dir = os.path.join(uploads.UPLOAD_DIR, "setup")
    before = sorted(os.listdir(setup_dir))

    resp = _upload(client, token, "sixth.png")
    assert resp.status_code == 400

    session = database.SessionLocal()
    try:
        assert session.query(models.UserSetupPhoto).count() == 5
    finally:
        session.close()
    assert sorted(os.listdir(setup_dir)) == before, "the rejected 6th photo still hit the disk"


def test_deleting_a_photo_removes_the_row_and_the_file(client):
    import uploads

    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    photo = _upload(client, token).json()["photos"][0]
    path = os.path.join(uploads.UPLOAD_DIR, "setup", os.path.basename(photo["url"]))
    assert os.path.exists(path)

    resp = client.delete(f"/api/setup/me/photos/{photo['id']}", headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["photos"] == []
    assert not os.path.exists(path)


def test_a_photo_starts_with_no_caption(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    assert _upload(client, token).json()["photos"][0]["caption"] is None


def test_captioning_a_photo(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    photo_id = _upload(client, token).json()["photos"][0]["id"]

    resp = client.patch(
        f"/api/setup/me/photos/{photo_id}",
        json={"caption": "before the cable management"},
        headers=auth_header(token),
    )
    assert resp.status_code == 200
    assert resp.json()["photos"][0]["caption"] == "before the cable management"


def test_a_caption_can_be_cleared(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    photo_id = _upload(client, token).json()["photos"][0]["id"]

    client.patch(f"/api/setup/me/photos/{photo_id}", json={"caption": "x"}, headers=auth_header(token))
    resp = client.patch(f"/api/setup/me/photos/{photo_id}", json={"caption": "  "}, headers=auth_header(token))
    assert resp.json()["photos"][0]["caption"] is None


def test_captions_reach_the_public_share(client):
    """The caption is most of the value on a shared link — it's the bit that says
    what you're looking at."""
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    photo_id = _upload(client, token).json()["photos"][0]["id"]
    client.patch(f"/api/setup/me/photos/{photo_id}", json={"caption": "the good side"}, headers=auth_header(token))

    share = client.post("/api/setup/me/share", headers=auth_header(token)).json()["token"]
    body = client.get("/api/setup/shared", headers={"X-Setup-Token": share}).json()
    assert body["photos"][0]["caption"] == "the good side"


def test_captioning_another_members_photo_is_404(client):
    make_user("founder", role="admin")
    make_user("bob")
    founder_token = login(client, "founder")
    _enable(client, founder_token)
    photo_id = _upload(client, founder_token).json()["photos"][0]["id"]

    resp = client.patch(
        f"/api/setup/me/photos/{photo_id}",
        json={"caption": "hacked"},
        headers=auth_header(login(client, "bob")),
    )
    assert resp.status_code == 404


def test_deleting_another_members_photo_is_404_not_403(client):
    """404, not 403 — no reason to confirm the id exists to someone with no
    business with it."""
    make_user("founder", role="admin")
    make_user("bob")
    founder_token = login(client, "founder")
    _enable(client, founder_token)

    photo_id = _upload(client, founder_token).json()["photos"][0]["id"]
    resp = client.delete(f"/api/setup/me/photos/{photo_id}", headers=auth_header(login(client, "bob")))
    assert resp.status_code == 404


def test_a_non_image_photo_is_rejected(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    resp = client.post(
        "/api/setup/me/photos",
        files={"file": ("evil.png", b"definitely not a png", "image/png")},
        headers=auth_header(token),
    )
    assert resp.status_code == 400


def test_sort_order_survives_deleting_from_the_middle(client):
    """max(existing)+1, not count() — with count(), deleting the middle photo and
    then uploading collides."""
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    ids = [_upload(client, token, f"r{i}.png").json()["photos"][-1]["id"] for i in range(3)]
    client.delete(f"/api/setup/me/photos/{ids[1]}", headers=auth_header(token))
    photos = _upload(client, token, "fresh.png").json()["photos"]

    assert len(photos) == 3
    session = database.SessionLocal()
    try:
        orders = [p.sort_order for p in session.query(models.UserSetupPhoto).all()]
        assert len(orders) == len(set(orders)), f"sort_order collided: {orders}"
    finally:
        session.close()


# ── Sharing ───────────────────────────────────────────────────────────────────

def _mint(client, token):
    resp = client.post("/api/setup/me/share", headers=auth_header(token))
    assert resp.status_code == 200
    return resp.json()["token"]


def _shared(client, share_token):
    return client.get("/api/setup/shared", headers={"X-Setup-Token": share_token})


def test_an_admin_cannot_mint_another_members_link(client):
    """The whole owner-only design: the route does not exist. Asserting it's
    absent rather than 403 is the point — you cannot forget a check you never
    had the opportunity to write."""
    founder_id = make_user("founder", role="admin")
    bob_id = make_user("bob")
    token = login(client, "founder")
    _enable(client, token)

    assert client.post(f"/api/setup/{bob_id}/share", headers=auth_header(token)).status_code in (404, 405)
    assert client.put(f"/api/setup/{bob_id}", json={"components": {}}, headers=auth_header(token)).status_code in (404, 405)
    assert client.post(f"/api/setup/{bob_id}/photos", headers=auth_header(token)).status_code in (404, 405, 422)


def test_the_owner_mints_their_own_link_and_it_serves_their_setup(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    client.put("/api/setup/me", json={"components": COMPONENTS}, headers=auth_header(token))

    resp = _shared(client, _mint(client, token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "founder"
    assert body["components"]["cpu"] == "Ryzen 7 7800X3D"


def test_the_shared_payload_carries_no_pii(client):
    """Assert on raw JSON keys, not the schema, so a later field addition to
    SetupSharedOut can't quietly re-leak. UserPublic would have brought role,
    is_online and last_seen along — hence the dedicated schema."""
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    client.put("/api/setup/me", json={"components": COMPONENTS}, headers=auth_header(token))

    resp = _shared(client, _mint(client, token))
    body = resp.json()

    for leaked in ("email", "phone", "role", "is_online", "last_seen", "user_id", "is_active", "created_at"):
        assert leaked not in body, f"{leaked} must not appear on a public URL"
    assert "@example.com" not in resp.text
    assert set(body) == {"username", "avatar_url", "components", "custom_fields", "photos"}


def test_no_header_is_401(client):
    make_user("founder", role="admin")
    _enable(client, login(client, "founder"))
    assert client.get("/api/setup/shared").status_code == 401


def test_a_wrong_token_is_401(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    _mint(client, token)
    assert _shared(client, "not-the-token").status_code == 401


def test_an_empty_token_is_401(client):
    """Guards `WHERE share_token = ''` from matching anything interesting."""
    make_user("founder", role="admin")
    _enable(client, login(client, "founder"))
    assert _shared(client, "").status_code == 401


def test_a_non_ascii_token_is_401_not_500(client):
    """compare_digest raises TypeError on a non-ASCII str, which would surface as
    a 500. Headers are ASCII by spec so it's near-unreachable over the wire —
    exercise the dependency directly, where it is expressible."""
    from fastapi import HTTPException

    from router_setup import require_setup_token

    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    _mint(client, token)

    session = database.SessionLocal()
    try:
        try:
            require_setup_token(x_setup_token="tökén-with-ümlauts", db=session)
            raised = None
        except HTTPException as exc:
            raised = exc.status_code
        except TypeError:
            raised = 500
        assert raised == 401
    finally:
        session.close()


def test_rotating_invalidates_the_old_link(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    first = _mint(client, token)
    second = _mint(client, token)
    assert first != second
    assert _shared(client, first).status_code == 401
    assert _shared(client, second).status_code == 200


def test_revoking_kills_the_link(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    share = _mint(client, token)
    assert _shared(client, share).status_code == 200
    assert client.delete("/api/setup/me/share", headers=auth_header(token)).status_code == 200
    assert _shared(client, share).status_code == 401


def test_get_share_reports_the_current_token(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)

    assert client.get("/api/setup/me/share", headers=auth_header(token)).json()["token"] is None
    minted = _mint(client, token)
    assert client.get("/api/setup/me/share", headers=auth_header(token)).json()["token"] == minted


def test_each_member_gets_their_own_link(client):
    make_user("founder", role="admin")
    make_user("bob")
    founder_token = login(client, "founder")
    _enable(client, founder_token)
    bob_token = login(client, "bob")

    client.put("/api/setup/me", json={"components": {"cpu": "founder-cpu"}}, headers=auth_header(founder_token))
    client.put("/api/setup/me", json={"components": {"cpu": "bob-cpu"}}, headers=auth_header(bob_token))

    assert _shared(client, _mint(client, founder_token)).json()["components"]["cpu"] == "founder-cpu"
    assert _shared(client, _mint(client, bob_token)).json()["components"]["cpu"] == "bob-cpu"


# ── Reading another member's setup, in-app ────────────────────────────────────

def test_a_member_can_read_another_members_setup_in_app(client):
    make_user("founder", role="admin")
    bob_id = make_user("bob")
    founder_token = login(client, "founder")
    _enable(client, founder_token)
    client.put("/api/setup/me", json={"components": {"cpu": "bob-cpu"}}, headers=auth_header(login(client, "bob")))

    resp = client.get(f"/api/setup/{bob_id}", headers=auth_header(founder_token))
    assert resp.status_code == 200
    assert resp.json()["components"]["cpu"] == "bob-cpu"
    assert resp.json()["username"] == "bob"


def test_reading_an_unknown_users_setup_is_404(client):
    make_user("founder", role="admin")
    token = login(client, "founder")
    _enable(client, token)
    assert client.get("/api/setup/999", headers=auth_header(token)).status_code == 404
