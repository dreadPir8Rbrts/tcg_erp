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

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db, settings
from app.dependencies import get_current_profile
from app.models.inventory import VendorInventory, VendorProfile
from app.models.profiles import Profile
from app.models.catalog import Card, Set, Serie
from app.schemas.vendor import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemWithCardResponse,
    VendorProfileCreate,
    VendorProfileResponse,
    VendorProfileUpdate,
    VALID_CONDITIONS,
)

router = APIRouter(tags=["vendor"])

PROFILE_IMAGE_TYPES = {"background", "avatar"}
PRESIGNED_URL_EXPIRY = 300  # seconds


class ProfileImageUploadRequest(BaseModel):
    image_type: str   # "background" or "avatar"
    content_type: str = "image/jpeg"


class ProfileImageUploadResponse(BaseModel):
    upload_url: str
    public_url: str


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
        bio=body.bio,
        buying_rate=body.buying_rate,
        trade_rate=body.trade_rate,
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


@router.post("/vendor/profile/image", response_model=ProfileImageUploadResponse)
def get_profile_image_upload_url(
    body: ProfileImageUploadRequest,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> dict:
    """
    Generate a presigned S3 PUT URL for uploading a profile background or avatar image.
    The client uploads directly to S3, then calls PATCH /vendor/profile with the public_url.
    """
    vendor = _get_vendor_or_404(profile, db)

    if body.image_type not in PROFILE_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"image_type must be one of {PROFILE_IMAGE_TYPES}",
        )

    ext = body.content_type.split("/")[-1] if "/" in body.content_type else "jpg"
    s3_key = f"profiles/{vendor.id}/{body.image_type}.{ext}"

    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=Config(signature_version="s3v4"),
    )
    try:
        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.aws_s3_bucket,
                "Key": s3_key,
                "ContentType": body.content_type,
            },
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )
    except ClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL",
        ) from exc

    public_url = f"https://{settings.aws_s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{s3_key}"
    return {"upload_url": upload_url, "public_url": public_url}


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@router.post("/inventory", response_model=InventoryItemResponse, status_code=status.HTTP_201_CREATED)
def add_inventory_item(
    body: InventoryItemCreate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> VendorInventory:
    _get_vendor_or_404(profile, db)  # ensure vendor profile exists

    if body.condition not in VALID_CONDITIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid condition '{body.condition}'",
        )

    card = db.get(Card, body.card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Card '{body.card_id}' not found")

    item = VendorInventory(
        id=str(uuid.uuid4()),
        profile_id=profile.id,
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


@router.get("/inventory", response_model=List[InventoryItemWithCardResponse])
def list_inventory(
    condition: Optional[str] = Query(None),
    card_id: Optional[str] = Query(None),
    is_for_sale: Optional[bool] = Query(None),
    is_for_trade: Optional[bool] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> List[dict]:
    _get_vendor_or_404(profile, db)  # ensure vendor profile exists

    query = (
        db.query(VendorInventory, Card, Set, Serie)
        .join(Card, VendorInventory.card_id == Card.id)
        .join(Set, Card.set_id == Set.id)
        .join(Serie, Set.serie_id == Serie.id)
        .filter(
            VendorInventory.profile_id == profile.id,
            VendorInventory.deleted_at.is_(None),
        )
    )

    if condition:
        query = query.filter(VendorInventory.condition == condition)
    if card_id:
        query = query.filter(VendorInventory.card_id == card_id)
    if is_for_sale is not None:
        query = query.filter(VendorInventory.is_for_sale == is_for_sale)
    if is_for_trade is not None:
        query = query.filter(VendorInventory.is_for_trade == is_for_trade)

    rows = query.order_by(VendorInventory.created_at.desc()).offset(offset).limit(limit).all()

    return [
        {
            "id": item.id,
            "card_id": item.card_id,
            "condition": item.condition,
            "quantity": item.quantity,
            "asking_price": item.asking_price,
            "is_for_sale": item.is_for_sale,
            "is_for_trade": item.is_for_trade,
            "notes": item.notes,
            "created_at": item.created_at,
            "card_name": card.name,
            "card_num": card.local_id,
            "set_name": set_row.name,
            "series_name": serie.name,
            "image_url": card.image_url,
            "rarity": card.rarity,
        }
        for item, card, set_row, serie in rows
    ]
