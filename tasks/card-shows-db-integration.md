# Card shows — DB integration + Celery scrape task

## Context
Read `CardOps-Project-Spec_v2.md`, `tasks/lessons.md`, and `tasks/todo.md`
before starting. This task integrates the OnTreasure scraper into the backend,
creating the `card_shows` table, a DB upsert writer, and a weekly Celery beat job.

The production scraper lives at `backend/scripts/scrape_ontreasure.py`. Confirm
this file exists before starting — if the `scripts/` directory is missing, create
it with an empty `__init__.py` first.

---

## Scope

1. Alembic migration — create `card_shows` table
2. SQLAlchemy model — `CardShow`
3. DB writer — sync upsert function used by both the Celery task and manual runs
4. Celery task — `shows.scrape_ontreasure` on weekly schedule
5. FastAPI endpoints — `GET /api/v1/shows` and `GET /api/v1/shows/{show_id}`

---

## Step 1 — Alembic migration

Create `backend/app/db/versions/20260408_0019_create_card_shows.py`.

```python
"""Create card_shows table.

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "card_shows",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"),
                  nullable=False),
        sa.Column("ontreasure_id", sa.VARCHAR(300), nullable=False),
        sa.Column("source_url", sa.VARCHAR(500), nullable=False),
        sa.Column("name", sa.VARCHAR(300), nullable=False),
        sa.Column("date_start", sa.Date(), nullable=False),
        sa.Column("date_end", sa.Date(), nullable=True),
        sa.Column("time_range", sa.VARCHAR(50), nullable=True),
        sa.Column("venue_name", sa.VARCHAR(300), nullable=True),
        sa.Column("address", sa.VARCHAR(500), nullable=True),
        sa.Column("street", sa.VARCHAR(300), nullable=True),
        sa.Column("city", sa.VARCHAR(100), nullable=True),
        sa.Column("state", sa.VARCHAR(2), nullable=True),
        sa.Column("zip_code", sa.VARCHAR(10), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("organizer_name", sa.VARCHAR(200), nullable=True),
        sa.Column("organizer_handle", sa.VARCHAR(200), nullable=True),
        sa.Column("ticket_price", sa.VARCHAR(20), nullable=True),
        sa.Column("table_price", sa.VARCHAR(20), nullable=True),
        sa.Column("poster_url", sa.VARCHAR(500), nullable=True),
        sa.Column("status", sa.VARCHAR(20), nullable=False,
                  server_default="'active'"),
        sa.Column("source", sa.VARCHAR(50), nullable=False,
                  server_default="'ontreasure'"),
        sa.Column("is_verified", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("last_scraped_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ontreasure_id", name="uq_card_shows_ontreasure_id"),
        sa.CheckConstraint("status IN ('active', 'cancelled')",
                           name="ck_card_shows_status"),
        schema="public",
    )

    op.create_index("idx_card_shows_date_start", "card_shows",
                    ["date_start"], schema="public")
    op.create_index("idx_card_shows_state", "card_shows",
                    ["state"], schema="public")
    op.create_index(
        "idx_card_shows_active",
        "card_shows",
        ["date_start"],
        postgresql_where=sa.text("status = 'active'"),
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("idx_card_shows_active", table_name="card_shows", schema="public")
    op.drop_index("idx_card_shows_state", table_name="card_shows", schema="public")
    op.drop_index("idx_card_shows_date_start", table_name="card_shows", schema="public")
    op.drop_table("card_shows", schema="public")
```

Run and verify:
```bash
source backend/.venv/bin/activate
alembic upgrade head
alembic check
# Confirm card_shows table visible in Supabase dashboard under public schema
```

---

## Step 2 — SQLAlchemy model

Create `backend/app/models/shows.py`:

```python
"""
SQLAlchemy model for the card_shows table.

Stores upcoming TCG card show events scraped from OnTreasure.
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, CheckConstraint, Date, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CardShow(Base):
    __tablename__ = "card_shows"
    __table_args__ = (
        UniqueConstraint("ontreasure_id", name="uq_card_shows_ontreasure_id"),
        CheckConstraint("status IN ('active', 'cancelled')",
                        name="ck_card_shows_status"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True,
                                          server_default="gen_random_uuid()")
    ontreasure_id: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    date_start: Mapped[date] = mapped_column(Date(), nullable=False)
    date_end: Mapped[Optional[date]] = mapped_column(Date(), nullable=True)
    time_range: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    venue_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    street: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    tags: Mapped[List] = mapped_column(JSONB(), nullable=False,
                                       server_default="'[]'::jsonb")
    organizer_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    organizer_handle: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ticket_price: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    table_price: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    poster_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False,
                                        server_default="'active'")
    source: Mapped[str] = mapped_column(String(50), nullable=False,
                                        server_default="'ontreasure'")
    is_verified: Mapped[bool] = mapped_column(Boolean(), nullable=False,
                                              server_default="false")
    last_scraped_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")
```

---

## Step 3 — DB writer

Create `backend/app/services/shows.py`:

```python
"""
Show upsert service — sync, uses the standard SQLAlchemy Session.

Called by the Celery scrape task and can be called directly for manual imports.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.shows import CardShow

logger = logging.getLogger(__name__)

# Tags like "+3", "+140" are OnTreasure UI overflow indicators — not real tags
_OVERFLOW_TAG_RE = re.compile(r"^\+\d+$")


def _clean_str(val: object, max_len: Optional[int] = None) -> Optional[str]:
    if not val or not str(val).strip():
        return None
    s = str(val).strip()
    if max_len:
        s = s[:max_len]
    return s


def _clean_event(raw: Dict) -> Dict:
    """
    Normalize a scraped event dict before writing to DB.

    - Strips overflow tags ("+3", "+140")
    - Collapses time_start / time_end into a single time_range string
    - Enforces state as exactly 2 uppercase chars or None
    - Truncates fields that exceed column widths
    - Replaces empty strings with None
    """
    tags = [
        t for t in (raw.get("tags") or [])
        if t and not _OVERFLOW_TAG_RE.match(str(t))
    ]
    tags = list(dict.fromkeys(tags))  # deduplicate, preserve order

    ts = _clean_str(raw.get("time_start"))
    te = _clean_str(raw.get("time_end"))
    if ts and te and ts == te:
        time_range = ts
    elif ts and te:
        time_range = f"{ts} – {te}"
    else:
        time_range = ts or te

    state = _clean_str(raw.get("state"))
    if state and len(state) != 2:
        state = None

    return {
        "ontreasure_id": raw["source_id"],
        "source_url": raw["source_url"],
        "name": _clean_str(raw.get("name"), 300),
        "date_start": raw["date_start"],
        "date_end": raw.get("date_end"),
        "time_range": _clean_str(time_range, 50),
        "venue_name": _clean_str(raw.get("venue_name"), 300),
        "address": _clean_str(raw.get("address"), 500),
        "street": _clean_str(raw.get("street"), 300),
        "city": _clean_str(raw.get("city"), 100),
        "state": state,
        "zip_code": _clean_str(raw.get("zip_code"), 10),
        "latitude": raw.get("latitude"),
        "longitude": raw.get("longitude"),
        "description": _clean_str(raw.get("description")),
        "tags": tags,
        "organizer_name": _clean_str(raw.get("organizer_name"), 200),
        "organizer_handle": _clean_str(raw.get("organizer_handle"), 200),
        "ticket_price": _clean_str(raw.get("ticket_price"), 20),
        "table_price": _clean_str(raw.get("table_price"), 20),
        "poster_url": _clean_str(raw.get("poster_url"), 500),
        "status": "active",
        "source": "ontreasure",
        "last_scraped_at": datetime.now(timezone.utc),
    }


def upsert_shows(events: List[Dict], session: Session) -> Dict:
    """
    Upsert a list of scraped event dicts into card_shows.

    Uses INSERT ... ON CONFLICT (ontreasure_id) DO UPDATE — safe to call
    repeatedly. Existing rows are updated; new rows are inserted.

    Returns: {"upserted": N, "skipped": N}
    """
    if not events:
        return {"upserted": 0, "skipped": 0}

    cleaned = []
    skipped = 0
    for raw in events:
        if not raw.get("source_id") or not raw.get("date_start"):
            skipped += 1
            continue
        try:
            cleaned.append(_clean_event(raw))
        except Exception as exc:
            logger.warning("Skipping event due to clean error: %s", exc)
            skipped += 1

    if not cleaned:
        return {"upserted": 0, "skipped": skipped}

    stmt = insert(CardShow).values(cleaned)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ontreasure_id"],
        set_={
            "name": stmt.excluded.name,
            "date_start": stmt.excluded.date_start,
            "date_end": stmt.excluded.date_end,
            "time_range": stmt.excluded.time_range,
            "venue_name": stmt.excluded.venue_name,
            "address": stmt.excluded.address,
            "street": stmt.excluded.street,
            "city": stmt.excluded.city,
            "state": stmt.excluded.state,
            "zip_code": stmt.excluded.zip_code,
            "description": stmt.excluded.description,
            "tags": stmt.excluded.tags,
            "organizer_name": stmt.excluded.organizer_name,
            "organizer_handle": stmt.excluded.organizer_handle,
            "ticket_price": stmt.excluded.ticket_price,
            "table_price": stmt.excluded.table_price,
            "poster_url": stmt.excluded.poster_url,
            "last_scraped_at": stmt.excluded.last_scraped_at,
            "updated_at": datetime.now(timezone.utc),
        },
    )

    session.execute(stmt)
    session.commit()
    return {"upserted": len(cleaned), "skipped": skipped}
```

---

## Step 4 — Scraper integration

Confirm `backend/scripts/scrape_ontreasure.py` exists. If `backend/scripts/`
is missing, create it:
```bash
mkdir backend/scripts
touch backend/scripts/__init__.py
```

Add the following **sync** entry point at the bottom of
`backend/scripts/scrape_ontreasure.py`. This is the single function called by
the Celery task and by manual runs. It uses `asyncio.run()` to drive the
Playwright-based scraper, then writes results with the sync DB service.

```python
def scrape_and_save(days: int = 90) -> dict:
    """
    Run the full scrape pipeline and write results to the database.

    Sync entry point — safe to call from a Celery worker or a plain script.
    Playwright is async internally; asyncio.run() is called here once at the
    top level, outside any running event loop.

    Manual usage:
        cd backend
        source .venv/bin/activate
        python -c "from scripts.scrape_ontreasure import scrape_and_save; print(scrape_and_save())"
    """
    import asyncio
    from app.db.session import SessionLocal
    from app.services.shows import upsert_shows

    events = asyncio.run(scrape(days=days, output_file=None))

    if not events:
        return {"scraped": 0, "upserted": 0, "skipped": 0}

    with SessionLocal() as session:
        result = upsert_shows(events, session)

    return {"scraped": len(events), **result}
```

Also update the `scrape()` function to accept `output_file=None` and skip the
JSON write when it is `None`:

```python
# In scrape(), replace the "Step 4: Save output" block with:
if output_file is not None:
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[DONE] {len(results)} events saved to {output_file}")
else:
    print(f"\n[DONE] {len(results)} events scraped (not written to file)")
```

---

## Step 5 — Celery task

Create `backend/app/tasks/shows_sync.py`:

```python
"""
Celery task: weekly OnTreasure scrape.

Scrapes 90 days of upcoming Non-Sports / TCG card shows and upserts
into the card_shows table.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="shows.scrape_ontreasure",
    bind=True,
    max_retries=2,
    default_retry_delay=300,  # 5 min between retries
)
def scrape_ontreasure_task(self):
    """
    Weekly card show scrape from OnTreasure.com.
    Scrapes 90 days ahead, upserts all events into card_shows table.
    """
    from scripts.scrape_ontreasure import scrape_and_save

    try:
        result = scrape_and_save(days=90)
        logger.info(
            "shows.scrape_ontreasure complete: "
            "scraped=%d upserted=%d skipped=%d",
            result["scraped"], result["upserted"], result["skipped"],
        )
        return result
    except Exception as exc:
        logger.error("shows.scrape_ontreasure failed: %s", exc)
        raise self.retry(exc=exc)
```

Add to the beat schedule in `backend/celery_app.py`:

```python
"shows-scrape-ontreasure": {
    "task": "shows.scrape_ontreasure",
    "schedule": crontab(hour=4, minute=0, day_of_week=1),  # every Monday 4am
},
```

Register the task module. Check whether `celery_app.py` uses `autodiscover_tasks`
or `include` — add to whichever is present:

```python
# If autodiscover_tasks:
app.autodiscover_tasks([
    "app.tasks.catalog_sync",
    "app.tasks.price_sync",
    "app.tasks.shows_sync",   # add this
])

# If include:
app = Celery(..., include=[
    "app.tasks.catalog_sync",
    "app.tasks.price_sync",
    "app.tasks.shows_sync",   # add this
])
```

---

## Step 6 — FastAPI endpoints

Create `backend/app/api/shows.py`:

```python
"""
Shows endpoints — public, no auth required.

Routes:
  GET /shows        — list upcoming card shows with optional state/date filters
  GET /shows/{id}   — single show by UUID or ontreasure_id slug
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.shows import CardShow

router = APIRouter(tags=["shows"])


class ShowResponse(BaseModel):
    id: str
    ontreasure_id: str
    name: str
    date_start: date
    date_end: Optional[date] = None
    time_range: Optional[str] = None
    venue_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    ticket_price: Optional[str] = None
    table_price: Optional[str] = None
    poster_url: Optional[str] = None
    organizer_name: Optional[str] = None
    source_url: str

    model_config = {"from_attributes": True}


@router.get("/shows", response_model=List[ShowResponse])
def list_shows(
    state: Optional[str] = Query(None, description="Filter by 2-letter state abbreviation e.g. NY"),
    from_date: Optional[date] = Query(None, description="Shows starting on or after this date"),
    until_date: Optional[date] = Query(None, description="Shows starting on or before this date"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List upcoming active card shows, ordered by date ascending."""
    filters = [
        CardShow.status == "active",
        CardShow.date_start >= (from_date or date.today()),
    ]
    if state:
        filters.append(CardShow.state == state.upper())
    if until_date:
        filters.append(CardShow.date_start <= until_date)

    shows = (
        db.query(CardShow)
        .filter(and_(*filters))
        .order_by(CardShow.date_start.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_build_response(s) for s in shows]


@router.get("/shows/{show_id}", response_model=ShowResponse)
def get_show(show_id: str, db: Session = Depends(get_db)):
    """Get a single show by UUID or ontreasure_id slug."""
    show = (
        db.query(CardShow)
        .filter(
            (CardShow.ontreasure_id == show_id) |
            (CardShow.id == show_id)
        )
        .first()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")
    return _build_response(show)


def _build_response(show: CardShow) -> dict:
    return {
        "id": str(show.id),
        "ontreasure_id": show.ontreasure_id,
        "name": show.name,
        "date_start": show.date_start,
        "date_end": show.date_end,
        "time_range": show.time_range,
        "venue_name": show.venue_name,
        "city": show.city,
        "state": show.state,
        "address": show.address,
        "latitude": float(show.latitude) if show.latitude is not None else None,
        "longitude": float(show.longitude) if show.longitude is not None else None,
        "ticket_price": show.ticket_price,
        "table_price": show.table_price,
        "poster_url": show.poster_url,
        "organizer_name": show.organizer_name,
        "source_url": show.source_url,
    }
```

Register in `backend/app/main.py`:
```python
from app.api.shows import router as shows_router
app.include_router(shows_router, prefix="/api/v1")
```

---

## Step 7 — Seed initial data

After the migration, run a one-time manual seed:

```bash
cd backend
source .venv/bin/activate
python -c "from scripts.scrape_ontreasure import scrape_and_save; print(scrape_and_save())"
```

Expected output:
```
[LISTING] 13 date windows × 7 days each
  [WINDOW] 2026-04-08 → 2026-04-14
  ...
[DONE] ~130 events scraped (not written to file)
{'scraped': 130, 'upserted': 130, 'skipped': 0}
```

Re-run to confirm idempotency — should produce `upserted: 130, skipped: 0`
with no duplicates in the table.

---

## Verification checklist

- [ ] `alembic upgrade head` succeeds — `card_shows` table visible in Supabase
- [ ] `alembic check` shows no pending migrations
- [ ] All 3 indexes created (Supabase → Table Editor → Indexes)
- [ ] `CardShow` model imports without error: `python -c "from app.models.shows import CardShow"`
- [ ] Manual seed inserts rows — confirm count in Supabase
- [ ] Re-running seed produces same `upserted` count, no duplicate rows
- [ ] `GET /api/v1/shows` returns list of shows
- [ ] `GET /api/v1/shows?state=MA` filters correctly
- [ ] `GET /api/v1/shows/{ontreasure_id}` returns a single show
- [ ] Celery task registered: `celery -A celery_app inspect registered` shows `shows.scrape_ontreasure`
- [ ] Beat schedule entry `shows-scrape-ontreasure` present in `celery_app.py`

---

## Stop conditions

Stop and flag to the user if:
- `backend/scripts/scrape_ontreasure.py` does not exist — do not proceed without the source scraper
- Playwright is not in `backend/requirements.txt` — the scraper requires it; add
  `playwright` and run `playwright install chromium` in the backend venv before running the seed
- The `scrape()` function in the scraper does not accept an `output_file` parameter —
  read the actual function signature before modifying it
- The Celery app does not exist at `backend/celery_app.py` — flag before creating tasks
