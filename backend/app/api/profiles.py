"""
Profile endpoints — onboarding and profile management.

Routes:
  GET   /profiles/me            — get own profile
  PATCH /profiles/me            — update own profile (role, display_name, bio, interests, zip, avatar, rates, onboarding_complete)
  POST  /profiles/me/background — upload background image to S3
  POST  /profiles/me/avatar     — upload avatar image to S3
"""

import uuid as uuid_module
from decimal import Decimal
from typing import Optional, List, Dict, Any

import boto3
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db, settings
from app.dependencies import get_current_profile
from app.models.profiles import Profile

router = APIRouter(tags=["profiles"])

_VALID_ROLES = {"vendor", "collector"}


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=50)
    role: Optional[str] = None
    bio: Optional[str] = None
    tcg_interests: Optional[List[str]] = None
    zip_code: Optional[str] = Field(None, pattern=r"^\d{5}$")
    avatar_url: Optional[str] = None
    onboarding_complete: Optional[bool] = None
    buying_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    trade_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    is_accounting_enabled: Optional[bool] = None


def _profile_response(profile: Profile) -> Dict[str, Any]:
    return {
        "id": profile.id,
        "role": profile.role,
        "display_name": profile.display_name,
        "bio": profile.bio,
        "tcg_interests": profile.tcg_interests,
        "onboarding_complete": profile.onboarding_complete,
        "zip_code": profile.zip_code,
        "avatar_url": profile.avatar_url,
        "background_url": profile.background_url,
        "buying_rate": profile.buying_rate,
        "trade_rate": profile.trade_rate,
        "is_accounting_enabled": profile.is_accounting_enabled,
    }


@router.get("/profiles/me")
def get_profile(
    profile: Profile = Depends(get_current_profile),
) -> Dict[str, Any]:
    """Return the authenticated user's profile."""
    return _profile_response(profile)


@router.patch("/profiles/me")
def update_profile(
    body: ProfileUpdate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update the authenticated user's profile."""
    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    if "role" in update_data and update_data["role"] not in _VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(_VALID_ROLES))}",
        )

    for key, value in update_data.items():
        setattr(profile, key, value)

    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _profile_response(profile)


@router.post("/profiles/me/background")
def upload_background(
    image: UploadFile = File(...),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Upload background image to S3, persist URL to profiles.background_url, return it."""
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    image_bytes = image.file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Background image must be under 10 MB")

    if not settings.aws_s3_bucket:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image storage not configured",
        )

    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    key = f"backgrounds/{profile.id}/{uuid_module.uuid4()}.jpg"
    s3.put_object(
        Bucket=settings.aws_s3_bucket,
        Key=key,
        Body=image_bytes,
        ContentType=image.content_type,
    )
    url = f"https://{settings.aws_s3_bucket}.s3.amazonaws.com/{key}"
    profile.background_url = url
    db.add(profile)
    db.commit()
    return {"background_url": url}


@router.post("/profiles/me/avatar")
def upload_avatar(
    image: UploadFile = File(...),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Upload avatar image to S3 and return the public URL."""
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    image_bytes = image.file.read()
    if len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Avatar must be under 5 MB")

    if not settings.aws_s3_bucket:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Avatar storage not configured",
        )

    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    key = f"avatars/{profile.id}/{uuid_module.uuid4()}.jpg"
    s3.put_object(
        Bucket=settings.aws_s3_bucket,
        Key=key,
        Body=image_bytes,
        ContentType=image.content_type,
    )
    url = f"https://{settings.aws_s3_bucket}.s3.amazonaws.com/{key}"
    profile.avatar_url = url
    db.add(profile)
    db.commit()
    return {"avatar_url": url}
