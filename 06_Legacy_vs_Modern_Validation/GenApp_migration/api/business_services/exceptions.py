"""
exceptions.py
--------------
Business-service exceptions, each tagged with the legacy CA-RETURN-CODE
it corresponds to (see 01-analysis/03_business_rules/GenApp_Business_Rules.md
Section 10's consolidated return-code catalogue). This is the modern
equivalent of GenApp's return-code propagation pattern - "SQLCA/return
codes -> Python exceptions/API responses" per the Legacy-to-Modern
Mapping report's own Quick-Reference table (Section 11).

The API layer (routers/business_*.py) catches these and translates
each to the appropriate HTTP status code, including the legacy code
in the response body for traceability back to the source system's
documented behavior.
"""


class BusinessServiceError(Exception):
    """Base class for all business-service errors."""
    legacy_return_code: str = "99"
    http_status: int = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(BusinessServiceError):
    """No row found for the given key. Legacy: CA-RETURN-CODE = '01'
    (SQLCODE +100), raised by LGICDB01/LGIPDB01/LGUCDB01/LGUPDB01."""
    legacy_return_code = "01"
    http_status = 404


class OptimisticLockError(BusinessServiceError):
    """The caller's last_changed value no longer matches the current
    row - someone else updated it first. Legacy: CA-RETURN-CODE = '02',
    raised only by LGUPDB01 (Update Policy). This modernization extends
    the same check to Customer updates - see sql/04_business_rules.sql
    and docs/MIGRATION_BLUEPRINT.md for the rationale."""
    legacy_return_code = "02"
    http_status = 409


class ValidationError(BusinessServiceError):
    """Caller-supplied data fails a business rule (e.g. missing
    required field, invalid policy_type). Legacy: CA-RETURN-CODE = '98'
    (COMMAREA too short for the request) is the closest legacy analog -
    GenApp's own field-level validation is minimal (Business Rules
    Section 5), so this exception covers rules genuinely enforced here
    that legacy either enforced via COMMAREA-length checks or via a
    Db2 constraint."""
    legacy_return_code = "98"
    http_status = 422


class UnsupportedOperationError(BusinessServiceError):
    """The operation is deliberately not offered, mirroring a real gap
    identified in the legacy system (e.g. no Delete Customer, no
    Update Commercial policy - see 07_CRUD_Matrix Section 5). Distinct
    from ValidationError: this isn't bad input, it's a function that
    legacy never implemented and this service intentionally preserves
    as unavailable, pending business confirmation per the source
    report's own caveat."""
    legacy_return_code = "99"
    http_status = 405


class ForeignKeyError(BusinessServiceError):
    """A referenced parent row doesn't exist (e.g. policy for an
    unknown customer_number). Legacy: CA-RETURN-CODE = '90' (general/
    unexpected Db2 SQLCODE), the catch-all Db2-layer failure code."""
    legacy_return_code = "90"
    http_status = 422
