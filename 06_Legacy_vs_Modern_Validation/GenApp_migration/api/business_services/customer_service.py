"""
customer_service.py
---------------------
Business logic tier equivalent of GenApp's LGACUS01 (Add), LGICUS01
(Inquire), LGUCUS01 (Update) - see
01-analysis/08_Legacy_to_Modern_Mapping/GenApp_Legacy_Modern_Mapping.md
Section 4: "CustomerService (Add/Get/Update methods) ... the most
directly translatable tier in the codebase."

Deliberately has NO delete_customer method. 07_CRUD_Matrix Gap 1: "No
delete function exists at any layer (COBOL, Db2, or VSAM)" for
Customer - this service preserves that as a genuine business-rule
finding rather than silently completing the CRUD set, per that
report's own guidance ("A migrated system should not silently
'complete' these CRUD sets without [business] confirmation"). The raw
CRUD API's DELETE /customers/{id} remains available as an explicit,
separately-flagged escape hatch outside this business-rules layer.
"""
import secrets

import psycopg2.errors

from .exceptions import NotFoundError, OptimisticLockError, ValidationError

# The exact literal value LGACDB01 hardcodes into every customer_secure
# row, regardless of what the user entered - see Business Rules Section 2:
# "every customer gets the identical stored password value ... a demo
# artifact, not a real credential system."
LEGACY_PLACEHOLDER_PASSWORD = "5732fec825535eeafb8fac50fee3a8aa"


class CustomerService:
    def __init__(self, conn, schema: str = "genapp", preserve_legacy_password_bug: bool = True):
        """
        preserve_legacy_password_bug: when True (default), add_customer
        reproduces LGACDB01's exact behavior - every customer_secure row
        gets the SAME hardcoded placeholder password. This is a known
        demo bug, not a design to imitate in production (Business Rules
        Section 2 and Legacy-to-Modern Mapping Section 8 both flag it
        explicitly: "Do not migrate as-is"). It defaults to True here
        because a business-services layer's job during a strangler-fig
        migration is to faithfully preserve documented legacy behavior
        for parity testing, not to silently "fix" security bugs no one
        asked about yet. Set False to get a random per-customer
        placeholder instead (still not real hashing - wire up bcrypt/
        Argon2 before using this table for actual authentication).
        """
        self.conn = conn
        self.schema = schema
        self.preserve_legacy_password_bug = preserve_legacy_password_bug

    # ------------------------------------------------------------------
    def add_customer(self, data: dict) -> dict:
        """Mirrors LGACUS01 -> LGACDB01 -> LGACDB02: creates the customer
        row AND its customer_secure row as one atomic unit (the two-phase
        Db2 write, collapsed into a single ACID transaction per
        Legacy-to-Modern Mapping Section 2's architecture-level guidance
        now that both live in one datastore)."""
        data = dict(data)
        if data.get("postcode"):
            # LGTESTC1: FUNCTION UPPER-CASE(CA-POSTCODE) before storage
            data["postcode"] = data["postcode"].upper()

        cols = list(data.keys())
        explicit_pk = "customer_number" in cols and data.get("customer_number") is not None
        if "customer_number" in cols and not explicit_pk:
            cols.remove("customer_number")
        col_list = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        overriding = " OVERRIDING SYSTEM VALUE " if explicit_pk else " "

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    f'INSERT INTO {self.schema}.customer ({col_list}){overriding}'
                    f'VALUES ({placeholders}) RETURNING *',
                    [data[c] for c in cols],
                )
                customer = cur.fetchone()

                password = (LEGACY_PLACEHOLDER_PASSWORD if self.preserve_legacy_password_bug
                            else secrets.token_hex(16))
                cur.execute(
                    f'INSERT INTO {self.schema}.customer_secure '
                    f'(customer_number, customer_pass, state_indicator, pass_changes) '
                    f'VALUES (%s, %s, %s, %s)',
                    (customer["customer_number"], password, "A", 0),
                )
            self.conn.commit()
        except psycopg2.errors.UniqueViolation as e:
            self.conn.rollback()
            raise ValidationError(f"customer_number already exists: {e.diag.message_primary or e}")
        except psycopg2.Error as e:
            # Catch-all - see the matching comment in policy_service.py's
            # add_policy for why this is required, not optional.
            self.conn.rollback()
            raise ValidationError(str(e.diag.message_primary or e))
        return customer

    # ------------------------------------------------------------------
    def get_customer(self, customer_number: int) -> dict:
        """Mirrors LGICUS01 -> LGICDB01 (Db2 read only - the VSAM read
        path LGICVS01 has no unique data per Database Analysis Section
        3b and is retired per Legacy-to-Modern Mapping Section 5)."""
        with self.conn.cursor() as cur:
            cur.execute(f'SELECT * FROM {self.schema}.customer WHERE customer_number = %s', (customer_number,))
            row = cur.fetchone()
        if row is None:
            raise NotFoundError(f"customer {customer_number} not found")
        return row

    # ------------------------------------------------------------------
    def update_customer(self, customer_number: int, data: dict, expected_last_changed=None) -> dict:
        """Mirrors LGUCUS01 -> LGUCDB01, PLUS an optimistic-concurrency
        check that legacy Customer updates never had (Business Rules
        Section 6 flags this as "an inconsistency ... worth flagging");
        Legacy-to-Modern Mapping Section 4 explicitly recommends fixing
        it here rather than preserving it. Pass expected_last_changed
        (the value from a prior get_customer call) to enforce the lock;
        pass None to skip the check (not recommended for concurrent
        callers, but kept optional so a single-writer admin tool isn't
        forced to round-trip a read first)."""
        current = self.get_customer(customer_number)  # raises NotFoundError if missing

        if expected_last_changed is not None and current["last_changed"] != expected_last_changed:
            raise OptimisticLockError(
                f"customer {customer_number} was modified by someone else "
                f"(expected last_changed={expected_last_changed}, actual={current['last_changed']})"
            )

        data = dict(data)
        if data.get("postcode"):
            data["postcode"] = data["postcode"].upper()
        data.pop("customer_number", None)
        data.pop("last_changed", None)  # trigger-maintained, never client-settable

        if not data:
            return current  # nothing to update

        set_clause = ", ".join(f"{c} = %s" for c in data.keys())
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    f'UPDATE {self.schema}.customer SET {set_clause} '
                    f'WHERE customer_number = %s RETURNING *',
                    list(data.values()) + [customer_number],
                )
                row = cur.fetchone()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return row
