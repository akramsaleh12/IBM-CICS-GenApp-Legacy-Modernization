from fastapi import Depends

from crud import make_crud_router
from database import get_db, SCHEMA
from schemas import CustomerOut, CustomerCreate, CustomerUpdate, PolicyOut

router = make_crud_router(
    table="customer",
    pk_field="customer_number",
    out_schema=CustomerOut,
    create_schema=CustomerCreate,
    update_schema=CustomerUpdate,
    tags=["customers"],
    prefix="/customers",
    pk_generated=True,
)


@router.get(
    "/{customer_number}/policies",
    response_model=list[PolicyOut],
    tags=["customers"],
    summary="All policies held by a customer",
)
def get_customer_policies(customer_number: int, db=Depends(get_db)):
    with db.cursor() as cur:
        cur.execute(
            f"SELECT * FROM {SCHEMA}.policy WHERE customer_number = %s ORDER BY policy_number",
            (customer_number,),
        )
        return cur.fetchall()
