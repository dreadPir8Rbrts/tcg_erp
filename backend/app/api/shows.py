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
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_profile
from app.models.inventory import VendorProfile
from app.models.profiles import Profile
from app.models.shows import CardShow, VendorShowRegistration

# ---------------------------------------------------------------------------
# Zip code → lat/lon resolution (module-level cache, lives for process lifetime)
# ---------------------------------------------------------------------------

_zip_cache: Dict[str, Tuple[float, float]] = {}


def _resolve_zip(zip_code: str) -> Optional[Tuple[float, float]]:
    """
    Resolve a US zip code to (latitude, longitude) via Nominatim.
    Results are cached in-process so repeated searches for the same zip
    cost only one network call.
    """
    key = zip_code.strip()
    if key in _zip_cache:
        return _zip_cache[key]

    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError

        geolocator = Nominatim(user_agent="cardops-api/1.0")
        location = geolocator.geocode(
            f"{key}, USA",
            addressdetails=False,
            language="en",
            timeout=10,
        )
        if location:
            coords = (location.latitude, location.longitude)
            _zip_cache[key] = coords
            return coords
    except Exception:
        pass

    return None


router = APIRouter(tags=["shows"])


class ShowVendorResponse(BaseModel):
    vendor_profile_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None

    model_config = {"from_attributes": True}


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
    zip_code: Optional[str] = Query(None, description="Filter shows within radius_miles of this US zip code"),
    latitude: Optional[float] = Query(None, description="Filter shows within radius_miles of this latitude"),
    longitude: Optional[float] = Query(None, description="Filter shows within radius_miles of this longitude"),
    radius_miles: float = Query(50.0, ge=1, le=500, description="Radius in miles for location filter"),
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

    # Resolve zip code to coordinates if provided
    center_lat: Optional[float] = latitude
    center_lon: Optional[float] = longitude

    if zip_code and (center_lat is None or center_lon is None):
        coords = _resolve_zip(zip_code)
        if coords is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not resolve zip code: {zip_code}",
            )
        center_lat, center_lon = coords

    # Apply haversine distance filter when coordinates are available
    # Formula: 3959 * acos(cos(lat1)*cos(lat2)*cos(lon2-lon1) + sin(lat1)*sin(lat2)) <= radius
    # Only includes shows that have lat/lon populated.
    if center_lat is not None and center_lon is not None:
        haversine = text(
            "latitude IS NOT NULL AND longitude IS NOT NULL AND "
            "3959 * acos("
            "  LEAST(1.0, "
            "    cos(radians(:lat)) * cos(radians(latitude)) "
            "    * cos(radians(longitude) - radians(:lon)) "
            "    + sin(radians(:lat)) * sin(radians(latitude))"
            "  )"
            ") <= :radius"
        ).bindparams(lat=center_lat, lon=center_lon, radius=radius_miles)
        filters.append(haversine)

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


@router.get("/shows/{show_id}/vendors", response_model=List[ShowVendorResponse])
def list_show_vendors(show_id: str, db: Session = Depends(get_db)):
    """List vendors registered as attending a show."""
    show = db.query(CardShow).filter(CardShow.id == show_id).first()
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    rows = (
        db.query(VendorProfile, Profile)
        .join(VendorShowRegistration, VendorShowRegistration.vendor_profile_id == VendorProfile.id)
        .join(Profile, Profile.id == VendorProfile.profile_id)
        .filter(VendorShowRegistration.show_id == show_id)
        .order_by(Profile.display_name.asc())
        .all()
    )
    return [
        {
            "vendor_profile_id": vendor.id,
            "display_name": profile.display_name,
            "avatar_url": profile.avatar_url,
            "bio": vendor.bio,
        }
        for vendor, profile in rows
    ]


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
