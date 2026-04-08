"""
Shows endpoints — public + authenticated.

Routes (public):
  GET  /shows              — list upcoming active shows with optional state/date filters
  GET  /shows/{show_id}    — single show by UUID or ontreasure_id slug

Routes (authenticated vendor):
  POST   /shows/{show_id}/register    — register the vendor for a show
  DELETE /shows/{show_id}/register    — unregister the vendor from a show
  GET    /vendor/shows/registered     — list shows the vendor is registered for
"""

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_profile
from app.models.inventory import VendorProfile
from app.models.profiles import Profile
from app.models.shows import CardShow, VendorShowRegistration

router = APIRouter(tags=["shows"])


class ShowResponse(BaseModel):
    id: str
    ontreasure_id: str
    name: str
    date_start: date
    date_end: Optional[date] = None
    time_range: Optional[str] = None
    venue_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    ticket_price: Optional[str] = None
    table_price: Optional[str] = None
    poster_url: Optional[str] = None
    organizer_name: Optional[str] = None
    description: Optional[str] = None
    source_url: str

    model_config = {"from_attributes": True}


def _build_response(show: CardShow) -> dict:
    return {
        "id": str(show.id),
        "ontreasure_id": show.ontreasure_id,
        "name": show.name,
        "date_start": show.date_start,
        "date_end": show.date_end,
        "time_range": show.time_range,
        "venue_name": show.venue_name,
        "city": show.city,
        "state": show.state,
        "address": show.address,
        "latitude": float(show.latitude) if show.latitude is not None else None,
        "longitude": float(show.longitude) if show.longitude is not None else None,
        "ticket_price": show.ticket_price,
        "table_price": show.table_price,
        "poster_url": show.poster_url,
        "organizer_name": show.organizer_name,
        "description": show.description,
        "source_url": show.source_url,
    }


def _get_vendor_or_404(profile: Profile, db: Session) -> VendorProfile:
    vendor = db.query(VendorProfile).filter(VendorProfile.profile_id == profile.id).first()
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor profile not found")
    return vendor


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@router.get("/shows", response_model=List[ShowResponse])
def list_shows(
    state: Optional[str] = Query(None, description="Filter by 2-letter state abbreviation e.g. NY"),
    from_date: Optional[date] = Query(None, description="Shows starting on or after this date"),
    until_date: Optional[date] = Query(None, description="Shows starting on or before this date"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List upcoming active card shows, ordered by date ascending."""
    filters = [
        CardShow.status == "active",
        CardShow.date_start >= (from_date or date.today()),
    ]
    if state:
        filters.append(CardShow.state == state.upper())
    if until_date:
        filters.append(CardShow.date_start <= until_date)

    shows = (
        db.query(CardShow)
        .filter(and_(*filters))
        .order_by(CardShow.date_start.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_build_response(s) for s in shows]


@router.get("/shows/{show_id}", response_model=ShowResponse)
def get_show(show_id: str, db: Session = Depends(get_db)):
    """Get a single show by UUID or ontreasure_id slug."""
    show = (
        db.query(CardShow)
        .filter(
            (CardShow.ontreasure_id == show_id) |
            (CardShow.id == show_id)
        )
        .first()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")
    return _build_response(show)


# ---------------------------------------------------------------------------
# Authenticated vendor routes
# ---------------------------------------------------------------------------

@router.post("/shows/{show_id}/register", status_code=status.HTTP_201_CREATED)
def register_for_show(
    show_id: str,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """Register the authenticated vendor as attending a show."""
    vendor = _get_vendor_or_404(profile, db)

    show = db.query(CardShow).filter(CardShow.id == show_id).first()
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    existing = (
        db.query(VendorShowRegistration)
        .filter(
            VendorShowRegistration.vendor_profile_id == str(vendor.id),
            VendorShowRegistration.show_id == show_id,
        )
        .first()
    )
    if existing:
        return {"id": str(existing.id), "show_id": show_id, "vendor_profile_id": str(vendor.id)}

    reg = VendorShowRegistration(
        id=str(uuid.uuid4()),
        vendor_profile_id=str(vendor.id),
        show_id=show_id,
    )
    db.add(reg)
    db.commit()
    return {"id": str(reg.id), "show_id": show_id, "vendor_profile_id": str(vendor.id)}


@router.delete("/shows/{show_id}/register", status_code=status.HTTP_204_NO_CONTENT)
def unregister_from_show(
    show_id: str,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """Unregister the authenticated vendor from a show."""
    vendor = _get_vendor_or_404(profile, db)

    reg = (
        db.query(VendorShowRegistration)
        .filter(
            VendorShowRegistration.vendor_profile_id == str(vendor.id),
            VendorShowRegistration.show_id == show_id,
        )
        .first()
    )
    if reg is None:
        raise HTTPException(status_code=404, detail="Registration not found")

    db.delete(reg)
    db.commit()


@router.get("/vendor/shows/registered", response_model=List[ShowResponse])
def list_registered_shows(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """List upcoming shows the authenticated vendor is registered for."""
    vendor = _get_vendor_or_404(profile, db)

    shows = (
        db.query(CardShow)
        .join(VendorShowRegistration, VendorShowRegistration.show_id == CardShow.id)
        .filter(
            VendorShowRegistration.vendor_profile_id == str(vendor.id),
            CardShow.date_start >= date.today(),
        )
        .order_by(CardShow.date_start.asc())
        .all()
    )
    return [_build_response(s) for s in shows]
