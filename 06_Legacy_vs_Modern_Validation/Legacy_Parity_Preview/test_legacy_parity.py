"""
test_legacy_parity.py
------------------------
Automated tests for legacy_parity.py. Requires a real, freshly-migrated
genapp database:

    cd api
    pytest test_legacy_parity.py -v
"""
import psycopg2
import psycopg2.extras
import pytest

from legacy_parity import RULES, run_legacy_parity_validation


@pytest.fixture
def conn():
    c = psycopg2.connect(host="localhost", port="5432", dbname="genapp", user="postgres", password="CHANGE_ME_LOCAL_ONLY")
    c.cursor_factory = psycopg2.extras.RealDictCursor
    yield c
    c.close()


VALID_STATUSES = {"MATCH", "DEVIATION", "NEW_CAPABILITY", "NOT_IMPLEMENTED", "FAIL"}


def test_every_rule_has_a_citation_and_unique_id():
    ids = [r["id"] for r in RULES]
    assert len(ids) == len(set(ids)), "duplicate rule IDs found"
    for rule in RULES:
        assert rule["citation"], f"{rule['id']} has no legacy citation"
        assert rule["check_type"] in {"static", "dynamic"}


def test_full_parity_run_has_no_fails(conn):
    """The overarching claim of this tool: every documented legacy rule
    either matches, is a deliberate documented deviation, is an
    explicitly-flagged new capability, or is an honestly-reported gap -
    never an unexplained contradiction."""
    report = run_legacy_parity_validation(conn)
    fails = [r for r in report["rules"] if r["status"] == "FAIL"]
    assert not fails, f"unexpected FAILs: {[(r['id'], r['evidence']) for r in fails]}"
    assert report["passed"] is True


def test_every_rule_resolves_to_a_valid_status(conn):
    report = run_legacy_parity_validation(conn)
    for r in report["rules"]:
        assert r["status"] in VALID_STATUSES, f"{r['id']} has invalid status {r['status']!r}"
        assert r["evidence"], f"{r['id']} produced no evidence string"


def test_run_is_repeatable_and_leaves_no_side_effects(conn):
    """Running the parity validator twice in a row must produce
    identical results and must not leak any rows into the database
    (every check cleans up after itself)."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM genapp.customer")
        customers_before = cur.fetchone()["c"]
        cur.execute("SELECT count(*) AS c FROM genapp.policy")
        policies_before = cur.fetchone()["c"]

    report1 = run_legacy_parity_validation(conn)
    report2 = run_legacy_parity_validation(conn)

    statuses1 = {r["id"]: r["status"] for r in report1["rules"]}
    statuses2 = {r["id"]: r["status"] for r in report2["rules"]}
    assert statuses1 == statuses2

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM genapp.customer")
        customers_after = cur.fetchone()["c"]
        cur.execute("SELECT count(*) AS c FROM genapp.policy")
        policies_after = cur.fetchone()["c"]
    assert customers_after == customers_before
    assert policies_after == policies_before


def test_customer_delete_gap_is_confirmed_match():
    """A specific, important assertion: the CRUD-Matrix-documented
    absence of a Customer delete capability must be independently
    confirmed by this suite too (not just legacy_parity.py's own
    self-check), so a future PR that accidentally adds
    DELETE /business/customers/{id} gets caught two different ways."""
    from business_services import CustomerService
    assert not hasattr(CustomerService, "delete_customer")

    from main import app
    delete_routes = [
        r for r in app.routes
        if getattr(r, "path", None) == "/business/customers/{customer_number}"
        and "DELETE" in getattr(r, "methods", set())
    ]
    assert not delete_routes, "a DELETE route now exists under /business/customers - update CRUD-GAP-01 or confirm with the business"


@pytest.mark.parametrize("rule_id", [r["id"] for r in RULES])
def test_individual_rule_runs_without_crashing(conn, rule_id):
    """Every rule's check function must run cleanly on its own (not
    just as part of the full batch), and must never leave the
    connection's transaction in an aborted state for the next test -
    this is exactly the class of bug the CRUD-GAP-03/NORM-01
    interaction caught during development (see policy_service.py and
    customer_service.py's added psycopg2.Error catch-all)."""
    rule = next(r for r in RULES if r["id"] == rule_id)
    status, evidence = rule["fn"](conn)
    assert status in VALID_STATUSES
    # confirm the connection is still usable afterward
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()
