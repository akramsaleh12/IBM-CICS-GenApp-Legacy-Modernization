from crud import make_crud_router
from schemas import ClaimOut, ClaimCreate, ClaimUpdate

router = make_crud_router(
    table="claim",
    pk_field="claim_number",
    out_schema=ClaimOut,
    create_schema=ClaimCreate,
    update_schema=ClaimUpdate,
    tags=["claims"],
    prefix="/claims",
    pk_generated=True,
)
