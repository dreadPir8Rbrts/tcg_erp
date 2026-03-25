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
**Rule:** Never pass a plain Python string as `server_default` for JSONB columns. Use `sa.text("'{}'")`  so SQLAlchemy treats it as a SQL expression rather than a literal — plain strings get triple-quoted into `'''{}'''` which is invalid JSON.
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
**Rule:** Never use `lazy="dynamic"` on SQLAlchemy 2.0 relationships — it raises `InvalidRequestError` at mapper init. Use `lazy="select"` (default) for standard loading. Use `lazy="dynamic"` only existed in 1.x.
**Context:** All SQLAlchemy model files with relationships

### 2026-03-25 — Cross-schema FK strings in SQLAlchemy ORM cause NoReferencedTableError
**Rule:** Do not declare `ForeignKey("public.cards.id")` string references in SQLAlchemy model columns when the target model is defined with `schema="public"`. SQLAlchemy fails to resolve the table at flush time. The FK is already enforced at the database level by the migration — omit it from the ORM column definition and add a comment: `# FK enforced at DB level`.
**Context:** `app/models/inventory.py`, any model referencing catalog tables

### 2026-03-18 — pydantic-settings rejects undeclared env vars
**Rule:** Any env var present in `.env` must have a corresponding field in the `Settings` class, or pydantic-settings raises `extra_forbidden`. Add all expected env vars as fields with defaults where appropriate (e.g. `redis_url: str = "redis://localhost:6379/0"`).
**Context:** `backend/app/db/session.py`, any Settings class
