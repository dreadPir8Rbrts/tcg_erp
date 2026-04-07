# CardOps — Task Board

## Active phase: V2 API catalog migration complete — Vendor Inventory live on cards_v2

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
  - UUID PKs, UNIQUE(game, external_id) business key
  - Supports pokemon (EN + JP) and onepiece (EN)
  - GIN trigram index on cards_v2.name
  - variants JSONB stores full API response including prices
  - price_data_uploaded_at tracks freshness of embedded prices
- [x] SQLAlchemy models — ExpansionV2, CardV2 (catalog_v2.py)
- [x] Settings fields: v2_api_key, v2_api_team_id (env vars: V2_API_KEY, V2_API_TEAM_ID)
- [x] catalog_sync_v2.py Celery tasks:
  - v2_api.sync_expansions — sync all expansions for a game
  - v2_api.sync_cards_for_expansion — paginated card sync
  - v2_api.full_sync — weekly Sunday 4am UTC beat schedule
  - v2_api.test_sync — smoke test (1 expansion per game)
  - v2_api.refresh_prices — written but NOT scheduled (Phase 2 activation pending)
- [x] Pagination fix: terminates on len(data) < PAGE_SIZE (not totalCount comparison)
- [x] Translation field fix: extracts nested dict → en name string before upsert
- [x] Full sync completed: all historical Pokémon sets (EN + JP) + One Piece populated
- [x] TCGdex catalog syncs frozen (catalog.sync_new_sets, catalog.delta_sync_cards removed from beat schedule)

### Pivot all active code to cards_v2 + expansions_v2
- [x] Migration 0017 — add card_v2_id to vendor_inventory + price_snapshots
  - vendor_inventory: card_v2_id UUID FK → cards_v2.id (legacy card_id kept as dead column)
  - price_snapshots: card_v2_id replaces card_id in unique constraint + index
- [x] api/catalog.py rewritten — GET /cards, GET /cards/{id}, GET /expansions, GET /expansions/{id}
  - Search params: name, card_num, game, language_code, set_name
  - image_url extracted server-side from images[0]['small'] (fast thumbnails)
- [x] api/vendor.py — inventory add/list join cards_v2 + expansions_v2
- [x] api/scans.py — Claude Vision lookup uses CardV2 + ExpansionV2; pokemon-only filter
- [x] services/catalog_match.py — Quick Scan fuzzy matcher rewritten for CardV2/ExpansionV2
- [x] tasks/scan_pipeline.py — _match_card joins ExpansionV2 on external_id
- [x] schemas/vendor.py — added game, language_code; series_name/card_num now Optional
- [x] frontend/lib/api.ts — Card interface updated (removed category/illustrator/series_logo_url/variants; added game, language_code; series_name optional)
- [x] next.config.mjs — images.scrydex.com added to remotePatterns
- [x] inventory page — replaced next/image with plain <img> for card thumbnails (avoids Next.js proxy 400 on CDN URLs)
- [x] profile/scan pages — added sizes prop to all next/image fill usages

---

## Upcoming — Phase 3 (not started)
- Card show listings (admin-seeded)
- Vendor show registration + table location
- Show inventory tagging
- Show detail page with vendor list

## Upcoming — Phase 4 (not started)
- Browse shows (no auth required)
- Browse vendors at a show
- Search card inventory across a show
- Card price lookup (from price_snapshots / cards_v2.variants)

## Backlog / deferred
- [ ] v2_api.refresh_prices activation — see tasks/full_tcg_api_ingestion_plan.md for credit cost analysis
- [ ] Quick Scan edition disambiguation (wrong-match failures — correct name, wrong set)
- [ ] One Piece scan support (scan pipeline currently Pokémon-only)
- [ ] Wishlist backend + frontend
- [ ] Drop legacy card_id column from vendor_inventory (migration 0018, after stable)
