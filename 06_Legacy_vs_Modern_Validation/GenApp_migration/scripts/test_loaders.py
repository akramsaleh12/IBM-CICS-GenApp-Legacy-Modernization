"""
test_loaders.py
------------------
Integration tests for load_vsam_customer.py, load_vsam_policy.py, and
db2_loader.py. Requires a real, freshly-migrated genapp database:

    cd scripts
    pytest test_loaders.py -v

These tests re-run the real loaders against the real sample data
files, so they double as a regression guard for the whole VSAM/DB2 ->
PostgreSQL pipeline, not just isolated units.
"""
import psycopg2
import psycopg2.extras
import pytest

import load_vsam_customer
import load_vsam_policy
import db2_loader


@pytest.fixture
def conn():
    c = psycopg2.connect(host="localhost", port="5432", dbname="genapp", user="postgres", password="CHANGE_ME_LOCAL_ONLY")
    c.cursor_factory = psycopg2.extras.RealDictCursor
    yield c
    c.close()


def test_load_vsam_customer_loads_all_ten_records_correctly(conn):
    n = load_vsam_customer.load("../sample_data/ksdscust.txt", conn, encoding="ascii", schema="genapp")
    assert n == 10
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM genapp.customer")
        assert cur.fetchone()["c"] >= 10  # >= since other tests may have added rows

    with conn.cursor() as cur:
        cur.execute("SELECT first_name, last_name FROM genapp.customer WHERE customer_number = 1")
        row = cur.fetchone()
    assert row["first_name"] == "ANDREW"
    assert row["last_name"] == "PANDY"


def test_load_vsam_customer_is_idempotent(conn):
    """Loading the same file twice must not create duplicates or error -
    the row count for the known 10 sample customers must stay at 10."""
    load_vsam_customer.load("../sample_data/ksdscust.txt", conn, encoding="ascii", schema="genapp")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM genapp.customer WHERE customer_number <= 10")
        count_after_first = cur.fetchone()["c"]

    load_vsam_customer.load("../sample_data/ksdscust.txt", conn, encoding="ascii", schema="genapp")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM genapp.customer WHERE customer_number <= 10")
        count_after_second = cur.fetchone()["c"]

    assert count_after_first == count_after_second == 10


def test_load_vsam_policy_dispatches_all_types_correctly(conn):
    counts = load_vsam_policy.load("../sample_data/ksdspoly.txt", conn, encoding="ascii", schema="genapp")
    assert counts["policy"] == 10
    assert counts["commercial"] == 2
    assert counts["endowment"] == 2
    assert counts["house"] == 3
    assert counts["motor"] == 3
    assert counts["skipped"] == 0


def test_load_vsam_policy_house_detail_matches_known_sample_value(conn):
    """Regression guard for the exact byte-offset math in
    derived_vsam_policy.cpy's POLICY-H-DATA REDEFINES - confirms a
    known field from the real sample data decodes correctly."""
    load_vsam_policy.load("../sample_data/ksdspoly.txt", conn, encoding="ascii", schema="genapp")
    with conn.cursor() as cur:
        cur.execute("SELECT property_type, postcode FROM genapp.house WHERE policy_number = 6")
        row = cur.fetchone()
    assert row["property_type"].strip() == "HOUSE"
    assert row["postcode"].strip() == "SO211UP"


def test_db2_loader_upserts_idempotently(conn, tmp_path):
    """db2_loader.py must use a staging-table + ON CONFLICT upsert, not
    a plain COPY, so re-running it (e.g. because run_migration.py was
    re-run) never fails with a duplicate-key error."""
    csv_path = tmp_path / "test_claim.csv"
    csv_path.write_text("claim_number,policy_number,cause,paid,value\n9999001,1,First load,100,100\n")

    n1 = db2_loader.load_csv(str(csv_path), "claim", conn, schema="genapp")
    assert n1 == 1

    # Change a field and reload the SAME key - must update, not duplicate
    csv_path.write_text("claim_number,policy_number,cause,paid,value\n9999001,1,Updated cause,200,200\n")
    n2 = db2_loader.load_csv(str(csv_path), "claim", conn, schema="genapp")
    assert n2 == 1

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c, cause FROM genapp.claim WHERE claim_number = 9999001 GROUP BY cause")
            rows = cur.fetchall()
        assert len(rows) == 1  # only one row exists for this key
        assert rows[0]["cause"] == "Updated cause"
        assert rows[0]["c"] == 1
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM genapp.claim WHERE claim_number = 9999001")
        conn.commit()
