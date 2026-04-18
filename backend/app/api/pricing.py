"""Pricing API — card price estimates, sold comps, and per-user pricing preferences.

Endpoints:
  GET  /cards/{card_v2_id}/pricing          — NM anchor + condition-based estimates
  GET  /cards/{card_v2_id}/sold-comps       — recent sold listings from eBay
  GET  /cards/{card_v2_id}/estimated-value  — single estimated value for one condition
  GET  /pricing/preferences                 — get current user's pricing formula settings
  PUT  /pricing/preferences                 — upsert current user's pricing formula settings

On-demand scraping:
  When /pricing is called and no fresh data exists, the endpoint enqueues
  prices.scrape_card_on_demand on the scraper droplet's Redis and returns
  HTTP 202 { "status": "pending" }. Frontend polls until 200 or times out.
"""

import logging
import uuid
from datetime import datetime, timedelta
from statistics import median, mean, quantiles
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db, settings
from app.dependencies import get_current_profile
from app.models.catalog import PriceSnapshot, SoldComp
from app.models.pricing_preferences import PricingPreferences
from app.models.profiles import Profile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pricing"])

# ---------------------------------------------------------------------------
# Constants — used as defaults when no user preferences exist
# ---------------------------------------------------------------------------

PRICING_FRESHNESS_DAYS = 7
COMPS_FRESHNESS_DAYS = 7

DEFAULT_MULTIPLIERS: Dict[str, float] = {
    "nm":  1.00,
    "lp":  0.75,
    "mp":  0.55,
    "hp":  0.35,
    "dmg": 0.15,
}

CONDITION_LABELS: Dict[str, str] = {
    "nm":  "Near Mint",
    "lp":  "Lightly Played",
    "mp":  "Moderately Played",
    "hp":  "Heavily Played",
    "dmg": "Damaged",
}


# ---------------------------------------------------------------------------
# Preferences helpers
# ---------------------------------------------------------------------------

def _get_or_create_preferences(db: Session, profile_id: str) -> PricingPreferences:
    """Return user's PricingPreferences row, creating it with defaults on first access."""
    prefs = db.query(PricingPreferences).filter(
        PricingPreferences.profile_id == profile_id
    ).first()
    if prefs is None:
        prefs = PricingPreferences(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
        )
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


def _effective_multipliers(prefs: PricingPreferences) -> Dict[str, float]:
    """Build the condition→multiplier map from stored preferences."""
    return {
        "nm":  1.00,
        "lp":  float(prefs.lp_multiplier),
        "mp":  float(prefs.mp_multiplier),
        "hp":  float(prefs.hp_multiplier),
        "dmg": float(prefs.dmg_multiplier),
    }


# ---------------------------------------------------------------------------
# Scraper enqueue helpers
# ---------------------------------------------------------------------------

def _get_scraper_app():
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
    scraper = _get_scraper_app()
    if scraper is None:
        logger.warning("SCRAPER_REDIS_URL not set — skipping on-demand enqueue for %s", card_v2_id)
        return False
    try:
        scraper.send_task("prices.scrape_card_on_demand", args=[str(card_v2_id)])
        logger.info("Enqueued scrape_card_on_demand for %s", card_v2_id)
        return True
    except Exception as exc:
        logger.error("Failed to enqueue scrape task for %s: %s", card_v2_id, exc)
        return False


def _enqueue_ebay_on_demand(
    card_v2_id: uuid.UUID,
    grading_company: Optional[str],
    grade: Optional[str],
    condition_type: Optional[str],
) -> bool:
    scraper = _get_scraper_app()
    if scraper is None:
        logger.warning("SCRAPER_REDIS_URL not set — skipping eBay on-demand enqueue for %s", card_v2_id)
        return False
    try:
        scraper.send_task(
            "prices.scrape_ebay_on_demand",
            args=[str(card_v2_id)],
            kwargs={"grading_company": grading_company, "grade": grade, "condition_type": condition_type},
        )
        logger.info("Enqueued scrape_ebay_on_demand for %s (%s %s)", card_v2_id, grading_company, grade)
        return True
    except Exception as exc:
        logger.error("Failed to enqueue eBay scrape task for %s: %s", card_v2_id, exc)
        return False


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _is_pricing_fresh(snapshot: Optional[PriceSnapshot]) -> bool:
    if snapshot is None or snapshot.market_price is None:
        return False
    cutoff = datetime.utcnow() - timedelta(days=PRICING_FRESHNESS_DAYS)
    return snapshot.fetched_at >= cutoff


def _price_estimate(nm_price: float, multiplier: float) -> float:
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
        "sale_type": comp.sale_type,
        "fetched_at": comp.fetched_at.isoformat(),
    }


def _remove_outliers(prices: List[float]) -> List[float]:
    """Remove clear outliers using IQR × 2.0 fencing.

    Only applied when there are at least 5 prices. If fencing would leave
    fewer than 3 prices the original list is returned unchanged — a wide
    spread on a small sample is more likely legitimate variance than noise.
    """
    if len(prices) < 5:
        return prices
    q1, _, q3 = quantiles(prices, n=4)
    iqr = q3 - q1
    lo = q1 - 2.0 * iqr
    hi = q3 + 2.0 * iqr
    filtered = [p for p in prices if lo <= p <= hi]
    return filtered if len(filtered) >= 3 else prices


def _aggregate_prices(prices: List[float], method: str) -> float:
    """Remove outliers then apply the user's aggregation method to a list of prices."""
    prices = _remove_outliers(prices)
    if method == "most_recent":
        return round(prices[0], 2)   # caller passes prices sorted date-desc
    if method == "average":
        return round(mean(prices), 2)
    return round(median(prices), 2)  # default: median


# ---------------------------------------------------------------------------
# Preferences endpoints
# ---------------------------------------------------------------------------

class PricingPreferencesResponse(BaseModel):
    lp_multiplier: float
    mp_multiplier: float
    hp_multiplier: float
    dmg_multiplier: float
    graded_comp_window_days: int
    graded_aggregation: str


class PricingPreferencesUpdate(BaseModel):
    lp_multiplier: Optional[float] = Field(None, ge=0, le=1)
    mp_multiplier: Optional[float] = Field(None, ge=0, le=1)
    hp_multiplier: Optional[float] = Field(None, ge=0, le=1)
    dmg_multiplier: Optional[float] = Field(None, ge=0, le=1)
    graded_comp_window_days: Optional[int] = Field(None)
    graded_aggregation: Optional[str] = None

    def validate_window(self) -> None:
        if self.graded_comp_window_days is not None and self.graded_comp_window_days not in (7, 14, 30):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="graded_comp_window_days must be 7, 14, or 30",
            )

    def validate_aggregation(self) -> None:
        valid = {"median", "average", "most_recent"}
        if self.graded_aggregation is not None and self.graded_aggregation not in valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"graded_aggregation must be one of {sorted(valid)}",
            )


@router.get("/pricing/preferences", response_model=PricingPreferencesResponse)
def get_pricing_preferences(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> PricingPreferencesResponse:
    """Return current user's pricing formula settings, creating defaults on first access."""
    prefs = _get_or_create_preferences(db, profile.id)
    return PricingPreferencesResponse(
        lp_multiplier=float(prefs.lp_multiplier),
        mp_multiplier=float(prefs.mp_multiplier),
        hp_multiplier=float(prefs.hp_multiplier),
        dmg_multiplier=float(prefs.dmg_multiplier),
        graded_comp_window_days=prefs.graded_comp_window_days,
        graded_aggregation=prefs.graded_aggregation,
    )


@router.put("/pricing/preferences", response_model=PricingPreferencesResponse)
def update_pricing_preferences(
    body: PricingPreferencesUpdate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> PricingPreferencesResponse:
    """Upsert current user's pricing formula settings. Only provided fields are updated."""
    body.validate_window()
    body.validate_aggregation()

    prefs = _get_or_create_preferences(db, profile.id)

    if body.lp_multiplier is not None:
        prefs.lp_multiplier = body.lp_multiplier
    if body.mp_multiplier is not None:
        prefs.mp_multiplier = body.mp_multiplier
    if body.hp_multiplier is not None:
        prefs.hp_multiplier = body.hp_multiplier
    if body.dmg_multiplier is not None:
        prefs.dmg_multiplier = body.dmg_multiplier
    if body.graded_comp_window_days is not None:
        prefs.graded_comp_window_days = body.graded_comp_window_days
    if body.graded_aggregation is not None:
        prefs.graded_aggregation = body.graded_aggregation

    prefs.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(prefs)

    return PricingPreferencesResponse(
        lp_multiplier=float(prefs.lp_multiplier),
        mp_multiplier=float(prefs.mp_multiplier),
        hp_multiplier=float(prefs.hp_multiplier),
        dmg_multiplier=float(prefs.dmg_multiplier),
        graded_comp_window_days=prefs.graded_comp_window_days,
        graded_aggregation=prefs.graded_aggregation,
    )


# ---------------------------------------------------------------------------
# Card pricing endpoints
# ---------------------------------------------------------------------------

@router.get("/cards/{card_v2_id}/pricing")
def get_card_pricing(
    card_v2_id: uuid.UUID,
    response: Response,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return NM market price anchor and estimated prices for all ungraded conditions.

    Condition estimates use the authenticated user's custom multipliers (falling
    back to defaults if no preferences row exists yet).

    Returns 200 with pricing data when fresh data exists.
    Returns 202 with { "status": "pending" } when data is stale/missing.
    """
    snapshots = (
        db.query(PriceSnapshot)
        .filter(
            PriceSnapshot.card_v2_id == card_v2_id,
            PriceSnapshot.source == "tcgplayer",
            PriceSnapshot.market_price.isnot(None),
        )
        .order_by(PriceSnapshot.fetched_at.desc())
        .all()
    )

    snapshot = None
    for preferred in ("holofoil", "normal"):
        snapshot = next((s for s in snapshots if s.variant == preferred), None)
        if snapshot:
            break
    if snapshot is None and snapshots:
        snapshot = snapshots[0]

    if not _is_pricing_fresh(snapshot):
        _enqueue_on_demand(card_v2_id)
        response.status_code = status.HTTP_202_ACCEPTED
        return {
            "card_v2_id": str(card_v2_id),
            "status": "pending",
            "message": "Pricing data is being fetched. Please try again shortly.",
        }

    nm_price = float(snapshot.market_price)
    prefs = _get_or_create_preferences(db, profile.id)
    multipliers = _effective_multipliers(prefs)

    condition_estimates = [
        {
            "condition": condition,
            "label": CONDITION_LABELS[condition],
            "multiplier": multiplier,
            "estimated_price": _price_estimate(nm_price, multiplier),
        }
        for condition, multiplier in multipliers.items()
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


@router.get("/cards/{card_v2_id}/estimated-value")
def get_card_estimated_value(
    card_v2_id: uuid.UUID,
    response: Response,
    condition_type: str = Query(..., description="'ungraded' or 'graded'"),
    condition_ungraded: Optional[str] = Query(None, description="'nm','lp','mp','hp','dmg'"),
    grading_company: Optional[str] = Query(None),
    grade: Optional[str] = Query(None),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return a single estimated value for one specific condition.

    For ungraded: nm_price × user's condition multiplier.
    For graded: aggregates recent sold comps using user's window + method.

    Returns 200 { estimated_value, basis, data_points, window_days }
    Returns 202 { status: "pending" } when underlying data is not yet available.
    """
    prefs = _get_or_create_preferences(db, profile.id)

    if condition_type == "ungraded":
        if not condition_ungraded:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="condition_ungraded is required for ungraded condition_type",
            )

        snapshots = (
            db.query(PriceSnapshot)
            .filter(
                PriceSnapshot.card_v2_id == card_v2_id,
                PriceSnapshot.source == "tcgplayer",
                PriceSnapshot.market_price.isnot(None),
            )
            .order_by(PriceSnapshot.fetched_at.desc())
            .all()
        )
        snapshot = None
        for preferred in ("holofoil", "normal"):
            snapshot = next((s for s in snapshots if s.variant == preferred), None)
            if snapshot:
                break
        if snapshot is None and snapshots:
            snapshot = snapshots[0]

        if not _is_pricing_fresh(snapshot):
            _enqueue_on_demand(card_v2_id)
            response.status_code = status.HTTP_202_ACCEPTED
            return {"card_v2_id": str(card_v2_id), "status": "pending"}

        multipliers = _effective_multipliers(prefs)
        multiplier = multipliers.get(condition_ungraded, 1.0)
        nm_price = float(snapshot.market_price)
        return {
            "card_v2_id": str(card_v2_id),
            "status": "ready",
            "estimated_value": _price_estimate(nm_price, multiplier),
            "basis": "nm_market_price",
            "data_points": 1,
            "window_days": None,
        }

    # Graded — aggregate sold comps
    if not grading_company or not grade:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="grading_company and grade are required for graded condition_type",
        )

    window_days = prefs.graded_comp_window_days
    sold_cutoff = datetime.utcnow() - timedelta(days=window_days)
    # Use a fixed 30-day fetched_at window to check whether we have cached data at all;
    # the sold_date filter then narrows to the user's preferred window for aggregation.
    fetch_cutoff = datetime.utcnow() - timedelta(days=30)

    cache_check = (
        db.query(SoldComp)
        .filter(
            SoldComp.card_v2_id == card_v2_id,
            SoldComp.condition_type == "graded",
            SoldComp.grading_company == grading_company,
            SoldComp.grade == grade,
            SoldComp.fetched_at >= fetch_cutoff,
        )
        .first()
    )
    if cache_check is None:
        _enqueue_ebay_on_demand(card_v2_id, grading_company, grade, "graded")
        response.status_code = status.HTTP_202_ACCEPTED
        return {"card_v2_id": str(card_v2_id), "status": "pending"}

    comps = (
        db.query(SoldComp)
        .filter(
            SoldComp.card_v2_id == card_v2_id,
            SoldComp.condition_type == "graded",
            SoldComp.grading_company == grading_company,
            SoldComp.grade == grade,
            SoldComp.sold_date >= sold_cutoff,
            SoldComp.price.isnot(None),
        )
        .order_by(SoldComp.sold_date.desc().nullslast())
        .all()
    )

    if not comps:
        # Cache exists but no sales within the user's window — return empty rather than pending
        return {
            "card_v2_id": str(card_v2_id),
            "status": "ready",
            "estimated_value": None,
            "basis": f"sold_comps_{prefs.graded_aggregation}",
            "data_points": 0,
            "window_days": window_days,
        }

    prices = [float(c.price) for c in comps]
    estimated = _aggregate_prices(prices, prefs.graded_aggregation)

    return {
        "card_v2_id": str(card_v2_id),
        "status": "ready",
        "estimated_value": estimated,
        "basis": f"sold_comps_{prefs.graded_aggregation}",
        "data_points": len(prices),
        "window_days": window_days,
    }


@router.get("/cards/{card_v2_id}/sold-comps")
def get_card_sold_comps(
    card_v2_id: uuid.UUID,
    response: Response,
    condition_type: Optional[str] = Query(None, description="'ungraded' or 'graded'"),
    grading_company: Optional[str] = Query(None),
    grade: Optional[str] = Query(None),
    condition_ungraded: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return recent eBay sold comps for a card with optional condition filters.

    Returns 200 with comps data when fresh data exists.
    Returns 202 with { "status": "pending" } when no fresh data exists.
    """
    cutoff = datetime.utcnow() - timedelta(days=COMPS_FRESHNESS_DAYS)
    freshness_query = db.query(SoldComp).filter(
        SoldComp.card_v2_id == card_v2_id,
        SoldComp.fetched_at >= cutoff,
    )
    if condition_type is not None:
        freshness_query = freshness_query.filter(SoldComp.condition_type == condition_type)
    if grading_company is not None:
        freshness_query = freshness_query.filter(SoldComp.grading_company == grading_company)
    if grade is not None:
        freshness_query = freshness_query.filter(SoldComp.grade == grade)
    if condition_ungraded is not None:
        freshness_query = freshness_query.filter(SoldComp.condition_ungraded == condition_ungraded)

    if freshness_query.first() is None:
        _enqueue_ebay_on_demand(card_v2_id, grading_company, grade, condition_type)
        response.status_code = status.HTTP_202_ACCEPTED
        return {
            "card_v2_id": str(card_v2_id),
            "status": "pending",
            "message": "Sold comps are being fetched. Please try again shortly.",
        }

    comps = (
        freshness_query
        .order_by(SoldComp.sold_date.desc().nullslast())
        .limit(limit)
        .all()
    )

    return {
        "card_v2_id": str(card_v2_id),
        "status": "ready",
        "total": len(comps),
        "comps": [_sold_comp_response(c) for c in comps],
    }
