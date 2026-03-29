# Quick Scan — Google Cloud Vision OCR implementation

## Context
This task adds a **Quick Scan** button to the existing `/scan` page. Quick Scan uses
Google Cloud Vision OCR to identify a card faster than the existing Claude Vision
pipeline. The existing **Identify** button and its Claude Vision flow must remain
completely untouched.

Read `CardOps-Project-Spec.md` and `tasks/lessons.md` before starting.

---

## Credentials setup

The following is already in `backend/.env`:

```
GOOGLE_CREDENTIALS_BASE64=<base64-encoded full JSON key>
```

The full service account details are:
- **client_email:** `cardops-vision@cardops-prod.iam.gserviceaccount.com`
- **client_id:** `107953612894855139997`
- **project_id:** `cardops-prod`
- **token_uri:** `https://oauth2.googleapis.com/token`

`GOOGLE_CREDENTIALS_BASE64` must be the entire service account JSON file
base64-encoded — not just the `private_key` field. If authentication fails,
this is the first thing to verify.

---

## Scope of changes

### What to build
1. Backend: new FastAPI endpoint `POST /api/v1/scans/quick-identify` that accepts
   an image, calls Google Cloud Vision OCR, fuzzy-matches against the `cards`
   catalog, and returns an identified card or a no-match result.
2. Frontend: a **Quick Scan** button on the `/scan` page that triggers the new
   endpoint and displays the result using the existing scan result UI components.

### What NOT to touch
- The existing `POST /api/v1/scans/identify` Claude Vision endpoint — do not
  modify it in any way.
- The existing **Identify** button and its associated frontend logic.
- Any existing scan job logging, Celery tasks, or S3 upload flows.
- The `scan_jobs` table schema.

---

## Backend implementation

### Step 1 — Install dependencies

Add to `pyproject.toml` (or `requirements.txt`):
```
google-cloud-vision>=3.7.0
google-auth>=2.28.0
rapidfuzz>=3.6.0
```

Run:
```bash
pip install google-cloud-vision google-auth rapidfuzz
```

Verify installation:
```bash
python -c "from google.cloud import vision; print('Vision SDK OK')"
```

### Step 2 — Add Google credentials to settings

In `backend/app/core/config.py` (or wherever `Settings`/`BaseSettings` lives),
add the credentials property. Do not remove or modify any existing settings fields.

```python
import base64
import json
from google.oauth2 import service_account

class Settings(BaseSettings):
    # --- existing fields stay exactly as-is ---

    # Google Cloud Vision
    google_credentials_base64: str = ""

    @property
    def google_vision_credentials(self):
        if not self.google_credentials_base64:
            return None
        key_data = json.loads(
            base64.b64decode(self.google_credentials_base64)
        )
        return service_account.Credentials.from_service_account_info(
            key_data,
            scopes=["https://www.googleapis.com/auth/cloud-vision"]
        )
```

### Step 3 — Create the OCR service

Create `backend/app/services/ocr.py`:

```python
"""
Google Cloud Vision OCR service.
Used by the Quick Scan endpoint to extract text from card images.
"""

import asyncio
import re
from google.cloud import vision
from app.core.config import settings


def get_vision_client() -> vision.ImageAnnotatorClient:
    creds = settings.google_vision_credentials
    if creds:
        return vision.ImageAnnotatorClient(credentials=creds)
    return vision.ImageAnnotatorClient()


async def extract_card_text(image_bytes: bytes) -> dict:
    """
    Send image to Google Cloud Vision and extract structured card fields.
    Returns a dict with keys: name, set_number, hp, illustrator.
    All values are strings or None if not detected.
    """
    client = get_vision_client()

    image = vision.Image(content=image_bytes)

    response = await asyncio.to_thread(client.text_detection, image=image)

    if response.error.message:
        raise RuntimeError(f"Google Vision error: {response.error.message}")

    if not response.text_annotations:
        return {"name": None, "set_number": None, "hp": None, "illustrator": None}

    raw_text = response.text_annotations[0].description
    return _parse_pokemon_card_text(raw_text)


def _parse_pokemon_card_text(raw_text: str) -> dict:
    """
    Extract structured fields from raw OCR text.
    Card name is typically the first line.
    Set number matches NNN/NNN pattern (e.g. 006/091).
    HP matches a number adjacent to 'HP'.
    Illustrator follows 'illus.' prefix.
    """
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    result = {"name": None, "set_number": None, "hp": None, "illustrator": None}

    if lines:
        result["name"] = lines[0]

    set_number_pattern = re.compile(r"\b(\d{1,3}/\d{1,3}|TG\d+/TG\d+)\b")
    for line in lines:
        match = set_number_pattern.search(line)
        if match:
            result["set_number"] = match.group(0)
            break

    hp_pattern = re.compile(r"\b(\d{2,3})\s*HP\b|\bHP\s*(\d{2,3})\b", re.IGNORECASE)
    for line in lines:
        match = hp_pattern.search(line)
        if match:
            result["hp"] = int(match.group(1) or match.group(2))
            break

    illus_pattern = re.compile(r"illus\.\s*(.+)", re.IGNORECASE)
    for line in lines:
        match = illus_pattern.search(line)
        if match:
            result["illustrator"] = match.group(1).strip()
            break

    return result
```

### Step 4 — Create the catalog matching service

Create `backend/app/services/catalog_match.py`:

```python
"""
Fuzzy matching service: maps OCR-extracted card text to a card in the catalog.
Uses pg_trgm for fast name search and rapidfuzz for re-ranking.
"""

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.catalog import Card


async def match_card_from_ocr(ocr: dict, session: AsyncSession) -> dict | None:
    """
    Attempt to identify a card from OCR-extracted fields.
    Returns {"card": Card, "confidence": float, "method": str} or None.

    Matching strategy (tries each tier, returns on first confident match):
      Tier 1: set_number + name exact match  → confidence 0.99
      Tier 2: set_number only               → confidence 0.90
      Tier 3: set_number + hp disambiguation → confidence 0.88
      Tier 4: fuzzy name match (pg_trgm)    → confidence varies
    """
    name = (ocr.get("name") or "").strip()
    set_number = (ocr.get("set_number") or "").strip()
    hp = ocr.get("hp")

    # Tier 1: set number + name
    if name and set_number:
        local_id = _parse_local_id(set_number)
        result = await session.execute(
            select(Card)
            .where(Card.local_id == local_id)
            .where(Card.name.ilike(f"%{name}%"))
        )
        card = result.scalar_one_or_none()
        if card:
            return {"card": card, "confidence": 0.99, "method": "exact"}

    # Tier 2: set number alone
    if set_number:
        local_id = _parse_local_id(set_number)
        result = await session.execute(
            select(Card).where(Card.local_id == local_id)
        )
        candidates = result.scalars().all()

        if len(candidates) == 1:
            return {"card": candidates[0], "confidence": 0.90, "method": "set_number"}

        # Tier 3: disambiguate with HP
        if hp and candidates:
            hp_matched = [c for c in candidates if c.hp == hp]
            if len(hp_matched) == 1:
                return {
                    "card": hp_matched[0],
                    "confidence": 0.88,
                    "method": "set_number_hp",
                }

    # Tier 4: fuzzy name match
    if name and len(name) >= 3:
        result = await session.execute(
            select(Card).where(Card.name.ilike(f"%{name}%")).limit(10)
        )
        candidates = result.scalars().all()

        if candidates:
            candidate_names = [c.name for c in candidates]
            best = process.extractOne(
                name, candidate_names, scorer=fuzz.token_sort_ratio
            )
            if best and best[1] >= 80:
                idx = candidate_names.index(best[0])
                return {
                    "card": candidates[idx],
                    "confidence": round(best[1] / 100, 2),
                    "method": "fuzzy_name",
                }

    return None


def _parse_local_id(set_number: str) -> str:
    """
    Extract the local ID from a set number string.
    '006/091' -> '6', 'TG15/TG30' -> 'TG15'
    """
    part = set_number.split("/")[0]
    if part.upper().startswith("TG"):
        return part.upper()
    return str(int(part)) if part.isdigit() else part
```

### Step 5 — Add the Quick Scan endpoint

In `backend/app/api/scans.py`, add the following endpoint.
Do not modify any existing endpoints in this file.

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session
from app.services.ocr import extract_card_text
from app.services.catalog_match import match_card_from_ocr

router = APIRouter(prefix="/api/v1/scans", tags=["scans"])

# --- existing endpoints remain exactly as-is above this line ---


@router.post("/quick-identify")
async def quick_identify(
    image: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Quick Scan endpoint: Google Cloud Vision OCR + catalog fuzzy match.
    Faster than Claude Vision but falls back gracefully when OCR confidence
    is low. Does not create a scan_job record or trigger Celery tasks.
    """
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await image.read()

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 10MB")

    try:
        ocr_result = await extract_card_text(image_bytes)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"OCR service error: {e}")

    if not ocr_result.get("name") and not ocr_result.get("set_number"):
        return {
            "matched": False,
            "reason": "no_text_detected",
            "ocr": ocr_result,
        }

    match = await match_card_from_ocr(ocr_result, session)

    if not match:
        return {
            "matched": False,
            "reason": "no_catalog_match",
            "ocr": ocr_result,
        }

    card = match["card"]

    return {
        "matched": True,
        "confidence": match["confidence"],
        "method": match["method"],
        "ocr": ocr_result,
        "card": {
            "id": card.id,
            "name": card.name,
            "set_id": card.set_id,
            "local_id": card.local_id,
            "image_url": card.image_url,
            "hp": card.hp,
            "rarity": card.rarity,
            "category": card.category,
        },
    }
```

Register the router in `main.py` if `scans.router` is not already included.

### Step 6 — Verify the endpoint

Start the backend and test with curl before touching the frontend:

```bash
curl -X POST http://localhost:8000/api/v1/scans/quick-identify \
  -F "image=@/path/to/test-card.jpg" \
  | python -m json.tool
```

Expected response shape on a successful match:
```json
{
  "matched": true,
  "confidence": 0.99,
  "method": "exact",
  "ocr": { "name": "Charizard", "set_number": "004/102", "hp": 120, "illustrator": "..." },
  "card": { "id": "base1-4", "name": "Charizard", ... }
}
```

Do not proceed to the frontend until this returns a correct response.

---

## Database — add pg_trgm index (if not already present)

Check whether `idx_cards_name_trgm` already exists in Supabase. If it does not,
create an Alembic migration:

```python
# backend/app/db/migrations/versions/XXX_add_trgm_index.py

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "idx_cards_name_trgm",
        "cards",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
        schema="public",
    )

def downgrade():
    op.drop_index("idx_cards_name_trgm", table_name="cards", schema="public")
```

Run: `alembic upgrade head`

---

## Frontend implementation

### Step 7 — Add the API client function

In `frontend/lib/api/scans.ts` (or wherever scan API calls live), add:

```typescript
// Do not modify the existing identifyCard function

export async function quickIdentifyCard(imageFile: File): Promise<QuickScanResult> {
  const formData = new FormData();
  formData.append("image", imageFile);

  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/api/v1/scans/quick-identify`,
    { method: "POST", body: formData }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail ?? "Quick scan failed");
  }

  return response.json();
}

export interface QuickScanResult {
  matched: boolean;
  reason?: string;
  confidence?: number;
  method?: string;
  ocr: {
    name: string | null;
    set_number: string | null;
    hp: number | null;
    illustrator: string | null;
  };
  card?: {
    id: string;
    name: string;
    set_id: string;
    local_id: string;
    image_url: string | null;
    hp: number | null;
    rarity: string | null;
    category: string;
  };
}
```

### Step 8 — Add the Quick Scan button to the scan page

In the scan page component (`frontend/app/(auth)/vendor/scan/page.tsx` or
equivalent path in your project):

- Keep the existing Identify button and its `onClick` handler exactly as-is
- Add a second button labeled **Quick Scan** beside it
- Add state for `quickScanResult` and `quickScanLoading` — separate from any
  existing scan state variables
- Reuse the existing file input / camera capture mechanism — both buttons use
  the same selected image

```tsx
"use client";

import { useState, useRef } from "react";
import { quickIdentifyCard, QuickScanResult } from "@/lib/api/scans";

// Keep all existing imports and state variables unchanged

export default function ScanPage() {
  // --- all existing state and logic stays exactly as-is ---

  // New state for Quick Scan only
  const [quickScanResult, setQuickScanResult] = useState<QuickScanResult | null>(null);
  const [quickScanLoading, setQuickScanLoading] = useState(false);
  const [quickScanError, setQuickScanError] = useState<string | null>(null);

  async function handleQuickScan() {
    if (!selectedImage) return;           // selectedImage = existing file state var

    setQuickScanLoading(true);
    setQuickScanError(null);
    setQuickScanResult(null);

    try {
      const result = await quickIdentifyCard(selectedImage);
      setQuickScanResult(result);
    } catch (err) {
      setQuickScanError(err instanceof Error ? err.message : "Quick scan failed");
    } finally {
      setQuickScanLoading(false);
    }
  }

  return (
    <div>
      {/* --- all existing JSX stays exactly as-is --- */}

      {/* Add Quick Scan button alongside the existing Identify button */}
      <div style={{ display: "flex", gap: "12px" }}>
        {/* Existing Identify button — DO NOT MODIFY */}
        <button onClick={handleIdentify} disabled={!selectedImage || loading}>
          {loading ? "Identifying..." : "Identify"}
        </button>

        {/* New Quick Scan button */}
        <button
          onClick={handleQuickScan}
          disabled={!selectedImage || quickScanLoading}
        >
          {quickScanLoading ? "Scanning..." : "Quick Scan"}
        </button>
      </div>

      {/* Quick Scan result display */}
      {quickScanError && (
        <p style={{ color: "red" }}>{quickScanError}</p>
      )}

      {quickScanResult && !quickScanResult.matched && (
        <div>
          <p>No match found.</p>
          {quickScanResult.ocr.name && (
            <p>OCR detected: "{quickScanResult.ocr.name}"</p>
          )}
          <p>Try the Identify button for Claude Vision analysis.</p>
        </div>
      )}

      {quickScanResult?.matched && quickScanResult.card && (
        <div>
          <p>
            <strong>{quickScanResult.card.name}</strong>
            {" — "}
            confidence: {Math.round((quickScanResult.confidence ?? 0) * 100)}%
          </p>
          {quickScanResult.card.image_url && (
            <img
              src={quickScanResult.card.image_url + "/low.webp"}
              alt={quickScanResult.card.name}
              width={200}
            />
          )}
          <p>Set: {quickScanResult.card.set_id} · #{quickScanResult.card.local_id}</p>
          {quickScanResult.card.hp && <p>HP: {quickScanResult.card.hp}</p>}
        </div>
      )}
    </div>
  );
}
```

Adapt the JSX to match the existing component's actual styling patterns —
use whatever component library (shadcn/ui etc.) is already in use for buttons
and result cards rather than plain HTML if that's the convention in the file.

---

## Verification checklist

Before marking this task complete, verify all of the following:

- [ ] `pip install google-cloud-vision google-auth rapidfuzz` succeeds
- [ ] `python -c "from google.cloud import vision; print('OK')"` passes
- [ ] `GOOGLE_CREDENTIALS_BASE64` in `.env` is the full JSON file base64-encoded
      (not just the `private_key` field)
- [ ] `POST /api/v1/scans/quick-identify` returns correct JSON with a test image
- [ ] `POST /api/v1/scans/identify` (Claude Vision) still works and is unchanged
- [ ] Quick Scan button appears on `/scan` page
- [ ] Identify button still works and is unchanged
- [ ] Quick Scan result renders correctly for a matched card
- [ ] Quick Scan shows a graceful no-match message when card is unidentified
- [ ] No existing tests are broken

---

## Stop conditions

Stop and flag to the user if:
- Authentication to Google Vision fails (401/403) — likely a credentials encoding issue
- The `cards` table returns 0 results on any query — catalog may not be seeded
- The scan page component structure differs significantly from the assumptions above —
  confirm the correct file path and existing state variable names before adding code
- Any modification to the existing Identify button or Claude Vision endpoint
  is being considered — that is out of scope for this task
