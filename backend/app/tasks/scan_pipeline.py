"""
Scan pipeline task — Claude Vision card identification.

Task:
  scans.process_scan_job — fetch image from S3, call Claude API,
      match result against cards table, update scan_job status.

Error handling: on any failure, set status='failed' and error_message.
Never retry automatically — vendor is prompted to scan again or search manually.
"""

import base64
import logging
import uuid
from datetime import datetime
from typing import Optional

import boto3
import anthropic
from celery import shared_task
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, settings
from app.models.scans import ScanJob
from app.models.catalog import Card

logger = logging.getLogger(__name__)

# Locked prompt — do not deviate from this (per spec)
CARD_IDENTIFICATION_PROMPT = """Identify this Pokémon card. Return only valid JSON with no other text:
{
  "card_name": "string",
  "set_name": "string",
  "set_code": "string (e.g. swsh3, base1)",
  "local_id": "string (card number within set, e.g. 136, 4)",
  "condition_estimate": "nm|lp|mp|hp|dmg",
  "confidence": 0.0-1.0
}
If you cannot identify the card with confidence >= 0.6, return {"confidence": 0.0}."""


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
        max_tokens=256,
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

    import json
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
