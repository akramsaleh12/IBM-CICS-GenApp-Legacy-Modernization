"""
policy_service.py
-------------------
Business logic tier equivalent of GenApp's LGAPOL01 (Add), LGIPOL01
(Inquire), LGUPOL01 (Update), LGDPOL01 (Delete) - one set of 4
programs shared by all 4 policy types (Motor/Endowment/House/
Commercial), branching internally on policyType. See
08_Legacy_to_Modern_Mapping Section 4: "PolicyService (Add/Get/Update/
Delete methods), type-parameterized ... already the correct shape for
a modern service layer." This class is exactly that: one
type-parameterized service instead of 4 near-duplicate ones,
consolidating the "wide, not deep" 4-way template duplication the
Complexity Analysis report flags in the legacy programs.
"""
import psycopg2.errors

from .exceptions import (
    NotFoundError, OptimisticLockError, ValidationError,
    UnsupportedOperationError, ForeignKeyError,
)

TYPE_TABLES = {"E": "endowment", "H": "house", "M": "motor", "C": "commercial"}

# 07_CRUD_Matrix Section 4/5: "Commercial policy | Update | ... No
# Update function - the only policy type that cannot be amended once
# created." The source report explicitly hedges on whether this is a
# deliberate business rule or incomplete demo coverage ("unclear
# whether this is an intentional business rule ... or simply
# incomplete demo coverage; worth confirming with the business").
# This service preserves the restriction by default (allow_commercial_update
# = False) rather than silently completing the CRUD set, consistent
# with the CRUD Matrix report's own guidance not to assume gaps are bugs.
NO_UPDATE_TYPES = {"C"}


class PolicyService:
    def __init__(self, conn, schema: str = "genapp", allow_commercial_update: bool = False):
        self.conn = conn
        self.schema = schema
        self.allow_commercial_update = allow_commercial_update

    # ------------------------------------------------------------------
    def add_policy(self, customer_number: int, policy_type: str, header: dict, detail: dict) -> dict:
        """Mirrors LGAPOL01 -> LGAPDB01: one CICS unit of work writing
        POLICY plus exactly one type-detail table (Business Rules
        Section 4/7). Here that's one Postgres transaction - both
        inserts commit together or neither does, matching the legacy
        "SYNCPOINT ROLLBACK on any failure partway through" rule."""
        policy_type = (policy_type or "").upper()
        if policy_type not in TYPE_TABLES:
            raise ValidationError(f"policy_type must be one of {sorted(TYPE_TABLES)}, got {policy_type!r}")

        header = dict(header)
        detail = dict(detail)
        header["customer_number"] = customer_number
        header["policy_type"] = policy_type
        header_cols = list(header.keys())
        explicit_pk = "policy_number" in header_cols and header.get("policy_number") is not None
        if "policy_number" in header_cols and not explicit_pk:
            header_cols.remove("policy_number")
        overriding = " OVERRIDING SYSTEM VALUE " if explicit_pk else " "

        try:
            with self.conn.cursor() as cur:
                cur.execute(f'SELECT 1 FROM {self.schema}.customer WHERE customer_number = %s', (customer_number,))
                if cur.fetchone() is None:
                    raise NotFoundError(f"customer {customer_number} not found - cannot add a policy for it")

                col_list = ", ".join(header_cols)
                placeholders = ", ".join(["%s"] * len(header_cols))
                cur.execute(
                    f'INSERT INTO {self.schema}.policy ({col_list}){overriding}'
                    f'VALUES ({placeholders}) RETURNING *',
                    [header[c] for c in header_cols],
                )
                policy = cur.fetchone()

                table = TYPE_TABLES[policy_type]
                detail["policy_number"] = policy["policy_number"]
                detail_cols = list(detail.keys())
                d_col_list = ", ".join(detail_cols)
                d_placeholders = ", ".join(["%s"] * len(detail_cols))
                cur.execute(
                    f'INSERT INTO {self.schema}.{table} ({d_col_list}) VALUES ({d_placeholders}) RETURNING *',
                    [detail[c] for c in detail_cols],
                )
                detail_row = cur.fetchone()
            self.conn.commit()
        except (NotFoundError, ValidationError):
            self.conn.rollback()
            raise
        except psycopg2.errors.ForeignKeyViolation as e:
            self.conn.rollback()
            raise ForeignKeyError(str(e.diag.message_primary or e))
        except psycopg2.errors.UniqueViolation as e:
            self.conn.rollback()
            raise ValidationError(str(e.diag.message_primary or e))

        return {"policy": policy, "detail_table": table, "detail": detail_row}

    # ------------------------------------------------------------------
    def get_policy(self, policy_number: int) -> dict:
        """Mirrors LGIPOL01 -> LGIPDB01: fetch the policy header plus
        its type-specific detail row in one call."""
        with self.conn.cursor() as cur:
            cur.execute(f'SELECT * FROM {self.schema}.policy WHERE policy_number = %s', (policy_number,))
            policy = cur.fetchone()
            if policy is None:
                raise NotFoundError(f"policy {policy_number} not found")

            table = TYPE_TABLES.get(policy["policy_type"])
            detail_row = {}
            if table:
                cur.execute(f'SELECT * FROM {self.schema}.{table} WHERE policy_number = %s', (policy_number,))
                detail_row = cur.fetchone() or {}

        return {"policy": policy, "detail_table": table or "", "detail": dict(detail_row)}

    # ------------------------------------------------------------------
    def update_policy(self, policy_number: int, expected_last_changed, header: dict, detail: dict) -> dict:
        """Mirrors LGUPOL01 -> LGUPDB01's optimistic-concurrency check
        (Business Rules Section 6): the caller must supply the
        last_changed value from a prior get_policy call, or the update
        is rejected with OptimisticLockError - exactly LGUPDB01's
        CA-RETURN-CODE='02' path, translated to a typed exception.

        Also enforces the Commercial-no-update rule (see NO_UPDATE_TYPES
        above) unless the service was constructed with
        allow_commercial_update=True."""
        current = self.get_policy(policy_number)  # raises NotFoundError if missing
        policy_type = current["policy"]["policy_type"]

        if policy_type in NO_UPDATE_TYPES and not self.allow_commercial_update:
            raise UnsupportedOperationError(
                f"policy {policy_number} is type '{policy_type}' (Commercial) - the legacy system "
                f"(LGTESTP4/LGUPDB01) never implemented an Update path for Commercial policies "
                f"(see 07_CRUD_Matrix Gap 2). Construct PolicyService(allow_commercial_update=True) "
                f"to override, after confirming with the business this restriction should be lifted."
            )

        if current["policy"]["last_changed"] != expected_last_changed:
            raise OptimisticLockError(
                f"policy {policy_number} was modified by someone else "
                f"(expected last_changed={expected_last_changed}, actual={current['policy']['last_changed']})"
            )

        header = dict(header)
        header.pop("policy_number", None)
        header.pop("customer_number", None)
        header.pop("policy_type", None)
        header.pop("last_changed", None)  # trigger-maintained

        detail = dict(detail)
        detail.pop("policy_number", None)

        try:
            with self.conn.cursor() as cur:
                if header:
                    set_clause = ", ".join(f"{c} = %s" for c in header.keys())
                    cur.execute(
                        f'UPDATE {self.schema}.policy SET {set_clause} WHERE policy_number = %s',
                        list(header.values()) + [policy_number],
                    )
                elif detail:
                    # No header fields changed, but the detail table is
                    # about to change. The optimistic lock protects the
                    # COMBINED policy+detail resource (that's what
                    # get_policy/update_policy present to callers), so
                    # policy.last_changed must still advance - otherwise
                    # two concurrent detail-only updates could silently
                    # clobber each other, since neither would ever touch
                    # the column the lock is based on. This harmless
                    # self-update exists purely to fire trg_policy_last_changed.
                    cur.execute(
                        f'UPDATE {self.schema}.policy SET policy_number = policy_number WHERE policy_number = %s',
                        (policy_number,),
                    )
                if detail:
                    table = TYPE_TABLES[policy_type]
                    set_clause = ", ".join(f"{c} = %s" for c in detail.keys())
                    cur.execute(
                        f'UPDATE {self.schema}.{table} SET {set_clause} WHERE policy_number = %s',
                        list(detail.values()) + [policy_number],
                    )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        return self.get_policy(policy_number)

    # ------------------------------------------------------------------
    def delete_policy(self, policy_number: int) -> None:
        """Mirrors LGDPOL01 -> LGDPDB01 exactly: "LGDPDB01 explicitly
        deletes only policy; the four type-detail tables and claim are
        removed via Db2's ON DELETE CASCADE, not by explicit DELETE
        statements in COBOL" (07_CRUD_Matrix Section 1). This method
        does the same - one DELETE, the database cascade handles the
        rest."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    f'DELETE FROM {self.schema}.policy WHERE policy_number = %s RETURNING policy_number',
                    (policy_number,),
                )
                row = cur.fetchone()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        if row is None:
            raise NotFoundError(f"policy {policy_number} not found")
