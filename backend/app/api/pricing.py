"""Pricing API — card price estimates and sold comps.

Endpoints:
  GET /cards/{card_v2_id}/pricing     — NM anchor + condition-based estimates
  GET /cards/{card_v2_id}/sold-comps  — recent sold listings from eBay

On-demand scraping:
  When /pricing is called and no fresh data exists for the card, the endpoint
  enqueues prices.scrape_card_on_demand on the scraper droplet's Redis and
  returns HTTP 202 with { "status": "pending" }. The frontend polls until
  data is available (200) or times out.

  If SCRAPER_REDIS_URL is not configured, the endpoint returns 202 without
  enqueueing — scraping will happen via the nightly beat instead.

Sold comps are filterable by condition_type, grading_company, grade, and
condition_ungraded.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db, settings
from app.models.catalog import PriceSnapshot, SoldComp

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pricing"])

# How many days before pricing data is considered stale and a re-scrape is triggered
PRICING_FRESHNESS_DAYS = 7

CONDITION_MULTIPLIERS: Dict[str, float] = {
    "nm": 1.00,
    "lp": 0.75,
    "mp": 0.55,
    "hp": 0.35,
    "dmg": 0.15,
}

CONDITION_LABELS: Dict[str, str] = {
    "nm": "Near Mint",
    "lp": "Lightly Played",
    "mp": "Moderately Played",
    "hp": "Heavily Played",
    "dmg": "Damaged",
}


def _get_scraper_app():
    """Return a minimal Celery app pointed at the scraper droplet's Redis.

    Returns None if SCRAPER_REDIS_URL is not configured. Import is deferred
    so the main app doesn't hard-depend on Celery being installed for this
    feature — though it is in requirements.txt.
    """
    if not settings.scraper_redis_url:
        return None
    try:
        from celery import Celery
        app = Celery(broker=settings.scraper_redis_url)
        app.conf.task_serializer = "json"
        return app
    except Exception as exc:
        logger.error("Failed to connect to scraper Redis: %s", exc)
        return None


def _enqueue_on_demand(card_v2_id: uuid.UUID) -> bool:
    """Enqueue scrape_card_on_demand on the droplet. Returns True if enqueued."""
    scraper = _get_scraper_app()
    if scraper is None:
        logger.warning(
            "SCRAPER_REDIS_URL not set — skipping on-demand enqueue for %s", card_v2_id
        )
        return False
    try:
        scraper.send_task(
            "prices.scrape_card_on_demand",
            args=[str(card_v2_id)],
        )
        logger.info("Enqueued scrape_card_on_demand for %s", card_v2_id)
        return True
    except Exception as exc:
        logger.error("Failed to enqueue scrape task for %s: %s", card_v2_id, exc)
        return False


def _is_pricing_fresh(snapshot: Optional[PriceSnapshot]) -> bool:
    if snapshot is None or snapshot.market_price is None:
        return False
    cutoff = datetime.utcnow() - timedelta(days=PRICING_FRESHNESS_DAYS)
    return snapshot.fetched_at >= cutoff


def _price_estimate(nm_price: float, condition: str) -> Optional[float]:
    multiplier = CONDITION_MULTIPLIERS.get(condition)
    if multiplier is None:
        return None
    return round(nm_price * multiplier, 2)


def _sold_comp_response(comp: SoldComp) -> Dict[str, Any]:
    return {
        "id": str(comp.id),
        "source": comp.source,
        "title": comp.title,
        "description": comp.description,
        "listing_url": comp.listing_url,
        "price": float(comp.price),
        "currency": comp.currency,
        "sold_date": comp.sold_date.isoformat() if comp.sold_date else None,
        "condition_type": comp.condition_type,
        "condition_ungraded": comp.condition_ungraded,
        "grading_company": comp.grading_company,
        "grade": comp.grade,
        "grading_company_other": comp.grading_company_other,
        "fetched_at": comp.fetched_at.isoformat(),
    }


@router.get("/cards/{card_v2_id}/pricing")
def get_card_pricing(
    card_v2_id: uuid.UUID,
    response: Response,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return NM market price anchor and estimated prices for all ungraded conditions.

    Returns 200 with pricing data when fresh data exists.
    Returns 202 with { "status": "pending" } when data is stale or missing —
    an on-demand scrape has been enqueued and the client should poll.
    """
    snapshot = (
        db.query(PriceSnapshot)
        .filter(
            PriceSnapshot.card_v2_id == card_v2_id,
            PriceSnapshot.source == "tcgplayer",
        )
        .order_by(PriceSnapshot.fetched_at.desc())
        .first()
    )

    if not _is_pricing_fresh(snapshot):
        _enqueue_on_demand(card_v2_id)
        response.status_code = status.HTTP_202_ACCEPTED
        return {
            "card_v2_id": str(card_v2_id),
            "status": "pending",
            "message": "Pricing data is being fetched. Please try again shortly.",
        }

    nm_price = float(snapshot.market_price)

    condition_estimates = [
        {
            "condition": condition,
            "label": CONDITION_LABELS[condition],
            "multiplier": multiplier,
            "estimated_price": _price_estimate(nm_price, condition),
        }
        for condition, multiplier in CONDITION_MULTIPLIERS.items()
    ]

    return {
        "card_v2_id": str(card_v2_id),
        "status": "ready",
        "nm_market_price": nm_price,
        "currency": snapshot.currency,
        "source": snapshot.source,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "expires_at": snapshot.expires_at.isoformat(),
        "condition_estimates": condition_estimates,
    }


@router.get("/cards/{card_v2_id}/sold-comps")
def get_card_sold_comps(
    card_v2_id: uuid.UUID,
    condition_type: Optional[str] = Query(None, description="'ungraded' or 'graded'"),
    grading_company: Optional[str] = Query(None, description="'psa', 'bgs', 'cgc', 'other'"),
    grade: Optional[str] = Query(None, description="e.g. '10', '9.5'"),
    condition_ungraded: Optional[str] = Query(None, description="'nm', 'lp', 'mp', 'hp', 'dmg'"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return recent eBay sold comps for a card with optional condition filters.

    Results are ordered by sold_date descending (most recent first).
    Returns an empty list (not 404) if no comps exist yet.
    """
    query = db.query(SoldComp).filter(SoldComp.card_v2_id == card_v2_id)

    if condition_type is not None:
        query = query.filter(SoldComp.condition_type == condition_type)
    if grading_company is not None:
        query = query.filter(SoldComp.grading_company == grading_company)
    if grade is not None:
        query = query.filter(SoldComp.grade == grade)
    if condition_ungraded is not None:
        query = query.filter(SoldComp.condition_ungraded == condition_ungraded)

    comps = (
        query
        .order_by(SoldComp.sold_date.desc().nullslast())
        .limit(limit)
        .all()
    )

    return {
        "card_v2_id": str(card_v2_id),
        "total": len(comps),
        "comps": [_sold_comp_response(c) for c in comps],
    }
