"""
claim_service.py
------------------
Unlike CustomerService and PolicyService, this has NO legacy program
to mirror. 07_CRUD_Matrix Section 4: "Claim | ... zero application-
level CRUD ... confirmed gap, recommend confirming scope with the
business." Legacy-to-Modern Mapping Section 5 marks this red-flagged:
"This is 100% new-build; do not assume claims functionality exists to
'lift'."

This service exists because the raw CRUD API already exposes
/claims, and a real modernized system will need SOME way to file a
claim - but it is built new, not migrated, and callers should treat
its business rules (there are none beyond "the policy must exist") as
a starting point pending real business requirements, not as a
faithful reproduction of anything GenApp did.
"""
from .exceptions import NotFoundError


class ClaimService:
    def __init__(self, conn, schema: str = "genapp"):
        self.conn = conn
        self.schema = schema

    def add_claim(self, policy_number: int, data: dict) -> dict:
        data = dict(data)
        data["policy_number"] = policy_number
        cols = list(data.keys())
        explicit_pk = "claim_number" in cols and data.get("claim_number") is not None
        if "claim_number" in cols and not explicit_pk:
            cols.remove("claim_number")
        overriding = " OVERRIDING SYSTEM VALUE " if explicit_pk else " "

        try:
            with self.conn.cursor() as cur:
                cur.execute(f'SELECT 1 FROM {self.schema}.policy WHERE policy_number = %s', (policy_number,))
                if cur.fetchone() is None:
                    raise NotFoundError(f"policy {policy_number} not found - cannot file a claim against it")

                col_list = ", ".join(cols)
                placeholders = ", ".join(["%s"] * len(cols))
                cur.execute(
                    f'INSERT INTO {self.schema}.claim ({col_list}){overriding}'
                    f'VALUES ({placeholders}) RETURNING *',
                    [data[c] for c in cols],
                )
                row = cur.fetchone()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return row

    def get_claim(self, claim_number: int) -> dict:
        with self.conn.cursor() as cur:
            cur.execute(f'SELECT * FROM {self.schema}.claim WHERE claim_number = %s', (claim_number,))
            row = cur.fetchone()
        if row is None:
            raise NotFoundError(f"claim {claim_number} not found")
        return row

    def list_claims_for_policy(self, policy_number: int) -> list:
        with self.conn.cursor() as cur:
            cur.execute(f'SELECT 1 FROM {self.schema}.policy WHERE policy_number = %s', (policy_number,))
            if cur.fetchone() is None:
                raise NotFoundError(f"policy {policy_number} not found")
            cur.execute(
                f'SELECT * FROM {self.schema}.claim WHERE policy_number = %s ORDER BY claim_number',
                (policy_number,),
            )
            return cur.fetchall()
