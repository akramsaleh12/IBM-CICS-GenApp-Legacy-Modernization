"""
test_validate_migration.py
------------------------------
Integration tests for validate_migration.py and resync_sequences.py.
Requires a real, freshly-migrated genapp database (same connection
defaults as the rest of this project):

    cd scripts
    pytest test_validate_migration.py -v

Run `python3 run_migration.py --data-dir ../sample_data ...` first if
starting from an empty server.
"""
import psycopg2
import psycopg2.extras
import pytest

from validate_migration import (
    _norm, _numeric_anomaly, run_full_validation,
    validate_type_dispatch_integrity, validate_referential_integrity,
)
from copybook_parser import parse_copybook
from resync_sequences import resync_sequences


@pytest.fixture
def conn():
    c = psycopg2.connect(host="localhost", port="5432", dbname="genapp", user="postgres", password="CHANGE_ME_LOCAL_ONLY")
    c.autocommit = True
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Unit-level: pure helper functions
# ---------------------------------------------------------------------------
def test_norm_treats_none_and_empty_as_equal():
    assert _norm(None) == _norm("")
    assert _norm("  x  ") == "x"


def test_numeric_anomaly_detects_embedded_space():
    """This is the exact pattern that caught the real bedrooms/status
    anomalies in ksdspoly.txt: a numeric DISPLAY field with a stray
    space in the middle instead of zero-padding."""
    class FakeField:
        pic = "9(03)"
        usage = "DISPLAY"
    anomaly = _numeric_anomaly(b"5 0", FakeField(), "ascii")
    assert anomaly is not None
    assert "5 0" in anomaly


def test_numeric_anomaly_accepts_properly_zero_padded_field():
    class FakeField:
        pic = "9(03)"
        usage = "DISPLAY"
    assert _numeric_anomaly(b"005", FakeField(), "ascii") is None


def test_numeric_anomaly_ignores_text_fields():
    class FakeField:
        pic = "X(03)"
        usage = "DISPLAY"
    assert _numeric_anomaly(b"A B", FakeField(), "ascii") is None


def test_numeric_anomaly_ignores_comp3_fields():
    """COMP-3 is pure binary - it can never have this class of anomaly,
    and must not be text-decoded to check for one (that would corrupt
    or crash on packed-decimal bytes)."""
    class FakeField:
        pic = "S9(03)"
        usage = "COMP-3"
    assert _numeric_anomaly(b"\x12\x3c", FakeField(), "ascii") is None


# ---------------------------------------------------------------------------
# Integration: full validation run against the real migrated database
# ---------------------------------------------------------------------------
def test_full_validation_passes_on_a_clean_migration(conn):
    report = run_full_validation(conn, "../sample_data", vsam_encoding="ascii", schema="genapp")
    assert report["passed"] is True
    for check in report["source_checks"]:
        assert check["passed"], f"{check['source']} failed: {check['field_mismatches']}"
    for check in report["integrity_checks"]:
        assert check["passed"], f"{check['check']} failed"


def test_validation_catches_a_deliberately_corrupted_field(conn):
    """Proves validate_migration.py isn't a rubber stamp: corrupt a
    real field, confirm it's caught with the exact key/column/values,
    then always restore it (even if an assertion fails) so this test
    never leaves the database in a bad state for other tests."""
    with conn.cursor() as cur:
        cur.execute("SELECT last_name FROM genapp.customer WHERE customer_number = 1")
        original = cur.fetchone()[0]
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE genapp.customer SET last_name = 'CORRUPTED_BY_TEST' WHERE customer_number = 1")

        report = run_full_validation(conn, "../sample_data", vsam_encoding="ascii", schema="genapp")
        customer_check = next(c for c in report["source_checks"] if "ksdscust" in c["source"])
        assert customer_check["passed"] is False
        mismatches = [m for m in customer_check["field_mismatches"] if m["key"] == 1 and m["column"] == "last_name"]
        assert len(mismatches) == 1
        assert mismatches[0]["target_value"] == "CORRUPTED_BY_TEST"
        assert mismatches[0]["source_value"] == original
    finally:
        with conn.cursor() as cur:
            cur.execute("UPDATE genapp.customer SET last_name = %s WHERE customer_number = 1", (original,))


def test_type_dispatch_integrity_passes_on_clean_data(conn):
    result = validate_type_dispatch_integrity(conn, schema="genapp")
    assert result["passed"] is True
    assert result["total_policies"] == 10


def test_type_dispatch_integrity_catches_an_orphan_detail_row(conn):
    """Insert a house detail row for a policy that's actually type Motor,
    confirm the integrity check flags it, then clean up."""
    with conn.cursor() as cur:
        cur.execute("SELECT policy_number FROM genapp.policy WHERE policy_type = 'M' LIMIT 1")
        motor_policy_number = cur.fetchone()[0]
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO genapp.house (policy_number, property_type) VALUES (%s, 'BOGUS')",
                (motor_policy_number,),
            )
        result = validate_type_dispatch_integrity(conn, schema="genapp")
        assert result["passed"] is False
        violation = next(v for v in result["violations"] if v["policy_number"] == motor_policy_number)
        assert "house=1" in violation["problem"]
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM genapp.house WHERE policy_number = %s", (motor_policy_number,))


def test_referential_integrity_passes_on_clean_data(conn):
    result = validate_referential_integrity(conn, schema="genapp")
    assert result["passed"] is True
    assert all(r["orphan_count"] == 0 for r in result["results"])


# ---------------------------------------------------------------------------
# Integration: identity sequence resync
# ---------------------------------------------------------------------------
def test_resync_sequences_fixes_a_deliberately_desynced_sequence(conn):
    """Reproduces the exact bug this project's own testing caught:
    manually inserting an explicit identity value doesn't advance the
    sequence, so the next auto-generated insert collides. Desync the
    claim sequence on purpose, confirm resync_sequences fixes it, and
    confirm a fresh auto-generated insert no longer collides."""
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(claim_number) FROM genapp.claim")
        max_before = cur.fetchone()[0] or 1000000
        # Force the sequence back to a colliding value
        cur.execute("SELECT setval(pg_get_serial_sequence('genapp.claim', 'claim_number'), 1, false)")

        # A naive auto-generated insert right now would collide
        cur.execute("SELECT nextval(pg_get_serial_sequence('genapp.claim', 'claim_number'))")
        desynced_next = cur.fetchone()[0]
        assert desynced_next <= max_before, "test setup didn't actually desync the sequence"

    resync_sequences(conn, schema="genapp", tables=[("claim", "claim_number")])

    with conn.cursor() as cur:
        cur.execute("SELECT nextval(pg_get_serial_sequence('genapp.claim', 'claim_number'))")
        resynced_next = cur.fetchone()[0]
    assert resynced_next > max_before


# ---------------------------------------------------------------------------
# Integration: copybook byte-length matches the real sample data files
# ---------------------------------------------------------------------------
def test_sample_data_files_match_copybook_record_lengths():
    from copybook_parser import record_length
    with open("../copybooks/derived_vsam_customer.cpy") as fh:
        cust_len = record_length(parse_copybook(fh.read()))
    with open("../copybooks/derived_vsam_policy.cpy") as fh:
        poly_len = record_length(parse_copybook(fh.read()))

    with open("../sample_data/ksdscust.txt", "rb") as fh:
        first_line = fh.readline().rstrip(b"\n")
    with open("../sample_data/ksdspoly.txt", "rb") as fh:
        first_poly_line = fh.readline().rstrip(b"\n")

    assert len(first_line) == cust_len
    assert len(first_poly_line) == poly_len
