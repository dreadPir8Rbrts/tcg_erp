"""
Scan pipeline task — Claude Vision card identification.

Task:
  scans.process_scan_job — fetch image from S3, call Claude API,
      match result against cards table, update scan_job status.

Error handling: on any failure, set status='failed' and error_message.
Never retry automatically — vendor is prompted to scan again or search manually.
"""

import base64
import io
import json
import logging
from datetime import datetime
from typing import Optional

import boto3
import anthropic
import imagehash
import redis
from celery import shared_task
from PIL import Image
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, settings
from app.models.scans import ScanJob
from app.models.catalog import Card

logger = logging.getLogger(__name__)

# Tightened prompt — only the fields needed for catalog lookup.
# Deliberately overrides the CLAUDE.md locked prompt per user request (2026-03-27).
# card_name / set_name / condition_estimate removed; they are redundant or set manually by vendor.
CARD_IDENTIFICATION_PROMPT = """Identify this Pokémon card. Reply with JSON only, no other text:
{"set_code":"","local_id":"","confidence":0.0}
set_code is the TCGdex set ID (e.g. swsh3, base1). local_id is the card number within the set. confidence is 0.0-1.0. If unsure, return confidence 0.0."""

_CACHE_TTL = 3600  # seconds


def _redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _image_phash(image_bytes: bytes) -> str:
    """Return the perceptual hash hex string for image bytes."""
    img = Image.open(io.BytesIO(image_bytes))
    return str(imagehash.phash(img))


def _fetch_image_from_s3(s3_key: str) -> bytes:
    """Download image bytes from S3."""
    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    response = s3.get_object(Bucket=settings.aws_s3_bucket, Key=s3_key)
    return response["Body"].read()


def _call_claude(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """Send image to Claude and return parsed JSON result."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": CARD_IDENTIFICATION_PROMPT,
                    },
                ],
            }
        ],
    )

    raw_text = message.content[0].text.strip()
    return json.loads(raw_text)


def _match_card(db: Session, set_code: str, local_id: str) -> Optional[str]:
    """
    Find the card ID in the local catalog by set_code + local_id.
    Returns card.id (e.g. 'swsh3-136') or None if not found.
    """
    card = db.query(Card).filter(
        Card.set_id == set_code,
        Card.local_id == local_id,
    ).first()
    return card.id if card else None


@shared_task(name="scans.process_scan_job")
def process_scan_job(scan_job_id: str) -> dict:
    """
    Process a pending scan job:
    1. Fetch image from S3
    2. Call Claude Vision API
    3. Match result against cards table
    4. Update scan_job with result or failure
    """
    db = SessionLocal()
    try:
        job = db.get(ScanJob, scan_job_id)
        if job is None:
            logger.error("scan_job %s not found", scan_job_id)
            return {"status": "error", "detail": "job not found"}

        if job.status != "pending":
            logger.info("scan_job %s already %s — skipping", scan_job_id, job.status)
            return {"status": job.status}

        # Mark as processing
        job.status = "processing"
        db.commit()

        # Fetch image
        try:
            image_bytes = _fetch_image_from_s3(job.image_s3_key)
        except Exception as exc:
            logger.error("scan_job %s — S3 fetch failed: %s", scan_job_id, exc)
            job.status = "failed"
            job.error_message = f"S3 fetch failed: {exc}"
            job.completed_at = datetime.utcnow()
            db.commit()
            return {"status": "failed"}

        # Check Redis perceptual hash cache before calling Claude.
        # Cache key includes action so add_inventory / log_sale don't collide.
        cache_key = None
        cached_card_id = None
        try:
            r = _redis_client()
            phash = _image_phash(image_bytes)
            cache_key = f"scan_cache:{phash}:{job.action}"
            cached = r.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                cached_card_id = cached_data.get("card_id")
                logger.info("scan_job %s — cache hit for phash %s", scan_job_id, phash)
        except Exception as exc:
            logger.warning("scan_job %s — cache lookup failed (continuing): %s", scan_job_id, exc)

        if cached_card_id:
            job.result_card_id = cached_card_id
            job.result_confidence = 1.0
            job.status = "complete"
            job.completed_at = datetime.utcnow()
            db.commit()
            return {"status": "complete", "result_card_id": cached_card_id}

        # Call Claude
        try:
            result = _call_claude(image_bytes)
        except Exception as exc:
            logger.error("scan_job %s — Claude API failed: %s", scan_job_id, exc)
            job.status = "failed"
            job.error_message = f"Claude API failed: {exc}"
            job.completed_at = datetime.utcnow()
            db.commit()
            return {"status": "failed"}

        job.result_raw = result
        confidence = float(result.get("confidence", 0.0))
        job.result_confidence = confidence

        # Match card if confidence is sufficient
        if confidence >= 0.6:
            set_code = result.get("set_code", "")
            local_id = result.get("local_id", "")
            matched_id = _match_card(db, set_code, local_id)
            if matched_id:
                job.result_card_id = matched_id
                job.status = "complete"
                logger.info("scan_job %s — matched card %s (confidence %.2f)", scan_job_id, matched_id, confidence)
                # Populate cache for repeat scans of the same card
                if cache_key:
                    try:
                        r.setex(cache_key, _CACHE_TTL, json.dumps({"card_id": matched_id}))
                    except Exception as exc:
                        logger.warning("scan_job %s — cache write failed: %s", scan_job_id, exc)
            else:
                job.status = "failed"
                job.error_message = f"Card not found in catalog: set_code={set_code}, local_id={local_id}"
                logger.warning("scan_job %s — no catalog match for %s/%s", scan_job_id, set_code, local_id)
        else:
            job.status = "failed"
            job.error_message = f"Low confidence: {confidence:.2f} — vendor should search manually"
            logger.info("scan_job %s — low confidence %.2f", scan_job_id, confidence)

        job.completed_at = datetime.utcnow()
        db.commit()
        return {"status": job.status, "result_card_id": job.result_card_id}

    except Exception as exc:
        logger.exception("scan_job %s — unexpected error: %s", scan_job_id, exc)
        db.rollback()
        try:
            job = db.get(ScanJob, scan_job_id)
            if job:
                job.status = "failed"
                job.error_message = f"Unexpected error: {exc}"
                job.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()
