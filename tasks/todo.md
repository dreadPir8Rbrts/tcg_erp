# CardOps — Task Board

## Active phase: Phase 2 complete + Vendor Tools (beyond spec)

---

## Phase 0 checklist ✅
- [x] Supabase project + DATABASE_URL / MIGRATION_DATABASE_URL / SUPABASE_URL in backend/.env
- [x] FastAPI project scaffold, venv, alembic.ini
- [x] Migration 0001 — series, sets, cards, price_snapshots
- [x] Migration 0002 — public.profiles referencing auth.users
- [x] seed_catalog.py — 22,754 cards (21 series, 200 sets) seeded
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
- [x] ScanJob SQLAlchemy model (vendor_id FK removed from ORM — enforced at DB level)
- [x] scans.process_scan_job Celery task (S3 → Claude Vision → card match)
- [x] POST /api/v1/scans — create job + presigned S3 PUT URL (SigV4, us-east-2)
- [x] POST /api/v1/scans/{id}/trigger — send_task via celery_app.app (not shared_task binding)
- [x] GET /api/v1/scans/{id} — poll status
- [x] WS /api/v1/scans/{id}/ws — WebSocket push with db.expire_all() per poll
- [x] CORS middleware added to main.py (allow localhost:3000)
- [x] websockets==12.0 installed for uvicorn WebSocket support

### Frontend
- [x] Next.js 14 scaffold in frontend/ — Tailwind v3, App Router, TypeScript
- [x] shadcn components: button, card, badge, progress, tabs
- [x] lib/supabase.ts, lib/api.ts, app/providers.tsx, app/layout.tsx
- [x] app/login/page.tsx — Supabase email/password login, redirects to /scan
- [x] app/scan/page.tsx — full scan UI with auth guard
- [x] next.config.mjs — assets.tcgdex.net + *.amazonaws.com in remotePatterns
- [x] End-to-end scan verified: upload → S3 → Celery → Claude → WebSocket → confirmation UI

### Phase 2 complete criteria ✅
- [x] Vendor uploads card photo from browser
- [x] Claude correctly identifies the card (base1-58 @ 0.95 confidence verified)
- [x] Confirmation UI shows identified card with confidence score
- [x] Confirming adds card to inventory

---

## Vendor Tools (post-Phase 2, in progress)

### Card search — /card-search ✅
- [x] GET /api/v1/cards extended — JOINs sets + series, returns enriched CardDetailResponse
- [x] Search params: name, card_num, set_name, series_name (AND logic, any combination)
- [x] Response fields: card_num, set_name, release_date, series_name, series_logo_url
- [x] frontend/app/card-search/page.tsx — 4-field search, debounced, Add to inventory per result

### Vendor profile — /vendor-profile (in progress)
- [x] Migration 0005 — background_img + avatar_img added to vendor_profiles
- [x] POST /api/v1/vendor/profile/image — presigned PUT URL for background/avatar upload
- [x] S3 bucket policy — profiles/* publicly readable
- [x] Block public access disabled on S3 bucket for profiles/* prefix
- [x] GET /api/v1/inventory — now JOINs cards/sets/series, returns InventoryItemWithCardResponse
- [x] frontend/app/vendor-profile/page.tsx:
  - Hero banner with background image upload
  - Circle avatar with upload button
  - display_name, bio, buying_rate, trade_rate, tcg_interests display
  - Full-width tab bar (Inventory | Wishlist)
  - Inventory tab: searchable list with card image, name, set, condition, price
  - Wishlist tab: placeholder
- [ ] Wishlist backend + frontend (not started)

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
- Card price lookup (from price_snapshots)
