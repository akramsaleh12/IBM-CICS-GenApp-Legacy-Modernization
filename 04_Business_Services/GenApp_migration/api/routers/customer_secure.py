from crud import make_crud_router
from schemas import CustomerSecureOut, CustomerSecureCreate, CustomerSecureUpdate

router = make_crud_router(
    table="customer_secure",
    pk_field="customer_number",
    out_schema=CustomerSecureOut,
    create_schema=CustomerSecureCreate,
    update_schema=CustomerSecureUpdate,
    tags=["customer-secure"],
    prefix="/customer-secure",
    pk_generated=False,
)
