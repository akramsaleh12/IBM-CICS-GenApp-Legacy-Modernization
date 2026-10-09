"""
business.py
-------------
FastAPI routers exposing the Business Services tier (../business_services/)
as REST endpoints under /business/*, kept deliberately separate from
the raw per-table CRUD under /customers, /policies, /claims etc.
(routers/customers.py and friends) - these two paths are the two
distinct tiers the Legacy-to-Modern Mapping report calls out:

    /customers, /policies, ...        <- Data Management tier
                                          (routers/*.py + crud.py; direct
                                          per-table access, like GenApp's
                                          LGxxDB01/LGxxVS01 Db2/VSAM programs)
    /business/customers, /business/policies, ...
                                       <- Business Logic tier (this file;
                                          orchestration + business rules,
                                          like GenApp's LGACUS01/LGAPOL01
                                          business-logic programs)

Every business_services exception is caught here and translated to an
HTTP response carrying BOTH a standard FastAPI-style detail message
AND the original legacy_return_code, for traceability back to
01-analysis/03_business_rules/GenApp_Business_Rules.md Section 10's
consolidated return-code catalogue.
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from database import get_db
from business_services import CustomerService, PolicyService, ClaimService
from business_services.exceptions import BusinessServiceError
from schemas import (
    CustomerCreate, CustomerUpdate, CustomerOut,
    PolicyDetailOut, ClaimOut,
    EndowmentCreate, HouseCreate, MotorCreate, CommercialCreate,
)

router = APIRouter(prefix="/business", tags=["business-services"])

_DETAIL_CREATE_SCHEMAS = {"E": EndowmentCreate, "H": HouseCreate, "M": MotorCreate, "C": CommercialCreate}


def _raise_http(e: BusinessServiceError):
    raise HTTPException(
        status_code=e.http_status,
        detail={"message": e.message, "legacy_return_code": e.legacy_return_code},
    )


# ---------------------------------------------------------------------------
# Customer business service
# ---------------------------------------------------------------------------
@router.post("/customers", response_model=CustomerOut, status_code=201,
             summary="Add Customer (business logic: LGACUS01 equivalent)")
def add_customer(payload: CustomerCreate, db=Depends(get_db)):
    """Creates the customer row AND its customer_secure row atomically -
    see business_services/customer_service.py for the full legacy
    parity notes (including the faithfully-reproduced placeholder-
    password behavior)."""
    svc = CustomerService(db)
    try:
        return svc.add_customer(payload.model_dump(exclude_unset=True))
    except BusinessServiceError as e:
        _raise_http(e)


@router.get("/customers/{customer_number}", response_model=CustomerOut,
            summary="Inquire Customer (business logic: LGICUS01 equivalent)")
def get_customer(customer_number: int, db=Depends(get_db)):
    svc = CustomerService(db)
    try:
        return svc.get_customer(customer_number)
    except BusinessServiceError as e:
        _raise_http(e)


@router.put("/customers/{customer_number}", response_model=CustomerOut,
            summary="Update Customer (business logic: LGUCUS01 equivalent, plus optimistic locking)")
def update_customer(
    customer_number: int,
    payload: CustomerUpdate,
    if_match: str | None = Header(
        default=None, alias="If-Match",
        description="The customer's last_changed timestamp from a prior GET, "
                     "ISO 8601 (e.g. 2026-08-20T03:20:23.179406). Omit to skip the optimistic-lock check.",
    ),
    db=Depends(get_db),
):
    """Enforces optimistic concurrency via the If-Match header (an
    ETag-style pattern) - see business_services/customer_service.py
    and sql/04_business_rules.sql for why Customer now gets the same
    lock Policy already had in the legacy system."""
    expected = datetime.datetime.fromisoformat(if_match) if if_match else None
    svc = CustomerService(db)
    try:
        return svc.update_customer(customer_number, payload.model_dump(exclude_unset=True), expected)
    except BusinessServiceError as e:
        _raise_http(e)


# ---------------------------------------------------------------------------
# Policy business service
# ---------------------------------------------------------------------------
class AddPolicyRequest(BaseModel):
    customer_number: int
    policy_type: str
    header: dict = {}
    detail: dict


class UpdatePolicyRequest(BaseModel):
    header: dict = {}
    detail: dict = {}


@router.post("/policies", response_model=PolicyDetailOut, status_code=201,
             summary="Add Policy (business logic: LGAPOL01 equivalent, type-parameterized)")
def add_policy(payload: AddPolicyRequest, db=Depends(get_db)):
    """One call creates the policy header AND its type-specific detail
    row in a single transaction (see business_services/policy_service.py) -
    the modern equivalent of LGAPOL01's Db2+VSAM two-phase commit,
    collapsed into one ACID transaction now that both live in
    PostgreSQL. `detail` is validated against the schema for
    `policy_type` (E/H/M/C)."""
    policy_type = (payload.policy_type or "").upper()
    detail_schema = _DETAIL_CREATE_SCHEMAS.get(policy_type)
    if detail_schema is None:
        raise HTTPException(
            status_code=422,
            detail={"message": f"policy_type must be one of E, H, M, C - got {payload.policy_type!r}",
                    "legacy_return_code": "98"},
        )
    try:
        detail_validated = detail_schema(policy_number=0, **payload.detail).model_dump(
            exclude={"policy_number"}, exclude_unset=True
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail={"message": str(e), "legacy_return_code": "98"})

    svc = PolicyService(db)
    try:
        return svc.add_policy(payload.customer_number, policy_type, payload.header, detail_validated)
    except BusinessServiceError as e:
        _raise_http(e)


@router.get("/policies/{policy_number}", response_model=PolicyDetailOut,
            summary="Inquire Policy (business logic: LGIPOL01 equivalent)")
def get_policy(policy_number: int, db=Depends(get_db)):
    svc = PolicyService(db)
    try:
        return svc.get_policy(policy_number)
    except BusinessServiceError as e:
        _raise_http(e)


@router.put("/policies/{policy_number}", response_model=PolicyDetailOut,
            summary="Update Policy (business logic: LGUPOL01 equivalent - optimistic lock + Commercial blocked)")
def update_policy(
    policy_number: int,
    payload: UpdatePolicyRequest,
    if_match: str = Header(
        ..., alias="If-Match",
        description="The policy's last_changed timestamp from a prior GET, ISO 8601. Required - "
                     "this mirrors LGUPDB01's mandatory optimistic-concurrency check.",
    ),
    db=Depends(get_db),
):
    """Rejects the update with 409 if If-Match doesn't match the
    policy's current last_changed (legacy CA-RETURN-CODE='02'), and
    rejects with 405 for Commercial policies (legacy: no Update path
    ever existed for that type - see business_services/policy_service.py)."""
    expected = datetime.datetime.fromisoformat(if_match)
    svc = PolicyService(db)
    try:
        return svc.update_policy(policy_number, expected, payload.header, payload.detail)
    except BusinessServiceError as e:
        _raise_http(e)


@router.delete("/policies/{policy_number}", status_code=204,
                summary="Delete Policy (business logic: LGDPOL01 equivalent - cascade to detail/claims)")
def delete_policy(policy_number: int, db=Depends(get_db)):
    svc = PolicyService(db)
    try:
        svc.delete_policy(policy_number)
    except BusinessServiceError as e:
        _raise_http(e)
    return None


# ---------------------------------------------------------------------------
# Claim business service (net-new - no legacy equivalent, see claim_service.py)
# ---------------------------------------------------------------------------
class AddClaimRequest(BaseModel):
    cause: str | None = None
    observations: str | None = None
    claim_date: str | None = None
    paid: int | None = None
    value: int | None = None


@router.post("/policies/{policy_number}/claims", response_model=ClaimOut, status_code=201,
             tags=["business-services"],
             summary="File a claim against a policy (net-new capability - no legacy equivalent)")
def add_claim(policy_number: int, payload: AddClaimRequest, db=Depends(get_db)):
    """No GenApp program ever implemented claims CRUD (07_CRUD_Matrix
    Gap 3) - this endpoint is entirely new-build, not a migration."""
    svc = ClaimService(db)
    try:
        return svc.add_claim(policy_number, payload.model_dump(exclude_unset=True))
    except BusinessServiceError as e:
        _raise_http(e)
