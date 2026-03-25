# Backend — Claude Code Instructions

> Extends root `CLAUDE.md`. Rules here apply to everything inside `backend/`.

## Directory structure (actual — as built)
```
backend/
  app/
    api/            # FastAPI routers, one file per domain
    models/         # SQLAlchemy models, one file per domain
    schemas/        # Pydantic v2 request/response models — create in Phase 1, not before
    services/       # Business logic layer — create in Phase 1, not before; no DB calls in routers
    tasks/          # Celery tasks
    db/
      env.py        # Alembic environment
      session.py    # Engine, SessionLocal, Base, get_db, Settings
      script.py.mako
      versions/     # Migration files (NOT migrations/versions — just versions/)
    main.py         # FastAPI app factory + router registration
  scripts/          # Utility scripts (backfill, admin ops)
  seed_catalog.py   # One-time catalog seed script
  celery_app.py     # Celery app + beat schedule (to be created)
  requirements.txt  # Dependencies (using pip + venv, not pyproject.toml)
  alembic.ini       # Alembic config — script_location = app/db
  .env              # Never commit — gitignored
  .env.example      # Committed placeholder
  .venv/            # Virtual environment — gitignored, activate before all Python commands
```

## Python version
This project runs on **Python 3.9**. Syntax rules:
- Use `Optional[X]` from `typing` — never `X | None` (requires 3.10+)
- Use `Union[X, Y]` from `typing` — never `X | Y` in type hints
- Use `List[X]`, `Dict[K, V]` from `typing` for generics in annotations

## Dependency management
- Use `pip` with `requirements.txt` and a venv at `backend/.venv`
- Activate venv before any Python command: `source backend/.venv/bin/activate`
- Do not use `uvicorn[standard]` — the extras require Rust (watchfiles/maturin); use plain `uvicorn`
- Pin exact versions for stability: `fastapi==0.115.6`
- **Before pinning any version, verify it exists on PyPI.** Use `pip index versions <package>` or check pypi.org. Do not guess version numbers.
- Core deps: `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `psycopg2-binary`, `pydantic-settings`, `tcgdex-sdk`, `celery[redis]`, `redis`, `httpx`
- Future deps (add when needed): `boto3`, `anthropic`

## FastAPI conventions
- One router per domain: `api/catalog.py`, `api/inventory.py`, `api/shows.py`, etc.
- All routers registered in `app/main.py`
- API prefix: currently `/api` — add `/v1` prefix when Phase 1 begins
- Dependency injection for DB sessions: `Depends(get_db)` (defined in `db/session.py`)
- Auth dependency (Phase 1+): `Depends(get_current_user)` — returns `public.profiles` row
- Response models always explicit — never return raw SQLAlchemy objects
- Route handlers are **sync** for now (psycopg2 is sync); switch to async when asyncpg is added

## SQLAlchemy conventions
- `Base` defined in `app/db/session.py` (DeclarativeBase)
- One model file per domain: `models/catalog.py`, `models/inventory.py`, etc.
- All timestamps as `DateTime` — use `datetime.utcnow` for defaults; timezone-aware in Phase 1+
- Soft delete pattern: `deleted_at = Column(DateTime, nullable=True)`
- Always filter soft-deleted rows: `.filter(Model.deleted_at.is_(None))`
- Use `session.merge()` for catalog upserts — never `session.add()` on TCGdex-sourced records

## Alembic conventions
- Migration files in `backend/app/db/versions/`
- Naming format: `YYYYMMDD_NNNN_descriptive_name.py` (e.g. `20260318_0001_catalog_tables.py`)
- Always include complete `downgrade()` — never `pass` or `raise NotImplementedError`
- Use `schema="public"` explicitly on all `op.create_table()` calls
- Run migrations with `MIGRATION_DATABASE_URL` (direct connection) — not the pooler URL
- Run `alembic check` before marking any migration task complete

## Celery conventions
- Task names follow `domain.action` pattern: `catalog.sync_new_sets`, `prices.refresh_active_inventory`
- Beat schedule defined in `celery_app.py` using `crontab`
- Tasks must be idempotent — safe to retry on failure
- See `backend/app/tasks/CLAUDE.md` for full task conventions

## Environment variables
```
# Database (both required — see backend/app/db/CLAUDE.md for why)
DATABASE_URL=postgresql://...@pooler.supabase.com:6543/postgres        # app connections
MIGRATION_DATABASE_URL=postgresql://...@db.supabase.co:5432/postgres   # alembic only

# Redis
REDIS_URL=redis://localhost:6379/0

# Supabase (Phase 1+)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=...    # Server-side only, never expose to frontend

# AWS (Phase 2+)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=...
AWS_REGION=...

# Anthropic (Phase 2+)
ANTHROPIC_API_KEY=...

# App
ENVIRONMENT=development|staging|production
```

All env vars must have a corresponding field in `Settings` (in `app/db/session.py`). pydantic-settings raises `extra_forbidden` on undeclared vars.

## Catalog ingestion rules
- `seed_catalog.py` must be idempotent — safe to re-run at any time
- Use `session.merge()` for series/set/card upserts
- Use `INSERT ... ON CONFLICT DO UPDATE` for `price_snapshots`
- Add 100ms sleep between card fetches during full seed runs
- TCGdex is authoritative — never mutate synced catalog fields directly
- Price data goes only to `price_snapshots` — never to `cards` table

## Testing
- Tests in `backend/tests/`, mirroring `app/` structure
- Use `pytest` + `pytest-asyncio`
- Separate test database (Supabase branch or local PostgreSQL)
- Required coverage: all service layer functions, all Celery tasks
- Never mock the database in service tests — use real DB with test fixtures
