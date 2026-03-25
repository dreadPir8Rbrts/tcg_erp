# CardOps — Task Board

## Active phase: Phase 0 — Catalog foundation

---

## In progress
- Phase 0 complete — beginning Phase 1 planning

---

## Phase 0 checklist

### Supabase + environment setup
- [x] Create Supabase project (free tier)
- [x] Copy `DATABASE_URL` (transaction pooler, port 6543) into `backend/.env`
- [x] Copy `MIGRATION_DATABASE_URL` (direct connection, port 5432) into `backend/.env`
- [ ] Copy `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` into `backend/.env` _(not needed until Phase 1 auth)_
- [x] Add `.env` to `.gitignore`; `backend/.env.example` created with placeholder keys
- [x] Confirm Supabase project reachable — `DATABASE_URL` connection verified
- [x] Confirm `MIGRATION_DATABASE_URL` connection (direct URL — verified)

### Project scaffolding
- [x] Initialize `backend/` with FastAPI project structure
- [x] `requirements.txt` with core dependencies (using pip + venv, not pyproject.toml)
- [x] Python venv at `backend/.venv` — activate before all Python commands
- [x] `alembic.ini` configured at `backend/` root, pointing to `app/db/` as script location
- [ ] Initialize `frontend/` with `create-next-app` (TypeScript, Tailwind, App Router) _(Phase 1)_

### Alembic migrations
- [x] `20260318_0001_catalog_tables.py` — `series`, `sets`, `cards`, `price_snapshots` (all catalog in one migration)
- [x] `20260318_0002_profiles.py` — `public.profiles` referencing `auth.users` via raw SQL
- [x] Run `alembic upgrade head` against Supabase — both migrations applied cleanly
- [x] Verify all tables created correctly in Supabase dashboard

### Catalog seed
- [x] `tcgdex-sdk==2.2.1` in requirements.txt (2.3.0 does not exist)
- [x] Write `backend/seed_catalog.py` — series → sets → cards → price_snapshots ingestion
- [x] Run `alembic upgrade head` first (tables must exist before seeding)
- [x] Full run: `python seed_catalog.py` — 22,754 cards seeded (English)
- [x] Validate: 21 series, 200 sets, 22,754 cards
- [x] Spot-check: `swsh3-136` Furret — attacks JSONB, variants, image_url all correct
- [x] Spot-check: `base1-4` Charizard — hp 120, Stage2, holo+firstEdition variants correct

### Celery setup
- [x] Write `backend/celery_app.py` with beat schedule
- [x] Implement `backend/app/tasks/catalog_sync.py`:
  - [x] `catalog.sync_new_sets` (runs 2am nightly)
  - [x] `catalog.delta_sync_cards` (runs 3am nightly)
- [x] Implement `backend/app/tasks/price_sync.py`:
  - [x] `prices.refresh_active_inventory` (runs every 6h)
- [x] Test tasks run successfully in local Celery worker
  - [x] Worker starts and connects to Redis
  - [x] All 3 tasks appear in `[tasks]` list on startup
  - [x] `catalog.sync_new_sets` — ran successfully, returned `{new_sets: 0, new_cards: 0}`
  - [x] `catalog.delta_sync_cards` — ran cleanly, found `exu` set with updates, 404 handling worked
  - [x] `prices.refresh_active_inventory` — returned `{cards_refreshed: 0, rows_written: 0}` (inventory_items is Phase 1 — graceful early return)

### FastAPI catalog endpoints
- [x] `GET /api/cards/{id}` — single card by TCGdex ID (note: no `/v1/` prefix yet — add when Phase 1 starts)
- [x] `GET /api/cards?q=` — search by name (ILIKE, GIN index)
- [x] `GET /api/sets` — list all sets, optional `?serie_id=` filter
- [x] `GET /api/sets/{id}` — single set with card count
- [x] Verify endpoints return correct data via HTTP request — all 4 confirmed

### Phase 0 complete criteria
- [x] All migrations applied cleanly (`alembic upgrade head` with no errors)
- [x] ~18,000+ cards in `cards` table — 22,754 seeded
- [x] All Celery beat tasks registered and tested
- [x] Catalog endpoints return correct responses against real seeded data
- [x] No hardcoded credentials anywhere in code — verified, only safe localhost default in Settings

---

## Upcoming — Phase 1 (not started)
- Supabase Auth setup (email provider + SUPABASE_URL / SUPABASE_SERVICE_KEY in .env)
- Auth trigger: auto-insert `public.profiles` on new `auth.users` (run via Supabase SQL editor — see `backend/app/db/CLAUDE.md`)
- Add `/v1` prefix to all API routes in `main.py`
- Vendor profile creation + TCG interest tags
- Manual inventory add
- Inventory list view

---

## Upcoming — Phase 2 (not started)
- S3 presigned URL upload endpoint
- Celery task: Claude Vision card identification
- Scan confirmation UI
- Scan → add inventory / log sale

---

## Completed tasks
- Backend project structure scaffolded
- SQLAlchemy models: `Serie`, `Set`, `Card`, `PriceSnapshot` in `app/models/catalog.py`
- Alembic environment configured (`app/db/env.py`, `app/db/script.py.mako`)
- Migration 0001: all catalog tables with GIN index on `cards.name`, check constraints, UNIQUE on price_snapshots
- Migration 0002: `public.profiles` with cross-schema FK to `auth.users` via raw SQL
- `seed_catalog.py` written with full ingestion logic, pricing upserts, CLI flags (`--serie-id`, `--set-id`)
- Catalog API endpoints scaffolded in `app/api/catalog.py`
- Supabase connection verified (both pooler and direct URLs)
- Python venv configured, all dependencies installed

---

## Results / review
_Added after phase completion_
