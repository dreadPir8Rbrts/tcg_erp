# Celery Tasks — Claude Code Instructions

> Extends `backend/CLAUDE.md`. Rules here apply to everything inside `backend/app/tasks/`.

## Task files
```
backend/app/tasks/
  catalog_sync.py     # TCGdex catalog sync jobs
  price_sync.py       # Price snapshot refresh jobs
  scan_pipeline.py    # Card image scan + Claude Vision jobs (Phase 2)
```

## Task naming convention
All tasks use `domain.action` pattern registered with `@shared_task(name="...")`:
```python
@shared_task(name="catalog.sync_new_sets")
@shared_task(name="catalog.delta_sync_cards")
@shared_task(name="prices.refresh_active_inventory")
@shared_task(name="scans.process_scan_job")   # Phase 2
```

## Idempotency requirement
Every task must be safe to run multiple times with the same input.
- Catalog sync: uses `session.merge()` — always safe
- Price sync: upserts on `UNIQUE(card_id, source, variant)` — always safe
- Scan jobs: check `scan_job.status` before processing — skip if already `complete`

## Beat schedule (defined in `celery_app.py`)
```python
beat_schedule = {
    "catalog-sync-new-sets": {
        "task": "catalog.sync_new_sets",
        "schedule": crontab(hour=2, minute=0),      # 2am daily
    },
    "catalog-delta-sync": {
        "task": "catalog.delta_sync_cards",
        "schedule": crontab(hour=3, minute=0),      # 3am daily
    },
    "prices-refresh": {
        "task": "prices.refresh_active_inventory",
        "schedule": crontab(minute=0, hour="*/6"),  # every 6 hours
    },
}
```

## Error handling
- All tasks must catch exceptions and log with context — never silent failures
- Failed scan jobs: set `status="failed"`, set `error_message`, do not retry automatically
- Failed price fetches: log and skip that card — do not block the rest of the batch
- Failed catalog sync: log the set ID and continue — do not abort the full run

## Scan pipeline (Phase 2 — do not build yet)
When Phase 2 begins, `scan_pipeline.py` will:
1. Receive `scan_job_id`
2. Set `status = "processing"`
3. Fetch image from S3 using `image_s3_key`
4. Call Claude API (`claude-sonnet-4-20250514`) with image as base64
5. Parse response → match `set_code + local_id` against `cards` table
6. Set `result_card_id`, `result_confidence`, `result_raw`
7. Set `status = "complete"` or `status = "failed"`
8. Push WebSocket event to vendor's browser session

Claude prompt for card identification (locked — do not deviate from this):
```
Identify this Pokémon card. Return only valid JSON with no other text:
{
  "card_name": "string",
  "set_name": "string",
  "set_code": "string (e.g. swsh3, base1)",
  "local_id": "string (card number within set, e.g. 136, 4)",
  "condition_estimate": "nm|lp|mp|hp|dmg",
  "confidence": 0.0-1.0
}
If you cannot identify the card with confidence >= 0.6, return {"confidence": 0.0}.
```
