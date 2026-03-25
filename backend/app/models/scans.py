"""
SQLAlchemy model for scan_jobs.

Each scan job represents one vendor card photo upload → Claude Vision identification.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSON

from app.db.session import Base


class ScanJob(Base):
    __tablename__ = "scan_jobs"
    __table_args__ = {"schema": "public"}

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    vendor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("public.vendor_profiles.id", ondelete="CASCADE"), nullable=False)
    image_s3_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    action: Mapped[str] = mapped_column(String, nullable=False)
    result_card_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    result_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3), nullable=True)
    result_raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
