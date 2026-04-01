# CardOps — Lessons Learned

> Updated after every user correction. Read at the start of each session.
> Write rules, not descriptions. Good: "Always do X." Bad: "I forgot to do X once."

---

## Format
```
### [date] — [short title]
**Rule:** The specific rule to follow going forward
**Context:** Where this applies
```

---

## CardOps-specific rules (always in force)

### 2026-03-28 — Quick Scan failure mode shifted after OCR fixes
**Rule:** After OCR parsing improvements, the dominant failure mode for Quick Scan shifted from `catalog_no_match` (OCR extracts wrong text) to `catalog_wrong_match` (OCR extracts correct name but wrong edition matched). Before fixing catalog matching, check the failure_reason breakdown — if `catalog_wrong_match` dominates, the problem is edition disambiguation, not parsing.
**Context:** `app/services/ocr.py`, `app/services/catalog_match.py`, `scripts/analyze_failures.py`

### 2026-03-28 — Quick Scan edition disambiguation is the current accuracy ceiling
**Rule:** The remaining wrong matches share a pattern: correct card name + correct or absent local_id, but multiple sets contain the same card and the matcher picks the wrong edition. Available signals for disambiguation: `card_count_official` (pins the set if OCR reads the denominator cleanly), HP (works when cards differ in HP across editions), and era signals (not yet implemented). Tier 2b fuzzy name helps when names differ across candidates but not for identical reprints.
**Context:** `app/services/catalog_match.py` Tier 2 + Tier 2b

### 2026-03-28 — OCR parser: Pocket cards print stage + name on one line
**Rule:** Pokémon TCG Pocket cards render "BASIC [name]" or "STAGE [name]" on a single line. The name parser must detect this inline-prefix pattern and extract the name from group 1, not treat the whole line as the name. Pattern: `^(?:BASIC|STAGE...)\s+(.+)$`.
**Context:** `app/services/ocr.py` `_INLINE_PREFIX_PATTERN`

### 2026-03-28 — OCR parser: old-format cards include level in name line
**Rule:** DPt/Platinum era and older cards print the level on the card face adjacent to the name (e.g. "Aron x.15", "Bronzong LV.49", "Froslass .44"). Always strip ` LV.X`, ` x.X`, ` V.X`, ` .X` suffixes after extracting the name. The DB stores names without level indicators.
**Context:** `app/services/ocr.py` `_strip_level_indicator()`

### 2026-03-28 — Quick Scan gold set is ~36 cards, not ~42
**Rule:** --generate-gold targets 2 cards per series (21 series = ~42 cards), but some cards in the gold set may lack `image_url` and are silently skipped by `load_gold_set()`. Actual gold set size will be slightly under target. This is expected — do not inflate the target to compensate.
**Context:** `scripts/benchmark_scanners.py` `load_gold_set()`

### Always check the spec before schema decisions
**Rule:** Before creating, modifying, or referencing any table or column, verify it exists in `CardOps-Project-Spec.md` Section 4. If it doesn't exist in the spec, stop and flag it.
**Context:** All migrations, all model files

### price_snapshots upsert target
**Rule:** All inserts to `price_snapshots` must use `ON CONFLICT (card_id, source, variant) DO UPDATE SET`. Never plain INSERT.
**Context:** `tasks/price_sync.py`, any code writing to `price_snapshots`

### Never touch auth schema
**Rule:** The Supabase `auth` schema is fully managed by Supabase. Never write migrations, queries, or code that modifies it. Application data hangs off `public.profiles`, not `auth.users` directly.
**Context:** All migrations, all model files

### Soft deletes on inventory_items
**Rule:** Never hard delete from `inventory_items`. Always set `deleted_at = now()`. Always filter `WHERE deleted_at IS NULL` in queries unless intentionally including deleted records for accounting/history.
**Context:** All inventory-related routes and services

### VARCHAR not ENUM for extensible fields
**Rule:** Use `VARCHAR` + check constraints (not PostgreSQL `ENUM` types) for fields that will expand in v2 (tcg type, price variant, condition). This avoids `ALTER TYPE` migrations when One Piece support is added.
**Context:** All migrations

---

## Session corrections

### 2026-03-27 — asyncio.create_task() is unreliable for background work in FastAPI
**Rule:** Never use `asyncio.create_task()` inside a FastAPI route for background I/O that must complete reliably. If the event loop shuts down mid-task, the work is silently lost. Use FastAPI's `BackgroundTasks` parameter instead — it guarantees the task runs after the response is sent and is tracked by the framework.
**Context:** `app/api/scans.py`, any route that needs post-response background work

### 2026-03-27 — Do not set Content-Type when using FormData in fetch
**Rule:** When posting `FormData` (file upload) via `fetch`, never manually set the `Content-Type` header. The browser must set it automatically to include the multipart boundary string. Setting it manually breaks the upload with a 400 or 422 error.
**Context:** `frontend/lib/api.ts` `identifyCard()`, any multipart fetch call

### 2026-03-27 — FastAPI UploadFile requires python-multipart
**Rule:** Any FastAPI route that uses `UploadFile` or `File(...)` requires `python-multipart` to be installed. Without it, FastAPI raises `RuntimeError` at startup and the server fails to load. Add `python-multipart==x.x.x` to `requirements.txt`.
**Context:** `backend/requirements.txt`, any route with file upload params

### 2026-03-27 — logging.basicConfig required for app logger output in uvicorn
**Rule:** uvicorn's `--log-level debug` only configures uvicorn's own loggers. Application `logging.getLogger(__name__)` calls are silent unless `logging.basicConfig(level=logging.INFO)` is called in `main.py` before the FastAPI app is created.
**Context:** `backend/app/main.py`

### 2026-03-27 — Claude Vision may return JSON wrapped in markdown code fences
**Rule:** Claude models (especially newer versions) sometimes wrap JSON responses in ` ```json ... ``` ` code fences even when instructed not to. Always strip markdown fences before `json.loads()`. Pattern: if `raw.startswith("```")`, split on ` ``` `, drop the `json` tag, strip whitespace, then parse.
**Context:** `app/api/scans.py` `_call_claude()`, any route that parses Claude JSON output

### 2026-03-27 — max_tokens too low causes empty Claude response
**Rule:** Setting `max_tokens` too aggressively low can cause Claude to return a truncated or empty response body (HTTP 200 but empty content), which causes `json.loads` to fail with `Expecting value: line 1 column 1`. Always set max_tokens with headroom above the expected response size. For the identify prompt (4 fields): use 150, not 100.
**Context:** `app/api/scans.py` `_call_claude()`

### 2026-03-27 — Physical card set code ≠ TCGdex set_id; use card name + number for lookup
**Rule:** The set abbreviation printed on a physical card (e.g., "SSP") does not reliably map to the TCGdex `set_id` (e.g., "sv8"). Claude Vision reads the physical abbreviation. Never rely on Claude's set_code alone for catalog lookup. Use card_name + local_id as the primary DB lookup (both are printed clearly in large text). Keep set_code + local_id as a fallback only.
**Context:** `app/api/scans.py` `identify_card()`

### 2026-03-27 — TCGdex local_id strips leading zeros; physical card does not
**Rule:** TCGdex stores card numbers without leading zeros (e.g., "44") but physical cards print them with padding (e.g., "044/191"). Claude reads the padded form. Always normalize by trying both the raw value and `lstrip("0")` form in DB queries. Use `Card.local_id.in_([local_id, local_id.lstrip("0") or "0"])`.
**Context:** `app/api/scans.py` `_normalize_local_id()`, any lookup using Claude-provided local_id

### 2026-03-27 — Redis phash cache serves stale wrong results after fixing misidentification
**Rule:** After fixing a scan misidentification bug, always flush the scan cache before retesting: `redis-cli --scan --pattern "scan_cache:*" | xargs redis-cli DEL`. A cached wrong result will keep returning the incorrect card_id regardless of prompt or model changes.
**Context:** Local dev, any time scan identification logic is changed

### 2026-03-27 — State variable name collision with React setter
**Rule:** Never name a state variable with the same identifier as a React useState setter from another state declaration. E.g. `const [name, setName]` and `const [setName, setSetName]` in the same component causes a compile error. Use distinct names like `setQuery` for set-name search state.
**Context:** All React components with multiple useState declarations

### 2026-03-27 — Celery shared_task uses AMQP default broker when celery app not initialized first
**Rule:** Never use `@shared_task` dispatch (`task.delay()`) from FastAPI routes when `celery_app.py` may not have been imported first. Instead, use `celery_app.app.send_task("task.name", args=[...])` in the route — this dispatches by name through the explicitly configured broker (Redis) regardless of import order.
**Context:** `app/api/scans.py`, any FastAPI route that dispatches Celery tasks

### 2026-03-27 — SQLAlchemy session caches stale data in WebSocket polling loop
**Rule:** Always call `db.expire_all()` before each `db.get()` inside a WebSocket polling loop. SQLAlchemy's identity map returns cached objects and will never see updates made by other processes (e.g. Celery workers) without expiring the cache first.
**Context:** `app/api/scans.py` WebSocket endpoint, any polling loop using a shared session

### 2026-03-27 — S3 presigned PUT returns 400 when AWS_REGION is wrong
**Rule:** Always verify `AWS_REGION` in `backend/.env` matches the actual bucket region. The error message from S3 XML response body contains the correct region: `<Region>us-east-2</Region>`. Check the response body in DevTools Network tab when debugging S3 400 errors.
**Context:** `backend/.env`, `app/api/scans.py`, `app/api/vendor.py`

### 2026-03-27 — S3 CORS must use virtual-hosted style URL, not path-style
**Rule:** Never set `endpoint_url` on the boto3 S3 client when generating presigned URLs for browser upload. Setting `endpoint_url` switches to path-style (`s3.region.amazonaws.com/bucket`) which may not match the bucket's CORS config. Without `endpoint_url`, boto3 generates virtual-hosted style (`bucket.s3.region.amazonaws.com`) which is where the CORS policy is applied.
**Context:** `app/api/scans.py`, `app/api/vendor.py` — any presigned URL generation

### 2026-03-27 — S3 Block Public Access must be disabled before bucket policy takes effect
**Rule:** When adding a bucket policy that allows public `s3:GetObject`, first disable "Block public access" in the bucket settings. The block settings override bucket policies — the policy will not save or take effect while block public access is enabled.
**Context:** AWS S3 console, profile image setup

### 2026-03-27 — Cross-schema FK on ScanJob.vendor_id causes NoReferencedTableError
**Rule:** Same rule as inventory_items — never declare `ForeignKey("public.vendor_profiles.id")` in the ScanJob ORM model. Remove FK from the mapped_column and add `# FK enforced at DB level` comment. The DB migration already enforces the constraint.
**Context:** `app/models/scans.py`

### 2026-03-27 — websockets package required for uvicorn WebSocket support
**Rule:** Install `websockets==12.0` explicitly (added to requirements.txt). Do not use `uvicorn[standard]` (requires Rust/maturin). Without `websockets`, uvicorn logs "No supported WebSocket library detected" and WebSocket routes return 404.
**Context:** `backend/requirements.txt`

### 2026-03-27 — Next.js requires explicit hostname allowlist for external images
**Rule:** Any external image hostname used with `next/image` must be added to `images.remotePatterns` in `next.config.mjs`. Required entries for this project: `assets.tcgdex.net` (card images), `*.amazonaws.com` (S3 profile images). Add new entries whenever a new image source is introduced.
**Context:** `frontend/next.config.mjs`

### 2026-03-24 — TCGdex SDK raises HTTPError on 404, does not return None
**Rule:** Wrap all `sdk.card.getSync()`, `sdk.set.getSync()`, and `sdk.serie.getSync()` calls in `try/except (urllib.error.HTTPError, urllib.error.URLError)`. The SDK raises rather than returns None for missing resources. Log the card/set ID and continue — never let a single 404 abort the run.
**Context:** `seed_catalog.py`, `app/tasks/catalog_sync.py`

### 2026-03-24 — Celery worker must be running before firing tasks
**Rule:** Always start the Celery worker (`celery -A celery_app worker`) in a separate terminal before calling `.delay()` on any task. Firing tasks without a running worker raises `kombu.exceptions.OperationalError: Connection refused`.
**Context:** Local development, task testing

### 2026-03-18 — Python 3.9 type union syntax
**Rule:** This project runs on Python 3.9. Never use `X | None` union syntax — it requires Python 3.10+. Always use `Optional[X]` from `typing` instead. Apply to all type hints: function signatures, Pydantic models, SQLAlchemy mapped columns.
**Context:** All Python files

### 2026-03-18 — tcgdex-sdk version pinning
**Rule:** Pin `tcgdex-sdk==2.2.1` in requirements.txt. Version 2.3.0 does not exist on PyPI. Verify package versions exist on PyPI before pinning.
**Context:** `backend/requirements.txt`

### 2026-03-18 — uvicorn extras require Rust
**Rule:** Use `uvicorn==x.x.x` (no `[standard]` extras) in requirements.txt. The `[standard]` extras pull in `watchfiles` which requires compiling Rust (maturin). Until Rust toolchain is confirmed, omit extras.
**Context:** `backend/requirements.txt`

### 2026-03-18 — Supabase MCP HTTP OAuth failure
**Rule:** Do not use HTTP transport for the Supabase MCP server. Claude Code's HTTP MCP transport attempts OAuth discovery (hits `/.well-known/oauth-authorization-server`) which returns 404 on Supabase's server. Use stdio transport with `@supabase/mcp-server-supabase` npm package and pass the access token via `env.SUPABASE_ACCESS_TOKEN`. See `.mcp.json`.
**Context:** MCP configuration

### 2026-03-18 — URL-encode special characters in Postgres connection strings
**Rule:** Special characters in database passwords must be URL-encoded when placed in a connection string URI. Common: `$` → `%24`, `@` → `%40`, `#` → `%23`, `%` → `%25`. Use `python3 -c "from urllib.parse import quote; print(quote('password', safe=''))"` to encode.
**Context:** `backend/.env`, any connection string

### 2026-03-18 — Supabase requires two connection URLs
**Rule:** Always configure two separate database URLs: `DATABASE_URL` (transaction pooler, port 6543) for the running app, and `MIGRATION_DATABASE_URL` (direct connection, port 5432) for Alembic migrations. PgBouncer transaction mode cannot run DDL. Check the IPv4 box in Supabase dashboard for both URLs.
**Context:** `backend/.env`, `backend/app/db/env.py`

### 2026-03-19 — Alembic server_default for JSONB must use sa.text()
**Rule:** Never pass a plain Python string as `server_default` for JSONB columns. Use `sa.text("'{}'")` so SQLAlchemy treats it as a SQL expression rather than a literal — plain strings get triple-quoted into `'''{}'''` which is invalid JSON.
**Context:** All migration files with JSONB columns

### 2026-03-19 — Alembic env.py must not use config.set_main_option() with URL-encoded passwords
**Rule:** Do not call `config.set_main_option("sqlalchemy.url", url)` in `env.py` when the URL contains URL-encoded characters (e.g. `%24`). Python's `configparser` interprets `%` as interpolation syntax and raises `ValueError`. Instead, build the engine directly with `create_engine(migration_url)` in `run_migrations_online()` and pass `url=migration_url` in `run_migrations_offline()`.
**Context:** `backend/app/db/env.py`

### 2026-03-25 — Supabase uses ES256 asymmetric JWT signing on new projects
**Rule:** Do not use HS256 + shared secret for JWT verification. New Supabase projects use ECC (P-256) asymmetric signing (ES256). Always verify JWTs by fetching the JWKS endpoint at `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` and using `jose.jwk.construct()`. Never store a JWT secret in `.env` for this purpose.
**Context:** `backend/app/dependencies.py`

### 2026-03-25 — Supabase auth trigger does not backfill existing users
**Rule:** The `on_auth_user_created` trigger only fires for new signups. Any user created before the trigger was installed will not have a `public.profiles` row. Manually insert missing rows via Supabase SQL editor: `INSERT INTO public.profiles (id, role) VALUES ('<user-id>', 'vendor') ON CONFLICT (id) DO NOTHING`.
**Context:** Supabase Auth setup, Phase 1 onboarding

### 2026-03-25 — SQLAlchemy 2.0 does not support lazy="dynamic" on relationships
**Rule:** Never use `lazy="dynamic"` on SQLAlchemy 2.0 relationships — it raises `InvalidRequestError` at mapper init. Use `lazy="select"` (default) for standard loading.
**Context:** All SQLAlchemy model files with relationships

### 2026-03-25 — Cross-schema FK strings in SQLAlchemy ORM cause NoReferencedTableError
**Rule:** Do not declare `ForeignKey("public.cards.id")` or `ForeignKey("public.vendor_profiles.id")` string references in SQLAlchemy model columns when the target model is defined with `schema="public"`. SQLAlchemy fails to resolve the table at flush time. The FK is already enforced at the database level by the migration — omit it from the ORM column definition and add a comment: `# FK enforced at DB level`.
**Context:** `app/models/inventory.py`, `app/models/scans.py`, any model referencing cross-schema tables

### 2026-03-26 — shadcn v4 + Tailwind v3 CSS conflict in Next.js 14
**Rule:** `create-next-app@14` installs Tailwind v3. `npx shadcn@latest init` installs shadcn v4 which generates Tailwind v4 syntax (`@import "shadcn/tailwind.css"`, `@import "tw-animate-css"`). These are incompatible with Tailwind v3. Fix: rewrite `globals.css` to use `@tailwind base/components/utilities` directives and HSL CSS variables, and update `tailwind.config.ts` with the full shadcn color token map. Do not use the shadcn v4 import syntax with Tailwind v3.
**Context:** `frontend/app/globals.css`, `frontend/tailwind.config.ts`

### 2026-03-18 — pydantic-settings rejects undeclared env vars
**Rule:** Any env var present in `.env` must have a corresponding field in the `Settings` class, or pydantic-settings raises `extra_forbidden`. Add all expected env vars as fields with defaults where appropriate (e.g. `redis_url: str = "redis://localhost:6379/0"`).
**Context:** `backend/app/db/session.py`, any Settings class
