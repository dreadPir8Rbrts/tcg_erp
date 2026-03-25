"""
Vendor profile and inventory endpoints.

Routes:
  POST /vendor/profile       — create vendor profile (authenticated)
  GET  /vendor/profile       — get own vendor profile (authenticated)
  PATCH /vendor/profile      — update vendor profile (authenticated)
  POST /inventory            — add inventory item (authenticated vendor)
  GET  /inventory            — list own inventory with filters (authenticated vendor)
"""

import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_profile
from app.models.inventory import InventoryItem, VendorProfile
from app.models.profiles import Profile
from app.models.catalog import Card
from app.schemas.vendor import (
    InventoryItemCreate,
    InventoryItemResponse,
    VendorProfileCreate,
    VendorProfileResponse,
    VendorProfileUpdate,
    VALID_CONDITIONS,
)

router = APIRouter(tags=["vendor"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_vendor_or_404(profile: Profile, db: Session) -> VendorProfile:
    vendor = db.query(VendorProfile).filter(VendorProfile.profile_id == profile.id).first()
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found — create one first via POST /vendor/profile",
        )
    return vendor


# ---------------------------------------------------------------------------
# Vendor profile
# ---------------------------------------------------------------------------

@router.post("/vendor/profile", response_model=VendorProfileResponse, status_code=status.HTTP_201_CREATED)
def create_vendor_profile(
    body: VendorProfileCreate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> VendorProfile:
    existing = db.query(VendorProfile).filter(VendorProfile.profile_id == profile.id).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vendor profile already exists")

    # Ensure profile has vendor role
    if profile.role != "vendor":
        profile.role = "vendor"
        db.add(profile)

    vendor = VendorProfile(
        id=str(uuid.uuid4()),
        profile_id=profile.id,
        display_name=body.display_name,
        bio=body.bio,
        buying_rate=body.buying_rate,
        trade_rate=body.trade_rate,
        tcg_interests=body.tcg_interests,
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor


@router.get("/vendor/profile", response_model=VendorProfileResponse)
def get_vendor_profile(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> VendorProfile:
    return _get_vendor_or_404(profile, db)


@router.patch("/vendor/profile", response_model=VendorProfileResponse)
def update_vendor_profile(
    body: VendorProfileUpdate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> VendorProfile:
    vendor = _get_vendor_or_404(profile, db)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(vendor, field, value)

    db.commit()
    db.refresh(vendor)
    return vendor


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@router.post("/inventory", response_model=InventoryItemResponse, status_code=status.HTTP_201_CREATED)
def add_inventory_item(
    body: InventoryItemCreate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> InventoryItem:
    vendor = _get_vendor_or_404(profile, db)

    if body.condition not in VALID_CONDITIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid condition '{body.condition}'",
        )

    card = db.get(Card, body.card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Card '{body.card_id}' not found")

    item = InventoryItem(
        id=str(uuid.uuid4()),
        vendor_id=vendor.id,
        card_id=body.card_id,
        condition=body.condition,
        grading_service=body.grading_service,
        cert_number=body.cert_number,
        quantity=body.quantity,
        cost_basis=body.cost_basis,
        asking_price=body.asking_price,
        is_for_sale=body.is_for_sale,
        is_for_trade=body.is_for_trade,
        notes=body.notes,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/inventory", response_model=List[InventoryItemResponse])
def list_inventory(
    condition: Optional[str] = Query(None),
    card_id: Optional[str] = Query(None),
    is_for_sale: Optional[bool] = Query(None),
    is_for_trade: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> List[InventoryItem]:
    vendor = _get_vendor_or_404(profile, db)

    query = db.query(InventoryItem).filter(
        InventoryItem.vendor_id == vendor.id,
        InventoryItem.deleted_at.is_(None),
    )

    if condition:
        query = query.filter(InventoryItem.condition == condition)
    if card_id:
        query = query.filter(InventoryItem.card_id == card_id)
    if is_for_sale is not None:
        query = query.filter(InventoryItem.is_for_sale == is_for_sale)
    if is_for_trade is not None:
        query = query.filter(InventoryItem.is_for_trade == is_for_trade)

    return query.order_by(InventoryItem.created_at.desc()).offset(offset).limit(limit).all()
