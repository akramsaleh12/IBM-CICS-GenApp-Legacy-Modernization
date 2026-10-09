"""
business_services
-------------------
The "Business Logic" tier of the modernized GenApp architecture -
see 01-analysis/08_Legacy_to_Modern_Mapping/GenApp_Legacy_Modern_Mapping.md
Section 4. Each service class is a type-parameterized, transaction-
aware orchestrator built from the specific business rules documented
in 01-analysis/03_business_rules/GenApp_Business_Rules.md, distinct
from the plain per-table CRUD in ../crud.py and ../routers/*.py
(which is the "Data Management" tier equivalent - see Section 5 of
the same mapping report).

    CustomerService  <- LGACUS01 / LGICUS01 / LGUCUS01
    PolicyService    <- LGAPOL01 / LGIPOL01 / LGUPOL01 / LGDPOL01 (type-parameterized)
    ClaimService     <- no legacy equivalent; net-new (07_CRUD_Matrix Gap 3)
"""
from .customer_service import CustomerService
from .policy_service import PolicyService
from .claim_service import ClaimService
from .exceptions import (
    BusinessServiceError,
    NotFoundError,
    OptimisticLockError,
    ValidationError,
    UnsupportedOperationError,
    ForeignKeyError,
)

__all__ = [
    "CustomerService", "PolicyService", "ClaimService",
    "BusinessServiceError", "NotFoundError", "OptimisticLockError",
    "ValidationError", "UnsupportedOperationError", "ForeignKeyError",
]
