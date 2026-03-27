"""
Scan job endpoints — S3 presigned upload URL + job status polling + WebSocket push.

Routes:
  POST /scans              — create scan job, return presigned S3 PUT URL
  GET  /scans/{id}         — poll scan job status and result
  WS   /scans/{id}/ws      — WebSocket: push completion event to vendor browser
"""

import json
import uuid
import asyncio
import logging
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import celery_app as _celery_module

from app.db.session import get_db, settings
from app.dependencies import get_current_profile
from app.models.inventory import VendorProfile
from app.models.profiles import Profile
from app.models.scans import ScanJob

logger = logging.getLogger(__name__)
router = APIRouter(tags=["scans"])

PRESIGNED_URL_EXPIRY = 300  # seconds


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ScanJobCreate(BaseModel):
    action: str  # add_inventory | log_sale | log_trade_out | log_trade_in
    content_type: str = "image/jpeg"  # MIME type of the image to be uploaded


class ScanJobResponse(BaseModel):
    id: str
    status: str
    action: str
    upload_url: Optional[str] = None  # only on creation
    result_card_id: Optional[str] = None
    result_confidence: Optional[float] = None
    result_raw: Optional[dict] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_ACTIONS = {"add_inventory", "log_sale", "log_trade_out", "log_trade_in"}


def _get_vendor_or_404(profile: Profile, db: Session) -> VendorProfile:
    vendor = db.query(VendorProfile).filter(VendorProfile.profile_id == profile.id).first()
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor profile not found")
    return vendor


def _generate_presigned_put_url(s3_key: str, content_type: str) -> str:
    """Generate a presigned S3 PUT URL for direct browser upload."""
    if not all([settings.aws_access_key_id, settings.aws_secret_access_key, settings.aws_s3_bucket]):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="S3 not configured",
        )
    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=Config(signature_version="s3v4"),
    )
    try:
        url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.aws_s3_bucket,
                "Key": s3_key,
                "ContentType": content_type,
            },
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )
        return url
    except ClientError as exc:
        logger.error("Failed to generate presigned URL: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate upload URL")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/scans", response_model=ScanJobResponse, status_code=status.HTTP_201_CREATED)
def create_scan_job(
    body: ScanJobCreate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> dict:
    """
    Create a scan job and return a presigned S3 PUT URL.
    Client uploads the image directly to S3, then calls POST /scans/{id}/trigger.
    """
    if body.action not in VALID_ACTIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid action '{body.action}'")

    vendor = _get_vendor_or_404(profile, db)
    job_id = str(uuid.uuid4())
    s3_key = f"scans/{vendor.id}/{job_id}.jpg"

    upload_url = _generate_presigned_put_url(s3_key, body.content_type)

    job = ScanJob(
        id=job_id,
        vendor_id=vendor.id,
        image_s3_key=s3_key,
        status="pending",
        action=body.action,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    return {
        "id": job.id,
        "status": job.status,
        "action": job.action,
        "upload_url": upload_url,
    }


@router.post("/scans/{scan_job_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
def trigger_scan_job(
    scan_job_id: str,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> dict:
    """
    Called by the client after the image has been uploaded to S3.
    Dispatches the Celery scan task.
    """
    vendor = _get_vendor_or_404(profile, db)
    job = db.get(ScanJob, scan_job_id)

    if job is None or job.vendor_id != vendor.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan job not found")
    if job.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job already {job.status}")

    _celery_module.app.send_task("scans.process_scan_job", args=[scan_job_id])
    return {"status": "queued", "scan_job_id": scan_job_id}


@router.get("/scans/{scan_job_id}", response_model=ScanJobResponse)
def get_scan_job(
    scan_job_id: str,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> ScanJob:
    """Poll scan job status and result."""
    vendor = _get_vendor_or_404(profile, db)
    job = db.get(ScanJob, scan_job_id)

    if job is None or job.vendor_id != vendor.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan job not found")

    return job


@router.websocket("/scans/{scan_job_id}/ws")
async def scan_job_websocket(
    websocket: WebSocket,
    scan_job_id: str,
    db: Session = Depends(get_db),
) -> None:
    """
    WebSocket endpoint — polls the scan job every second and pushes a completion
    event when status changes to 'complete' or 'failed'. Client connects after
    triggering the scan and waits for the push instead of polling REST.
    """
    await websocket.accept()
    try:
        while True:
            db.expire_all()
            job = db.get(ScanJob, scan_job_id)
            if job is None:
                await websocket.send_text(json.dumps({"error": "job not found"}))
                break

            if job.status in ("complete", "failed"):
                await websocket.send_text(json.dumps({
                    "status": job.status,
                    "result_card_id": job.result_card_id,
                    "result_confidence": float(job.result_confidence) if job.result_confidence else None,
                    "error_message": job.error_message,
                }))
                break

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for scan_job %s", scan_job_id)
