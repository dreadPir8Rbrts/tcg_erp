"""
SQLAlchemy models for vendor inventory.

Tables: vendor_profiles, inventory_items
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSON

from app.db.session import Base


class VendorProfile(Base):
    __tablename__ = "vendor_profiles"
    __table_args__ = {"schema": "public"}

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("public.profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    buying_rate: Mapped[Optional[float]] = mapped_column(Numeric(4, 2), nullable=True)
    trade_rate: Mapped[Optional[float]] = mapped_column(Numeric(4, 2), nullable=True)
    tcg_interests: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    notification_prefs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    background_img: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar_img: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_accounting_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    inventory_items: Mapped[list] = relationship("InventoryItem", back_populates="vendor", lazy="select")


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = {"schema": "public"}

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    vendor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("public.vendor_profiles.id", ondelete="CASCADE"), nullable=False)
    card_id: Mapped[str] = mapped_column(String, nullable=False)  # FK enforced at DB level
    condition: Mapped[str] = mapped_column(String, nullable=False)
    grading_service: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cert_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
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

    vendor: Mapped["VendorProfile"] = relationship("VendorProfile", back_populates="inventory_items")
