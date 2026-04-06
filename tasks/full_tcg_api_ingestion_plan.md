# Full TCG API Ingestion Plan — Scrydex

## Overview

Replace the existing TCGdex catalog (English Pokémon only) with Scrydex as the primary card data source. Scrydex supports Pokémon (English + Japanese) and One Piece (English), giving the platform multi-game and multi-language coverage from a single API.

This document covers:
- Phase 1: Schema + full structural sync (Day 1)
- Phase 2: Lightweight price refresh (follow-on)

---

## Background

| | TCGdex (current) | Scrydex (new) |
|---|---|---|
| Games | Pokémon only | Pokémon, One Piece (+ MTG, Lorcana, Gundam) |
| Languages | English only | English + Japanese |
| Pricing | Via separate sources | Embedded in card variants |
| Status | Freeze syncs | New source of truth |

The existing `cards`, `sets`, and `series` tables remain in the database but TCGdex sync jobs are removed from the beat schedule. `cards_v2` and `expansions_v2` are the new catalog layer. Inventory FK migration (from `cards.id` → `cards_v2.id`) is a separate future phase.

---

## Phase 1 — Schema & Full Structural Sync

### Deliverables

1. **Migration 0016** — `expansions_v2` + `cards_v2` tables
2. **`backend/app/tasks/scrydex_sync.py`** — three Celery tasks
3. **Freeze TCGdex beat schedule** — remove entries from `celery_app.py`
4. **Settings update** — add `scrydex_api_key` + `scrydex_team_id` to `session.py`

---

### Migration 0016 — `expansions_v2`

```sql
CREATE TABLE expansions_v2 (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id       VARCHAR     NOT NULL,
    game              VARCHAR     NOT NULL,
    name              VARCHAR     NOT NULL,
    series            VARCHAR,                -- Pokémon only: "Scarlet & Violet"
    code              VARCHAR,                -- Short code e.g. "BLK", "OP13"
    type              VARCHAR,                -- One Piece only: "Booster Pack"
    total             INTEGER,
    printed_total     INTEGER,                -- Pokémon only
    language          VARCHAR     NOT NULL,
    language_code     VARCHAR(5)  NOT NULL,
    release_date      DATE,
    is_online_only    BOOLEAN,                -- Pokémon only
    logo_url          VARCHAR,
    symbol_url        VARCHAR,                -- Pokémon only
    translation       VARCHAR,                -- English name for non-English sets
    last_synced_at    TIMESTAMP   NOT NULL,

    CONSTRAINT uq_expansions_v2_game_external_id UNIQUE (game, external_id),
    CONSTRAINT ck_expansions_v2_game CHECK (game IN ('pokemon', 'onepiece'))
);
```

**Key design decisions:**
- UUID PK (not external_id) — Scrydex IDs are unique within a game, not guaranteed across games
- `UNIQUE(game, external_id)` is the business key used for all upserts
- Nullable game-specific columns rather than separate tables — consistent with existing `cards` table pattern and no ENUM rule

---

### Migration 0016 — `cards_v2`

```sql
CREATE TABLE cards_v2 (
    -- Shared fields
    id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id              VARCHAR     NOT NULL,
    game                     VARCHAR     NOT NULL,
    expansion_id             UUID        NOT NULL REFERENCES expansions_v2(id),
    name                     VARCHAR     NOT NULL,
    number                   VARCHAR,
    printed_number           VARCHAR,
    rarity                   VARCHAR,
    rarity_code              VARCHAR,
    language                 VARCHAR     NOT NULL,
    language_code            VARCHAR(5)  NOT NULL,
    expansion_sort_order     INTEGER,
    images                   JSONB,      -- [{type, small, medium, large}]
    variants                 JSONB,      -- Full API response incl. prices (see note)
    price_data_uploaded_at   TIMESTAMP,  -- NULL until first sync; updated on every sync
    last_synced_at           TIMESTAMP   NOT NULL,

    -- Pokémon-only fields
    supertype                VARCHAR,    -- "Pokémon" | "Trainer" | "Energy"
    subtypes                 JSONB,      -- ["Stage 2"]
    types                    JSONB,      -- ["Fire"]
    hp                       VARCHAR,    -- Stored as string (API returns string)
    level                    VARCHAR,    -- Older sets only
    evolves_from             JSONB,      -- Array of parent names
    abilities                JSONB,      -- [{type, name, text}]
    attacks                  JSONB,      -- [{cost, converted_energy_cost, name, text, damage}]
    weaknesses               JSONB,
    resistances              JSONB,
    retreat_cost             JSONB,      -- Array of energy strings
    national_pokedex_numbers JSONB,      -- [6]
    flavor_text              TEXT,
    regulation_mark          VARCHAR,
    artist                   VARCHAR,

    -- One Piece-only fields
    cost                     VARCHAR,
    power                    VARCHAR,
    attribute                VARCHAR,    -- "Strike" | "Slash"
    card_type                VARCHAR,    -- "Character" | "Leader" | "Event" | "Stage"
    colors                   JSONB,      -- ["Green"]
    rules                    JSONB,      -- Array of rule text strings
    printings                JSONB,      -- Expansion codes the card appears in
    tags                     JSONB,

    CONSTRAINT uq_cards_v2_game_external_id UNIQUE (game, external_id),
    CONSTRAINT ck_cards_v2_game CHECK (game IN ('pokemon', 'onepiece'))
);

CREATE INDEX ix_cards_v2_expansion_id ON cards_v2 (expansion_id);
CREATE INDEX ix_cards_v2_name_trgm ON cards_v2 USING GIN (name gin_trgm_ops);
```

**On `variants` JSONB content:**
The full API variant object is stored as-is, including any embedded price fields. `price_data_uploaded_at` is set to the current timestamp on every write so consumers know how stale the price data is. A `NULL` value means the card has been inserted but no price data has been synced yet (edge case — normal syncs always include variants).

---

### Celery Tasks — `backend/app/tasks/scrydex_sync.py`

#### Task naming (follows `domain.action` convention)

```
scrydex.sync_expansions             — fetch + upsert all expansions for one game
scrydex.sync_cards_for_expansion    — fetch + upsert all cards for one expansion
scrydex.full_sync                   — orchestrator: expansions → fan out cards
```

#### `scrydex.sync_expansions(game: str)`

1. `GET /v1/expansions?page_size=100` (paginated) for the given game
2. Upsert each expansion into `expansions_v2` on `UNIQUE(game, external_id)`
3. Updates `last_synced_at` on every upsert

#### `scrydex.sync_cards_for_expansion(expansion_external_id: str, game: str)`

1. `GET /v1/expansions/{external_id}/cards?page_size=100` (paginated)
2. Resolve `expansion_id` UUID from `expansions_v2` via `(game, external_id)`
3. Upsert each card into `cards_v2` on `UNIQUE(game, external_id)`
4. Sets both `last_synced_at` and `price_data_uploaded_at` on every upsert

#### `scrydex.full_sync()`

1. For each game in `['pokemon', 'onepiece']`:
   a. Call `sync_expansions(game)`
2. Query `expansions_v2` for all rows
3. Dispatch one `sync_cards_for_expansion` task per expansion

**Error handling (following project conventions):**
- Failed expansion fetch: log set ID and continue — do not abort full run
- Failed card fetch: log card ID and continue — do not block the batch
- All tasks must catch exceptions and log with context — no silent failures
- All tasks are idempotent — safe to re-run with same inputs

#### Beat schedule addition to `celery_app.py`

```python
"scrydex-full-sync": {
    "task": "scrydex.full_sync",
    "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Sunday 4am
},
```

#### Beat schedule removals from `celery_app.py`

```python
# REMOVE — TCGdex syncs frozen
"catalog-sync-new-sets"    # was: catalog.sync_new_sets, daily 2am
"catalog-delta-sync"       # was: catalog.delta_sync_cards, daily 3am
```

`prices-refresh` (existing `price_snapshots` from TCGplayer/Cardmarket) is left unchanged — it references `cards.id` and is unrelated to v2.

---

### Settings update — `session.py`

```python
scrydex_api_key:  Optional[str] = None
scrydex_team_id:  Optional[str] = None
```

Both sourced from `backend/.env`. Injected as headers on every Scrydex request:
```
X-Api-Key:  {scrydex_api_key}
X-Team-ID:  {scrydex_team_id}
```

---

### Games covered (Phase 1)

| Game | Languages | Source endpoint |
|---|---|---|
| Pokémon | English + Japanese | `https://api.scrydex.com/pokemon/v1/` |
| One Piece | English only | `https://api.scrydex.com/onepiece/v1/` |

---

### Credit budget estimate

| Operation | Estimated requests |
|---|---|
| Pokémon expansions (~1,000 total, 100/page) | ~10 |
| One Piece expansions (~100 total, 100/page) | ~2 |
| Pokémon cards (~900 sets × avg 150 cards / 100 per page) | ~1,350 |
| One Piece cards (~100 sets × avg 100 cards / 250 per page) | ~40 |
| **Total — initial full sync** | **~1,400 credits** |

Monthly recurring (weekly full sync, mostly no-ops on unchanged data): ~1,400 × 4 = ~5,600 credits/month. Well within the 50,000/month plan.

---

### Initial data load

After deploying migration 0016 and the new Celery tasks, trigger the initial sync manually:

```bash
celery -A app.celery_app call scrydex.full_sync
```

---

## Phase 2 — Lightweight Price Refresh

### Motivation

Card structure (name, attacks, HP, rarity) changes almost never — a weekly sync is sufficient.
Prices change daily. Running a full structural sync just to get fresh prices is wasteful.

### New task — `scrydex.refresh_prices`

```
scrydex.refresh_prices   — re-fetch variants (prices only) for all cards in cards_v2
```

#### Behavior

1. Query all `(game, external_id)` pairs from `cards_v2`
2. For each card: `GET /{game}/v1/cards/{external_id}?select=variants`
   - Uses `select=variants` to minimize response size and credit cost
3. Update `cards_v2.variants` and `cards_v2.price_data_uploaded_at` only — no other columns touched
4. Runs independently of `full_sync` — does not re-pull structural fields

#### Beat schedule

```python
"scrydex-refresh-prices": {
    "task": "scrydex.refresh_prices",
    "schedule": crontab(hour="*/6", minute=0),  # Every 6 hours (adjust to taste)
},
```

#### Credit cost (Phase 2)

1 credit per card request. At ~90,000 cards (rough estimate for Pokémon EN+JP + One Piece EN):
- Per 6-hour run: ~90,000 credits
- Per month: ~90,000 × 4/day × 30 days = high

**This makes the `select=variants` optimization critical.** The Phase 2 implementation must confirm whether Scrydex counts `select`-filtered requests at the same 1 credit rate or at a reduced rate. If per-card requests are prohibitive, the alternative is to re-fetch at the expansion level (`/expansions/{id}/cards?select=variants&page_size=100`) which amortizes credits across 100 cards per request — reducing the cost by ~100×.

**Decision to make at Phase 2 time:**
- Per-card refresh (maximum freshness, higher credit cost)
- Per-expansion refresh (100 cards/request, lower cost, slightly less targeted)
- Hybrid: only refresh cards that have active inventory (most practical)

The hybrid approach — refreshing prices only for cards that appear in `vendor_inventory` or `collector_inventory` — is likely the right long-term answer since price freshness matters most for cards people actually own or are selling.

---

## Future phases (not in scope yet)

- **Inventory FK migration** — add nullable `card_v2_id UUID → cards_v2.id` to `vendor_inventory` and `collector_inventory`; populate from existing `card_id` matches; eventually make NOT NULL and drop `card_id`
- **Drop TCGdex tables** — once inventory migration is complete and no code references `cards`/`sets`/`series`
- **One Piece Japanese** — add `'JP'` language to the One Piece sync once confirmed available via Scrydex
- **Additional games** — Scrydex supports MTG, Lorcana, Gundam, Riftbound; same `cards_v2`/`expansions_v2` schema accommodates them with new `game` values
- **Dedicated `price_snapshots_v2` table** — normalized price history if point-in-time queries become a product requirement
