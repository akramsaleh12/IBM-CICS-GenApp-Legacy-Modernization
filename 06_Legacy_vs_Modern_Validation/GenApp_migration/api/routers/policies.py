from fastapi import Depends, HTTPException

from crud import make_crud_router
from database import get_db, SCHEMA
from schemas import PolicyOut, PolicyCreate, PolicyUpdate, PolicyDetailOut, ClaimOut

router = make_crud_router(
    table="policy",
    pk_field="policy_number",
    out_schema=PolicyOut,
    create_schema=PolicyCreate,
    update_schema=PolicyUpdate,
    tags=["policies"],
    prefix="/policies",
    pk_generated=True,
)

# policy_type -> detail table name
_TYPE_TABLE = {"E": "endowment", "H": "house", "M": "motor", "C": "commercial"}


@router.get(
    "/{policy_number}/detail",
    response_model=PolicyDetailOut,
    tags=["policies"],
    summary="Policy header joined with its type-specific detail row",
)
def get_policy_detail(policy_number: int, db=Depends(get_db)):
    """Hides the REDEFINES-by-policy-type dispatch (see
    docs/MIGRATION_BLUEPRINT.md Section 2) behind one call: fetches the
    policy row, looks at policy_type, and joins in the matching
    endowment/house/motor/commercial row automatically."""
    with db.cursor() as cur:
        cur.execute(f"SELECT * FROM {SCHEMA}.policy WHERE policy_number = %s", (policy_number,))
        policy = cur.fetchone()
        if policy is None:
            raise HTTPException(status_code=404, detail=f"policy policy_number={policy_number} not found")

        detail_table = _TYPE_TABLE.get(policy["policy_type"])
        detail = {}
        if detail_table:
            cur.execute(f"SELECT * FROM {SCHEMA}.{detail_table} WHERE policy_number = %s", (policy_number,))
            detail_row = cur.fetchone()
            detail = dict(detail_row) if detail_row else {}

    return {"policy": policy, "detail_table": detail_table or "", "detail": detail}


@router.get(
    "/{policy_number}/claims",
    response_model=list[ClaimOut],
    tags=["policies"],
    summary="All claims filed against a policy",
)
def get_policy_claims(policy_number: int, db=Depends(get_db)):
    with db.cursor() as cur:
        cur.execute(f"SELECT * FROM {SCHEMA}.policy WHERE policy_number = %s", (policy_number,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"policy policy_number={policy_number} not found")
        cur.execute(
            f"SELECT * FROM {SCHEMA}.claim WHERE policy_number = %s ORDER BY claim_number", (policy_number,)
        )
        return cur.fetchall()
