"""
SQLAlchemy model for public.profiles.

Bridge table between auth.users (Supabase-managed) and application data.
vendor_profiles and customer_profiles FK to this table.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = {"schema": "public"}

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
