"""
Pydantic v2 request/response schemas for vendor profiles and inventory.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field


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
# Inventory
# ---------------------------------------------------------------------------

VALID_CONDITIONS = {
    "nm", "lp", "mp", "hp", "dmg",
    "psa_7", "psa_8", "psa_9", "psa_10",
    "bgs_9", "bgs_9_5", "bgs_10",
    "cgc_9", "cgc_9_5", "cgc_10",
}


class InventoryItemCreate(BaseModel):
    card_id: str
    condition: str
    grading_service: Optional[str] = None
    cert_number: Optional[str] = None
    quantity: int = Field(1, ge=1)
    cost_basis: Optional[Decimal] = Field(None, ge=0)
    asking_price: Optional[Decimal] = Field(None, ge=0)
    is_for_sale: bool = True
    is_for_trade: bool = False
    notes: Optional[str] = None


class InventoryItemResponse(BaseModel):
    id: str
    profile_id: str
    card_id: str
    condition: str
    grading_service: Optional[str]
    cert_number: Optional[str]
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
    condition: str
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
