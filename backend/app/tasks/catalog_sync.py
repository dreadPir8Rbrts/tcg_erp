"""
Catalog sync tasks — keep the local series/sets/cards tables in sync with TCGdex.

Tasks:
  catalog.sync_new_sets    — detect and seed sets that exist on TCGdex but not locally (2am nightly)
  catalog.delta_sync_cards — re-sync cards updated in the last 48h on TCGdex (3am nightly)

Both tasks are idempotent: session.merge() means safe to re-run at any time.
Error handling: log and continue — a single bad set/card never aborts the full run.
"""

import logging
import time
import urllib.error
from datetime import datetime, timedelta
from typing import Optional

from celery import shared_task
from tcgdexsdk import TCGdex

from app.db.session import SessionLocal
from app.models.catalog import Card, Serie, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers (shared with seed_catalog.py logic)
# ---------------------------------------------------------------------------

def _upsert_serie(db, sdk_serie) -> None:
    """Merge a TCGdex serie object into the local series table."""
    row = Serie(
        id=sdk_serie.id,
        name=sdk_serie.name,
        logo_url=getattr(sdk_serie, "logo", None),
        tcg="pokemon",
        last_synced_at=datetime.utcnow(),
    )
    db.merge(row)


def _upsert_set(db, sdk_set, serie_id: str) -> None:
    """Merge a TCGdex set object into the local sets table."""
    release_date = None
    if getattr(sdk_set, "releaseDate", None):
        try:
            release_date = datetime.strptime(sdk_set.releaseDate, "%Y-%m-%d").date()
        except ValueError:
            pass

    card_count = getattr(sdk_set, "cardCount", None)
    row = Set(
        id=sdk_set.id,
        serie_id=serie_id,
        name=sdk_set.name,
        release_date=release_date,
        card_count_official=getattr(card_count, "official", None) if card_count else None,
        card_count_total=getattr(card_count, "total", None) if card_count else None,
        logo_url=getattr(sdk_set, "logo", None),
        symbol_url=getattr(sdk_set, "symbol", None),
        last_synced_at=datetime.utcnow(),
    )
    db.merge(row)


def _upsert_card(db, sdk_card) -> None:
    """Merge a full TCGdex card object into the local cards table."""
    legal = getattr(sdk_card, "legal", None)
    variants_raw = getattr(sdk_card, "variants", None)
    variants = {}
    if variants_raw:
        variants = {
            "normal": getattr(variants_raw, "normal", False) or False,
            "holo": getattr(variants_raw, "holo", False) or False,
            "reverse": getattr(variants_raw, "reverse", False) or False,
            "firstEdition": getattr(variants_raw, "firstEdition", False) or False,
        }

    updated_raw = getattr(sdk_card, "updated", None)
    tcgdex_updated_at: Optional[datetime] = None
    if updated_raw:
        try:
            tcgdex_updated_at = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
        except ValueError:
            pass

    def _to_list(obj):
        if obj is None:
            return None
        if isinstance(obj, list):
            return [
                item.__dict__ if hasattr(item, "__dict__") else item
                for item in obj
            ]
        return obj

    row = Card(
        id=sdk_card.id,
        set_id=sdk_card.set.id,
        local_id=str(sdk_card.localId),
        name=sdk_card.name,
        category=sdk_card.category,
        rarity=getattr(sdk_card, "rarity", None),
        illustrator=getattr(sdk_card, "illustrator", None),
        image_url=getattr(sdk_card, "image", None),
        hp=getattr(sdk_card, "hp", None),
        types=getattr(sdk_card, "types", None),
        dex_ids=getattr(sdk_card, "dexId", None),
        stage=getattr(sdk_card, "stage", None),
        evolve_from=getattr(sdk_card, "evolveFrom", None),
        description=getattr(sdk_card, "description", None),
        attacks=_to_list(getattr(sdk_card, "attacks", None)),
        abilities=_to_list(getattr(sdk_card, "abilities", None)),
        weaknesses=_to_list(getattr(sdk_card, "weaknesses", None)),
        resistances=_to_list(getattr(sdk_card, "resistances", None)),
        retreat=getattr(sdk_card, "retreat", None),
        suffix=getattr(sdk_card, "suffix", None),
        level=str(getattr(sdk_card, "level", None)) if getattr(sdk_card, "level", None) is not None else None,
        regulation_mark=getattr(sdk_card, "regulationMark", None),
        effect=getattr(sdk_card, "effect", None),
        trainer_type=getattr(sdk_card, "trainerType", None),
        energy_type=getattr(sdk_card, "energyType", None),
        variants=variants,
        legal_standard=getattr(legal, "standard", None) if legal else None,
        legal_expanded=getattr(legal, "expanded", None) if legal else None,
        tcgdex_updated_at=tcgdex_updated_at,
        last_synced_at=datetime.utcnow(),
    )
    db.merge(row)


def _seed_set(db, sdk, set_id: str, serie_id: str) -> int:
    """
    Fetch all cards for a set and upsert them. Returns count of cards processed.
    Logs and skips cards that return 404 or other errors — never aborts the run.
    """
    try:
        full_set = sdk.set.getSync(set_id)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        logger.error("Failed to fetch set %s: %s — skipping", set_id, exc)
        return 0

    if full_set is None:
        logger.warning("Set %s returned None from TCGdex — skipping", set_id)
        return 0

    _upsert_set(db, full_set, serie_id)

    cards = getattr(full_set, "cards", None) or []
    count = 0
    for card_brief in cards:
        try:
            full_card = sdk.card.getSync(card_brief.id)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            logger.warning("Failed to fetch card %s: %s — skipping", card_brief.id, exc)
            time.sleep(0.1)
            continue

        if full_card is None:
            logger.warning("Card %s returned None — skipping", card_brief.id)
            continue

        try:
            _upsert_card(db, full_card)
            count += 1
        except Exception as exc:
            logger.error("Failed to upsert card %s: %s — skipping", card_brief.id, exc)

        time.sleep(0.1)

    db.commit()
    logger.info("Set %s: upserted %d cards", set_id, count)
    return count


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@shared_task(name="catalog.sync_new_sets")
def sync_new_sets() -> dict:
    """
    Compare TCGdex remote set list against local sets table.
    Seed any sets that exist remotely but not locally.
    Runs nightly at 2am UTC.
    """
    logger.info("catalog.sync_new_sets started")
    sdk = TCGdex("en")
    db = SessionLocal()
    new_sets = 0
    new_cards = 0

    try:
        remote_series = sdk.serie.listSync()
        if not remote_series:
            logger.warning("TCGdex returned empty series list — aborting sync")
            return {"new_sets": 0, "new_cards": 0}

        local_set_ids = {row[0] for row in db.query(Set.id).all()}

        for serie_brief in remote_series:
            try:
                full_serie = sdk.serie.getSync(serie_brief.id)
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                logger.error("Failed to fetch serie %s: %s — skipping", serie_brief.id, exc)
                continue

            if full_serie is None:
                continue

            _upsert_serie(db, full_serie)
            db.commit()

            for set_brief in (getattr(full_serie, "sets", None) or []):
                if set_brief.id in local_set_ids:
                    continue
                logger.info("New set detected: %s — seeding", set_brief.id)
                count = _seed_set(db, sdk, set_brief.id, full_serie.id)
                new_sets += 1
                new_cards += count

    except Exception as exc:
        logger.exception("catalog.sync_new_sets failed with unexpected error: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()

    logger.info("catalog.sync_new_sets complete — %d new sets, %d new cards", new_sets, new_cards)
    return {"new_sets": new_sets, "new_cards": new_cards}


@shared_task(name="catalog.delta_sync_cards")
def delta_sync_cards() -> dict:
    """
    Re-sync cards in sets where at least one card was updated in the last 48h on TCGdex.
    Uses the `updated` field on card objects to detect stale local rows.
    Runs nightly at 3am UTC.
    """
    logger.info("catalog.delta_sync_cards started")
    sdk = TCGdex("en")
    db = SessionLocal()
    sets_synced = 0
    cards_synced = 0
    cutoff = datetime.utcnow() - timedelta(hours=48)

    try:
        # Fetch all set IDs from local DB to iterate
        local_sets = db.query(Set.id, Set.serie_id).all()

        for set_id, serie_id in local_sets:
            try:
                full_set = sdk.set.getSync(set_id)
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                logger.warning("Failed to fetch set %s during delta sync: %s — skipping", set_id, exc)
                continue

            if full_set is None:
                continue

            cards = getattr(full_set, "cards", None) or []

            # Check if any card in this set has been updated since cutoff
            set_needs_sync = False
            for card_brief in cards:
                local_card = db.query(Card).filter(Card.id == card_brief.id).first()
                if local_card is None:
                    set_needs_sync = True
                    break
                if local_card.tcgdex_updated_at and local_card.tcgdex_updated_at > cutoff:
                    set_needs_sync = True
                    break

            if not set_needs_sync:
                continue

            logger.info("Delta sync: set %s has updates — re-seeding", set_id)
            count = _seed_set(db, sdk, set_id, serie_id)
            sets_synced += 1
            cards_synced += count

    except Exception as exc:
        logger.exception("catalog.delta_sync_cards failed with unexpected error: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()

    logger.info("catalog.delta_sync_cards complete — %d sets, %d cards", sets_synced, cards_synced)
    return {"sets_synced": sets_synced, "cards_synced": cards_synced}
