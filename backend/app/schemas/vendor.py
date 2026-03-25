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
    display_name: str = Field(..., min_length=1, max_length=100)
    bio: Optional[str] = None
    buying_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    trade_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    tcg_interests: Optional[List[str]] = None


class VendorProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    bio: Optional[str] = None
    buying_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    trade_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    tcg_interests: Optional[List[str]] = None


class VendorProfileResponse(BaseModel):
    id: str
    profile_id: str
    display_name: str
    bio: Optional[str]
    buying_rate: Optional[Decimal]
    trade_rate: Optional[Decimal]
    tcg_interests: Optional[List[str]]
    is_accounting_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

VALID_CONDITIONS = {
    "psa_1","psa_2","psa_3","psa_4","psa_5","psa_6","psa_7","psa_8","psa_9","psa_10",
    "bgs_1","bgs_2","bgs_3","bgs_4","bgs_5","bgs_6","bgs_7","bgs_8","bgs_9","bgs_10",
    "cgc_1","cgc_2","cgc_3","cgc_4","cgc_5","cgc_6","cgc_7","cgc_8","cgc_9","cgc_10",
    "sgc_1","sgc_2","sgc_3","sgc_4","sgc_5","sgc_6","sgc_7","sgc_8","sgc_9","sgc_10",
    "raw_nm","raw_lp","raw_mp","raw_hp","raw_dmg",
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
    vendor_id: str
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
