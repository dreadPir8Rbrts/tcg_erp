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

### Scan pipeline optimizations ✅
- [x] Client-side image compression (1400px max, 85% JPEG) before upload
- [x] Tightened Claude prompt — text-reading first, returns card_name + set_code + local_id + confidence
- [x] max_tokens=150 (was 256)
- [x] Redis perceptual hash cache — repeat scans return instantly (TTL 1h, key: scan_cache:{phash}:{action})
- [x] Pillow + imagehash + python-multipart added to requirements.txt
- [x] Refactored scan hot path: removed S3+Celery from identification flow
  - New endpoint: POST /api/v1/scans/identify (multipart UploadFile, async)
  - FastAPI → Claude directly, returns full card details in one response
  - S3 image storage + DB scan_job log written via BackgroundTasks (non-blocking)
- [x] Frontend: single identifyCard() call replaces 4-step flow (no WebSocket, no presigned URL, no trigger)
- [x] Lookup strategy: name+local_id primary (reliable text read), set_code+local_id fallback
- [x] Leading-zero normalization: "044" and "44" both match DB records
- [x] Model upgraded: claude-sonnet-4-20250514 → claude-sonnet-4-6
- [x] logging.basicConfig in main.py — app logger now outputs to uvicorn terminal
- [x] IdentifyResponse includes full card details — eliminates second GET /cards/{id} round-trip
- [x] claude_card_name shown in UI when it differs from matched DB card name (mismatch indicator)

### Quick Scan — Google Cloud Vision OCR ✅
- [x] POST /api/v1/scans/quick-identify — Google Cloud Vision OCR + fuzzy catalog match
- [x] backend/app/services/ocr.py — async Vision client (singleton ImageAnnotatorAsyncClient), text parser
- [x] backend/app/services/catalog_match.py — 4-tier matching: name+local_id → local_id → local_id+hp → fuzzy name
- [x] card_count_official used to pin set (num_2 from "029/131" = 131 = sets.card_count_official)
- [x] Leading-zero normalization + 4-digit num_2 truncation (OCR reads "1910" instead of "191")
- [x] HP detection searches full raw text (not per-line) to handle "HP\n100" split across lines
- [x] Name parser skips STAGE1/STAGE2/BASIC/HP/bare numbers — picks first real text line
- [x] Google credentials loaded from GOOGLE_CREDENTIALS_BASE64 in backend/.env (full JSON base64)
- [x] Requirements: google-cloud-vision==3.13.0, google-auth==2.28.0, rapidfuzz==3.6.1, protobuf==6.33.6
- [x] Frontend: Quick Scan button alongside Identify Card button on /scan page
- [x] Quick Scan compression: 1200px max, 70% JPEG (vs 1400px/85% for Claude Vision)
- [x] On match: routes into existing confirm → Add to Inventory flow (same UI as Claude Vision)
- [x] On no-match: inline feedback card with OCR detected text + "Try Identify Card" prompt
- [x] ocr_num1 / ocr_num2 fields in OCR result + response for debugging
- [x] Raw OCR text logged at INFO level for debugging
- [x] claude_vision.py service extracted: call_claude() + lookup_card_from_claude_result()
  - scans.py now imports call_claude from service (thin wrapper)
  - benchmark script uses service directly without importing scans router

### Scanner benchmark script ✅
- [x] backend/scripts/benchmark_scanners.py
- [x] Randomly samples one card per set (200 sets), set order shuffled, --limit applies to sets
- [x] Fetches TCGdex CDN images (low.webp for Quick Scan, high.webp for Claude Vision)
- [x] Quick Scan: calls extract_card_text() + match_card_from_ocr() directly (no server needed)
- [x] Claude Vision: calls call_claude() + lookup_card_from_claude_result() directly
- [x] Outputs per-card table: name, set, #, Quick Scan result ✓/✗, time, Claude result ✓/✗, time
- [x] Summary: accuracy % + p50/p95 latency per scanner
- [x] --claude flag (off by default — costs money), --limit N, --set SET_ID, --output CSV, --high-res
- [x] No FastAPI server required — runs against DB + APIs directly

### Quick Scan accuracy system (in progress)
- [x] Option 1: Enriched CSV — ocr_name, ocr_set_number, ocr_hp, match_method, match_confidence, failure_reason per row
- [x] Option 2: Gold set — --generate-gold (2 cards/series, ~36-42 cards) + --gold flag for reproducible runs
- [x] Option 3: backend/scripts/analyze_failures.py — breakdown by failure_reason, top failing sets, samples per category
- [x] OCR parser fixes (22% → 41% on gold set):
  - Extended _NON_NAME_PATTERN: TRAINER, ENERGY, STAGE I/II, STAGET
  - Inline prefix stripping: "BASIC Litten" → "Litten", "STAGE Electrode" → "Electrode"
  - Level indicator stripping: "Aron x.15" → "Aron", "Bronzong LV.49" → "Bronzong"
  - Evolves-from line filter: skips "Evolves from X" lines on Base Set era cards
- [x] Catalog matcher: Tier 2b — fuzzy name tiebreaker when multiple cards share local_id
- [ ] Edition disambiguation for wrong-match failures (now 76% of all failures):
  - Dominant pattern: correct name + correct local_id but wrong set (e.g. Gyarados col1 → lc, Gouging Fire sv08 → sm6)
  - Tier 2b fuzzy fires but set still wrong when card name is identical across printings
  - Need set-pinning strategy using card_count, HP, or era signals

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
