"""
Price sync tasks — refresh price_snapshots for cards in active vendor inventory.

Tasks:
  prices.refresh_active_inventory — fetch current pricing from TCGdex for all
      cards with stale or missing price snapshots in active inventory.
      Runs every 6 hours.

Upsert target: UNIQUE(card_id, source, variant) — never plain INSERT.
Error handling: log and skip per card — never block the rest of the batch.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from tcgdexsdk import TCGdex

from app.db.session import SessionLocal
from app.models.catalog import PriceSnapshot

logger = logging.getLogger(__name__)

PRICE_TTL_HOURS = 24


def _is_stale(snapshot: Optional[PriceSnapshot]) -> bool:
    """Return True if snapshot is missing or past its TTL."""
    if snapshot is None:
        return True
    return datetime.utcnow() > snapshot.expires_at


def _upsert_price_row(
    db,
    card_id: str,
    source: str,
    variant: str,
    currency: str,
    fields: dict,
) -> None:
    """
    Upsert a single price_snapshots row using ON CONFLICT (card_id, source, variant).
    Never uses plain INSERT — always safe to re-run.
    """
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=PRICE_TTL_HOURS)

    stmt = text("""
        INSERT INTO price_snapshots (
            id, card_id, source, variant, currency,
            low_price, mid_price, high_price, market_price, direct_low_price,
            avg, trend, avg_1, avg_7, avg_30,
            fetched_at, expires_at
        ) VALUES (
            gen_random_uuid(), :card_id, :source, :variant, :currency,
            :low_price, :mid_price, :high_price, :market_price, :direct_low_price,
            :avg, :trend, :avg_1, :avg_7, :avg_30,
            :fetched_at, :expires_at
        )
        ON CONFLICT (card_id, source, variant) DO UPDATE SET
            currency        = EXCLUDED.currency,
            low_price       = EXCLUDED.low_price,
            mid_price       = EXCLUDED.mid_price,
            high_price      = EXCLUDED.high_price,
            market_price    = EXCLUDED.market_price,
            direct_low_price = EXCLUDED.direct_low_price,
            avg             = EXCLUDED.avg,
            trend           = EXCLUDED.trend,
            avg_1           = EXCLUDED.avg_1,
            avg_7           = EXCLUDED.avg_7,
            avg_30          = EXCLUDED.avg_30,
            fetched_at      = EXCLUDED.fetched_at,
            expires_at      = EXCLUDED.expires_at
    """)

    db.execute(stmt, {
        "card_id": card_id,
        "source": source,
        "variant": variant,
        "currency": currency,
        "low_price": fields.get("low_price"),
        "mid_price": fields.get("mid_price"),
        "high_price": fields.get("high_price"),
        "market_price": fields.get("market_price"),
        "direct_low_price": fields.get("direct_low_price"),
        "avg": fields.get("avg"),
        "trend": fields.get("trend"),
        "avg_1": fields.get("avg_1"),
        "avg_7": fields.get("avg_7"),
        "avg_30": fields.get("avg_30"),
        "fetched_at": now,
        "expires_at": expires_at,
    })


def _sync_card_prices(db, sdk: TCGdex, card_id: str) -> int:
    """
    Fetch pricing for a single card from TCGdex and upsert into price_snapshots.
    Returns the number of price rows written. Logs and returns 0 on any error.
    """
    try:
        card = sdk.card.getSync(card_id)
    except Exception as exc:
        logger.warning("Failed to fetch card %s for pricing: %s — skipping", card_id, exc)
        return 0

    if card is None:
        logger.warning("Card %s returned None from TCGdex — skipping pricing", card_id)
        return 0

    pricing = getattr(card, "pricing", None)
    if not pricing:
        return 0

    rows_written = 0

    # TCGPlayer (USD)
    tcgplayer = getattr(pricing, "tcgplayer", None) if hasattr(pricing, "tcgplayer") else (
        pricing.get("tcgplayer") if isinstance(pricing, dict) else None
    )
    if tcgplayer:
        variant_map = {
            "normal": "normal",
            "holofoil": "holofoil",
            "reverseHolofoil": "reverse-holofoil",
            "1stEdition": "1st-edition",
            "1stEditionHolofoil": "1st-edition-holofoil",
            "unlimited": "unlimited",
            "unlimitedHolofoil": "unlimited-holofoil",
        }
        for sdk_key, db_variant in variant_map.items():
            variant_data = (
                getattr(tcgplayer, sdk_key, None)
                if not isinstance(tcgplayer, dict)
                else tcgplayer.get(sdk_key)
            )
            if not variant_data:
                continue
            try:
                _upsert_price_row(db, card_id, "tcgplayer", db_variant, "USD", {
                    "low_price": getattr(variant_data, "lowPrice", None) if not isinstance(variant_data, dict) else variant_data.get("lowPrice"),
                    "mid_price": getattr(variant_data, "midPrice", None) if not isinstance(variant_data, dict) else variant_data.get("midPrice"),
                    "high_price": getattr(variant_data, "highPrice", None) if not isinstance(variant_data, dict) else variant_data.get("highPrice"),
                    "market_price": getattr(variant_data, "marketPrice", None) if not isinstance(variant_data, dict) else variant_data.get("marketPrice"),
                    "direct_low_price": getattr(variant_data, "directLowPrice", None) if not isinstance(variant_data, dict) else variant_data.get("directLowPrice"),
                })
                rows_written += 1
            except Exception as exc:
                logger.warning("Failed to upsert TCGPlayer price for %s/%s: %s", card_id, db_variant, exc)

    # Cardmarket (EUR)
    cardmarket = getattr(pricing, "cardmarket", None) if hasattr(pricing, "cardmarket") else (
        pricing.get("cardmarket") if isinstance(pricing, dict) else None
    )
    if cardmarket:
        try:
            _upsert_price_row(db, card_id, "cardmarket", "normal", "EUR", {
                "low_price": getattr(cardmarket, "low", None) if not isinstance(cardmarket, dict) else cardmarket.get("low"),
                "market_price": getattr(cardmarket, "avg", None) if not isinstance(cardmarket, dict) else cardmarket.get("avg"),
                "avg": getattr(cardmarket, "avg", None) if not isinstance(cardmarket, dict) else cardmarket.get("avg"),
                "trend": getattr(cardmarket, "trend", None) if not isinstance(cardmarket, dict) else cardmarket.get("trend"),
                "avg_1": getattr(cardmarket, "avg1", None) if not isinstance(cardmarket, dict) else cardmarket.get("avg1"),
                "avg_7": getattr(cardmarket, "avg7", None) if not isinstance(cardmarket, dict) else cardmarket.get("avg7"),
                "avg_30": getattr(cardmarket, "avg30", None) if not isinstance(cardmarket, dict) else cardmarket.get("avg30"),
            })
            rows_written += 1
        except Exception as exc:
            logger.warning("Failed to upsert Cardmarket price for %s: %s", card_id, exc)

    return rows_written


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@shared_task(name="prices.refresh_active_inventory")
def refresh_active_inventory() -> dict:
    """
    Refresh price snapshots for cards currently in active vendor inventory.
    Only fetches cards with stale snapshots (expired TTL or no snapshot at all).
    Runs every 6 hours.
    """
    logger.info("prices.refresh_active_inventory started")
    sdk = TCGdex("en")
    db = SessionLocal()
    cards_refreshed = 0
    rows_written = 0

    try:
        # Get distinct card IDs from active (non-deleted) inventory.
        # inventory_items is created in Phase 1 — return early if table doesn't exist yet.
        try:
            active_card_ids = db.execute(text("""
                SELECT DISTINCT card_id
                FROM inventory_items
                WHERE deleted_at IS NULL
            """)).fetchall()
        except ProgrammingError:
            db.rollback()
            logger.info("inventory_items table not yet created (Phase 1) — skipping price refresh")
            return {"cards_refreshed": 0, "rows_written": 0}

        if not active_card_ids:
            logger.info("No active inventory — nothing to price refresh")
            return {"cards_refreshed": 0, "rows_written": 0}

        logger.info("Refreshing prices for %d distinct cards in active inventory", len(active_card_ids))

        for (card_id,) in active_card_ids:
            # Check if any snapshot for this card is still fresh
            freshest = db.query(PriceSnapshot).filter(
                PriceSnapshot.card_id == card_id,
                PriceSnapshot.expires_at > datetime.utcnow(),
            ).first()

            if not _is_stale(freshest):
                continue  # Still within TTL — skip

            count = _sync_card_prices(db, sdk, card_id)
            if count > 0:
                db.commit()
                cards_refreshed += 1
                rows_written += count

            time.sleep(0.1)  # Be a good citizen

    except Exception as exc:
        logger.exception("prices.refresh_active_inventory failed: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()

    logger.info(
        "prices.refresh_active_inventory complete — %d cards refreshed, %d rows written",
        cards_refreshed, rows_written,
    )
    return {"cards_refreshed": cards_refreshed, "rows_written": rows_written}
