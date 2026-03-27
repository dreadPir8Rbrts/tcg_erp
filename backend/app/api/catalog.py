from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.catalog import Card, Serie, Set

router = APIRouter(tags=["catalog"])


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class CardDetailResponse(BaseModel):
    id: str
    card_num: str
    name: str
    category: str
    rarity: Optional[str] = None
    illustrator: Optional[str] = None
    image_url: Optional[str] = None
    variants: Optional[dict] = None
    set_name: str
    release_date: Optional[str] = None
    series_name: str
    series_logo_url: Optional[str] = None

    model_config = {"from_attributes": True}


def _build_response(card: Card, set_row: Set, serie: Serie) -> dict:
    return {
        "id": card.id,
        "card_num": card.local_id,
        "name": card.name,
        "category": card.category,
        "rarity": card.rarity,
        "illustrator": card.illustrator,
        "image_url": card.image_url,
        "variants": card.variants,
        "set_name": set_row.name,
        "release_date": str(set_row.release_date) if set_row.release_date else None,
        "series_name": serie.name,
        "series_logo_url": serie.logo_url,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/cards/{card_id}", response_model=CardDetailResponse)
def get_card(card_id: str, db: Session = Depends(get_db)):
    row = (
        db.query(Card, Set, Serie)
        .join(Set, Card.set_id == Set.id)
        .join(Serie, Set.serie_id == Serie.id)
        .filter(Card.id == card_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Card not found")
    card, set_row, serie = row
    return _build_response(card, set_row, serie)


@router.get("/cards", response_model=List[CardDetailResponse])
def search_cards(
    name: Optional[str] = Query(None, min_length=2, description="Filter by card name (contains)"),
    card_num: Optional[str] = Query(None, min_length=1, description="Filter by card number within set"),
    set_name: Optional[str] = Query(None, min_length=2, description="Filter by set name (contains)"),
    series_name: Optional[str] = Query(None, min_length=2, description="Filter by series name (contains)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if not any([name, card_num, set_name, series_name]):
        raise HTTPException(status_code=422, detail="At least one search parameter is required.")

    query = (
        db.query(Card, Set, Serie)
        .join(Set, Card.set_id == Set.id)
        .join(Serie, Set.serie_id == Serie.id)
    )
    if name:
        query = query.filter(Card.name.ilike(f"%{name}%"))
    if card_num:
        query = query.filter(Card.local_id.ilike(f"%{card_num}%"))
    if set_name:
        query = query.filter(Set.name.ilike(f"%{set_name}%"))
    if series_name:
        query = query.filter(Serie.name.ilike(f"%{series_name}%"))

    rows = query.order_by(Card.name).offset(offset).limit(limit).all()
    return [_build_response(card, set_row, serie) for card, set_row, serie in rows]


@router.get("/sets/{set_id}")
def get_set(set_id: str, db: Session = Depends(get_db)):
    set_row = db.get(Set, set_id)
    if set_row is None:
        raise HTTPException(status_code=404, detail="Set not found")
    card_count = db.query(func.count(Card.id)).filter(Card.set_id == set_id).scalar()
    return {**set_row.__dict__, "card_count_local": card_count}


@router.get("/sets")
def list_sets(
    serie_id: Optional[str] = Query(None, description="Filter by serie id"),
    db: Session = Depends(get_db),
):
    query = db.query(Set)
    if serie_id:
        query = query.filter(Set.serie_id == serie_id)
    return query.order_by(Set.release_date.desc()).all()
