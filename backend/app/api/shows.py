"""
Shows endpoints — public, no auth required.

Routes:
  GET /shows              — list upcoming active shows with optional state/date filters
  GET /shows/{show_id}    — single show by UUID or ontreasure_id slug
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.shows import CardShow

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
