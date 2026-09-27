"""Riot ID on the profile — the pure parser, then PUT /api/users/{id}."""
import pytest

from conftest import register, login, auth_header, make_user
from riot_id import parse_riot_id


# ── Pure: parsing and the matching key ────────────────────────────────────────

def test_parse_keeps_casing_and_builds_a_casefolded_key():
    assert parse_riot_id("CrossWax#EUW") == ("CrossWax#EUW", "crosswax#euw")


def test_parse_trims_around_the_hash():
    assert parse_riot_id("  Cross Wax  #  EUW1 ") == ("Cross Wax#EUW1", "cross wax#euw1")


def test_parse_accepts_accents_and_spaces_in_the_game_name():
    display, key = parse_riot_id("Élodie la Fée#FR1")
    assert display == "Élodie la Fée#FR1"
    assert key == "élodie la fée#fr1"


def test_name_length_counts_characters():
    # Same case as frontend/src/lib/riotId.test.ts — 16 characters is the limit.
    assert parse_riot_id("🎮" * 16 + "#EUW")[0] == "🎮" * 16 + "#EUW"


def test_key_ignores_case_so_two_spellings_collide():
    assert parse_riot_id("CROSSWAX#euw")[1] == parse_riot_id("crosswax#EUW")[1]


@pytest.mark.parametrize("raw", [
    "CrossWax",            # no tag
    "CrossWax#",           # empty tag
    "#EUW",                # empty name
    "ab#EUW",              # name too short
    "a" * 17 + "#EUW",     # name too long
    "CrossWax#EU",         # tag too short
    "CrossWax#EUWEST",     # tag too long
    "CrossWax#EU-W",       # tag not alphanumeric
    "Cross#Wax#EUW",       # '#' inside the name
])
def test_parse_rejects_malformed_ids(raw):
    with pytest.raises(ValueError):
        parse_riot_id(raw)


# ── API: PUT /api/users/{id} ──────────────────────────────────────────────────

def _me(client, token):
    return client.get("/api/auth/me", headers=auth_header(token)).json()


def _set(client, token, user_id, riot_id):
    return client.put(f"/api/users/{user_id}", json={"riot_id": riot_id}, headers=auth_header(token))


@pytest.fixture
def bob(client):
    register(client, "founder", "founder@example.com")  # first user = admin
    bob_id = make_user("bob")
    return bob_id, login(client, "bob")


def test_riot_id_is_unset_by_default(client, bob):
    _, token = bob
    assert _me(client, token)["riot_id"] is None


def test_member_sets_own_riot_id(client, bob):
    bob_id, token = bob
    r = _set(client, token, bob_id, "  Bob The Builder #  EUW ")
    assert r.status_code == 200
    assert r.json()["riot_id"] == "Bob The Builder#EUW"
    assert _me(client, token)["riot_id"] == "Bob The Builder#EUW"


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_null_or_blank_clears_it(client, bob, empty):
    bob_id, token = bob
    _set(client, token, bob_id, "BobLoL#EUW").raise_for_status()
    r = _set(client, token, bob_id, empty)
    assert r.status_code == 200
    assert r.json()["riot_id"] is None


def test_malformed_riot_id_is_422(client, bob):
    bob_id, token = bob
    assert _set(client, token, bob_id, "BobLoL").status_code == 422
    assert _me(client, token)["riot_id"] is None


def test_riot_id_already_taken_is_409_case_insensitively(client, bob):
    bob_id, bob_token = bob
    carol_id = make_user("carol")
    carol_token = login(client, "carol")
    _set(client, bob_token, bob_id, "BobLoL#EUW").raise_for_status()

    r = _set(client, carol_token, carol_id, "boblol#euw")
    assert r.status_code == 409
    assert _me(client, carol_token)["riot_id"] is None


def test_re_saving_own_riot_id_with_other_casing_is_fine(client, bob):
    bob_id, token = bob
    _set(client, token, bob_id, "BobLoL#EUW").raise_for_status()
    r = _set(client, token, bob_id, "BOBLOL#euw")
    assert r.status_code == 200
    assert r.json()["riot_id"] == "BOBLOL#euw"


def test_cleared_riot_id_is_free_for_someone_else(client, bob):
    bob_id, bob_token = bob
    carol_id = make_user("carol")
    carol_token = login(client, "carol")
    _set(client, bob_token, bob_id, "BobLoL#EUW").raise_for_status()
    _set(client, bob_token, bob_id, None).raise_for_status()
    assert _set(client, carol_token, carol_id, "BobLoL#EUW").status_code == 200


def test_other_fields_leave_the_riot_id_alone(client, bob):
    bob_id, token = bob
    _set(client, token, bob_id, "BobLoL#EUW").raise_for_status()
    client.put(f"/api/users/{bob_id}", json={"phone": "0612345678"}, headers=auth_header(token)).raise_for_status()
    assert _me(client, token)["riot_id"] == "BobLoL#EUW"


def test_member_cannot_set_someone_elses_riot_id(client, bob):
    _, bob_token = bob
    carol_id = make_user("carol")
    assert _set(client, bob_token, carol_id, "CarolLoL#EUW").status_code == 403


def test_riot_id_is_not_on_the_public_roster(client, bob):
    """Same exposure as the Discord/Steam names: self and admins only."""
    bob_id, token = bob
    _set(client, token, bob_id, "BobLoL#EUW").raise_for_status()
    make_user("carol")
    carol_token = login(client, "carol")
    roster = client.get("/api/users/", headers=auth_header(carol_token)).json()
    assert all("riot_id" not in u for u in roster)


def test_deleting_an_account_frees_its_riot_id(client, bob):
    bob_id, bob_token = bob
    admin = login(client, "founder")
    carol_id = make_user("carol")
    carol_token = login(client, "carol")
    _set(client, bob_token, bob_id, "BobLoL#EUW").raise_for_status()

    client.delete(f"/api/users/{bob_id}", headers=auth_header(admin)).raise_for_status()
    assert _set(client, carol_token, carol_id, "BobLoL#EUW").status_code == 200
