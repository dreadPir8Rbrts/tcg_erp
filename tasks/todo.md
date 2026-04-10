# CardOps — Task Board

## Active phase: Pricing infrastructure live — frontend pricing UI next

---

## Phase 0 checklist ✅
- [x] Supabase project + DATABASE_URL / MIGRATION_DATABASE_URL / SUPABASE_URL in backend/.env
- [x] FastAPI project scaffold, venv, alembic.ini
- [x] Migration 0001 — series, sets, cards, price_snapshots
- [x] Migration 0002 — public.profiles referencing auth.users
- [x] seed_catalog.py — 22,754 cards (21 series, 200 sets) seeded (TCGdex, now frozen)
- [x] Celery beat: catalog.sync_new_sets, catalog.delta_sync_cards, prices.refresh_active_inventory
- [x] GET /api/v1/cards/{id}, GET /api/v1/cards, GET /api/v1/sets, GET /api/v1/sets/{id}

---

## Phase 1 checklist ✅
- [x] Supabase Auth trigger — auto-insert public.profiles on signup
- [x] Migration 0003 — vendor_profiles + inventory_items
- [x] SQLAlchemy models — VendorProfile, InventoryItem, Profile
- [x] Auth dependency — ES256 JWT via Supabase JWKS
- [x] POST/GET/PATCH /api/v1/vendor/profile
- [x] POST/GET /api/v1/inventory
- [x] End-to-end auth test passed

---

## Phase 2 checklist ✅

### Backend
- [x] Migration 0004 — scan_jobs table
- [x] ScanJob SQLAlchemy model
- [x] scans.process_scan_job Celery task (S3 → Claude Vision → card match)
- [x] POST /api/v1/scans — create job + presigned S3 PUT URL
- [x] POST /api/v1/scans/{id}/trigger — dispatch Celery task
- [x] GET /api/v1/scans/{id} — poll status
- [x] WS /api/v1/scans/{id}/ws — WebSocket push
- [x] CORS middleware added to main.py

### Frontend
- [x] Next.js 14 scaffold — Tailwind v3, App Router, TypeScript, shadcn/ui
- [x] lib/supabase.ts, lib/api.ts, app/providers.tsx
- [x] Login page — Supabase email/password auth + onboarding_complete cookie gate
- [x] Scan page — Claude Vision + Quick Scan (Google Cloud Vision OCR)
- [x] End-to-end scan verified

---

## Vendor Tools ✅

### Card search + inventory — /vendor/inventory
- [x] GET /api/v1/cards — search by name, card_num, set_name, series_name
- [x] POST/GET /api/v1/inventory — add + list inventory with card details
- [x] Vendor inventory page — search + scan + confirm + add to inventory flow
- [x] Inventory list on vendor profile page

### Vendor profile — /vendor/profile
- [x] Migration 0005 — background_img + avatar_img on vendor_profiles
- [x] POST /api/v1/vendor/profile/image — presigned PUT URL for S3 upload
- [x] Hero banner + avatar upload
- [x] Profile display: bio, buying_rate, trade_rate

### Scan pipeline optimizations
- [x] Client-side image compression before upload
- [x] Redis perceptual hash cache (TTL 1h)
- [x] POST /api/v1/scans/identify — Claude Vision fast path (no Celery queue)
- [x] POST /api/v1/scans/quick-identify — Google Cloud Vision OCR + fuzzy match
- [x] 4-tier fuzzy matcher: name+local_id → local_id → local_id+hp → fuzzy name
- [x] Scanner benchmark script — accuracy % + latency per scanner

---

## V2 API Catalog Migration ✅ (2026-04-06 → 2026-04-07)

### New catalog source: V2 API (api.scrydex.com)
- [x] Migration 0016 — expansions_v2 + cards_v2 tables
- [x] SQLAlchemy models — ExpansionV2, CardV2 (catalog_v2.py)
- [x] catalog_sync_v2.py Celery tasks
- [x] Full sync completed: all historical Pokémon sets (EN + JP) + One Piece populated
- [x] TCGdex catalog syncs frozen

### Pivot all active code to cards_v2 + expansions_v2
- [x] Migration 0017 — add card_v2_id to vendor_inventory + price_snapshots
- [x] api/catalog.py rewritten for cards_v2 + expansions_v2
- [x] api/vendor.py, api/scans.py, services/catalog_match.py updated

---

## App restructure ✅ (2026-04-09)
- [x] Unified `/profile/[profile_id]` route (owner + public visitor)
- [x] All user-scoped routes nested under `[profile_id]`: dashboard, inventory, scan, wishlist, transactions
- [x] Login/onboarding redirect to `/dashboard/{profile_id}`
- [x] Sidebar reads `profileId` from React Query cache
- [x] Card shows: route renamed `/shows` → `/card-shows`, sidebar label updated
- [x] Two-button show registration: "Attending as Vendor" / "Attending as Collector"
- [x] Backend: `attending_as` field on `profile_show_registrations` (migration 0024)
- [x] Backend: `GET /profile/shows/registrations` endpoint added

---

## Pricing infrastructure ✅ (2026-04-10)

### Scraper droplet (card-ops-droplet repo)
- [x] Standalone repo deployed to DO droplet (159.203.130.99, NYC3, 1GB)
- [x] Redis + Celery worker + Celery beat running as systemd services
- [x] `prices.scrape_tcgplayer_nm` — nightly 2am UTC, active inventory cards
- [x] `prices.scrape_ebay_sold_comps` — nightly 3am UTC, active inventory cards
- [x] `prices.scrape_card_on_demand` — user-triggered, single card, all grade targets
- [x] eBay scraper: targeted grade queries + 20→7 filtering/scoring logic
- [x] TCGPlayer scraper: JSON extraction + HTML fallback
- [x] Migration 0025 — `sold_comps` table (run and applied)

### Main app backend
- [x] `SoldComp` SQLAlchemy model added to `models/catalog.py`
- [x] `GET /api/v1/cards/{card_v2_id}/pricing` — NM anchor + condition estimates; returns 202 + enqueues on-demand scrape when stale
- [x] `GET /api/v1/cards/{card_v2_id}/sold-comps` — filtered sold comps (condition_type, grading_company, grade, condition_ungraded)
- [x] `SCRAPER_REDIS_URL` setting added — points to scraper droplet private IP

### Infrastructure
- [x] App droplet deployed (134.209.170.89, NYC3, 2GB) — FastAPI + Nginx
- [x] Scraper droplet Redis bound to private IP (10.108.0.2) — accessible from app droplet only
- [x] Private VPC networking between app droplet and scraper droplet
- [x] Main app deployed at http://134.209.170.89

---

## Active — next up

- [ ] Frontend pricing component:
  - Ungraded pricing dropdown: NM (TCGPlayer) + LP/MP/HP/DMG estimates
  - "View recent sales" per condition → sold comps inline
  - Graded pricing dropdown: grader selector + grade selector + sold comps
  - Polling state: "pricing loading..." while 202 pending → auto-refresh on ready
- [ ] SSL/domain setup on app droplet (Certbot)
- [ ] Update frontend API base URL from localhost:8000 → http://134.209.170.89

---

## Backlog / deferred
- [ ] v2_api.refresh_prices activation — see tasks/full_tcg_api_ingestion_plan.md
- [ ] Quick Scan edition disambiguation (wrong-match failures)
- [ ] One Piece scan support
- [ ] Wishlist backend + frontend
- [ ] Drop legacy card_id column from vendor_inventory (migration 0018)
- [ ] Validate eBay scraper CSS selectors against live eBay HTML
- [ ] Validate TCGPlayer scraper JSON extraction patterns
