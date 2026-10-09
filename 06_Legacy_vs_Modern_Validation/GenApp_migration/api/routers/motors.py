from crud import make_crud_router
from schemas import MotorOut, MotorCreate, MotorUpdate

router = make_crud_router(
    table="motor",
    pk_field="policy_number",
    out_schema=MotorOut,
    create_schema=MotorCreate,
    update_schema=MotorUpdate,
    tags=["motor-policies"],
    prefix="/motors",
    pk_generated=False,
)
