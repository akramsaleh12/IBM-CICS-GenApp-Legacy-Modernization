from crud import make_crud_router
from schemas import EndowmentOut, EndowmentCreate, EndowmentUpdate

router = make_crud_router(
    table="endowment",
    pk_field="policy_number",
    out_schema=EndowmentOut,
    create_schema=EndowmentCreate,
    update_schema=EndowmentUpdate,
    tags=["endowment-policies"],
    prefix="/endowments",
    pk_generated=False,
)
