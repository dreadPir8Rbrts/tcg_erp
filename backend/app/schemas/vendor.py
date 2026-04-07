"""
Pydantic v2 request/response schemas for vendor profiles and inventory.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Vendor profile
# ---------------------------------------------------------------------------

class VendorProfileCreate(BaseModel):
    bio: Optional[str] = None
    buying_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    trade_rate: Optional[Decimal] = Field(None, ge=0, le=1)


class VendorProfileUpdate(BaseModel):
    bio: Optional[str] = None
    buying_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    trade_rate: Optional[Decimal] = Field(None, ge=0, le=1)


class VendorProfileResponse(BaseModel):
    id: str
    profile_id: str
    bio: Optional[str]
    buying_rate: Optional[Decimal]
    trade_rate: Optional[Decimal]
    is_accounting_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Condition validation constants
# ---------------------------------------------------------------------------

VALID_UNGRADED = {"nm", "lp", "mp", "hp", "dmg"}
VALID_COMPANIES = {"psa", "bgs", "cgc", "other"}


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class InventoryItemCreate(BaseModel):
    card_id: str
    condition_type: Literal["ungraded", "graded"]
    condition_ungraded: Optional[str] = None
    grading_company: Optional[str] = None
    grade: Optional[str] = None
    grading_company_other: Optional[str] = None
    quantity: int = Field(1, ge=1)
    cost_basis: Optional[Decimal] = Field(None, ge=0)
    asking_price: Optional[Decimal] = Field(None, ge=0)
    is_for_sale: bool = True
    is_for_trade: bool = False
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_condition(self) -> "InventoryItemCreate":
        if self.condition_type == "ungraded":
            if not self.condition_ungraded:
                raise ValueError("condition_ungraded is required when condition_type is 'ungraded'")
            if self.condition_ungraded not in VALID_UNGRADED:
                raise ValueError(f"condition_ungraded must be one of {sorted(VALID_UNGRADED)}")
            if self.grading_company or self.grade:
                raise ValueError("grading_company and grade must be null for ungraded items")
        else:  # graded
            if not self.grading_company:
                raise ValueError("grading_company is required when condition_type is 'graded'")
            if self.grading_company not in VALID_COMPANIES:
                raise ValueError(f"grading_company must be one of {sorted(VALID_COMPANIES)}")
            if not self.grade:
                raise ValueError("grade is required when condition_type is 'graded'")
            if self.condition_ungraded:
                raise ValueError("condition_ungraded must be null for graded items")
            if self.grading_company == "other" and not self.grading_company_other:
                raise ValueError("grading_company_other is required when grading_company is 'other'")
        return self


class InventoryItemResponse(BaseModel):
    id: str
    profile_id: str
    card_id: str
    condition_type: str
    condition_ungraded: Optional[str]
    grading_company: Optional[str]
    grade: Optional[str]
    grading_company_other: Optional[str]
    quantity: int
    cost_basis: Optional[Decimal]
    asking_price: Optional[Decimal]
    is_for_sale: bool
    is_for_trade: bool
    notes: Optional[str]
    photo_url: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InventoryItemWithCardResponse(BaseModel):
    id: str
    card_id: str
    condition_type: str
    condition_ungraded: Optional[str]
    grading_company: Optional[str]
    grade: Optional[str]
    grading_company_other: Optional[str]
    quantity: int
    asking_price: Optional[Decimal]
    is_for_sale: bool
    is_for_trade: bool
    notes: Optional[str]
    created_at: datetime
    # Card details
    card_name: str
    card_num: str
    set_name: str
    series_name: str
    image_url: Optional[str]
    rarity: Optional[str]

    model_config = {"from_attributes": True}
