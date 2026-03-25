# Database & Migrations — Claude Code Instructions

> Extends `backend/CLAUDE.md`. Rules here apply to everything inside `backend/app/db/`.

## Alembic setup (actual — as built)
- `alembic.ini` at `backend/` root — `script_location = app/db`
- Migration environment: `backend/app/db/env.py` (NOT `alembic_env.py`)
- Migration template: `backend/app/db/script.py.mako`
- Versions: `backend/app/db/versions/` (NOT `migrations/versions/`)
- `sqlalchemy.url` set from `MIGRATION_DATABASE_URL` env var in `env.py` — never hardcoded

## Migration naming
```
20260318_0001_catalog_tables.py
20260318_0002_profiles.py
20260318_0003_...py
```
Format: `YYYYMMDD_NNNN_descriptive_name.py`. Date prefix ensures chronological file ordering.

## Supabase connection URLs — critical distinction
| URL | Port | Use for |
|---|---|---|
| `DATABASE_URL` | 6543 | Running app (SQLAlchemy engine, all queries) |
| `MIGRATION_DATABASE_URL` | 5432 | Alembic only (`alembic upgrade head`, `alembic check`) |

PgBouncer transaction mode (pooler) **cannot run DDL**. Alembic must always use the direct URL.
Both live in `backend/.env`. The `env.py` reads `MIGRATION_DATABASE_URL`, falling back to `DATABASE_URL`.

## Required patterns for every migration

### Table creation — always explicit schema
```python
op.create_table(
    "table_name",
    sa.Column("id", sa.UUID(), nullable=False),
    ...
    schema="public"   # always — never omit
)
```

### Check constraints instead of ENUMs
```python
# Correct
sa.Column("role", sa.VARCHAR(50), nullable=False),
sa.CheckConstraint("role IN ('vendor', 'customer', 'admin')", name="ck_profiles_role"),

# Wrong — do not use
sa.Column("role", sa.Enum("vendor", "customer", "admin", name="role_enum"))
```

### Cross-schema FKs (auth.users only)
Alembic cannot model cross-schema FKs to Supabase-managed tables. Use raw SQL:
```python
op.execute("""
    CREATE TABLE public.profiles (
        id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
        ...
    )
""")
```

### Downgrade must be complete
```python
def downgrade() -> None:
    op.drop_index("ix_name", table_name="table_name", schema="public")
    op.drop_table("table_name", schema="public")
    # Drop in reverse order of creation
```
Never leave `downgrade()` as `pass` or `raise NotImplementedError`.

## Indexes to always add
- `cards.name` → GIN trigram index (requires `pg_trgm` extension — created in migration 0001)
- `inventory_items.vendor_id` → B-tree
- `inventory_items.card_id` → B-tree
- `inventory_items.deleted_at` → partial index (`WHERE deleted_at IS NULL`)
- `price_snapshots.(card_id, source, variant)` → unique index (already in migration 0001)
- `vendor_show_registrations.(vendor_id, show_id)` → unique index

## Migrations already applied
| File | Contents |
|---|---|
| `20260318_0001_catalog_tables.py` | `series`, `sets`, `cards`, `price_snapshots` + GIN index + pg_trgm |
| `20260318_0002_profiles.py` | `public.profiles` referencing `auth.users` via raw SQL |

## auth trigger (Phase 1)
When Phase 1 begins, run this via Supabase SQL editor — **not Alembic** (touches `auth` schema):
```sql
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, role)
  VALUES (new.id, 'customer');  -- default role; vendor role set via profile creation flow
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
```
This is the ONLY interaction with the `auth` schema — executed manually, never via Alembic.

## Verification checklist after any migration
- [ ] `alembic check` shows no pending migrations
- [ ] All tables visible in Supabase dashboard under `public` schema
- [ ] All indexes created (Supabase dashboard → Table Editor → Indexes)
- [ ] `alembic downgrade -1` works cleanly
- [ ] `alembic upgrade head` from scratch works on a clean schema
