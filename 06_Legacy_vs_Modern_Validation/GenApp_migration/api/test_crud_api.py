"""
test_crud_api.py
-------------------
Integration tests for the raw per-table CRUD API (routers/*.py +
crud.py), using FastAPI's TestClient against a real genapp database:

    cd api
    pytest test_crud_api.py -v

A single parametrized test exercises the full create -> read -> update
-> delete lifecycle identically across representative tables, which is
a good test of crud.py's generic factory itself (if the factory has a
bug, it breaks the SAME way for every table, and this test catches
that immediately rather than needing near-duplicate test functions).
"""
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _app_lifespan():
    with TestClient(app) as c:
        yield c


CRUD_CASES = [
    ("/customers", "customer_number",
     {"first_name": "CRUD", "last_name": "TEST", "email_address": "crud@test.com"},
     {"last_name": "UPDATED"}, "last_name"),
    ("/policies", "policy_number",
     {"customer_number": 1, "policy_type": "M"},
     {"broker_id": 42}, "broker_id"),
    ("/claims", "claim_number",
     {"policy_number": 1, "cause": "CRUD test claim"},
     {"cause": "UPDATED_CAUSE"}, "cause"),
]


@pytest.mark.parametrize("prefix,pk_field,create_payload,update_payload,check_field", CRUD_CASES)
def test_full_crud_lifecycle(prefix, pk_field, create_payload, update_payload, check_field):
    # CREATE
    r = client.post(prefix, json=create_payload)
    assert r.status_code == 201, r.text
    created = r.json()
    pk = created[pk_field]

    # READ
    r = client.get(f"{prefix}/{pk}")
    assert r.status_code == 200
    assert r.json()[pk_field] == pk

    # UPDATE
    r = client.put(f"{prefix}/{pk}", json=update_payload)
    assert r.status_code == 200, r.text
    assert r.json()[check_field] == update_payload[check_field]

    # DELETE
    r = client.delete(f"{prefix}/{pk}")
    assert r.status_code == 204

    # CONFIRM GONE
    r = client.get(f"{prefix}/{pk}")
    assert r.status_code == 404


def test_motor_crud_lifecycle_via_dependent_policy():
    """motor's PK is policy_number with no identity of its own - needs
    a real policy created first, tested separately from the generic
    parametrized case above."""
    r = client.post("/policies", json={"customer_number": 1, "policy_type": "M"})
    assert r.status_code == 201
    policy_number = r.json()["policy_number"]
    try:
        r = client.post("/motors", json={"policy_number": policy_number, "make": "HONDA"})
        assert r.status_code == 201

        r = client.put(f"/motors/{policy_number}", json={"make": "TOYOTA"})
        assert r.status_code == 200
        assert r.json()["make"] == "TOYOTA"

        r = client.delete(f"/motors/{policy_number}")
        assert r.status_code == 204
    finally:
        client.delete(f"/policies/{policy_number}")


@pytest.mark.parametrize("prefix", ["/customers", "/policies", "/motors", "/houses",
                                     "/endowments", "/commercials", "/claims", "/customer-secure"])
def test_get_nonexistent_returns_404(prefix):
    r = client.get(f"{prefix}/999999")
    assert r.status_code == 404


def test_create_policy_for_nonexistent_customer_returns_422():
    r = client.post("/policies", json={"customer_number": 999999, "policy_type": "M"})
    assert r.status_code == 422


def test_customer_secure_password_never_returned():
    # Use a throwaway customer, not one from the original sample data
    # (customer_secure.csv already covers customer_number 1 and 2 -
    # reusing either of those and then deleting it as cleanup would
    # permanently destroy real sample data, breaking
    # validate_migration.py for every test that runs after this one).
    r = client.post("/customers", json={"first_name": "SECTEST", "last_name": "TEMP"})
    assert r.status_code == 201
    temp_customer_number = r.json()["customer_number"]
    try:
        r = client.post("/customer-secure", json={
            "customer_number": temp_customer_number, "customer_pass": "supersecret", "state_indicator": "A",
        })
        assert r.status_code == 201, r.text
        assert "customer_pass" not in r.json()
        r = client.get(f"/customer-secure/{temp_customer_number}")
        assert "customer_pass" not in r.json()
    finally:
        client.delete(f"/customer-secure/{temp_customer_number}")
        client.delete(f"/customers/{temp_customer_number}")


def test_list_endpoint_respects_limit():
    r = client.get("/customers?limit=3")
    assert r.status_code == 200
    assert len(r.json()) <= 3


# ---------------------------------------------------------------------------
# Composite endpoints
# ---------------------------------------------------------------------------
def test_customer_policies_endpoint():
    r = client.get("/customers/1/policies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_policy_detail_endpoint_joins_correct_table():
    r = client.get("/policies/6/detail")  # policy 6 is a House policy in sample data
    assert r.status_code == 200
    body = r.json()
    assert body["detail_table"] == "house"
    assert "property_type" in body["detail"]


def test_policy_claims_endpoint():
    r = client.get("/policies/6/claims")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Meta endpoints
# ---------------------------------------------------------------------------
def test_tables_endpoint_lists_all_eight():
    r = client.get("/tables")
    assert r.status_code == 200
    names = {t["table_name"] for t in r.json()}
    assert names == {"customer", "customer_secure", "policy", "endowment",
                      "house", "motor", "commercial", "claim"}


@pytest.mark.parametrize("table", ["customer", "policy", "endowment", "house",
                                     "motor", "commercial", "claim", "customer_secure"])
def test_table_columns_endpoint_has_descriptions(table):
    r = client.get(f"/tables/{table}/columns")
    assert r.status_code == 200
    columns = r.json()
    assert len(columns) > 0
    # every column should have a description, since sql/03_comments.sql
    # and sql/04_business_rules.sql cover 100% of columns (see README)
    missing = [c["column"] for c in columns if not c["description"]]
    assert not missing, f"{table} has undocumented columns: {missing}"


def test_table_columns_endpoint_404_for_unknown_table():
    r = client.get("/tables/not_a_real_table/columns")
    assert r.status_code == 404


def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
