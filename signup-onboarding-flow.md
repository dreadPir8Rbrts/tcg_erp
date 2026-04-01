# Signup onboarding flow — implementation spec

## Context
This task implements the multi-step onboarding flow that runs immediately after
a new user completes Supabase Auth signup. Read `CardOps-Project-Spec.md`,
`tasks/lessons.md`, and `tasks/todo.md` before starting.

---

## Overview of what to build

A 4-step onboarding wizard that collects initial profile information after
signup. Steps are:

1. **Role + display name** — required, blocks proceeding
2. **Interests** — recommended, skippable
3. **Avatar** — optional, always skippable
4. **Location** — ZIP code, required for show discovery

After completion the user lands on their dashboard in the appropriate mode.

This flow runs once per user, immediately after first signup. Returning users
who have completed onboarding bypass it entirely.

---

## Schema changes required

### 1. Update the profiles role constraint

The current check constraint only allows `'vendor'` and `'collector'`. Add
`'both'` as a valid value.

Write an Alembic migration:

```python
def upgrade():
    op.execute("""
        ALTER TABLE public.profiles
        DROP CONSTRAINT IF EXISTS ck_profiles_role;
    """)
    op.execute("""
        ALTER TABLE public.profiles
        ADD CONSTRAINT ck_profiles_role
        CHECK (role IN ('vendor', 'collector', 'both'));
    """)

def downgrade():
    op.execute("""
        ALTER TABLE public.profiles
        DROP CONSTRAINT IF EXISTS ck_profiles_role;
    """)
    op.execute("""
        ALTER TABLE public.profiles
        ADD CONSTRAINT ck_profiles_role
        CHECK (role IN ('vendor', 'collector'));
    """)
```

### 2. Add onboarding_complete flag to profiles

Add a boolean column so the app can detect whether a user needs to be routed
to onboarding or their dashboard.

```python
def upgrade():
    op.add_column(
        "profiles",
        sa.Column(
            "onboarding_complete",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        schema="public",
    )

def downgrade():
    op.drop_column("profiles", "onboarding_complete", schema="public")
```

### 3. Add zip_code to profiles

```python
def upgrade():
    op.add_column(
        "profiles",
        sa.Column("zip_code", sa.VARCHAR(10), nullable=True),
        schema="public",
    )

def downgrade():
    op.drop_column("profiles", "zip_code", schema="public")
```

### 4. Add avatar_url to profiles

```python
def upgrade():
    op.add_column(
        "profiles",
        sa.Column("avatar_url", sa.VARCHAR(500), nullable=True),
        schema="public",
    )

def downgrade():
    op.drop_column("profiles", "avatar_url", schema="public")
```

These can be combined into a single migration file. Run `alembic upgrade head`
and verify the columns appear in Supabase before proceeding.

---

## Supabase auth trigger update

The existing trigger that auto-creates a `public.profiles` row on signup
should set `onboarding_complete = false` by default. If the trigger already
uses `server_default` this is handled automatically. Verify the trigger in
the Supabase SQL editor:

```sql
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, role, onboarding_complete)
  VALUES (new.id, 'collector', false);
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

Default role is `'collector'` — the onboarding step 1 will update this to
`'vendor'`, `'collector'`, or `'both'` based on user selection.

---

## Backend — new API endpoints

### Endpoint 1: `PATCH /api/v1/profiles/me`

Updates the current user's `public.profiles` row. Used by the onboarding
wizard to save progress at each step.

```python
# backend/app/api/profiles.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session
from app.auth import get_current_profile

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=50)
    role: Literal["vendor", "collector", "both"] | None = None
    tcg_interests: list[str] | None = None
    zip_code: str | None = Field(None, pattern=r"^\d{5}$")
    avatar_url: str | None = None
    onboarding_complete: bool | None = None


@router.patch("/me")
async def update_profile(
    body: ProfileUpdate,
    profile=Depends(get_current_profile),
    session: AsyncSession = Depends(get_session),
):
    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    for key, value in update_data.items():
        setattr(profile, key, value)

    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile
```

### Endpoint 2: `POST /api/v1/profiles/me/vendor`

Creates a `vendor_profiles` row for the current user if one does not already
exist. Called at the end of onboarding when role is `'vendor'` or `'both'`.

```python
@router.post("/me/vendor")
async def create_vendor_profile(
    profile=Depends(get_current_profile),
    session: AsyncSession = Depends(get_session),
):
    from app.models.app import VendorProfile
    from sqlalchemy import select

    existing = await session.execute(
        select(VendorProfile).where(VendorProfile.profile_id == profile.id)
    )
    if existing.scalar_one_or_none():
        return {"message": "vendor profile already exists"}

    vendor = VendorProfile(
        profile_id=profile.id,
        display_name=profile.display_name,
        tcg_interests=profile.tcg_interests or [],
        is_accounting_enabled=False,
    )
    session.add(vendor)
    await session.commit()
    return {"message": "vendor profile created"}
```

### Endpoint 3: `POST /api/v1/profiles/me/avatar`

Accepts an image upload, stores it in S3, returns the URL. Called during
onboarding step 3 if the user uploads an avatar.

```python
@router.post("/me/avatar")
async def upload_avatar(
    image: UploadFile = File(...),
    profile=Depends(get_current_profile),
):
    import boto3, uuid
    from app.core.config import settings

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await image.read()
    if len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Avatar must be under 5MB")

    s3 = boto3.client("s3")
    key = f"avatars/{profile.id}/{uuid.uuid4()}.jpg"
    s3.put_object(
        Bucket=settings.aws_s3_bucket,
        Key=key,
        Body=image_bytes,
        ContentType=image.content_type,
    )

    url = f"https://{settings.aws_s3_bucket}.s3.amazonaws.com/{key}"
    return {"avatar_url": url}
```

Register all three endpoints in `main.py`.

---

## Frontend — routing and middleware

### Onboarding route

Create the onboarding wizard at:
```
frontend/app/(auth)/onboarding/page.tsx
```

This route must:
- Be accessible only to authenticated users
- Redirect to `/vendor/dashboard` or `/collector/dashboard` if
  `onboarding_complete === true`
- Not show the main nav/sidebar (use a minimal layout)

### Middleware update

Update `frontend/middleware.ts` to handle the onboarding redirect:

```typescript
import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  const response = NextResponse.next();
  const supabase = createServerClient(/* config */);

  const { data: { session } } = await supabase.auth.getSession();

  const isOnboardingRoute = request.nextUrl.pathname.startsWith("/onboarding");
  const isAuthRoute = request.nextUrl.pathname.startsWith("/auth");
  const isPublicRoute = request.nextUrl.pathname.startsWith("/shows") ||
                        request.nextUrl.pathname === "/";

  // Not logged in — redirect to login unless public route
  if (!session && !isAuthRoute && !isPublicRoute) {
    return NextResponse.redirect(new URL("/auth/login", request.url));
  }

  // Logged in — check onboarding status
  if (session && !isOnboardingRoute && !isAuthRoute) {
    const { data: profile } = await supabase
      .from("profiles")
      .select("onboarding_complete, role")
      .eq("id", session.user.id)
      .single();

    if (profile && !profile.onboarding_complete) {
      return NextResponse.redirect(new URL("/onboarding", request.url));
    }
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api).*)"],
};
```

---

## Frontend — Zustand store

Create `frontend/lib/stores/useActiveRoleStore.ts`:

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";

type ActiveRole = "vendor" | "collector";

interface ActiveRoleStore {
  activeRole: ActiveRole;
  setActiveRole: (role: ActiveRole) => void;
}

export const useActiveRoleStore = create<ActiveRoleStore>()(
  persist(
    (set) => ({
      activeRole: "vendor",
      setActiveRole: (role) => set({ activeRole: role }),
    }),
    { name: "cardops-active-role" }
  )
);
```

This persists across page refreshes via `localStorage`. Dual-role users
(`role === 'both'`) see a toggle in the nav that calls `setActiveRole`.
Single-role users never see the toggle.

---

## Frontend — onboarding wizard

Create `frontend/app/(auth)/onboarding/page.tsx`.

### State shape

```typescript
interface OnboardingState {
  step: 1 | 2 | 3 | 4;
  // Step 1
  role: "vendor" | "collector" | "both" | null;
  displayName: string;
  // Step 2
  interests: string[];
  // Step 3
  avatarFile: File | null;
  avatarPreviewUrl: string | null;
  // Step 4
  zipCode: string;
  // Submission
  submitting: boolean;
  error: string | null;
}
```

### Step 1 — Role + display name

```tsx
// Three clickable role cards side by side
// "Collector" | "Vendor" | "Both"
// Each card shows a brief description of what that role unlocks

// Display name: text input, required, 1-50 chars
// "Continue" button disabled until role selected AND displayName.trim().length > 0

const roleOptions = [
  {
    value: "collector",
    label: "Collector",
    description: "Browse shows, search vendor inventory, track your collection",
  },
  {
    value: "vendor",
    label: "Vendor",
    description: "Manage inventory, register for shows, log sales and trades",
  },
  {
    value: "both",
    label: "Both",
    description: "Full access to vendor tools and collector features",
  },
];
```

Validation before proceeding to step 2:
- `role` must not be null
- `displayName.trim()` must be at least 1 character

On Continue: call `PATCH /api/v1/profiles/me` with `{ role, display_name }`.
Do not wait for success to advance — optimistically advance and handle errors
on final submission.

### Step 2 — Interests

```tsx
// Simple multi-select pill buttons
// Start with just TCG options for MVP

const tcgOptions = [
  { value: "pokemon", label: "Pokémon" },
  { value: "one_piece", label: "One Piece" },
];

// "Skip for now" link — advances to step 3 without saving interests
// "Continue" button — saves selected interests and advances
// User can select multiple
```

Skippable — show a "Skip for now →" text link below the Continue button.

### Step 3 — Avatar

```tsx
// Drag-and-drop or click-to-upload image area
// Shows preview once image is selected
// File size validation: max 5MB, image/* only
// "Skip for now →" text link — always visible
// "Upload & Continue" button — uploads to /api/v1/profiles/me/avatar,
//   then saves returned avatar_url to local state, advances to step 4
```

Always skippable — avatar_url remains null if skipped.

### Step 4 — ZIP code

```tsx
// Single text input: 5-digit ZIP code
// Basic validation: must match /^\d{5}$/
// Helper text: "Used to find card shows near you"
// "Finish" button — disabled until valid ZIP entered

// On Finish:
//   1. PATCH /api/v1/profiles/me with { zip_code, onboarding_complete: true }
//   2. If role is 'vendor' or 'both':
//        POST /api/v1/profiles/me/vendor
//   3. Set activeRole in Zustand:
//        role === 'vendor' → activeRole = 'vendor'
//        role === 'collector' → activeRole = 'collector'
//        role === 'both' → activeRole = 'vendor' (default for dual-role)
//   4. Redirect:
//        activeRole === 'vendor' → /vendor/dashboard
//        activeRole === 'collector' → /collector/dashboard
```

### Progress indicator

Show a simple step indicator at the top of every step:

```tsx
// Step 1 of 4 — Role
// Step 2 of 4 — Interests
// Step 3 of 4 — Avatar
// Step 4 of 4 — Location

// Visual: four dots or pills, filled for completed steps, current step
// highlighted, future steps muted.
// Do NOT show a back button — forward-only flow for simplicity in MVP.
```

### Layout

Onboarding runs in a minimal layout — no main sidebar, no top nav with links.
Just the CardOps logo, the step indicator, and the form content. Center the
form card on screen. Max width ~480px.

---

## Frontend — nav role toggle (post-onboarding)

For users with `role === 'both'`, add a toggle to the main nav. This is
separate from onboarding but should be built in the same task since the
Zustand store is being set up anyway.

```tsx
// frontend/components/shared/RoleToggle.tsx

import { useActiveRoleStore } from "@/lib/stores/useActiveRoleStore";

export function RoleToggle({ userRole }: { userRole: string }) {
  const { activeRole, setActiveRole } = useActiveRoleStore();

  // Only render for dual-role users
  if (userRole !== "both") return null;

  return (
    <div>
      <button
        onClick={() => setActiveRole("vendor")}
        aria-pressed={activeRole === "vendor"}
      >
        Vendor
      </button>
      <button
        onClick={() => setActiveRole("collector")}
        aria-pressed={activeRole === "collector"}
      >
        Collector
      </button>
    </div>
  );
}
```

Apply styling consistent with the rest of the nav. When `activeRole` changes,
the nav links update to show the relevant set of pages. Implement this toggle
in the existing nav layout component — do not rebuild the nav from scratch.

---

## API client functions

Add to `frontend/lib/api/profiles.ts`:

```typescript
const API = process.env.NEXT_PUBLIC_API_URL;

export async function updateProfile(data: Partial<ProfileUpdate>) {
  const res = await fetch(`${API}/api/v1/profiles/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "Update failed");
  return res.json();
}

export async function createVendorProfile() {
  const res = await fetch(`${API}/api/v1/profiles/me/vendor`, {
    method: "POST",
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "Failed");
  return res.json();
}

export async function uploadAvatar(file: File): Promise<{ avatar_url: string }> {
  const formData = new FormData();
  formData.append("image", file);
  const res = await fetch(`${API}/api/v1/profiles/me/avatar`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "Upload failed");
  return res.json();
}

interface ProfileUpdate {
  display_name?: string;
  role?: "vendor" | "collector" | "both";
  tcg_interests?: string[];
  zip_code?: string;
  avatar_url?: string;
  onboarding_complete?: boolean;
}
```

---

## Verification checklist

Do not mark this task complete until all of the following pass:

- [ ] Alembic migrations applied — `onboarding_complete`, `zip_code`,
      `avatar_url` columns visible in Supabase, role constraint updated
- [ ] Supabase trigger updated to insert `onboarding_complete = false`
- [ ] `PATCH /api/v1/profiles/me` updates the correct fields
- [ ] `POST /api/v1/profiles/me/vendor` creates `vendor_profiles` row
- [ ] New user who signs up is redirected to `/onboarding` by middleware
- [ ] Step 1 blocks Continue until role and display name are both filled
- [ ] Step 2 is skippable, Continue saves selected interests
- [ ] Step 3 is skippable, upload saves avatar_url correctly
- [ ] Step 4 validates 5-digit ZIP before enabling Finish
- [ ] Finish writes `onboarding_complete = true` to DB
- [ ] Finish creates `vendor_profiles` row when role is vendor or both
- [ ] Finish redirects to correct dashboard based on role
- [ ] Returning user with `onboarding_complete = true` is NOT redirected
      to onboarding — they go directly to their dashboard
- [ ] `RoleToggle` component appears in nav only for `role === 'both'` users
- [ ] Switching role via toggle updates nav links without a full page reload
- [ ] No existing scan page functionality is broken

---

## Stop conditions

Stop and check in with the user if:

- The existing middleware structure differs significantly from what's assumed
  above — confirm the actual auth session checking pattern before rewriting it
- `get_current_profile` dependency does not exist yet — it needs to be
  implemented before the profile endpoints will work (it should decode the
  Supabase JWT and look up the `public.profiles` row)
- S3 credentials are not yet configured in `.env` — avatar upload will fail
  silently; flag this rather than skipping the endpoint
- The dashboard routes `/vendor/dashboard` or `/collector/dashboard` do not
  exist yet — create stub pages with a placeholder heading so the redirect
  lands somewhere rather than a 404
