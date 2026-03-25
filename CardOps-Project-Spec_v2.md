# CardOps — Project Specification
**Version:** 1.1  
**Status:** Planning complete — ready to build  
**Date:** March 2026  
**Changelog:** v1.1 — Supabase adopted as PostgreSQL host; auth + database unified on single platform; `users` table replaced with `public.profiles` referencing `auth.users`

---

## 1. Platform Overview

CardOps is a dual-sided platform for the TCG card show ecosystem with two distinct user types:

- **Vendors** — a full ERP suite for running a TCG business: inventory, sales, trades, show management, accounting, and push notifications
- **Customers** — show discovery, cross-vendor inventory search, market pricing, and personal collection profiles

**Initial TCG focus:** Pokémon (expand to One Piece in v2)  
**MVP target platform:** Web app, desktop-first  
**Working name:** CardOps

---

## 2. Tech Stack

### Frontend
| Technology | Rationale |
|---|---|
| Next.js 14 (App Router) | SSR for SEO on customer-facing pages; RSC for performance |
| TypeScript | Required at scale — inventory/financial logic needs type safety |
| Tailwind CSS | Rapid UI development |
| shadcn/ui + Radix | Accessible, composable components |
| React Query (TanStack) | Server state, caching, background inventory sync |
| Zustand | Lightweight client state (active show, wishlist) |

### Backend
| Technology | Rationale |
|---|---|
| FastAPI (Python) | Primary API server; natural fit for ML/AI pipelines |
| Supabase (PostgreSQL) | Managed PostgreSQL host — same instance as auth; standard connection string for SQLAlchemy |
| Redis | Session cache, task queue, rate limiting |
| Celery + Redis | Async task queue for image processing and background sync jobs |
| SQLAlchemy + Alembic | ORM + migrations; Alembic runs against Supabase's `public` schema as normal |

### AI / ML
| Technology | Rationale |
|---|---|
| Claude API (claude-sonnet-4-20250514) | Multimodal card identification from vendor photos |
| TCGdex API (via tcgdex-sdk) | Card catalog source of truth + pricing aggregation |

### Infrastructure
| Technology | Rationale |
|---|---|
| Fly.io (MVP) → AWS ECS (scale) | Low ops overhead for MVP launch |
| AWS S3 | Vendor card photo uploads |
| Supabase | Auth + managed PostgreSQL in one platform; RLS available for row-level data isolation |
| Upstash Redis | Serverless Redis for push notifications and queues |

### Real-time
| Technology | Rationale |
|---|---|
| WebSockets (FastAPI native) | Vendor push notifications, deal announcements |
| Server-Sent Events (SSE) | Customer read-only inventory update streams |

---

## 3. Card Catalog Strategy

### Decision: Own the catalog, reference images externally

We ingest all **immutable** card data from TCGdex into our own PostgreSQL tables (hosted on Supabase). Market pricing is fetched separately and cached in `price_snapshots`. Card images are referenced directly from the TCGdex CDN — not re-hosted.

**TCGdex image URL pattern:**  
`https://assets.tcgdex.net/{lang}/{serie}/{set}/{localId}`

**Why this approach:**
- Fast queries with no external API latency on hot paths
- Full control over search indexing (GIN index on card name)
- No TCGPlayer API account needed in MVP — TCGdex already aggregates TCGPlayer + Cardmarket pricing
- Image re-hosting deferred (IP risk + CDN cost) — revisit in v2

### TCGdex Data Hierarchy

```
Serie (e.g. "Sword & Shield")
  └── Set (e.g. "swsh3 — Darkness Ablaze")
        └── Card (e.g. "swsh3-136 Furret")
```

All three levels are first-class tables in our schema. TCGdex IDs are used as primary keys (string, not UUID).

### What We Store vs. Skip

**Stored (immutable catalog data):**
- Card: id, localId, name, category, rarity, illustrator, image_url
- Pokemon-specific: hp, types, dexId, stage, evolveFrom, description, attacks, abilities, weaknesses, resistances, retreat, suffix, level, regulationMark, legal
- Trainer-specific: effect, trainerType
- Energy-specific: effect, energyType
- Shared: variants (normal/holo/reverse/firstEdition), tcgdex_updated_at

**Not stored on card rows (lives in `price_snapshots` only):**
- `pricing.tcgplayer.*`
- `pricing.cardmarket.*`

**JSONB fields:** `attacks`, `abilities`, `weaknesses`, `resistances`, `variants` — flexible, avoids sparse columns, trivially extensible to new TCGs.

---

## 4. Database Schema

### Catalog Tables (TCGdex-sourced)

#### `series`
```
id               string PK         -- TCGdex serie id e.g. 'swsh'
name             string
logo_url         string nullable
tcg              enum(pokemon)     -- future: one_piece
last_synced_at   timestamp
```

#### `sets`
```
id                    string PK    -- TCGdex set id e.g. 'swsh3'
serie_id              string FK → series
name                  string
release_date          date nullable
card_count_official   integer
card_count_total      integer
logo_url              string nullable
symbol_url            string nullable
last_synced_at        timestamp
```

#### `cards`
```
id                  string PK      -- TCGdex id e.g. 'swsh3-136'
set_id              string FK → sets
local_id            string         -- card number within set
name                string
category            enum(Pokemon, Trainer, Energy)
rarity              string nullable
illustrator         string nullable
image_url           string nullable -- TCGdex CDN URL (not re-hosted)
-- Pokemon-specific
hp                  integer nullable
types               JSONB nullable  -- ['Fire', 'Water']
dex_ids             JSONB nullable  -- [4, 5, 6]
stage               string nullable -- Basic, Stage1, Stage2
evolve_from         string nullable
description         text nullable
attacks             JSONB nullable
abilities           JSONB nullable
weaknesses          JSONB nullable
resistances         JSONB nullable
retreat             integer nullable
suffix              string nullable
level               string nullable
regulation_mark     string nullable
-- Trainer-specific
effect              text nullable
trainer_type        string nullable
-- Energy-specific
energy_type         string nullable
-- Shared
variants            JSONB           -- {normal, holo, reverse, firstEdition}
legal_standard      boolean nullable
legal_expanded      boolean nullable
tcgdex_updated_at   timestamp
last_synced_at      timestamp
```

#### `price_snapshots`
```
id               UUID PK
card_id          string FK → cards
source           enum(tcgplayer, cardmarket)
variant          string             -- 'normal', 'holofoil', 'reverse-holofoil', '1st-edition', etc.
currency         string             -- 'USD', 'EUR'
low_price        decimal nullable
mid_price        decimal nullable
high_price       decimal nullable
market_price     decimal nullable
direct_low_price decimal nullable
-- Cardmarket-only
avg              decimal nullable
trend            decimal nullable
avg_1            decimal nullable
avg_7            decimal nullable
avg_30           decimal nullable
fetched_at       timestamp
expires_at       timestamp          -- fetched_at + 24h TTL
```

---

### Application Tables

> **Supabase auth integration:** Supabase provides a built-in `auth.users` table managed by its auth system. Our application tables live in the `public` schema and reference `auth.users(id)` rather than maintaining a redundant users table. Alembic manages all `public` schema migrations normally — do not touch the `auth` schema.

#### `public.profiles`
```
id        UUID PK  REFERENCES auth.users(id) ON DELETE CASCADE
role      VARCHAR CHECK (role IN ('vendor', 'customer', 'admin'))
-- Minimal bridge table. auth.users holds email, created_at, auth provider.
-- vendor_profiles and customer_profiles hang off this via profiles.id FK.
```

#### `vendor_profiles`
```
id                       UUID PK
profile_id               UUID FK → public.profiles(id)
display_name             string
bio                      text nullable
buying_rate              decimal nullable    -- 0.0–1.0, e.g. 0.70 = 70% of market
trade_rate               decimal nullable
tcg_interests            JSONB              -- ['vintage_japanese_pokemon', 'psa10', 'first_edition']
notification_prefs       JSONB
is_accounting_enabled    boolean DEFAULT false
created_at               timestamp
```

#### `inventory_items`
```
id               UUID PK
vendor_id        UUID FK → vendor_profiles
card_id          string FK → cards
condition        enum(psa_1..10, bgs_1..10, cgc_1..10, sgc_1..10, raw_nm, raw_lp, raw_mp, raw_hp, raw_dmg)
grading_service  string nullable    -- PSA, BGS, CGC, SGC
cert_number      string nullable    -- graded cert # for verification lookup
quantity         integer DEFAULT 1
cost_basis       decimal nullable
asking_price     decimal nullable
is_for_sale      boolean DEFAULT true
is_for_trade     boolean DEFAULT false
notes            text nullable
photo_url        string nullable    -- vendor's own photo of this specific copy (S3)
created_at       timestamp
updated_at       timestamp
deleted_at       timestamp nullable -- soft delete; transactions reference deleted items
```

#### `card_shows`
```
id               UUID PK
name             string
organizer        string nullable
venue_name       string
address          string
city             string
state            string
date_start       date
date_end         date
floor_plan_url   string nullable
is_verified      boolean DEFAULT false
created_by       UUID FK → public.profiles(id) nullable
created_at       timestamp
```

#### `vendor_show_registrations`
```
id               UUID PK
vendor_id        UUID FK → vendor_profiles
show_id          UUID FK → card_shows
table_location   string nullable    -- 'Row B, Table 12'
is_confirmed     boolean DEFAULT false
active_deals     JSONB nullable     -- [{message, expires_at}]
created_at       timestamp
```

#### `show_inventory_tags`
```
id                  UUID PK
registration_id     UUID FK → vendor_show_registrations
inventory_item_id   UUID FK → inventory_items
-- Junction: which items a vendor is bringing to a specific show
```

#### `transactions`
```
id          UUID PK
type        enum(sale, trade, purchase)
vendor_id   UUID FK → vendor_profiles
show_id     UUID FK → card_shows nullable
notes       text nullable
created_at  timestamp
```

#### `transaction_items`
```
id                   UUID PK
transaction_id       UUID FK → transactions
inventory_item_id    UUID FK → inventory_items nullable
card_id              string FK → cards
direction            enum(out, in)    -- out=sold/traded away, in=bought/traded in
quantity             integer
unit_price           decimal
condition            string
```

#### `customer_profiles`
```
id               UUID PK
profile_id       UUID FK → public.profiles(id)
display_name     string nullable
tcg_interests    JSONB nullable
is_public        boolean DEFAULT false
created_at       timestamp
```

#### `customer_inventory`
```
id              UUID PK
customer_id     UUID FK → customer_profiles
card_id         string FK → cards
condition       string
quantity        integer DEFAULT 1
is_for_trade    boolean DEFAULT false
is_for_sale     boolean DEFAULT false
asking_price    decimal nullable
notes           text nullable
```

#### `wishlists`
```
id                    UUID PK
customer_id           UUID FK → customer_profiles
card_id               string FK → cards
max_price             decimal nullable
preferred_condition   string nullable
notes                 text nullable
created_at            timestamp
```

#### `scan_jobs`
```
id                UUID PK
vendor_id         UUID FK → vendor_profiles
image_s3_key      string
status            enum(pending, processing, complete, failed)
action            enum(add_inventory, log_sale, log_trade_out, log_trade_in)
result_card_id    string FK → cards nullable
result_confidence decimal nullable
result_raw        JSONB nullable     -- full Claude API response
error_message     text nullable
created_at        timestamp
completed_at      timestamp nullable
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| TCGdex string IDs as PKs on catalog tables | Avoids mapping table; `swsh3-136` is more debuggable than a UUID |
| `price_snapshots` normalized per variant | One row per card+source+variant. Clean queries for "give me the holofoil market price" |
| `show_inventory_tags` junction table | Separates "vendor owns this" from "vendor is bringing this to show X" |
| Soft deletes on `inventory_items` | `deleted_at` nullable. Transactions must reference sold/traded items for accounting integrity |
| JSONB for attacks, abilities, weaknesses | Flexible across card types; avoids 20+ sparse columns |
| `cert_number` on inventory_items | Graded card cert enables external PSA/BGS verification — trust signal for customers |

---

## 5. Card Catalog Ingestion Pipeline

### Overview

```
Phase 0 (one-time):  seed_catalog.py  →  series + sets + cards tables
Nightly 2am:         catalog.sync_new_sets  →  detect + seed new sets
Nightly 3am:         catalog.delta_sync_cards  →  re-sync cards where updated > now-48h
Every 6 hours:       prices.refresh_active_inventory  →  refresh prices for cards in vendor inventory
```

### Ingestion Tools

- **Python SDK:** `pip install tcgdex-sdk` — typed models, async/sync, query builder
- **Upsert strategy:** `SQLAlchemy.merge()` by primary key — safe to re-run at any time
- **Rate limiting:** 100ms sleep between card fetches during initial seed (good citizen behavior)
- **Initial seed estimate:** ~18,000+ Pokémon cards, 30–60 min on first run

### Sync Strategy

| Job | Trigger | Logic |
|---|---|---|
| `seed_catalog.py` | One-time on deploy | Fetch all series → sets → cards via tcgdex-sdk |
| `catalog.sync_new_sets` | Nightly 2am | Compare remote set list vs local; seed missing sets |
| `catalog.delta_sync_cards` | Nightly 3am | Query TCGdex for `updated > now-48h`; re-seed those sets |
| `prices.refresh_active_inventory` | Every 6h | Fetch pricing only for cards in active vendor inventory with stale snapshots |

### Conflict Policy

TCGdex is authoritative for all catalog fields. Any local correction (e.g. fixing a card name typo) must go in a `catalog_overrides` table — never mutate the synced fields directly. This keeps re-syncs safe.

---

## 6. Pricing Strategy

### Data Flow

```
TCGdex card.pricing  →  price_snapshots table  →  API response  →  UI
     (TCGPlayer + Cardmarket aggregated)              (24h TTL)
```

### Currency

- TCGPlayer → USD (primary, shown to US users)
- Cardmarket → EUR (secondary, shown on request)

### Usage by Feature

| Feature | Pricing behavior |
|---|---|
| Vendor inventory valuation | `market_price` for card's variant + condition |
| Scan → log sale | Auto-fill asking price with current `market_price`; vendor overrides |
| Trade delta calculation | Both sides priced at market; delta shown |
| Customer price lookup | Market price by variant + sparkline from avg_7/avg_30 |
| Customer scan-to-price | Claude identifies card → immediate cache lookup |
| "Is this a good deal?" | vendor `asking_price` vs `market_price` → % above/below |
| Bulk price update | Set `asking_price = market_price × factor` across selected inventory |

### Future: Direct TCGPlayer API (v2)

For high-value cards (PSA 10 vintage holos) where real-time pricing matters, add a direct TCGPlayer API integration with on-demand refresh. Design accommodates this — `price_source` enum on `price_snapshots` already supports it.

---

## 7. Feature Specification

### Vendor Features

#### Inventory Management
- **Manual inventory entry** — search card catalog, add copy with condition/price/quantity; bulk CSV import
- **Camera scan → add to inventory** — photo → S3 → Celery → Claude Vision → confirmation UI → inventory_item created
- **Camera scan → log sale** — same pipeline, action=sale; prompts price; creates Transaction + decrements quantity
- **Camera scan → log trade** — dual scan (out + in); system prices both sides; creates Transaction with in/out items
- **Inventory dashboard** — filterable table: TCG, set, condition, for-sale, for-trade; cost basis vs market price
- **Bulk price update** — auto-set asking prices at X% of market across selected inventory

#### Show Management
- **Show discovery & registration** — browse upcoming shows; register with table location
- **Show-specific inventory subset** — tag which inventory items you're bringing to a show
- **Push notifications / deal announcements** — broadcast a deal to customers browsing that show (WebSocket)

#### Vendor Profile
- **Public profile** — display name, bio, TCG interests, buying/trade rates, upcoming shows, public inventory slice
- **TCG interest tags** — multi-select: 'vintage_japanese_pokemon', 'graded_psa10', 'first_edition_base_set', etc.
- **Buying/trade rate settings** — displayed on profile for customer expectations

#### Accounting (opt-in)
- **P&L dashboard** — revenue, COGS, gross profit by date range and show
- **Show performance report** — per-show revenue, transactions, top sellers
- **Inventory valuation** — total cost basis vs current market value
- **CSV/PDF export** — transaction history for tax filing (Schedule C)

---

### Customer Features

#### Show & Vendor Discovery
- **Browse shows** — list of upcoming shows by date/location (no auth required)
- **Browse vendors at a show** — vendor grid with TCG interests, buy/trade rates, table location
- **Search inventory across a show** — find which vendors at a show have a specific card, with price + condition
- **Find vendors interested in your cards** — input cards you want to sell/trade → match against vendor interest tags
- **Show floor map** — visual table map; highlights vendors matching customer wishlist

#### Market Data
- **Card price lookup** — TCGPlayer market price by variant + condition; Cardmarket EUR secondary
- **Price history chart** — 30/90/365 day sparkline from stored avg_7/avg_30 snapshots
- **Scan to price** — photo a card at the show → Claude identifies it → instant market price lookup

#### Customer Profile & Collection
- **Customer collection** — log owned cards with condition; public profile for vendor browsing
- **Wishlist** — save cards you're looking for; used to highlight matching vendor inventory at shows
- **Vendor match alerts** — notification when a vendor with wishlist items registers for an upcoming show

---

## 8. Card Scan Pipeline (Technical Detail)

The scan pipeline is the most complex system. Every scan is async.

```
1. Vendor taps "Scan" → selects action (add inventory / log sale / trade)
2. Camera opens → photo captured → uploaded to S3 (presigned URL)
3. POST /scans creates scan_job (status=pending, image_s3_key, action)
4. Celery task picks up job → status=processing
5. Claude multimodal API call:
     - Image sent as base64
     - Prompt: "Identify this Pokémon card. Return JSON: 
       {card_name, set_name, set_code, local_id, condition_estimate, confidence}"
6. result_raw stored; result_card_id matched against cards table by set_code + local_id
7. status=complete; WebSocket pushes completion event to vendor's browser
8. Vendor sees confirmation UI: card image + identified card side-by-side
9. Vendor confirms (or corrects) → downstream action executes:
     - add_inventory → INSERT inventory_items
     - log_sale → INSERT transaction + transaction_items + decrement quantity
     - log_trade → same as sale but with inbound scan also completed first
```

**Failure handling:** If Claude cannot identify the card (confidence < threshold or no match found), status=failed and vendor is prompted to search manually. The `scan_jobs` table provides full audit history.

---

## 9. MVP Scope

### Phase 0 — Catalog foundation (pre-dev, ~2 days)
- [ ] Create Supabase project; copy `DATABASE_URL` (connection pooler string) into `.env`
- [ ] Alembic migrations: `public.profiles`, `series`, `sets`, `cards`, `price_snapshots`
- [ ] Run `seed_catalog.py` — full Pokémon catalog, English
- [ ] Validate: ~18,000+ cards, all sets, JSONB fields correct
- [ ] Celery beat: `catalog.sync_new_sets` (2am) + `catalog.delta_sync_cards` (3am)
- [ ] Celery beat: `prices.refresh_active_inventory` (every 6h)
- [ ] FastAPI endpoints: `GET /cards/{id}`, `GET /cards/search?q=`, `GET /sets`

### Phase 1 — Foundation (Weeks 1–3)
- [ ] Supabase Auth: enable email provider; configure vendor + customer roles via `public.profiles`
- [ ] Supabase auth trigger: auto-insert `public.profiles` row on `auth.users` creation
- [ ] Vendor profile creation + TCG interest tags
- [ ] Manual inventory add (search catalog → add copy)
- [ ] Inventory list view with filtering

### Phase 2 — Scan pipeline (Weeks 4–6)
- [ ] S3 presigned URL upload endpoint
- [ ] Celery task: Claude Vision → card identification
- [ ] Scan confirmation UI
- [ ] Scan → add inventory
- [ ] Scan → log sale

### Phase 3 — Shows (Weeks 7–9)
- [ ] Card show listings (admin-seeded)
- [ ] Vendor show registration + table location
- [ ] Show inventory tagging
- [ ] Show detail page with vendor list

### Phase 4 — Customer discovery (Weeks 10–12)
- [ ] Browse shows (no auth required)
- [ ] Browse vendors at a show
- [ ] Search card inventory across a show
- [ ] Card price lookup (from price_snapshots)

### Deferred to v2
- Accounting / P&L dashboard
- Trade logging (dual-scan)
- Customer collection + wishlist
- Push notifications / deal alerts
- Customer scan-to-price
- Show floor map visualization
- One Piece TCG support
- Vendor match alerts
- Bulk price updates
- Price history charts

---

## 10. Constraints & Decisions Log

| # | Decision | Rationale |
|---|---|---|
| 1 | TCGdex as catalog source | Open, well-maintained, typed SDK, aggregates pricing |
| 2 | TCGdex string IDs as PKs | Debuggable; stable; avoids mapping table |
| 3 | Card images: reference TCGdex CDN, not re-hosted | Avoids IP risk + S3 cost in MVP; revisit v2 |
| 4 | No direct TCGPlayer API account in MVP | TCGdex pricing aggregation is sufficient |
| 5 | Prices in separate table with TTL | Keeps catalog data clean; price staleness explicit |
| 6 | `show_inventory_tags` junction table | Vendor brings subset of inventory to each show |
| 7 | Soft deletes on inventory_items | Accounting integrity — sold items must remain referenceable |
| 8 | Claude Vision for card scanning (no OCR fallback) | Sufficient for MVP; simpler stack |
| 9 | Admin-seeded shows in MVP | Data quality control; no vendor self-serve show creation until v2 |
| 10 | Customers anonymous by default | Browse/search requires no account; accounts unlock wishlist + collection |
| 11 | Accounting opt-in only | Financial data isolation; transaction records stored always, UI deferred |
| 13 | Supabase as PostgreSQL host | Auth + DB on one platform; single dashboard, one connection string, RLS available |
| 14 | `public.profiles` references `auth.users` | Supabase owns auth lifecycle; profiles table bridges to app data without duplicating auth fields |
| 15 | Alembic manages `public` schema only | Never touch Supabase's `auth` schema; all migrations scoped to `public` |
| 16 | `price_snapshots` UNIQUE(card_id, source, variant) | Enables clean upserts in ingestion jobs; enforces one row per card+source+variant |
| 17 | VARCHAR + check constraints over PG enums | Easier to extend for One Piece v2 without `ALTER TYPE` migrations |

---

*CardOps Project Specification — v1.1 — Ready to build*
