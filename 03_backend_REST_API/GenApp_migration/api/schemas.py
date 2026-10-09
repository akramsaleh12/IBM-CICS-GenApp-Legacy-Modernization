"""
schemas.py
-----------
Pydantic request/response models, one triplet (Base/Create/Update +
an Out model with the primary key) per table in sql/02_target_schema.sql.
Field names and types mirror that DDL exactly - see
docs/MIGRATION_BLUEPRINT.md Section 1 for the full type-mapping
rationale behind each column.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# customer
# ---------------------------------------------------------------------------
class CustomerBase(BaseModel):
    first_name: Optional[str] = Field(None, max_length=10)
    last_name: Optional[str] = Field(None, max_length=20)
    date_of_birth: Optional[date] = None
    house_name: Optional[str] = Field(None, max_length=20)
    house_number: Optional[str] = Field(None, max_length=4)
    postcode: Optional[str] = Field(None, max_length=8)
    phone_home: Optional[str] = Field(None, max_length=20)
    phone_mobile: Optional[str] = Field(None, max_length=20)
    email_address: Optional[str] = Field(None, max_length=100)


class CustomerCreate(CustomerBase):
    customer_number: Optional[int] = Field(
        None, description="Omit to auto-generate; provide to carry over a legacy VSAM/DB2 key."
    )


class CustomerUpdate(CustomerBase):
    pass


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    customer_number: int


# ---------------------------------------------------------------------------
# customer_secure
# ---------------------------------------------------------------------------
class CustomerSecureBase(BaseModel):
    state_indicator: Optional[str] = Field(None, max_length=1)
    pass_changes: Optional[int] = None


class CustomerSecureCreate(CustomerSecureBase):
    customer_number: int
    customer_pass: Optional[str] = Field(
        None, max_length=32, description="Hashed credential. Never send/store plaintext passwords."
    )


class CustomerSecureUpdate(CustomerSecureBase):
    customer_pass: Optional[str] = Field(None, max_length=32)


class CustomerSecureOut(CustomerSecureBase):
    model_config = ConfigDict(from_attributes=True)
    customer_number: int
    # customer_pass intentionally omitted from responses - never echo credentials back


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------
class PolicyBase(BaseModel):
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    broker_id: Optional[int] = None
    brokers_reference: Optional[str] = Field(None, max_length=10)
    payment: Optional[int] = None
    commission: Optional[int] = None


class PolicyCreate(PolicyBase):
    policy_number: Optional[int] = Field(None, description="Omit to auto-generate.")
    customer_number: int
    policy_type: str = Field(..., min_length=1, max_length=1, description="C, E, H, or M")


class PolicyUpdate(PolicyBase):
    customer_number: Optional[int] = None
    policy_type: Optional[str] = Field(None, min_length=1, max_length=1)


class PolicyOut(PolicyBase):
    model_config = ConfigDict(from_attributes=True)
    policy_number: int
    customer_number: int
    policy_type: Optional[str]
    last_changed: Optional[datetime] = None


# ---------------------------------------------------------------------------
# endowment / house / motor / commercial (policy_type-specific detail)
# ---------------------------------------------------------------------------
class EndowmentBase(BaseModel):
    equities: Optional[str] = Field(None, max_length=1)
    with_profits: Optional[str] = Field(None, max_length=1)
    managed_fund: Optional[str] = Field(None, max_length=1)
    fund_name: Optional[str] = Field(None, max_length=10)
    term: Optional[int] = None
    sum_assured: Optional[int] = None
    life_assured: Optional[str] = Field(None, max_length=31)
    padding_data: Optional[str] = None


class EndowmentCreate(EndowmentBase):
    policy_number: int


class EndowmentUpdate(EndowmentBase):
    pass


class EndowmentOut(EndowmentBase):
    model_config = ConfigDict(from_attributes=True)
    policy_number: int


class HouseBase(BaseModel):
    property_type: Optional[str] = Field(None, max_length=15)
    bedrooms: Optional[int] = None
    value: Optional[int] = None
    house_name: Optional[str] = Field(None, max_length=20)
    house_number: Optional[str] = Field(None, max_length=4)
    postcode: Optional[str] = Field(None, max_length=8)


class HouseCreate(HouseBase):
    policy_number: int


class HouseUpdate(HouseBase):
    pass


class HouseOut(HouseBase):
    model_config = ConfigDict(from_attributes=True)
    policy_number: int


class MotorBase(BaseModel):
    make: Optional[str] = Field(None, max_length=15)
    model: Optional[str] = Field(None, max_length=15)
    value: Optional[int] = None
    reg_number: Optional[str] = Field(None, max_length=7)
    colour: Optional[str] = Field(None, max_length=8)
    cc: Optional[int] = None
    year_of_manufacture: Optional[date] = None
    premium: Optional[int] = None
    accidents: Optional[int] = None


class MotorCreate(MotorBase):
    policy_number: int


class MotorUpdate(MotorBase):
    pass


class MotorOut(MotorBase):
    model_config = ConfigDict(from_attributes=True)
    policy_number: int


class CommercialBase(BaseModel):
    request_date: Optional[datetime] = None
    start_date: Optional[date] = None
    renewal_date: Optional[date] = None
    address: Optional[str] = Field(None, max_length=255)
    zipcode: Optional[str] = Field(None, max_length=8)
    latitude_n: Optional[str] = Field(None, max_length=11)
    longitude_w: Optional[str] = Field(None, max_length=11)
    customer: Optional[str] = Field(None, max_length=255)
    property_type: Optional[str] = Field(None, max_length=255)
    fire_peril: Optional[int] = None
    fire_premium: Optional[int] = None
    crime_peril: Optional[int] = None
    crime_premium: Optional[int] = None
    flood_peril: Optional[int] = None
    flood_premium: Optional[int] = None
    weather_peril: Optional[int] = None
    weather_premium: Optional[int] = None
    status: Optional[int] = None
    rejection_reason: Optional[str] = Field(None, max_length=255)


class CommercialCreate(CommercialBase):
    policy_number: int


class CommercialUpdate(CommercialBase):
    pass


class CommercialOut(CommercialBase):
    model_config = ConfigDict(from_attributes=True)
    policy_number: int


# ---------------------------------------------------------------------------
# claim
# ---------------------------------------------------------------------------
class ClaimBase(BaseModel):
    claim_date: Optional[date] = None
    paid: Optional[int] = None
    value: Optional[int] = None
    cause: Optional[str] = Field(None, max_length=255)
    observations: Optional[str] = Field(None, max_length=255)


class ClaimCreate(ClaimBase):
    claim_number: Optional[int] = Field(None, description="Omit to auto-generate.")
    policy_number: int


class ClaimUpdate(ClaimBase):
    policy_number: Optional[int] = None


class ClaimOut(ClaimBase):
    model_config = ConfigDict(from_attributes=True)
    claim_number: int
    policy_number: int


# ---------------------------------------------------------------------------
# Composite / utility response models
# ---------------------------------------------------------------------------
class PolicyDetailOut(BaseModel):
    """Policy header joined with its type-specific detail row - a
    convenience endpoint that hides the REDEFINES-by-type dispatch
    from API consumers (see docs/MIGRATION_BLUEPRINT.md Section 2)."""
    policy: PolicyOut
    detail_table: str
    detail: dict


class TableInfo(BaseModel):
    table_name: str
    table_description: Optional[str] = None
    column_count: int


class ColumnInfo(BaseModel):
    position: int
    column: str
    data_type: str
    nullable: bool
    default: Optional[str] = None
    key: Optional[str] = None
    references: Optional[str] = None
    description: Optional[str] = None
