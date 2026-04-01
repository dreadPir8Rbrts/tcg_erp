"""
SQLAlchemy models for card show management.

Tables: card_shows, vendor_show_registrations, show_inventory_tags
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy import TIMESTAMP, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class CardShow(Base):
    __tablename__ = "card_shows"
    __table_args__ = {"schema": "public"}

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    organizer_profile_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    registrations: Mapped[list] = relationship("VendorShowRegistration", back_populates="show", lazy="select")


class VendorShowRegistration(Base):
    __tablename__ = "vendor_show_registrations"
    __table_args__ = (
        UniqueConstraint("vendor_profile_id", "show_id", name="uq_vendor_show_registrations"),
        {"schema": "public"},
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    vendor_profile_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.vendor_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    show_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.card_shows.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    show: Mapped["CardShow"] = relationship("CardShow", back_populates="registrations")


class ShowInventoryTag(Base):
    __tablename__ = "show_inventory_tags"
    __table_args__ = (
        UniqueConstraint("inventory_id", "show_id", name="uq_show_inventory_tags"),
        {"schema": "public"},
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    inventory_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.vendor_inventory.id", ondelete="CASCADE"),
        nullable=False,
    )
    show_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.card_shows.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
