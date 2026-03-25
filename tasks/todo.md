# CardOps — Task Board

## Active phase: Phase 2 — Scan pipeline

---

## In progress
- Phase 2 backend complete (migration, Celery task, scan endpoints, WebSocket)
- Next: `create-next-app` frontend scaffold + scan confirmation UI

---

## Phase 0 checklist ✅

### Supabase + environment setup
- [x] Create Supabase project (free tier)
- [x] Copy `DATABASE_URL` (transaction pooler, port 6543) into `backend/.env`
- [x] Copy `MIGRATION_DATABASE_URL` (direct connection, port 5432) into `backend/.env`
- [x] Copy `SUPABASE_URL` into `backend/.env`
- [x] Add `.env` to `.gitignore`; `backend/.env.example` created with placeholder keys
- [x] Confirm Supabase project reachable — `DATABASE_URL` connection verified
- [x] Confirm `MIGRATION_DATABASE_URL` connection (direct URL — verified)

### Project scaffolding
- [x] Initialize `backend/` with FastAPI project structure
- [x] `requirements.txt` with core dependencies (using pip + venv, not pyproject.toml)
- [x] Python venv at `backend/.venv` — activate before all Python commands
- [x] `alembic.ini` configured at `backend/` root, pointing to `app/db/` as script location

### Alembic migrations
- [x] `20260318_0001_catalog_tables.py` — `series`, `sets`, `cards`, `price_snapshots`
- [x] `20260318_0002_profiles.py` — `public.profiles` referencing `auth.users` via raw SQL
- [x] Run `alembic upgrade head` — all migrations applied cleanly
- [x] Verify all tables created correctly in Supabase dashboard

### Catalog seed
- [x] `tcgdex-sdk==2.2.1` in requirements.txt
- [x] Write `backend/seed_catalog.py` — series → sets → cards → price_snapshots ingestion
- [x] Full run: `python seed_catalog.py` — 22,754 cards seeded (English)
- [x] Validate: 21 series, 200 sets, 22,754 cards
- [x] Spot-check: `swsh3-136` Furret and `base1-4` Charizard verified correct

### Celery setup
- [x] Write `backend/celery_app.py` with beat schedule
- [x] `catalog.sync_new_sets`, `catalog.delta_sync_cards`, `prices.refresh_active_inventory` — all tested

### FastAPI catalog endpoints
- [x] `GET /api/v1/cards/{id}`, `GET /api/v1/cards?q=`, `GET /api/v1/sets`, `GET /api/v1/sets/{id}` — all verified

---

## Phase 1 checklist ✅
- [x] Supabase Auth trigger — auto-insert `public.profiles` on new `auth.users`
- [x] Add `/v1` prefix to all API routes in `main.py`
- [x] Migration 0003 — `vendor_profiles` + `inventory_items`
- [x] SQLAlchemy models — `VendorProfile`, `InventoryItem`, `Profile`
- [x] Auth dependency — JWT verification via Supabase JWKS (ES256)
- [x] `POST /api/v1/vendor/profile` — create vendor profile
- [x] `GET /api/v1/vendor/profile` — get own vendor profile
- [x] `PATCH /api/v1/vendor/profile` — update vendor profile
- [x] `POST /api/v1/inventory` — add inventory item
- [x] `GET /api/v1/inventory` — list inventory with filters
- [x] End-to-end auth test — JWT → profile → inventory item → list all confirmed

---

## Phase 2 checklist

### Backend (complete)
- [x] `boto3==1.35.99` + `anthropic==0.40.0` added to requirements.txt
- [x] AWS + Anthropic env vars added to Settings and `backend/.env`
- [x] Migration 0004 — `scan_jobs` table
- [x] SQLAlchemy model — `ScanJob` in `app/models/scans.py`
- [x] Celery task — `scans.process_scan_job` in `app/tasks/scan_pipeline.py`
- [x] `POST /api/v1/scans` — create scan job + presigned S3 PUT URL
- [x] `POST /api/v1/scans/{id}/trigger` — dispatch Celery task after S3 upload
- [x] `GET /api/v1/scans/{id}` — poll scan job status
- [x] `WS /api/v1/scans/{id}/ws` — WebSocket push on completion

### Frontend (not started)
- [ ] `create-next-app` scaffold — TypeScript, Tailwind, App Router in `frontend/`
- [ ] Install shadcn/ui, React Query, Zustand
- [ ] Auth: Supabase JS client + session management
- [ ] Scan page: camera/file upload → presigned S3 PUT → trigger endpoint
- [ ] WebSocket listener → completion push
- [ ] Scan confirmation UI: photo + identified card side-by-side
- [ ] Confirm → `POST /api/v1/inventory` (add_inventory action)

### Phase 2 complete criteria
- [ ] Vendor can upload a card photo from the browser
- [ ] Claude correctly identifies the card
- [ ] Confirmation UI shows identified card with confidence score
- [ ] Confirming adds the card to inventory

---

## Upcoming — Phase 3 (not started)
- Card show listings (admin-seeded)
- Vendor show registration + table location
- Show inventory tagging
- Show detail page with vendor list

---

## Upcoming — Phase 4 (not started)
- Browse shows (no auth required)
- Browse vendors at a show
- Search card inventory across a show
- Card price lookup (from price_snapshots)
