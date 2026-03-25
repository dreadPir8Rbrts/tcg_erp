# CardOps — Claude Code Instructions

## Session start checklist
Before doing anything else, every session:
1. Read `CardOps-Project-Spec_v2.md` — especially Section 10 (Decisions Log)
2. Read `tasks/lessons.md` — patterns and corrections from prior sessions
3. Read `tasks/todo.md` — current task state and active phase
4. Identify the current phase from the spec before writing any code

## Project spec
`CardOps-Project-Spec_v2.md` is the source of truth for all architectural decisions.
All entries in Section 10 (Decisions Log) are final unless the user explicitly overrides them in this session.
When in doubt about a design choice, check the spec before proceeding.

## Repository structure
```
cardops/
  backend/          # FastAPI + Python
  frontend/         # Next.js 14
  tasks/            # Session planning and lessons
  CardOps-Project-Spec_v2.md
  CLAUDE.md
```

## Tech stack — quick reference
- **Backend:** FastAPI, Python, SQLAlchemy, Alembic, Celery + Redis
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui, React Query, Zustand
- **Database:** Supabase (PostgreSQL) — `public` schema only
- **Auth:** Supabase Auth — `auth.users` is managed by Supabase, never by us
- **AI:** Claude API `claude-sonnet-4-20250514` for card scan/identification
- **Catalog:** TCGdex via `tcgdex-sdk` Python package
- **Storage:** AWS S3 for vendor card photos only (card images reference TCGdex CDN directly)

## Current phase
**Phase 0 — Catalog foundation**
Do not scaffold auth, vendor profiles, or any app features yet.
Current work: Supabase project setup, Alembic migrations, seed_catalog.py, Celery beat jobs.
See `tasks/todo.md` for active checklist.

## Hard rules — never violate these
- Never modify the Supabase `auth` schema
- Never hard delete `inventory_items` — use `deleted_at` soft delete only
- Never store pricing data on the `cards` table — prices live in `price_snapshots` only
- Never re-host card images — reference TCGdex CDN URLs directly
- Never use PostgreSQL ENUM types — use VARCHAR + check constraints (easier to extend for One Piece v2)
- Never run migrations that touch more than the `public` schema
- Always scope Alembic migrations to `public` schema

## Schema guardrails
- `price_snapshots` requires `UNIQUE(card_id, source, variant)` — use upsert on conflict
- `cards.variants` JSONB shape: `{"normal": bool, "holo": bool, "reverse": bool, "firstEdition": bool}`
- `public.profiles` is the bridge between `auth.users` and app tables — vendor/customer profiles FK to this
- `catalog_overrides` table is planned but not yet defined — do not create it, do not reference it

## Code conventions

### Python / Backend
- **Python 3.9** — use `Optional[X]` not `X | None`, use `List[X]` not `list[X]`
- Type hints on all functions — no untyped code
- Route handlers are sync (psycopg2); switch to async when asyncpg is adopted
- Use `SQLAlchemy.merge()` for all catalog upserts (idempotent, safe to re-run)
- Pydantic v2 for request/response models
- Raise `HTTPException` with explicit status codes — no bare `raise`
- Environment variables via `pydantic-settings` `BaseSettings` class — all env vars must be declared as fields
- Never hardcode credentials or connection strings

### TypeScript / Frontend
- Strict mode enabled — no `any` types
- React Query for all server state — no raw `fetch` in components
- shadcn/ui components before writing custom UI
- Route handlers in `app/api/` for BFF calls to FastAPI
- Zustand stores in `lib/stores/`

### General
- No temporary fixes or TODO comments left in committed code
- Every new file gets a docstring / top-level comment explaining its purpose
- Tests for any non-trivial business logic (inventory updates, transaction creation, scan pipeline)

## Migration procedure
Any task requiring a schema change must follow this sequence:
1. Flag the migration to the user before writing it
2. Write migration in `backend/app/db/versions/` (naming: `YYYYMMDD_NNNN_description.py`)
3. Run `alembic upgrade head` using `MIGRATION_DATABASE_URL` (direct connection, not pooler)
4. Never run migrations against production without explicit user approval

## Workflow
See `tasks/workflow.md` for the full task and self-improvement workflow.

## When to stop and check in
Stop and flag to the user (do not proceed autonomously) if:
- A task requires a schema migration not already planned in the spec
- A fix would touch the `auth` schema
- A dependency is not in the approved tech stack
- A design decision conflicts with Section 10 of the spec
- You are more than 2 steps into a plan that wasn't reviewed
