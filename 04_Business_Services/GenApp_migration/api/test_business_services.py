"""
test_business_services.py
----------------------------
Automated tests for api/business_services/ - codifies every scenario
verified manually during development, so regressions get caught
automatically. Run against a real PostgreSQL genapp database (uses
the same connection defaults as the rest of this project).

USAGE:
    cd api
    pip install pytest
    pytest test_business_services.py -v

Each test is independent and cleans up after itself (deletes what it
created), so the suite can run repeatedly against the same database
without needing a fresh migration each time.
"""
import psycopg2
import psycopg2.extras
import pytest

from business_services import CustomerService, PolicyService, ClaimService
from business_services.exceptions import (
    NotFoundError, OptimisticLockError, ValidationError, UnsupportedOperationError,
)


@pytest.fixture
def conn():
    c = psycopg2.connect(host="localhost", port="5432", dbname="genapp", user="postgres", password="CHANGE_ME_LOCAL_ONLY")
    c.cursor_factory = psycopg2.extras.RealDictCursor
    yield c
    c.close()


@pytest.fixture
def customer_service(conn):
    return CustomerService(conn)


@pytest.fixture
def policy_service(conn):
    return PolicyService(conn)


@pytest.fixture
def claim_service(conn):
    return ClaimService(conn)


# ---------------------------------------------------------------------------
# CustomerService
# ---------------------------------------------------------------------------
class TestCustomerService:
    def test_add_customer_creates_secure_row_atomically(self, conn, customer_service):
        cust = customer_service.add_customer({"first_name": "T", "last_name": "U", "email_address": "t@u.com"})
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT customer_pass FROM genapp.customer_secure WHERE customer_number = %s",
                            (cust["customer_number"],))
                row = cur.fetchone()
            assert row is not None
            assert row["customer_pass"]  # placeholder password set
        finally:
            _cleanup_customer(conn, cust["customer_number"])

    def test_get_customer_not_found_raises(self, customer_service):
        with pytest.raises(NotFoundError) as exc:
            customer_service.get_customer(999999)
        assert exc.value.legacy_return_code == "01"

    def test_update_customer_with_correct_lock_succeeds(self, conn, customer_service):
        cust = customer_service.add_customer({"first_name": "A", "last_name": "B"})
        try:
            updated = customer_service.update_customer(
                cust["customer_number"], {"last_name": "C"}, expected_last_changed=cust["last_changed"]
            )
            assert updated["last_name"] == "C"
            assert updated["last_changed"] != cust["last_changed"]
        finally:
            _cleanup_customer(conn, cust["customer_number"])

    def test_update_customer_with_stale_lock_conflicts(self, conn, customer_service):
        cust = customer_service.add_customer({"first_name": "A", "last_name": "B"})
        try:
            customer_service.update_customer(cust["customer_number"], {"last_name": "C"}, cust["last_changed"])
            with pytest.raises(OptimisticLockError) as exc:
                customer_service.update_customer(cust["customer_number"], {"last_name": "D"}, cust["last_changed"])
            assert exc.value.legacy_return_code == "02"
        finally:
            _cleanup_customer(conn, cust["customer_number"])

    def test_postcode_uppercased(self, conn, customer_service):
        cust = customer_service.add_customer({"first_name": "A", "last_name": "B", "postcode": "sw1a 1aa"})
        try:
            assert cust["postcode"] == "SW1A 1AA"
        finally:
            _cleanup_customer(conn, cust["customer_number"])


# ---------------------------------------------------------------------------
# PolicyService
# ---------------------------------------------------------------------------
class TestPolicyService:
    def test_add_policy_invalid_type_raises(self, policy_service):
        with pytest.raises(ValidationError) as exc:
            policy_service.add_policy(1, "X", {}, {})
        assert exc.value.legacy_return_code == "98"

    def test_add_policy_unknown_customer_raises_and_does_not_leave_orphan(self, conn, policy_service):
        with pytest.raises(NotFoundError):
            policy_service.add_policy(999999, "M", {}, {"make": "FORD"})
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM genapp.policy WHERE customer_number = 999999")
            assert cur.fetchone()["c"] == 0

    def test_add_and_get_policy_atomic(self, conn, policy_service):
        result = policy_service.add_policy(1, "M", {}, {"make": "TOYOTA", "model": "YARIS", "value": 9000})
        policy_number = result["policy"]["policy_number"]
        try:
            fetched = policy_service.get_policy(policy_number)
            assert fetched["detail_table"] == "motor"
            assert fetched["detail"]["make"] == "TOYOTA"
        finally:
            policy_service.delete_policy(policy_number)

    def test_update_policy_detail_only_still_bumps_lock(self, policy_service):
        result = policy_service.add_policy(1, "H", {}, {"property_type": "FLAT", "bedrooms": 2})
        policy_number = result["policy"]["policy_number"]
        try:
            lc1 = result["policy"]["last_changed"]
            updated = policy_service.update_policy(policy_number, lc1, {}, {"bedrooms": 3})
            lc2 = updated["policy"]["last_changed"]
            assert lc2 != lc1, "policy.last_changed must advance even on a detail-only update"
            with pytest.raises(OptimisticLockError):
                policy_service.update_policy(policy_number, lc1, {}, {"bedrooms": 4})
        finally:
            policy_service.delete_policy(policy_number)

    def test_commercial_update_blocked_by_default(self, policy_service):
        result = policy_service.add_policy(1, "C", {}, {"zipcode": "AB1 2CD", "status": 1})
        policy_number = result["policy"]["policy_number"]
        try:
            with pytest.raises(UnsupportedOperationError) as exc:
                policy_service.update_policy(policy_number, result["policy"]["last_changed"], {}, {"status": 2})
            assert exc.value.legacy_return_code == "99"
        finally:
            policy_service.delete_policy(policy_number)

    def test_commercial_update_allowed_with_override(self, conn):
        svc = PolicyService(conn, allow_commercial_update=True)
        result = svc.add_policy(1, "C", {}, {"zipcode": "AB1 2CD", "status": 1})
        policy_number = result["policy"]["policy_number"]
        try:
            updated = svc.update_policy(policy_number, result["policy"]["last_changed"], {}, {"status": 2})
            assert updated["detail"]["status"] == 2
        finally:
            svc.delete_policy(policy_number)

    def test_delete_policy_cascades_detail_row(self, conn, policy_service):
        result = policy_service.add_policy(1, "M", {}, {"make": "VW"})
        policy_number = result["policy"]["policy_number"]
        policy_service.delete_policy(policy_number)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM genapp.motor WHERE policy_number = %s", (policy_number,))
            assert cur.fetchone()["c"] == 0

    def test_delete_missing_policy_raises(self, policy_service):
        with pytest.raises(NotFoundError):
            policy_service.delete_policy(999999)


# ---------------------------------------------------------------------------
# ClaimService
# ---------------------------------------------------------------------------
class TestClaimService:
    def test_add_claim_against_unknown_policy_raises(self, claim_service):
        with pytest.raises(NotFoundError):
            claim_service.add_claim(999999, {"cause": "orphan"})

    def test_add_get_list_claim(self, conn, policy_service, claim_service):
        result = policy_service.add_policy(1, "M", {}, {"make": "BMW"})
        policy_number = result["policy"]["policy_number"]
        try:
            claim = claim_service.add_claim(policy_number, {"cause": "Test", "value": 100, "paid": 90})
            assert claim_service.get_claim(claim["claim_number"])["cause"] == "Test"
            assert len(claim_service.list_claims_for_policy(policy_number)) == 1
        finally:
            policy_service.delete_policy(policy_number)  # claim cascades too


def _cleanup_customer(conn, customer_number):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM genapp.customer WHERE customer_number = %s", (customer_number,))
    conn.commit()
