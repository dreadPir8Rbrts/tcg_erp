from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.catalog import Card, Set

router = APIRouter(tags=["catalog"])


@router.get("/cards/{card_id}")
def get_card(card_id: str, db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.get("/cards")
def search_cards(
    q: str = Query(..., min_length=2, description="Search by card name"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    results = (
        db.query(Card)
        .filter(Card.name.ilike(f"%{q}%"))
        .order_by(Card.name)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return results


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
