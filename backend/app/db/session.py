from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    # Direct (non-pooler) URL used by Alembic for DDL migrations.
    # Supabase's PgBouncer transaction mode cannot execute DDL.
    # Falls back to database_url if not set (fine for local Postgres).
    migration_database_url: Optional[str] = None
    redis_url: str = "redis://localhost:6379/0"
    supabase_url: Optional[str] = None
    supabase_service_key: Optional[str] = None  # for server-side admin operations (Phase 2+)

    model_config = {"env_file": ".env"}


settings = Settings()

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
