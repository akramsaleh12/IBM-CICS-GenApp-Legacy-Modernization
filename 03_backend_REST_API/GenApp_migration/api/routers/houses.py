from crud import make_crud_router
from schemas import HouseOut, HouseCreate, HouseUpdate

router = make_crud_router(
    table="house",
    pk_field="policy_number",
    out_schema=HouseOut,
    create_schema=HouseCreate,
    update_schema=HouseUpdate,
    tags=["house-policies"],
    prefix="/houses",
    pk_generated=False,
)
