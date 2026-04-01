"""
SQLAlchemy models for vendor inventory.

Tables: vendor_profiles, vendor_inventory
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class VendorProfile(Base):
    __tablename__ = "vendor_profiles"
    __table_args__ = {"schema": "public"}

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.profiles.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    buying_rate: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    trade_rate: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    is_accounting_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)



class VendorInventory(Base):
    __tablename__ = "vendor_inventory"
    __table_args__ = {"schema": "public"}

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    card_id: Mapped[str] = mapped_column(String, nullable=False)  # FK enforced at DB level
    condition_type: Mapped[str] = mapped_column(String(10), nullable=False)
    condition_ungraded: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    grading_company: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    grade: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    grading_company_other: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cost_basis: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    asking_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    is_for_sale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_for_trade: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
