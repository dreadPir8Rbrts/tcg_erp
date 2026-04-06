"""
Scrydex catalog sync tasks — populate expansions_v2 and cards_v2 from the Scrydex API.

Tasks:
  scrydex.sync_expansions             — fetch + upsert all expansions for one game
  scrydex.sync_cards_for_expansion    — fetch + upsert all cards for one expansion (paginated)
  scrydex.full_sync                   — orchestrator: syncs expansions then fans out card tasks
  scrydex.refresh_prices              — lightweight price refresh (NOT scheduled — ready for Phase 2)

All tasks are idempotent: upsert on UNIQUE(game, external_id) — safe to re-run at any time.
Error handling: log and continue — a single bad card/expansion never aborts the full run.

Authentication: every request sends X-Api-Key and X-Team-ID headers from settings.
"""

import logging
import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import httpx
from celery import shared_task
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import SessionLocal, settings
from app.models.catalog_v2 import CardV2, ExpansionV2

logger = logging.getLogger(__name__)

SCRYDEX_BASE = "https://api.scrydex.com"
PAGE_SIZE = 100

# Games covered by the full sync.
# Add "onepiece_jp" here (with appropriate endpoint adjustments) when JP One Piece is confirmed.
SYNC_GAMES = ["pokemon", "onepiece"]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _scrydex_client() -> httpx.Client:
    """Return a configured httpx Client with Scrydex auth headers."""
    return httpx.Client(
        timeout=30.0,
        headers={
            "X-Api-Key": settings.scrydex_api_key or "",
            "X-Team-ID": settings.scrydex_team_id or "",
        },
    )


def _fetch_all_pages(client: httpx.Client, url: str, extra_params: Optional[Dict[str, Any]] = None) -> List[dict]:
    """
    Paginate through a Scrydex list endpoint and return all items.
    Raises httpx.HTTPStatusError on non-2xx responses.
    """
    params: Dict[str, Any] = dict(extra_params or {})
    params["page_size"] = PAGE_SIZE
    all_items: List[dict] = []
    page = 1

    while True:
        params["page"] = page
        resp = client.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()

        data = body.get("data", [])
        all_items.extend(data)

        total = body.get("totalCount", 0)
        if not data or len(all_items) >= total:
            break

        page += 1

    return all_items


# ---------------------------------------------------------------------------
# Expansion parsing + upsert
# ---------------------------------------------------------------------------

def _parse_release_date(raw: Optional[str]) -> Optional[date]:
    """Parse Scrydex date format 'YYYY/MM/DD' → date object."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y/%m/%d").date()
    except ValueError:
        return None


def _upsert_expansion(db, game: str, data: dict) -> None:
    """Upsert a single expansion into expansions_v2."""
    now = datetime.utcnow()

    row = {
        "id": uuid.uuid4(),
        "external_id": data["id"],
        "game": game,
        "name": data["name"],
        # Pokemon-only
        "series": data.get("series"),
        "code": data.get("code"),
        "printed_total": data.get("printed_total"),
        "is_online_only": data.get("is_online_only"),
        "symbol_url": data.get("symbol"),
        "translation": data.get("translation"),
        # One Piece-only
        "type": data.get("type"),
        # Shared
        "total": data.get("total"),
        "language": data.get("language", ""),
        "language_code": data.get("language_code", ""),
        "release_date": _parse_release_date(data.get("release_date")),
        "logo_url": data.get("logo"),
        "last_synced_at": now,
    }

    stmt = pg_insert(ExpansionV2.__table__).values(**row)
    # On conflict: update all fields except the PK and business key columns
    update_fields = {k: stmt.excluded[k] for k in row if k not in ("id", "external_id", "game")}
    stmt = stmt.on_conflict_do_update(
        constraint="uq_expansions_v2_game_external_id",
        set_=update_fields,
    )
    db.execute(stmt)


# ---------------------------------------------------------------------------
# Card parsing + upsert
# ---------------------------------------------------------------------------

def _upsert_card(db, game: str, expansion_id: uuid.UUID, data: dict) -> None:
    """Upsert a single card into cards_v2."""
    now = datetime.utcnow()

    row: Dict[str, Any] = {
        "id": uuid.uuid4(),
        "external_id": data["id"],
        "game": game,
        "expansion_id": expansion_id,
        "name": data["name"],
        "number": data.get("number"),
        "printed_number": data.get("printed_number"),
        "rarity": data.get("rarity"),
        "rarity_code": data.get("rarity_code"),
        "language": data.get("language", ""),
        "language_code": data.get("language_code", ""),
        "expansion_sort_order": data.get("expansion_sort_order"),
        "images": data.get("images"),
        "variants": data.get("variants"),
        # Set price timestamp when variants (which include prices) are present
        "price_data_uploaded_at": now if data.get("variants") else None,
        "last_synced_at": now,
        # Pokemon-only
        "supertype": data.get("supertype"),
        "subtypes": data.get("subtypes"),
        "types": data.get("types"),
        "hp": str(data["hp"]) if data.get("hp") is not None else None,
        "level": str(data["level"]) if data.get("level") is not None else None,
        "evolves_from": data.get("evolves_from"),
        "abilities": data.get("abilities"),
        "attacks": data.get("attacks"),
        "weaknesses": data.get("weaknesses"),
        "resistances": data.get("resistances"),
        "retreat_cost": data.get("retreat_cost"),
        "national_pokedex_numbers": data.get("national_pokedex_numbers"),
        "flavor_text": data.get("flavor_text"),
        "regulation_mark": data.get("regulation_mark"),
        "artist": data.get("artist"),
        # One Piece-only
        "cost": data.get("cost"),
        "power": data.get("power"),
        "attribute": data.get("attribute"),
        "card_type": data.get("type"),  # API field "type" → column "card_type" (avoids SQL keyword)
        "colors": data.get("colors"),
        "rules": data.get("rules"),
        "printings": data.get("printings"),
        "tags": data.get("tags"),
    }

    stmt = pg_insert(CardV2.__table__).values(**row)
    update_fields = {k: stmt.excluded[k] for k in row if k not in ("id", "external_id", "game")}
    stmt = stmt.on_conflict_do_update(
        constraint="uq_cards_v2_game_external_id",
        set_=update_fields,
    )
    db.execute(stmt)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@shared_task(name="scrydex.sync_expansions")
def sync_expansions(game: str) -> dict:
    """
    Fetch all expansions for a game from Scrydex and upsert into expansions_v2.
    Runs as part of full_sync; can also be triggered independently.
    """
    logger.info("scrydex.sync_expansions started — game=%s", game)

    if not settings.scrydex_api_key or not settings.scrydex_team_id:
        logger.error("SCRYDEX_API_KEY or SCRYDEX_TEAM_ID not configured — aborting")
        return {"game": game, "expansions_synced": 0, "error": "missing credentials"}

    url = f"{SCRYDEX_BASE}/{game}/v1/expansions"
    db = SessionLocal()
    synced = 0

    try:
        with _scrydex_client() as client:
            expansions = _fetch_all_pages(client, url)

        for exp_data in expansions:
            try:
                _upsert_expansion(db, game, exp_data)
                synced += 1
            except Exception as exc:
                logger.error(
                    "Failed to upsert expansion %s (game=%s): %s — skipping",
                    exp_data.get("id"), game, exc,
                )

        db.commit()

    except httpx.HTTPError as exc:
        logger.exception("HTTP error fetching expansions for game=%s: %s", game, exc)
        db.rollback()
        raise
    except Exception as exc:
        logger.exception("Unexpected error in sync_expansions (game=%s): %s", game, exc)
        db.rollback()
        raise
    finally:
        db.close()

    logger.info("scrydex.sync_expansions complete — game=%s, synced=%d", game, synced)
    return {"game": game, "expansions_synced": synced}


@shared_task(name="scrydex.sync_cards_for_expansion")
def sync_cards_for_expansion(expansion_external_id: str, game: str) -> dict:
    """
    Fetch all cards for a single expansion and upsert into cards_v2.
    Dispatched once per expansion by full_sync. Can also be triggered independently.
    """
    logger.info(
        "scrydex.sync_cards_for_expansion started — game=%s, expansion=%s",
        game, expansion_external_id,
    )

    if not settings.scrydex_api_key or not settings.scrydex_team_id:
        logger.error("SCRYDEX_API_KEY or SCRYDEX_TEAM_ID not configured — aborting")
        return {"game": game, "expansion": expansion_external_id, "cards_synced": 0, "error": "missing credentials"}

    db = SessionLocal()
    synced = 0

    try:
        # Resolve the UUID for this expansion
        expansion = (
            db.query(ExpansionV2)
            .filter_by(game=game, external_id=expansion_external_id)
            .first()
        )
        if expansion is None:
            logger.error(
                "Expansion %s (game=%s) not found in expansions_v2 — run sync_expansions first",
                expansion_external_id, game,
            )
            return {"game": game, "expansion": expansion_external_id, "cards_synced": 0, "error": "expansion not found"}

        expansion_id = expansion.id
        url = f"{SCRYDEX_BASE}/{game}/v1/expansions/{expansion_external_id}/cards"

        with _scrydex_client() as client:
            cards = _fetch_all_pages(client, url)

        for card_data in cards:
            try:
                _upsert_card(db, game, expansion_id, card_data)
                synced += 1
            except Exception as exc:
                logger.error(
                    "Failed to upsert card %s (game=%s, expansion=%s): %s — skipping",
                    card_data.get("id"), game, expansion_external_id, exc,
                )

        db.commit()

    except httpx.HTTPError as exc:
        logger.exception(
            "HTTP error fetching cards for expansion=%s (game=%s): %s",
            expansion_external_id, game, exc,
        )
        db.rollback()
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected error in sync_cards_for_expansion (expansion=%s, game=%s): %s",
            expansion_external_id, game, exc,
        )
        db.rollback()
        raise
    finally:
        db.close()

    logger.info(
        "scrydex.sync_cards_for_expansion complete — game=%s, expansion=%s, synced=%d",
        game, expansion_external_id, synced,
    )
    return {"game": game, "expansion": expansion_external_id, "cards_synced": synced}


@shared_task(name="scrydex.full_sync")
def full_sync() -> dict:
    """
    Orchestrator for the full Scrydex catalog sync.

    Steps:
      1. Run sync_expansions in-process for each game (must complete before card fan-out)
      2. Query all expansions from expansions_v2
      3. Dispatch one sync_cards_for_expansion task per expansion

    Scheduled weekly (Sunday 4am UTC) via celery beat.
    For the initial data load, trigger manually:
        celery -A celery_app call scrydex.full_sync
    """
    logger.info("scrydex.full_sync started")
    total_expansions = 0

    # Step 1: sync all expansions for each game in-process so they're available
    # before we fan out card tasks
    for game in SYNC_GAMES:
        try:
            result = sync_expansions(game)
            total_expansions += result.get("expansions_synced", 0)
        except Exception as exc:
            logger.error("sync_expansions failed for game=%s: %s — continuing", game, exc)

    # Step 2: load all expansions and fan out card sync tasks
    db = SessionLocal()
    try:
        expansions = db.query(ExpansionV2.external_id, ExpansionV2.game).all()
    finally:
        db.close()

    dispatched = 0
    for external_id, game in expansions:
        sync_cards_for_expansion.delay(external_id, game)
        dispatched += 1

    logger.info(
        "scrydex.full_sync dispatched — expansions_synced=%d, card_tasks_dispatched=%d",
        total_expansions, dispatched,
    )
    return {
        "expansions_synced": total_expansions,
        "card_sync_tasks_dispatched": dispatched,
    }


@shared_task(name="scrydex.refresh_prices")
def refresh_prices() -> dict:
    """
    Lightweight price refresh — re-fetches variants (price data) for all cards in cards_v2
    and updates variants + price_data_uploaded_at without touching structural fields.

    NOT scheduled — ready for Phase 2 activation.
    To schedule, add to celery_app.py beat_schedule:
        "scrydex-refresh-prices": {
            "task": "scrydex.refresh_prices",
            "schedule": crontab(hour="*/6", minute=0),
        }

    Phase 2 decision required before activating:
      - Per-card refresh: 1 credit/card — most targeted but expensive at scale
      - Per-expansion refresh: ~1 credit per 100 cards — recommended default
      - Hybrid: only refresh cards with active inventory — most cost-efficient
    See tasks/full_tcg_api_ingestion_plan.md for full credit cost analysis.
    """
    logger.info("scrydex.refresh_prices started")

    if not settings.scrydex_api_key or not settings.scrydex_team_id:
        logger.error("SCRYDEX_API_KEY or SCRYDEX_TEAM_ID not configured — aborting")
        return {"cards_refreshed": 0, "error": "missing credentials"}

    db = SessionLocal()
    refreshed = 0
    errors = 0

    try:
        cards = db.query(CardV2.id, CardV2.game, CardV2.external_id).all()

        with _scrydex_client() as client:
            for card_id, game, external_id in cards:
                url = f"{SCRYDEX_BASE}/{game}/v1/cards/{external_id}"
                try:
                    resp = client.get(url, params={"select": "variants"})
                    resp.raise_for_status()
                    body = resp.json()

                    # The single-card endpoint returns the card object directly (not paginated)
                    variants = body.get("variants") if isinstance(body, dict) else None

                    db.query(CardV2).filter(CardV2.id == card_id).update({
                        "variants": variants,
                        "price_data_uploaded_at": datetime.utcnow() if variants else None,
                    })
                    refreshed += 1

                    # Commit in batches of 500 to avoid long-running transactions
                    if refreshed % 500 == 0:
                        db.commit()
                        logger.info("scrydex.refresh_prices — %d cards refreshed so far", refreshed)

                except httpx.HTTPError as exc:
                    logger.error("Failed to refresh prices for card %s (game=%s): %s — skipping", external_id, game, exc)
                    errors += 1

        db.commit()

    except Exception as exc:
        logger.exception("Unexpected error in scrydex.refresh_prices: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()

    logger.info("scrydex.refresh_prices complete — refreshed=%d, errors=%d", refreshed, errors)
    return {"cards_refreshed": refreshed, "errors": errors}
