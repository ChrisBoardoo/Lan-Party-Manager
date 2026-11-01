"""Trésorerie 2.0 (1.4.2): transfers entered by the treasurer, the frozen plan,
catch-up of payments made outside the app — md/2.features/treso2.0.md.

Seeded with the real October 2026 LAN (8 members, 1 212.87 €; fronted amounts
deduced from the treasury screenshots, the greedy reproduces the "Qui doit à
qui" screen to the cent) and its three payments recorded in the app."""
import random
from datetime import date, timedelta

import pytest

import database
import models
from conftest import login, auth_header, make_user, run_concurrently
from prorata import greedy_lines, impute_transfers

NAMES = ["CrossWax", "HugeP", "Chakiboule", "patatedouce", "Max_Leordia", "Byndou", "Alfred", "Marsha"]
FRONTED = {"HugeP": 564.00, "Chakiboule": 315.54, "Alfred": 213.00, "Byndou": 80.33, "Max_Leordia": 40.00}
PAID_IN_APP = [("CrossWax", "HugeP", 14412), ("Byndou", "Chakiboule", 2776), ("Byndou", "Alfred", 1738)]

# The screen today, before anything else is paid.
SCREEN = {
    ("patatedouce", "HugeP"): 167.29,
    ("Max_Leordia", "HugeP"): 85.30,
    ("Max_Leordia", "Chakiboule"): 41.99,
    ("Marsha", "Chakiboule"): 78.50,
    ("Marsha", "Alfred"): 46.97,
    ("CrossWax", "Alfred"): 23.18,
}


@pytest.fixture
def lan(client):
    ids = {n: make_user(n, role="admin" if n == "CrossWax" else "user") for n in NAMES}
    s = database.SessionLocal()
    try:
        event = models.LanEvent(title="LAN octobre", start_date=date(2026, 10, 14), end_date=date(2026, 10, 18),
                                created_by=ids["CrossWax"])
        s.add(event)
        s.flush()
        for n in NAMES:
            s.add(models.EventRSVP(
                event_id=event.id, user_id=ids[n], status="in",
                arrival_date=date(2026, 10, 14) if n in NAMES[:5] else date(2026, 10, 15),
                departure_date=date(2026, 10, 18),
            ))
        for n, amount in FRONTED.items():
            s.add(models.Expense(description="courses", amount=amount, category="food", date=date(2026, 10, 15),
                                 created_by=ids[n], paid_by=ids[n], event_id=event.id))
        for f, t, cents in PAID_IN_APP:
            s.add(models.Transfer(event_id=event.id, from_user_id=ids[f], to_user_id=ids[t], amount_cents=cents,
                                  transferred_on=date(2026, 10, 17), recorded_by=ids[f]))
        s.commit()
        return {"event_id": event.id, "ids": ids, "names": {v: k for k, v in ids.items()}}
    finally:
        s.close()


def _prorata(client, lan, who="CrossWax"):
    r = client.get(f"/api/expenses/prorata?event_id={lan['event_id']}", headers=auth_header(login(client, who)))
    assert r.status_code == 200
    return r.json()


def _to_pay(client, lan, who="CrossWax"):
    return {
        (l["from_username"], l["to_username"]): l["amount"]
        for l in _prorata(client, lan, who)["settlements"] if not l["paid"]
    }


def _labels(client, lan):
    return {
        (l["from_username"], l["to_username"]): l["label"]
        for l in _prorata(client, lan)["settlements"] if not l["paid"] and l["label"]
    }


def _post(client, lan, transfers, who="CrossWax", confirm=False):
    body = {
        "event_id": lan["event_id"],
        "transfers": [
            {"from_user_id": lan["ids"][f], "to_user_id": lan["ids"][t], "amount": a,
             "transferred_on": (d or date.today()).isoformat(), **({"note": note} if note else {})}
            for f, t, a, d, note in (tuple(x) + (None,) * (5 - len(x)) for x in transfers)
        ],
        "confirm_outside_split": confirm,
    }
    return client.post("/api/expenses/transfers", json=body, headers=auth_header(login(client, who)))


def _mark(client, lan, who, to):
    return client.post("/api/expenses/settlements/mark",
                       json={"event_id": lan["event_id"], "to_user_id": lan["ids"][to]},
                       headers=auth_header(login(client, who)))


def _notified(action):
    s = database.SessionLocal()
    try:
        return sorted(
            s.get(models.User, a.recipient_user_id).username
            for a in s.query(models.ActivityLog).filter_by(action=action).all()
        )
    finally:
        s.close()


# ── The plan shown ────────────────────────────────────────────────────────────

def test_the_screen_is_reproduced_and_not_frozen_until_a_payment(client, lan):
    data = _prorata(client, lan)
    assert data["total_expenses"] == 1212.87
    assert _to_pay(client, lan) == SCREEN
    assert data["plan"] == {"frozen": False, "frozen_on": None}
    paid = [l for l in data["settlements"] if l["paid"]]
    assert [(l["from_username"], l["to_username"], l["amount"], l["transferred_on"]) for l in paid] == [
        ("CrossWax", "HugeP", 144.12, "2026-10-17"),
        ("Byndou", "Chakiboule", 27.76, "2026-10-17"),
        ("Byndou", "Alfred", 17.38, "2026-10-17"),
    ]


def test_paying_your_line_only_removes_your_line(client, lan):
    """Case A: with the greedy recomputed, Max's and CrossWax's lines used to
    change creditor when Marsha paid exactly her own line."""
    assert _mark(client, lan, "Marsha", "Chakiboule").status_code == 200
    expected = dict(SCREEN)
    del expected[("Marsha", "Chakiboule")]
    assert _to_pay(client, lan) == expected
    assert _prorata(client, lan)["plan"]["frozen"] is True
    assert _notified("settlement_plan_changed") == []


def test_everyone_paying_their_line_in_any_order_settles_everything(client, lan):
    for f, t in reversed(list(SCREEN)):
        assert _mark(client, lan, f, t).status_code == 200, (f, t)
    assert _to_pay(client, lan) == {}


def test_a_partial_payment_only_lowers_that_line(client, lan):
    """Case D: the treasurer records 40 € of Max's 85.30 to HugeP."""
    r = _post(client, lan, [("Max_Leordia", "HugeP", 40.0)])
    assert r.status_code == 201 and r.json()["plan_recalculated"] is False
    assert _to_pay(client, lan) == {**SCREEN, ("Max_Leordia", "HugeP"): 45.30}
    assert _notified("transfer_recorded") == ["HugeP", "Max_Leordia"]


def test_a_transfer_outside_the_plan_redirects_a_debtor_who_has_not_paid(client, lan):
    """Case B: Marsha sends 50 to HugeP instead of Chakiboule. patatedouce, who
    owes HugeP and hasn't paid anything, pays Chakiboule 50 instead; nobody
    else's lines move."""
    assert _post(client, lan, [("Marsha", "HugeP", 50.0)]).status_code == 201
    assert _to_pay(client, lan) == {
        **SCREEN,
        ("patatedouce", "HugeP"): 117.29,
        ("patatedouce", "Chakiboule"): 50.00,
        ("Marsha", "Chakiboule"): 28.50,
    }
    assert _labels(client, lan) == {("patatedouce", "Chakiboule"): "redirected"}
    assert _notified("settlement_plan_changed") == ["patatedouce"]


def test_an_overpayment_is_absorbed_without_moving_anyone_else(client, lan):
    """Case C: CrossWax sends 50 to Alfred, who was owed 23.18 by him."""
    assert _post(client, lan, [("CrossWax", "Alfred", 50.0)]).status_code == 201
    expected = dict(SCREEN)
    del expected[("CrossWax", "Alfred")]
    expected.update({("Marsha", "Alfred"): 20.15, ("Marsha", "CrossWax"): 26.82})
    assert _to_pay(client, lan) == expected


def test_without_anyone_to_redirect_the_payee_gives_back(client, lan):
    """Everyone owing Alfred has started paying: the overpaid part goes back."""
    assert _mark(client, lan, "Marsha", "Alfred").status_code == 200
    assert _post(client, lan, [("CrossWax", "Alfred", 50.0)]).status_code == 201
    to_pay = _to_pay(client, lan)
    assert to_pay[("Alfred", "CrossWax")] == 26.82
    assert ("CrossWax", "Alfred") not in to_pay
    assert _labels(client, lan)[("Alfred", "CrossWax")] == "give_back"


# ── Catch-up: payments made outside the app, entered afterwards ───────────────

def test_catch_up_of_the_two_bank_transfers_recomputes_the_plan(client, lan):
    """The real case: during the LAN, patatedouce and Marsha sent HugeP their
    share of the then total (144.12 and 108.09) and never recorded it. Entered
    with their real date, the plan is recomputed from what is actually owed."""
    r = _post(client, lan, [
        ("patatedouce", "HugeP", 144.12, date(2026, 10, 16), "virement pendant la LAN"),
        ("Marsha", "HugeP", 108.09, date(2026, 10, 16)),
    ])
    assert r.status_code == 201 and r.json()["plan_recalculated"] is True
    assert _to_pay(client, lan) == {
        ("Max_Leordia", "Chakiboule"): 120.49,
        ("Max_Leordia", "Alfred"): 6.80,
        ("CrossWax", "Alfred"): 23.18,
        ("patatedouce", "Alfred"): 23.17,
        ("Marsha", "Alfred"): 17.00,
        ("Marsha", "HugeP"): 0.38,
    }
    plan = _prorata(client, lan)["plan"]
    assert plan["frozen"] is True and plan["frozen_on"] == date.today().isoformat()
    # One notification per member for the whole batch.
    changed = _notified("settlement_plan_changed")
    assert changed == sorted(set(changed)) and "Max_Leordia" in changed
    s = database.SessionLocal()
    try:
        assert s.query(models.AuditLog).filter_by(action="transfer_recorded").count() == 2
        assert s.query(models.AuditLog).filter_by(action="settlement_plan_recalculated").count() == 1
        note = s.query(models.Transfer).filter(models.Transfer.note.isnot(None)).one()
        assert note.note == "virement pendant la LAN" and note.recorded_by == lan["ids"]["CrossWax"]
    finally:
        s.close()
    history = [l for l in _prorata(client, lan)["settlements"] if l["paid"] and l["on_behalf"]]
    assert {(l["from_username"], l["recorded_by_username"]) for l in history} == {
        ("patatedouce", "CrossWax"), ("Marsha", "CrossWax"),
    }


def test_a_transfer_dated_before_a_frozen_plan_recomputes_it(client, lan):
    assert _mark(client, lan, "Marsha", "Chakiboule").status_code == 200  # freezes the plan today
    r = _post(client, lan, [("Max_Leordia", "HugeP", 20.0, date.today() - timedelta(days=3))])
    assert r.json()["plan_recalculated"] is True


def test_a_changed_expense_makes_the_frozen_plan_stale(client, lan):
    assert _mark(client, lan, "Marsha", "Chakiboule").status_code == 200
    s = database.SessionLocal()
    try:
        s.add(models.Expense(description="glaçons", amount=29.0, category="food", date=date(2026, 10, 16),
                             created_by=lan["ids"]["Alfred"], paid_by=lan["ids"]["Alfred"], event_id=lan["event_id"]))
        s.commit()
    finally:
        s.close()
    data = _prorata(client, lan)
    assert data["plan"]["frozen"] is False and data["total_expenses"] == 1241.87


# ── Deleting ──────────────────────────────────────────────────────────────────

def _transfer_id(f, t, lan):
    s = database.SessionLocal()
    try:
        return s.query(models.Transfer.id).filter_by(
            event_id=lan["event_id"], from_user_id=lan["ids"][f], to_user_id=lan["ids"][t],
        ).order_by(models.Transfer.id.desc()).first()[0]
    finally:
        s.close()


def test_deleting_a_transfer_entered_since_the_freeze_restores_the_lines(client, lan):
    _post(client, lan, [("Marsha", "HugeP", 50.0)])
    tid = _transfer_id("Marsha", "HugeP", lan)
    r = client.delete(f"/api/expenses/transfers/{tid}", headers=auth_header(login(client, "CrossWax")))
    assert r.status_code == 200 and r.json()["plan_recalculated"] is False
    assert _to_pay(client, lan) == SCREEN
    assert _notified("transfer_deleted") == ["HugeP", "Marsha"]


def test_deleting_a_transfer_the_plan_counted_recomputes_it(client, lan):
    assert _mark(client, lan, "Marsha", "Chakiboule").status_code == 200  # freezes, counting the 3 old ones
    tid = _transfer_id("Byndou", "Alfred", lan)
    r = client.delete(f"/api/expenses/transfers/{tid}", headers=auth_header(login(client, "CrossWax")))
    assert r.status_code == 200 and r.json()["plan_recalculated"] is True
    assert sum(a for (f, _), a in _to_pay(client, lan).items() if f == "Byndou") == 17.38


def test_a_member_deletes_only_what_they_recorded_themselves(client, lan):
    _mark(client, lan, "Marsha", "Chakiboule")
    _post(client, lan, [("Marsha", "Alfred", 10.0)])  # entered by the treasurer
    own = _transfer_id("Marsha", "Chakiboule", lan)
    theirs = _transfer_id("Marsha", "Alfred", lan)
    other = _transfer_id("CrossWax", "HugeP", lan)
    marsha = auth_header(login(client, "Marsha"))
    assert client.delete(f"/api/expenses/transfers/{theirs}", headers=marsha).status_code == 403
    assert client.delete(f"/api/expenses/transfers/{other}", headers=marsha).status_code == 403
    assert client.delete(f"/api/expenses/transfers/{own}", headers=marsha).status_code == 200
    assert client.delete("/api/expenses/transfers/99999", headers=marsha).status_code == 404


# ── Who may, and what is accepted ─────────────────────────────────────────────

def test_only_the_treasurer_or_an_admin_enters_transfers(client, lan):
    assert _post(client, lan, [("Marsha", "HugeP", 10.0)], who="Marsha").status_code == 403
    make_user("tresorier", role="treasurer")
    assert _post(client, lan, [("Marsha", "HugeP", 10.0)], who="tresorier").status_code == 201
    assert client.post("/api/expenses/transfers/recalculate", json={"event_id": lan["event_id"]},
                       headers=auth_header(login(client, "Marsha"))).status_code == 403


@pytest.mark.parametrize("amount", [0, -5, 1.234, 100_001])
def test_invalid_amounts_are_refused(client, lan, amount):
    assert _post(client, lan, [("Marsha", "HugeP", amount)]).status_code == 422


def test_same_member_twice_and_future_dates_are_refused(client, lan):
    assert _post(client, lan, [("Marsha", "Marsha", 10.0)]).status_code == 422
    assert _post(client, lan, [("Marsha", "HugeP", 10.0, date.today() + timedelta(days=1))]).status_code == 400


def test_a_member_outside_the_split_needs_a_confirmation(client, lan):
    lan["ids"]["pote"] = make_user("pote")
    r = _post(client, lan, [("pote", "HugeP", 20.0)])
    assert r.status_code == 400 and "pote" in r.json()["detail"]
    assert _post(client, lan, [("pote", "HugeP", 20.0)], confirm=True).status_code == 201


def test_a_replayed_batch_is_refused(client, lan):
    assert _post(client, lan, [("Marsha", "HugeP", 10.0)]).status_code == 201
    assert _post(client, lan, [("Marsha", "HugeP", 10.0)]).status_code == 409


def test_two_marks_at_once_freeze_one_plan_and_record_once(client, lan):
    token = auth_header(login(client, "Marsha"))
    body = {"event_id": lan["event_id"], "to_user_id": lan["ids"]["Chakiboule"]}

    def mark():
        return client.post("/api/expenses/settlements/mark", json=body, headers=token)

    statuses = sorted(r.status_code for r in run_concurrently(mark, mark))
    assert statuses[0] == 200 and statuses[1] in (400, 409), statuses
    s = database.SessionLocal()
    try:
        assert s.query(models.SettlementPlan).filter_by(event_id=lan["event_id"]).count() == 1
        assert s.query(models.Transfer).filter_by(from_user_id=lan["ids"]["Marsha"]).count() == 1
    finally:
        s.close()


def test_recalculate_starts_again_from_what_is_owed(client, lan):
    _post(client, lan, [("Marsha", "HugeP", 50.0)])
    r = client.post("/api/expenses/transfers/recalculate", json={"event_id": lan["event_id"]},
                    headers=auth_header(login(client, "CrossWax")))
    assert r.status_code == 200
    s = database.SessionLocal()
    try:
        assert s.query(models.AuditLog).filter_by(action="settlement_plan_recalculated").count() == 1
    finally:
        s.close()
    # Same money, possibly other pairs.
    assert round(sum(_to_pay(client, lan).values()), 2) == round(sum(SCREEN.values()) - 50, 2)


def test_deleting_the_event_takes_its_transfers_and_plan(client, lan):
    _mark(client, lan, "Marsha", "Chakiboule")
    assert client.delete(f"/api/events/{lan['event_id']}",
                         headers=auth_header(login(client, "CrossWax"))).status_code == 200
    s = database.SessionLocal()
    try:
        assert s.query(models.Transfer).count() == 0
        assert s.query(models.SettlementPlan).count() == 0
    finally:
        s.close()


# ── The imputation itself: the money never depends on it ──────────────────────

def test_imputation_never_changes_what_anyone_owes():
    rng = random.Random(2026)
    for _ in range(500):
        people = list(range(1, rng.randint(3, 9)))
        bal = {p: rng.randint(-30000, 30000) for p in people[:-1]}
        bal[people[-1]] = -sum(bal.values())
        frozen = greedy_lines(bal)
        transfers = [(*rng.sample(people, 2), rng.randint(1, 20000)) for _ in range(rng.randint(0, 6))]
        lines = impute_transfers(frozen, transfers, paid_before=rng.sample(people, rng.randint(0, 2)))
        after = dict(bal)
        for a, b, x in transfers:
            after[a] += x
            after[b] -= x
        net = {p: 0 for p in people}
        for f, t, x in lines:
            assert x > 0
            net[f] += x
            net[t] -= x
        assert all(net[p] == -after[p] for p in people)
