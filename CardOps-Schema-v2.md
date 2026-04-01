# CardOps — revised database schema v2.0

## Overview

15 tables across 4 categories. All application tables live in the `public`
schema. The `auth` schema is owned by Supabase and never touched directly.

TCGdex string IDs (e.g. `swsh3-136`) are used as primary keys on catalog
tables. All application tables use UUID primary keys. All timestamps are
`TIMESTAMP WITH TIME ZONE` (timezone-aware). Soft deletes via `deleted_at`
on transactional tables — never hard delete.

---

## Category 1 — Catalog tables (TCGdex-sourced)

These tables are populated by the TCGdex ingestion pipeline and Celery sync
jobs. Application code treats them as read-only. Never write to these tables
from application logic — only the ingestion scripts and sync tasks write here.

---

### `series`

Top-level TCG groupings (e.g. "Sword & Shield", "Scarlet & Violet").

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | VARCHAR | PK | TCGdex serie ID e.g. `swsh` |
| `name` | VARCHAR(200) | NOT NULL | Display name e.g. "Sword & Shield" |
| `logo_url` | VARCHAR(500) | nullable | TCGdex CDN logo URL |
| `tcg` | VARCHAR(50) | NOT NULL, CHECK IN ('pokemon') | TCG type — expand for One Piece v2 |
| `last_synced_at` | TIMESTAMPTZ | NOT NULL | When this row was last written by the sync job |

---

### `sets`

Individual card set releases within a serie (e.g. "swsh3 — Darkness Ablaze").

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | VARCHAR | PK | TCGdex set ID e.g. `swsh3` |
| `serie_id` | VARCHAR | FK → series(id) NOT NULL | Parent serie |
| `name` | VARCHAR(200) | NOT NULL | Display name e.g. "Darkness Ablaze" |
| `release_date` | DATE | nullable | Official release date |
| `card_count_official` | INTEGER | nullable | Official card count (excludes secret rares) |
| `card_count_total` | INTEGER | nullable | Total including secret rares |
| `logo_url` | VARCHAR(500) | nullable | TCGdex CDN set logo URL |
| `symbol_url` | VARCHAR(500) | nullable | TCGdex CDN set symbol URL |
| `last_synced_at` | TIMESTAMPTZ | NOT NULL | When this row was last written |

---

### `cards`

Individual Pokémon cards. One row per unique card (set + local_id combination).
Fields vary by category (Pokemon / Trainer / Energy) — non-applicable fields
are NULL.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | VARCHAR | PK | TCGdex card ID e.g. `swsh3-136` |
| `set_id` | VARCHAR | FK → sets(id) NOT NULL | Parent set |
| `local_id` | VARCHAR(20) | NOT NULL | Card number within the set e.g. `136`, `TG15` |
| `name` | VARCHAR(200) | NOT NULL | Card name e.g. "Furret" |
| `category` | VARCHAR(20) | NOT NULL, CHECK IN ('Pokemon','Trainer','Energy') | Card type |
| `rarity` | VARCHAR(100) | nullable | e.g. "Common", "Rare Holo", "Illustration Rare" |
| `illustrator` | VARCHAR(200) | nullable | Artist name |
| `image_url` | VARCHAR(500) | nullable | TCGdex CDN base URL — append `/high.webp` or `/low.webp` |
| `hp` | INTEGER | nullable | Hit points — Pokemon only |
| `types` | JSONB | nullable | `["Fire"]` or `["Water","Psychic"]` — Pokemon only |
| `dex_ids` | JSONB | nullable | `[4, 5, 6]` National Pokédex IDs — Pokemon only |
| `stage` | VARCHAR(50) | nullable | `"Basic"`, `"Stage1"`, `"Stage2"` — Pokemon only |
| `evolve_from` | VARCHAR(200) | nullable | Pre-evolution name — Pokemon only |
| `description` | TEXT | nullable | Flavor text — Pokemon only |
| `attacks` | JSONB | nullable | `[{name, cost, damage, effect}]` — Pokemon only |
| `abilities` | JSONB | nullable | `[{name, type, effect}]` — Pokemon only |
| `weaknesses` | JSONB | nullable | `[{type, value}]` e.g. `[{"type":"Fighting","value":"×2"}]` |
| `resistances` | JSONB | nullable | `[{type, value}]` — Pokemon only |
| `retreat` | INTEGER | nullable | Retreat cost in energy — Pokemon only |
| `suffix` | VARCHAR(50) | nullable | e.g. "ex", "V", "VMAX", "GX" |
| `level` | VARCHAR(20) | nullable | Level or "X" for LV.X cards |
| `regulation_mark` | VARCHAR(5) | nullable | e.g. "D", "E", "F", "G", "H" |
| `effect` | TEXT | nullable | Card effect text — Trainer and Energy only |
| `trainer_type` | VARCHAR(100) | nullable | e.g. "Item", "Supporter", "Stadium" — Trainer only |
| `energy_type` | VARCHAR(50) | nullable | `"Basic"` or `"Special"` — Energy only |
| `variants` | JSONB | NOT NULL | `{"normal":true,"holo":false,"reverse":true,"firstEdition":false}` |
| `legal_standard` | BOOLEAN | nullable | Whether legal in Standard format |
| `legal_expanded` | BOOLEAN | nullable | Whether legal in Expanded format |
| `tcgdex_updated_at` | TIMESTAMPTZ | nullable | TCGdex's own `updated` field — used for delta sync |
| `last_synced_at` | TIMESTAMPTZ | NOT NULL | When this row was last written by the sync job |

**Indexes:**
- GIN index on `name` using `gin_trgm_ops` for fast fuzzy text search
- B-tree index on `local_id` for set number lookups
- B-tree index on `set_id`

---

### `price_snapshots`

Market pricing data fetched from TCGdex (which aggregates TCGPlayer + Cardmarket).
One row per card + source + variant combination. Refreshed every 6 hours for
cards in active vendor inventory.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `card_id` | VARCHAR | FK → cards(id) NOT NULL | |
| `source` | VARCHAR(50) | NOT NULL, CHECK IN ('tcgplayer','cardmarket') | Pricing source |
| `variant` | VARCHAR(50) | NOT NULL | e.g. `normal`, `holofoil`, `reverse-holofoil`, `1st-edition`, `1st-edition-holofoil`, `unlimited`, `unlimited-holofoil` |
| `currency` | VARCHAR(5) | NOT NULL | `USD` for TCGPlayer, `EUR` for Cardmarket |
| `low_price` | DECIMAL(10,2) | nullable | Lowest listed price |
| `mid_price` | DECIMAL(10,2) | nullable | Median price |
| `high_price` | DECIMAL(10,2) | nullable | Highest listed price |
| `market_price` | DECIMAL(10,2) | nullable | Current market price — primary price signal |
| `direct_low_price` | DECIMAL(10,2) | nullable | TCGPlayer direct seller price — TCGPlayer only |
| `avg` | DECIMAL(10,2) | nullable | Average sale price — Cardmarket only |
| `trend` | DECIMAL(10,2) | nullable | Trend price — Cardmarket only |
| `avg_1` | DECIMAL(10,2) | nullable | 24-hour average — Cardmarket only |
| `avg_7` | DECIMAL(10,2) | nullable | 7-day average — Cardmarket only |
| `avg_30` | DECIMAL(10,2) | nullable | 30-day average — Cardmarket only |
| `fetched_at` | TIMESTAMPTZ | NOT NULL | When this snapshot was recorded |
| `expires_at` | TIMESTAMPTZ | NOT NULL | fetched_at + 24h — stale after this |

**Unique constraint:** `UNIQUE(card_id, source, variant)` — upsert target for
all price writes. Use `INSERT ... ON CONFLICT (card_id, source, variant) DO UPDATE`.

---

## Category 2 — User / auth tables

---

### `public.profiles`

Bridge table between `auth.users` (Supabase-owned) and all application tables.
Every authenticated user has exactly one `profiles` row, created automatically
by the Supabase DB trigger on `auth.users` INSERT.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK, FK → auth.users(id) ON DELETE CASCADE | Matches Supabase auth user ID |
| `role` | VARCHAR(20) | NOT NULL, CHECK IN ('vendor','collector','both') DEFAULT 'collector' | User's role(s) |
| `display_name` | VARCHAR(50) | nullable | Shown in nav, on profiles, in show listings |
| `avatar_url` | VARCHAR(500) | nullable | S3 URL for uploaded avatar image |
| `zip_code` | VARCHAR(10) | nullable, CHECK matching `^\d{5}$` | Used for nearby show discovery |
| `tcg_interests` | JSONB | nullable DEFAULT '[]' | `["pokemon","one_piece"]` — shared across both modes |
| `is_public` | BOOLEAN | NOT NULL DEFAULT false | Whether collector collection is publicly visible |
| `onboarding_complete` | BOOLEAN | NOT NULL DEFAULT false | Set to true when onboarding wizard is finished |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Notes:**
- `display_name`, `avatar_url`, `tcg_interests` serve both vendor and
  collector contexts. There is one display name per user — not separate names
  per mode.
- `is_public` controls collector collection visibility. Vendor inventory
  visibility is controlled per-item via `vendor_inventory.is_for_sale`.
- The Supabase trigger inserts a row with `role='collector'`,
  `onboarding_complete=false` on every new `auth.users` row.
- All application tables FK to `profiles(id)`, never directly to `auth.users`.

**Supabase trigger (run in SQL editor — NOT via Alembic):**
```sql
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, role, onboarding_complete)
  VALUES (new.id, 'collector', false);
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
```

---

### `vendor_profiles`

Vendor-specific data. Only exists for users with `role = 'vendor'` or
`role = 'both'`. Created at the end of onboarding when the user selects a
vendor role.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `profile_id` | UUID | FK → profiles(id) ON DELETE CASCADE, UNIQUE | One vendor profile per user |
| `bio` | TEXT | nullable | Free-text vendor bio shown on public profile |
| `buying_rate` | DECIMAL(4,3) | nullable, CHECK BETWEEN 0 AND 1 | Fraction of market value vendor pays e.g. 0.70 = 70% |
| `trade_rate` | DECIMAL(4,3) | nullable, CHECK BETWEEN 0 AND 1 | Fraction of market value given as trade credit |
| `is_accounting_enabled` | BOOLEAN | NOT NULL DEFAULT false | Opt-in to P&L dashboard and accounting features |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Notes:**
- `display_name`, `avatar_url`, `tcg_interests` live on `profiles` — not
  duplicated here.
- `buying_rate = 0.70` means vendor pays 70% of market price when buying.
- `trade_rate = 0.80` means vendor gives 80% of market value as trade credit.

---

## Category 3 — Vendor operations tables

---

### `vendor_inventory`

Every physical card a vendor owns. One row per unique copy (same card can have
multiple rows if the vendor owns multiple copies in different conditions or at
different prices). Soft-deleted when sold or traded — never hard deleted,
because transaction history references these rows.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `profile_id` | UUID | FK → profiles(id) NOT NULL | Owning vendor |
| `card_id` | VARCHAR | FK → cards(id) NOT NULL | Which card this copy is |
| `condition` | VARCHAR(20) | NOT NULL, CHECK IN ('psa_1','psa_2','psa_3','psa_4','psa_5','psa_6','psa_7','psa_8','psa_9','psa_10','bgs_1','bgs_2','bgs_3','bgs_4','bgs_5','bgs_6','bgs_7','bgs_8','bgs_9','bgs_9_5','bgs_10','cgc_1','cgc_2','cgc_3','cgc_4','cgc_5','cgc_6','cgc_7','cgc_8','cgc_9','cgc_9_5','cgc_10','sgc_1','sgc_2','sgc_3','sgc_4','sgc_5','sgc_6','sgc_7','sgc_8','sgc_9','sgc_10','raw_nm','raw_lp','raw_mp','raw_hp','raw_dmg') | Physical condition of this copy |
| `grading_service` | VARCHAR(10) | nullable, CHECK IN ('PSA','BGS','CGC','SGC') | Grading company — only set for graded cards |
| `cert_number` | VARCHAR(50) | nullable | Grading cert number — enables external verification on grading service website |
| `quantity` | INTEGER | NOT NULL DEFAULT 1, CHECK > 0 | Number of copies at this condition/price |
| `cost_basis` | DECIMAL(10,2) | nullable | What vendor paid — used for P&L calculations |
| `asking_price` | DECIMAL(10,2) | nullable | Listed sale price |
| `is_for_sale` | BOOLEAN | NOT NULL DEFAULT true | Whether vendor is willing to sell |
| `is_for_trade` | BOOLEAN | NOT NULL DEFAULT false | Whether vendor is willing to trade |
| `notes` | TEXT | nullable | Internal notes e.g. "slight crease on back", "signed by artist" |
| `photo_url` | VARCHAR(500) | nullable | S3 URL for vendor's own photo of this specific copy |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | Updated on any field change |
| `deleted_at` | TIMESTAMPTZ | nullable | Soft delete timestamp — NULL means active |

**Indexes:**
- B-tree on `profile_id`
- B-tree on `card_id`
- Partial index on `deleted_at` WHERE `deleted_at IS NULL` — all active-inventory
  queries filter on this

**Notes:**
- Always filter `WHERE deleted_at IS NULL` unless explicitly querying history.
- When quantity reaches 0 after a sale, set `deleted_at = now()` rather than
  deleting the row.
- `cert_number` is only meaningful when `grading_service` is set.

---

### `card_shows`

Upcoming and past card shows. Admin-seeded in MVP — no vendor self-serve
show creation.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `name` | VARCHAR(200) | NOT NULL | Show name e.g. "Miami Pokémon Card Show" |
| `organizer` | VARCHAR(200) | nullable | Organizer name or company |
| `venue_name` | VARCHAR(200) | NOT NULL | Venue name |
| `address` | VARCHAR(300) | NOT NULL | Street address |
| `city` | VARCHAR(100) | NOT NULL | |
| `state` | VARCHAR(50) | NOT NULL | |
| `zip_code` | VARCHAR(10) | nullable | For proximity matching against user ZIP |
| `date_start` | DATE | NOT NULL | Show start date |
| `date_end` | DATE | NOT NULL | Show end date (same as start for single-day shows) |
| `floor_plan_url` | VARCHAR(500) | nullable | Optional floor plan image URL |
| `is_verified` | BOOLEAN | NOT NULL DEFAULT false | Admin-verified show |
| `created_by` | UUID | FK → profiles(id) nullable | Admin user who created this record |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Index:** B-tree on `date_start` for chronological show listings.

---

### `vendor_show_registrations`

Links a vendor to a show they plan to attend. One row per vendor per show.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `profile_id` | UUID | FK → profiles(id) NOT NULL | Vendor attending |
| `show_id` | UUID | FK → card_shows(id) NOT NULL | Show being attended |
| `table_location` | VARCHAR(100) | nullable | e.g. "Row B, Table 12" — shown to customers on show floor map |
| `is_confirmed` | BOOLEAN | NOT NULL DEFAULT false | Admin confirmation of attendance |
| `active_deals` | JSONB | nullable DEFAULT '[]' | `[{message, expires_at}]` — current deal broadcasts |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Unique constraint:** `UNIQUE(profile_id, show_id)` — vendor can only register
once per show.

---

### `show_inventory_tags`

Junction table linking vendor inventory items to a specific show registration.
Represents "this vendor is bringing this card to this show." Drives the
customer-facing "search inventory at this show" feature.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `registration_id` | UUID | FK → vendor_show_registrations(id) ON DELETE CASCADE NOT NULL | The show registration this tag belongs to |
| `inventory_item_id` | UUID | FK → vendor_inventory(id) ON DELETE CASCADE NOT NULL | The inventory item being brought |

**Unique constraint:** `UNIQUE(registration_id, inventory_item_id)` — same item
can't be tagged twice for the same show.

**Notes:**
- Cascade delete: if a show registration is deleted, all its inventory tags are
  deleted automatically.
- Customer inventory search at a show: JOIN `show_inventory_tags` →
  `vendor_inventory` → `cards` WHERE `registration.show_id = ?` AND
  `cards.name ILIKE ?` AND `vendor_inventory.deleted_at IS NULL`.

---

### `transactions`

Header record for a sale, purchase, or trade. One row per transaction event.
Line items are in `transaction_items`.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `type` | VARCHAR(20) | NOT NULL, CHECK IN ('sale','purchase','trade') | Transaction type |
| `profile_id` | UUID | FK → profiles(id) NOT NULL | Vendor who performed this transaction |
| `show_id` | UUID | FK → card_shows(id) nullable | Show where transaction occurred — NULL for off-show transactions |
| `notes` | TEXT | nullable | Free text notes |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Index:** B-tree on `profile_id`, B-tree on `created_at DESC`.

---

### `transaction_items`

Line items for a transaction. A sale of one card has one item (direction=out).
A trade has at least two items — one or more going out, one or more coming in.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `transaction_id` | UUID | FK → transactions(id) ON DELETE CASCADE NOT NULL | Parent transaction |
| `inventory_item_id` | UUID | FK → vendor_inventory(id) nullable | The inventory item involved — nullable because item may be soft-deleted later |
| `card_id` | VARCHAR | FK → cards(id) NOT NULL | Denormalized card reference — always queryable even if inventory item is deleted |
| `direction` | VARCHAR(5) | NOT NULL, CHECK IN ('out','in') | `out` = sold/traded away, `in` = purchased/received in trade |
| `quantity` | INTEGER | NOT NULL DEFAULT 1, CHECK > 0 | |
| `unit_price` | DECIMAL(10,2) | NOT NULL | Price per unit at time of transaction |
| `condition` | VARCHAR(20) | NOT NULL | Condition at time of transaction — snapshot, not FK |

**Notes:**
- `card_id` is denormalized (also on `inventory_item_id → vendor_inventory.card_id`)
  intentionally. If the inventory item is later soft-deleted, `card_id` still
  lets you query what card was involved without a nullable join.
- `unit_price` for `direction=out` is the sale price. For `direction=in` it is
  the purchase price (cost basis).
- For a trade: `direction=out` items sum to what vendor gave up in value,
  `direction=in` items sum to what vendor received. The cash difference is
  the delta.

---

### `scan_jobs`

Audit log for every card scan attempt. Used for debugging misidentifications,
collecting training data for future ML model, and tracking scan method
performance.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `profile_id` | UUID | FK → profiles(id) NOT NULL | Vendor who performed the scan |
| `image_s3_key` | VARCHAR(500) | nullable | S3 key for the scanned image — nullable if image storage is async and fails |
| `scan_method` | VARCHAR(20) | NOT NULL, CHECK IN ('quick_scan','full_scan') | `quick_scan` = Google Vision OCR, `full_scan` = Claude Vision |
| `status` | VARCHAR(20) | NOT NULL, CHECK IN ('pending','processing','complete','failed') DEFAULT 'pending' | |
| `action` | VARCHAR(20) | NOT NULL, CHECK IN ('add_inventory','log_sale','log_purchase','log_trade') | What the vendor intended to do with this scan |
| `result_card_id` | VARCHAR | FK → cards(id) nullable | Card identified — NULL if scan failed |
| `result_confidence` | DECIMAL(4,3) | nullable, CHECK BETWEEN 0 AND 1 | Confidence score 0.0–1.0 |
| `result_raw` | JSONB | nullable | Full raw response from OCR/Claude — for debugging |
| `error_message` | TEXT | nullable | Error detail if status = 'failed' |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| `completed_at` | TIMESTAMPTZ | nullable | When status reached 'complete' or 'failed' |

---

## Category 4 — Collector operations tables

---

### `collector_inventory`

A collector's personal card collection. Distinct from `vendor_inventory` — this
is what the collector owns personally, not what they're selling professionally.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `profile_id` | UUID | FK → profiles(id) ON DELETE CASCADE NOT NULL | Owning collector |
| `card_id` | VARCHAR | FK → cards(id) NOT NULL | Which card |
| `condition` | VARCHAR(20) | NOT NULL | Same CHECK values as vendor_inventory.condition |
| `quantity` | INTEGER | NOT NULL DEFAULT 1, CHECK > 0 | |
| `is_for_trade` | BOOLEAN | NOT NULL DEFAULT false | Whether collector is open to trading this |
| `is_for_sale` | BOOLEAN | NOT NULL DEFAULT false | Whether collector is open to selling this |
| `asking_price` | DECIMAL(10,2) | nullable | Asking price if for sale |
| `notes` | TEXT | nullable | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Index:** B-tree on `profile_id`, B-tree on `card_id`.

**Notes:**
- Only visible to other users when `profiles.is_public = true` for this
  collector.
- Vendors can browse public collector inventories to find trade opportunities.

---

### `wishlists`

Cards a collector is looking for. Used to surface matching vendor inventory
at upcoming shows and trigger future notification features.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK DEFAULT gen_random_uuid() | |
| `profile_id` | UUID | FK → profiles(id) ON DELETE CASCADE NOT NULL | Collector who owns this wishlist entry |
| `card_id` | VARCHAR | FK → cards(id) NOT NULL | Card being sought |
| `max_price` | DECIMAL(10,2) | nullable | Maximum price collector is willing to pay |
| `preferred_condition` | VARCHAR(20) | nullable | Preferred condition — uses same CHECK values as vendor_inventory.condition |
| `notes` | TEXT | nullable | e.g. "must be 1st edition", "PSA 9 or better" |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Unique constraint:** `UNIQUE(profile_id, card_id)` — one wishlist entry per
card per collector.

---

## Relationship summary

```
auth.users (Supabase-owned)
  └── profiles (1:1)
        ├── vendor_profiles (1:0..1) — only for vendor/both users
        │     └── vendor_inventory (1:N)
        │           ├── show_inventory_tags (1:N)
        │           │     └── vendor_show_registrations (N:1)
        │           │           └── card_shows (N:1)
        │           └── transaction_items (1:N)
        │                 └── transactions (N:1)
        │                       └── card_shows (N:1, nullable)
        ├── collector_inventory (1:N)
        ├── wishlists (1:N)
        └── scan_jobs (1:N)

cards (catalog)
  ├── vendor_inventory (1:N)
  ├── collector_inventory (1:N)
  ├── transaction_items (1:N)
  ├── wishlists (1:N)
  └── price_snapshots (1:N)

sets → series (N:1)
cards → sets (N:1)
```

---

## Alembic migration checklist

The following changes are needed from the previously planned schema.
Run all migrations in order.

### Already applied (from Phase 0)
- [x] `series`, `sets`, `cards`, `price_snapshots` created
- [x] `public.profiles` created (original version)

### Needed now — run before any application code is built

```
001_extend_profiles.py
  ADD COLUMN tcg_interests JSONB DEFAULT '[]'
  ADD COLUMN is_public BOOLEAN DEFAULT false
  ADD COLUMN onboarding_complete BOOLEAN DEFAULT false
  ADD COLUMN zip_code VARCHAR(10)
  ADD COLUMN avatar_url VARCHAR(500)
  ADD COLUMN display_name VARCHAR(50)
  UPDATE constraint: role CHECK IN ('vendor','collector','both')

002_drop_customer_profiles.py
  DROP TABLE customer_profiles (if exists)

003_create_vendor_profiles.py
  CREATE TABLE vendor_profiles (all fields as above)

004_create_vendor_inventory.py
  CREATE TABLE vendor_inventory (all fields as above)
  CREATE indexes

005_create_card_shows.py
  CREATE TABLE card_shows

006_create_vendor_show_registrations.py
  CREATE TABLE vendor_show_registrations
  CREATE UNIQUE(profile_id, show_id)

007_create_show_inventory_tags.py
  CREATE TABLE show_inventory_tags
  CREATE UNIQUE(registration_id, inventory_item_id)

008_create_transactions.py
  CREATE TABLE transactions
  CREATE TABLE transaction_items

009_create_scan_jobs.py
  CREATE TABLE scan_jobs
  ADD COLUMN scan_method VARCHAR(20) — note: if scan_jobs already exists,
  this migration adds the scan_method column and backfills 'full_scan'

010_create_collector_inventory.py
  CREATE TABLE collector_inventory  (renamed from customer_inventory)

011_create_wishlists.py
  CREATE TABLE wishlists
  CREATE UNIQUE(profile_id, card_id)
```

### Scope rules for Alembic
- All migrations use `schema="public"` on every `op.create_table()` and
  `op.add_column()` call
- All check constraints use VARCHAR + CHECK, never PostgreSQL ENUM types
- All `downgrade()` functions must be fully implemented — never `pass`
- Run `alembic check` after every migration to verify no pending drift
- Never write a migration that touches the `auth` schema

---

## Key query patterns

### Find all inventory a vendor is bringing to a show
```sql
SELECT vi.*, c.name, c.image_url
FROM show_inventory_tags sit
JOIN vendor_show_registrations vsr ON sit.registration_id = vsr.id
JOIN vendor_inventory vi ON sit.inventory_item_id = vi.id
JOIN cards c ON vi.card_id = c.id
WHERE vsr.show_id = :show_id
  AND vsr.profile_id = :vendor_profile_id
  AND vi.deleted_at IS NULL;
```

### Search for a card across all vendors at a show
```sql
SELECT vi.*, c.name, c.image_url, p.display_name, vsr.table_location
FROM show_inventory_tags sit
JOIN vendor_show_registrations vsr ON sit.registration_id = vsr.id
JOIN vendor_inventory vi ON sit.inventory_item_id = vi.id
JOIN cards c ON vi.card_id = c.id
JOIN profiles p ON vi.profile_id = p.id
WHERE vsr.show_id = :show_id
  AND c.name ILIKE :search_query
  AND vi.is_for_sale = true
  AND vi.deleted_at IS NULL
ORDER BY vi.asking_price ASC;
```

### Get vendor's active inventory with current market price
```sql
SELECT vi.*, c.name, c.set_id, c.image_url,
       ps.market_price, ps.currency,
       (vi.asking_price - ps.market_price) AS price_delta
FROM vendor_inventory vi
JOIN cards c ON vi.card_id = c.id
LEFT JOIN price_snapshots ps ON ps.card_id = vi.card_id
  AND ps.source = 'tcgplayer'
  AND ps.variant = 'normal'
  AND ps.expires_at > now()
WHERE vi.profile_id = :profile_id
  AND vi.deleted_at IS NULL
ORDER BY vi.created_at DESC;
```

### Find vendors at upcoming shows who have a collector's wishlist cards
```sql
SELECT DISTINCT p.display_name, p.id AS profile_id,
       cs.name AS show_name, cs.date_start,
       vsr.table_location,
       c.name AS card_name, vi.asking_price, vi.condition
FROM wishlists w
JOIN cards c ON w.card_id = c.id
JOIN vendor_inventory vi ON vi.card_id = w.card_id
  AND vi.is_for_sale = true
  AND vi.deleted_at IS NULL
JOIN show_inventory_tags sit ON sit.inventory_item_id = vi.id
JOIN vendor_show_registrations vsr ON sit.registration_id = vsr.id
JOIN card_shows cs ON vsr.show_id = cs.id
  AND cs.date_start >= CURRENT_DATE
JOIN profiles p ON vi.profile_id = p.id
WHERE w.profile_id = :collector_profile_id
  AND (w.max_price IS NULL OR vi.asking_price <= w.max_price);
```
