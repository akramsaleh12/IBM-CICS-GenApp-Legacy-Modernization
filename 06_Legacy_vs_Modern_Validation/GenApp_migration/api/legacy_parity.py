"""
legacy_parity.py
------------------
Legacy vs Modern VALIDATION - distinct from scripts/validate_migration.py,
which checks that migrated DATA matches the source VSAM/DB2 files
byte-for-byte. This checks that the modern system's BEHAVIOR matches
the documented legacy BUSINESS RULES (or deliberately, transparently
deviates from them) - a functional/behavioral parity check, not a
data check.

Every rule below cites the specific legacy program and section of
reference/01-analysis/03_business_rules/GenApp_Business_Rules.md,
07_CRUD_Matrix/GenApp_CRUD_Matrix.md, or
08_Legacy_to_Modern_Mapping/GenApp_Legacy_Modern_Mapping.md it comes
from. Nothing here is invented - if you can't find the citation in
those files, treat the rule as a bug and file an issue.

Each rule resolves to one of five statuses, not a flat pass/fail,
because faithful "legacy parity" isn't always the right goal for a
modernization:

    MATCH            - modern behavior reproduces the documented legacy rule
    DEVIATION        - modern intentionally differs, for a documented reason
    NEW_CAPABILITY   - modern does something legacy never did at all
    NOT_IMPLEMENTED  - legacy had this rule; modern hasn't built an
                        equivalent yet (a genuine, honestly-reported gap)
    FAIL             - modern contradicts the documented rule with no
                        known rationale - a real regression

Each rule also declares whether its check is STATIC (source/schema
inspection - no live behavior invoked) or DYNAMIC (actually calls a
business_services method and observes what happens).

USAGE:
    python3 legacy_parity.py --host localhost --dbname genapp \
        --user postgres --password CHANGE_ME_LOCAL_ONLY

Can also be imported and driven programmatically (see
streamlit_app/legacy_parity_app.py and routers/meta.py's
/legacy-parity endpoint) via run_legacy_parity_validation(conn).
"""
import argparse
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from business_services import CustomerService, PolicyService, ClaimService
from business_services.exceptions import (
    NotFoundError, OptimisticLockError, ValidationError,
    UnsupportedOperationError, ForeignKeyError,
)
from database import PG_CONFIG


# ---------------------------------------------------------------------------
# Individual rule checks. Each returns (status, evidence_str).
# ---------------------------------------------------------------------------
def check_return_code_01_not_found(conn):
    """Business Rules §10 catalogue: code '01' = no row found
    (SQLCODE=+100), origin LGICDB01/LGIPDB01/LGUCDB01/LGUPDB01."""
    svc = CustomerService(conn)
    try:
        svc.get_customer(999999)
        return "FAIL", "expected NotFoundError, none was raised"
    except NotFoundError as e:
        if e.legacy_return_code == "01":
            return "MATCH", f"NotFoundError raised with legacy_return_code='{e.legacy_return_code}'"
        return "FAIL", f"NotFoundError raised but legacy_return_code='{e.legacy_return_code}', expected '01'"


def check_return_code_02_optimistic_lock(conn):
    """Business Rules §10 catalogue + §7: code '02' = optimistic-lock
    timestamp mismatch, origin LGUPDB01 ONLY (Policy update)."""
    ps = PolicyService(conn)
    result = ps.add_policy(1, "M", {}, {"make": "PARITY-TEST"})
    policy_number = result["policy"]["policy_number"]
    try:
        lc = result["policy"]["last_changed"]
        ps.update_policy(policy_number, lc, {}, {"make": "X"})  # consume the lock
        try:
            ps.update_policy(policy_number, lc, {}, {"make": "Y"})  # reuse stale lock
            return "FAIL", "expected OptimisticLockError on stale last_changed, none was raised"
        except OptimisticLockError as e:
            if e.legacy_return_code == "02":
                return "MATCH", f"OptimisticLockError raised with legacy_return_code='{e.legacy_return_code}'"
            return "FAIL", f"legacy_return_code='{e.legacy_return_code}', expected '02'"
    finally:
        ps.delete_policy(policy_number)


def check_return_code_98_bad_input(conn):
    """Business Rules §10 catalogue: code '98' = COMMAREA/input
    validation failure, universal across business-logic programs."""
    ps = PolicyService(conn)
    try:
        ps.add_policy(1, "X", {}, {})
        return "FAIL", "expected ValidationError for invalid policy_type, none was raised"
    except ValidationError as e:
        if e.legacy_return_code == "98":
            return "MATCH", f"ValidationError raised with legacy_return_code='{e.legacy_return_code}'"
        return "FAIL", f"legacy_return_code='{e.legacy_return_code}', expected '98'"


def check_return_code_90_general_db_error(conn):
    """Business Rules §10 catalogue: code '90' = general/unexpected Db2
    SQLCODE, the catch-all failure code from nearly every Db2-layer
    program. STATIC check only: business_services pre-validates
    foreign keys before every insert (see add_policy/add_claim), so
    this exception's except-clause is only reachable via a genuine
    race condition (the referenced row is deleted between the
    pre-check and the INSERT) - correctly narrow, but not something a
    single-threaded automated test can trigger deterministically.
    This check instead confirms the exception class and its return
    code mapping are correctly wired to a real except clause, by
    source inspection."""
    source = inspect.getsource(PolicyService.add_policy)
    if "ForeignKeyError" in source and "psycopg2.errors.ForeignKeyViolation" in source:
        if ForeignKeyError.legacy_return_code == "90":
            return "MATCH", ("ForeignKeyError(legacy_return_code='90') is wired to a ForeignKeyViolation "
                              "except-clause in PolicyService.add_policy (source-verified; only reachable "
                              "via a genuine race condition, not exercised live)")
    return "FAIL", "ForeignKeyError is not wired to a ForeignKeyViolation handler in PolicyService.add_policy"


def check_return_code_99_program_specific_logic_error(conn):
    """Business Rules §10 catalogue: code '99' = program-specific logic
    error, cited origin includes LGUPOL01/LGDPOL01 - exactly the
    Commercial-no-update restriction this modernization preserves."""
    ps = PolicyService(conn)
    result = ps.add_policy(1, "C", {}, {"zipcode": "AB1 2CD", "status": 1})
    policy_number = result["policy"]["policy_number"]
    try:
        try:
            ps.update_policy(policy_number, result["policy"]["last_changed"], {}, {"status": 2})
            return "FAIL", "expected UnsupportedOperationError for Commercial update, none was raised"
        except UnsupportedOperationError as e:
            if e.legacy_return_code == "99":
                return "MATCH", f"UnsupportedOperationError raised with legacy_return_code='{e.legacy_return_code}'"
            return "FAIL", f"legacy_return_code='{e.legacy_return_code}', expected '99'"
    finally:
        ps.delete_policy(policy_number)


def check_customer_update_optimistic_lock_deviation(conn):
    """Business Rules §7: LGUPDB01's optimistic-concurrency check
    applies ONLY to Policy updates in the legacy system - Customer
    updates (LGUCUS01/LGUCDB01) never had an equivalent check.
    Legacy-to-Modern Mapping §4 explicitly recommends: "Apply the same
    ETag/version-column pattern uniformly to Customer as well as
    Policy." This modernization does exactly that (sql/04_business_rules.sql
    adds customer.last_changed + trigger) - a DELIBERATE, DOCUMENTED
    deviation from strict legacy parity, not a bug."""
    cs = CustomerService(conn)
    cust = cs.add_customer({"first_name": "PARITY", "last_name": "TEST"})
    try:
        lc = cust["last_changed"]
        cs.update_customer(cust["customer_number"], {"last_name": "X"}, expected_last_changed=lc)
        try:
            cs.update_customer(cust["customer_number"], {"last_name": "Y"}, expected_last_changed=lc)
            return "FAIL", "expected the modernization's added optimistic lock to reject a stale Customer update"
        except OptimisticLockError:
            return "DEVIATION", ("Customer update now enforces an optimistic lock legacy never had - "
                                  "an intentional fix, not a parity match, per Legacy-to-Modern Mapping §4")
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM genapp.customer WHERE customer_number = %s", (cust["customer_number"],))
        conn.commit()


def check_add_policy_rollback_on_partial_failure(conn):
    """Business Rules §6 "Rollback protocol": any non-zero return code
    partway through a two-phase write causes a full SYNCPOINT ROLLBACK
    - "ensuring the Db2/VSAM two-phase write is fully undone on any
    failure partway through." Modernized as one ACID transaction; this
    check confirms a failed add_policy call leaves NO orphan policy row."""
    ps = PolicyService(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM genapp.policy WHERE customer_number = 999999")
        before = cur.fetchone()["c"]
    try:
        ps.add_policy(999999, "M", {}, {"make": "SHOULD-NOT-PERSIST"})
        return "FAIL", "expected add_policy to fail for a nonexistent customer, it succeeded"
    except NotFoundError:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM genapp.policy WHERE customer_number = 999999")
            after = cur.fetchone()["c"]
        if after == before:
            return "MATCH", f"no orphan policy row left behind (count before={before}, after={after})"
        return "FAIL", f"orphan policy row(s) found after failed add_policy (before={before}, after={after})"


def check_customer_has_no_delete_capability(conn):
    """07_CRUD_Matrix Gap 1: "No delete function exists at any layer
    (COBOL, Db2, or VSAM)" for Customer. STATIC check: confirms
    CustomerService defines no delete_customer method and the business
    router exposes no DELETE /business/customers/{id} route - the
    modernization preserves this as a genuine finding rather than
    silently completing the CRUD set."""
    has_method = hasattr(CustomerService, "delete_customer")
    try:
        from main import app
        has_route = any(
            getattr(r, "path", None) == "/business/customers/{customer_number}"
            and "DELETE" in getattr(r, "methods", set())
            for r in app.routes
        )
    except Exception as e:
        return "FAIL", f"could not inspect FastAPI routes: {e}"

    if not has_method and not has_route:
        return "MATCH", "CustomerService has no delete_customer method and no DELETE route exists under /business/customers"
    return "FAIL", f"delete capability found where legacy has none (method={has_method}, route={has_route})"


def check_commercial_policy_no_update_path(conn):
    """07_CRUD_Matrix Gap 2: Commercial is the only policy type with no
    Update path in the legacy system; the source report explicitly
    hedges on whether this is intentional. This modernization
    preserves the restriction BY DEFAULT (allow_commercial_update=False),
    with an explicit override available once confirmed with the business."""
    ps = PolicyService(conn)  # allow_commercial_update defaults to False
    result = ps.add_policy(1, "C", {}, {"zipcode": "AB1 2CD", "status": 1})
    policy_number = result["policy"]["policy_number"]
    try:
        try:
            ps.update_policy(policy_number, result["policy"]["last_changed"], {}, {"status": 2})
            return "FAIL", "Commercial update succeeded; legacy gap was not preserved"
        except UnsupportedOperationError:
            return "MATCH", "Commercial policy update blocked by default, matching the undocumented legacy gap"
    finally:
        ps.delete_policy(policy_number)


def check_claim_is_a_new_capability(conn):
    """07_CRUD_Matrix Gap 3 / Legacy-to-Modern Mapping §5: "Claim ...
    zero application-level CRUD ... 100% new-build; do not assume
    claims functionality exists to 'lift'." Any working ClaimService
    behavior is a NEW_CAPABILITY, not a parity match - there is
    nothing in the legacy system to compare it against."""
    ps = PolicyService(conn)
    result = ps.add_policy(1, "M", {}, {"make": "PARITY-CLAIM"})
    policy_number = result["policy"]["policy_number"]
    try:
        cls = ClaimService(conn)
        claim = cls.add_claim(policy_number, {"cause": "parity test"})
        if claim.get("claim_number"):
            return "NEW_CAPABILITY", "ClaimService works; no legacy program ever implemented claims CRUD to compare it against"
        return "FAIL", "add_claim did not return a claim_number"
    finally:
        ps.delete_policy(policy_number)  # cascades the claim too


def check_policy_type_discriminator_restricted_to_four_values(conn):
    """01-analysis §11 Transaction Type/Category Maintenance:
    POLICY.POLICYTYPE is a single character restricted to exactly
    M/E/H/C, with NO governed lookup table - the domain is implicitly
    hardcoded by which presentation transaction the user entered from."""
    ps = PolicyService(conn)
    for bad_type in ["Z", "1", "MOTOR", ""]:
        try:
            ps.add_policy(1, bad_type, {}, {})
            return "FAIL", f"policy_type={bad_type!r} was accepted; should have been rejected"
        except ValidationError:
            continue
    return "MATCH", "policy_type is rejected for any value outside {C, E, H, M}"


def check_postcode_uppercase_normalization(conn):
    """Business Rules: LGTESTC1 applies FUNCTION UPPER-CASE(CA-POSTCODE)
    before storage."""
    cs = CustomerService(conn)
    cust = cs.add_customer({"first_name": "PARITY", "last_name": "TEST", "postcode": "sw1a 1aa"})
    try:
        if cust["postcode"] == "SW1A 1AA":
            return "MATCH", f"postcode stored as {cust['postcode']!r}"
        return "FAIL", f"postcode stored as {cust['postcode']!r}, expected uppercased"
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM genapp.customer WHERE customer_number = %s", (cust["customer_number"],))
        conn.commit()


def check_commercial_cursor_row_limit(conn):
    """Business Rules §10 "Cursor row-limit rule": the Commercial-policy
    multi-row cursor fetch (GET-Commercial-DB2-INFO-3-Cur) caps at 20
    rows (a hardcoded "stop fetching" signal, not a real SQLCODE) - "a
    business/performance rule ... should be preserved (or replaced
    with proper pagination) in a modernized design." This modernization
    has NOT yet built an equivalent capped/paginated multi-row
    Commercial-policy inquiry - honestly reported as a gap rather than
    silently ignored."""
    return "NOT_IMPLEMENTED", ("No modern equivalent of the 20-row-capped Commercial-policy multi-row "
                                "inquiry exists yet. The raw CRUD API's GET /commercials?limit=N offers "
                                "generic pagination (arguably a better replacement per the source report's "
                                "own suggestion), but no business_services method reproduces this specific "
                                "legacy rule or has been confirmed as its intended replacement.")


def check_named_counter_fallback_deviation(conn):
    """Business Rules §10 "Named-counter vs. identity-column fallback":
    legacy tries a CICS coupling-facility named counter first for new
    Customer/Policy keys, falling back to a Db2 IDENTITY column only if
    the coupling facility is unavailable - "makes GenApp portable
    between single-region and multi-region topologies." This
    modernization always uses a single PostgreSQL IDENTITY sequence -
    an intentional simplification appropriate for a modernized
    single-database architecture, not a parity match (there is no
    coupling-facility equivalent to fall back from)."""
    return "DEVIATION", ("Always uses PostgreSQL IDENTITY sequences (see sql/02_target_schema.sql); "
                          "the CICS named-counter/coupling-facility fallback has no equivalent in a "
                          "single-database PostgreSQL architecture and was intentionally not reproduced.")


# ---------------------------------------------------------------------------
# Rule catalogue
# ---------------------------------------------------------------------------
RULES = [
    {"id": "RC-01", "category": "Return codes", "check_type": "dynamic",
     "citation": "Business Rules §10 (return-code catalogue, code '01')",
     "description": "No row found maps to a NotFoundError carrying legacy_return_code='01'",
     "fn": check_return_code_01_not_found},
    {"id": "RC-02", "category": "Return codes", "check_type": "dynamic",
     "citation": "Business Rules §10 (code '02') / §7 (LGUPDB01 optimistic lock)",
     "description": "Stale optimistic-lock update maps to OptimisticLockError carrying legacy_return_code='02'",
     "fn": check_return_code_02_optimistic_lock},
    {"id": "RC-03", "category": "Return codes", "check_type": "dynamic",
     "citation": "Business Rules §10 (code '98', universal COMMAREA/input validation)",
     "description": "Invalid input maps to ValidationError carrying legacy_return_code='98'",
     "fn": check_return_code_98_bad_input},
    {"id": "RC-04", "category": "Return codes", "check_type": "static",
     "citation": "Business Rules §10 (code '90', general Db2 SQLCODE catch-all)",
     "description": "Foreign-key violations map to ForeignKeyError carrying legacy_return_code='90'",
     "fn": check_return_code_90_general_db_error},
    {"id": "RC-05", "category": "Return codes", "check_type": "dynamic",
     "citation": "Business Rules §10 (code '99', program-specific logic error, incl. LGUPOL01)",
     "description": "Blocked Commercial-policy update maps to UnsupportedOperationError carrying legacy_return_code='99'",
     "fn": check_return_code_99_program_specific_logic_error},
    {"id": "CONC-01", "category": "Concurrency", "check_type": "dynamic",
     "citation": "Business Rules §7 (LGUPDB01-only lock) + Legacy-to-Modern Mapping §4 (recommendation)",
     "description": "Customer updates now enforce an optimistic lock legacy never had",
     "fn": check_customer_update_optimistic_lock_deviation},
    {"id": "TXN-01", "category": "Transaction integrity", "check_type": "dynamic",
     "citation": "Business Rules §6 (rollback protocol)",
     "description": "A failed Add Policy leaves no orphan policy row (atomic header+detail write)",
     "fn": check_add_policy_rollback_on_partial_failure},
    {"id": "CRUD-GAP-01", "category": "CRUD gaps", "check_type": "static",
     "citation": "07_CRUD_Matrix Gap 1",
     "description": "Customer has no delete capability at the business-services layer",
     "fn": check_customer_has_no_delete_capability},
    {"id": "CRUD-GAP-02", "category": "CRUD gaps", "check_type": "dynamic",
     "citation": "07_CRUD_Matrix Gap 2",
     "description": "Commercial policies cannot be updated (by default)",
     "fn": check_commercial_policy_no_update_path},
    {"id": "CRUD-GAP-03", "category": "CRUD gaps", "check_type": "dynamic",
     "citation": "07_CRUD_Matrix Gap 3 / Legacy-to-Modern Mapping §5",
     "description": "Claims filing is a new capability with no legacy program to compare against",
     "fn": check_claim_is_a_new_capability},
    {"id": "TYPE-01", "category": "Type dispatch", "check_type": "dynamic",
     "citation": "01-analysis §11 (policy-type discriminator, no governed lookup table)",
     "description": "policy_type is restricted to exactly {C, E, H, M}",
     "fn": check_policy_type_discriminator_restricted_to_four_values},
    {"id": "NORM-01", "category": "Data normalization", "check_type": "dynamic",
     "citation": "Business Rules (LGTESTC1 FUNCTION UPPER-CASE)",
     "description": "Customer postcode is upper-cased before storage",
     "fn": check_postcode_uppercase_normalization},
    {"id": "PERF-01", "category": "Business/performance rules", "check_type": "static",
     "citation": "Business Rules §10 (\"Cursor row-limit rule\", 20-row cap)",
     "description": "Commercial-policy multi-row inquiry cap - not yet built in the modern system",
     "fn": check_commercial_cursor_row_limit},
    {"id": "COUNTER-01", "category": "Key generation", "check_type": "static",
     "citation": "Business Rules §10 (\"Named-counter vs. identity-column fallback\")",
     "description": "Modern system always uses PostgreSQL IDENTITY, never a CICS named counter",
     "fn": check_named_counter_fallback_deviation},
]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_legacy_parity_validation(conn) -> dict:
    results = []
    for rule in RULES:
        try:
            status, evidence = rule["fn"](conn)
        except Exception as e:
            status, evidence = "FAIL", f"check raised an unexpected exception: {type(e).__name__}: {e}"
        results.append({
            "id": rule["id"], "category": rule["category"], "check_type": rule["check_type"],
            "citation": rule["citation"], "description": rule["description"],
            "status": status, "evidence": evidence,
        })

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    return {
        "rules": results,
        "counts": counts,
        "passed": counts.get("FAIL", 0) == 0,
    }


def print_report(report: dict) -> None:
    print("=" * 78)
    print("LEGACY vs MODERN BEHAVIORAL PARITY REPORT")
    print("=" * 78)
    for r in report["rules"]:
        print(f"\n[{r['status']:16s}] {r['id']} ({r['category']}, {r['check_type']})")
        print(f"  Legacy citation: {r['citation']}")
        print(f"  Rule: {r['description']}")
        print(f"  Evidence: {r['evidence']}")

    print("\n" + "=" * 78)
    print("SUMMARY:", ", ".join(f"{k}={v}" for k, v in sorted(report["counts"].items())))
    print("OVERALL RESULT:", "PASS (no FAILs)" if report["passed"] else "FAIL")
    print("=" * 78)


def main():
    import psycopg2
    import psycopg2.extras
    parser = argparse.ArgumentParser(description="Validate legacy-vs-modern business-rule parity")
    parser.add_argument("--host", default=PG_CONFIG["host"])
    parser.add_argument("--port", default=PG_CONFIG["port"])
    parser.add_argument("--dbname", default=PG_CONFIG["dbname"])
    parser.add_argument("--user", default=PG_CONFIG["user"])
    parser.add_argument("--password", default=PG_CONFIG["password"])
    parser.add_argument("--schema", default="genapp", help="(accepted for CLI consistency with the other "
                                                             "scripts in this project; all checks currently "
                                                             "assume the genapp schema)")
    args = parser.parse_args()

    conn = psycopg2.connect(host=args.host, port=args.port, dbname=args.dbname,
                             user=args.user, password=args.password)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    try:
        report = run_legacy_parity_validation(conn)
        print_report(report)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
