from crud import make_crud_router
from schemas import CommercialOut, CommercialCreate, CommercialUpdate

router = make_crud_router(
    table="commercial",
    pk_field="policy_number",
    out_schema=CommercialOut,
    create_schema=CommercialCreate,
    update_schema=CommercialUpdate,
    tags=["commercial-policies"],
    prefix="/commercials",
    pk_generated=False,
)
