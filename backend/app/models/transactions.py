"""
SQLAlchemy models for transactions.

Tables: transactions, transaction_items
type: 'sale' | 'purchase' | 'trade'
direction: 'in' (item acquired) | 'out' (item sold/traded away)
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = {"schema": "public"}

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    vendor_profile_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.vendor_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    collector_profile_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    show_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.card_shows.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    total_cash: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    items: Mapped[list] = relationship("TransactionItem", back_populates="transaction", lazy="select")


class TransactionItem(Base):
    __tablename__ = "transaction_items"
    __table_args__ = {"schema": "public"}

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    inventory_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("public.vendor_inventory.id", ondelete="SET NULL"),
        nullable=True,
    )
    card_id: Mapped[str] = mapped_column(String(50), nullable=False)  # FK enforced at DB level
    condition: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)

    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="items")
