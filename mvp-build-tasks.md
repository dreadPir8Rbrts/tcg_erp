# CardOps MVP — build task breakdown

## Status key
- [ ] Not started
- [~] In progress
- [x] Complete

## Already complete
- [x] Phase 0 — Catalog foundation (TCGdex seed, Alembic migrations, Celery jobs)
- [x] Phase 2 — Scan pipeline (Quick Scan + Full Scan)
- [~] Signup onboarding flow (in progress — see tasks/signup-onboarding-flow.md)

---

## Task 1 — App shell + navigation
**File:** `tasks/task-01-app-shell.md`
**Depends on:** Onboarding complete (auth working, profiles exist)
**Estimated effort:** Medium

Build the persistent layout that wraps all authenticated pages:
- Top nav bar with CardOps logo, role toggle (vendor/collector, only for `role === 'both'`),
  and avatar dropdown (Profile, Settings, Sign Out)
- Vendor sidebar nav (Dashboard, Inventory, Scan, Shows, Transactions, Profile)
- Collector sidebar nav (Dashboard, Collection, Wishlist, Shows, Profile)
- Public top nav (Browse Shows, Sign In, Sign Up) — no sidebar
- Minimal layout for onboarding (logo only, no nav)
- Active link highlighting based on current route
- Role toggle wires to `useActiveRoleStore` Zustand store
- Switching mode redirects to the equivalent dashboard

---

## Task 2 — Vendor dashboard
**File:** `tasks/task-02-vendor-dashboard.md`
**Depends on:** Task 1 (app shell), inventory_items table populated
**Estimated effort:** Medium

The vendor's at-home home screen — summary of their business state:
- Inventory summary cards: total items, total market value, items for sale, items for trade
- Upcoming shows: next 3 shows the vendor is registered for (from vendor_show_registrations)
- Recent transactions: last 5 sales/purchases/trades (from transactions table)
- Quick action buttons: Add Card, Scan, Register for Show
- Empty states for each section when no data exists yet

Backend endpoints needed:
- `GET /api/v1/vendor/dashboard` — returns summary stats, upcoming shows, recent transactions
  in a single call to avoid waterfall requests

---

## Task 3 — Inventory management
**File:** `tasks/task-03-inventory.md`
**Depends on:** Task 1 (app shell)
**Estimated effort:** Large

The core vendor tool. Three sub-pages:

### 3a — Inventory list (`/vendor/inventory`)
- Table view with columns: card image, name + set, variant, condition, qty, cost basis,
  asking price, market price, delta (asking vs market as %), for-sale toggle, for-trade toggle
- Filters: set, condition, for-sale, for-trade, price range
- Sort: by name, market price, delta, days in inventory
- Inline price editing (click asking price → type → enter)
- Soft delete (sets deleted_at, removes from view)
- Bulk select + bulk actions: mark for sale, mark for trade, delete
- Empty state with CTA to Add Card or Scan

### 3b — Add card (`/vendor/inventory/add`)
- Search bar that queries `GET /api/v1/cards/search?q=`
- Results show card image (TCGdex CDN), name, set, rarity
- Selecting a card opens a form: variant selector, condition selector, quantity,
  cost basis (optional), asking price (optional), notes (optional), photo upload (optional)
- Submit creates an `inventory_items` row
- After submit: stay on page with success toast + option to add another

### 3c — Inventory item detail (`/vendor/inventory/[itemId]`)
- Shows all fields for one inventory item
- Edit any field inline
- Shows which shows this item is tagged for
- Photo gallery if photos exist
- Delete button (soft delete with confirmation)

Backend endpoints needed:
- `GET /api/v1/vendor/inventory` — paginated, filterable, sortable
- `POST /api/v1/vendor/inventory` — create inventory item
- `GET /api/v1/vendor/inventory/[itemId]` — single item
- `PATCH /api/v1/vendor/inventory/[itemId]` — update item
- `DELETE /api/v1/vendor/inventory/[itemId]` — soft delete

---

## Task 4 — Wire scans to inventory + transactions
**File:** `tasks/task-04-scan-wiring.md`
**Depends on:** Task 3 (inventory exists), existing scan page
**Estimated effort:** Medium

The scan page already identifies cards. This task connects identification to
inventory and transaction writes.

### Scan → add to inventory
After a successful Quick Scan or Full Scan identification:
- Show confirmation UI: identified card image + details side by side with the scanned photo
- Form fields: condition selector, asking price, cost basis (optional), quantity
- Confirm button → creates `inventory_items` row
- Cancel → discards, returns to scan

### Scan → log sale
New scan mode (add a "Sell" action button before scanning):
- Scan identifies card
- Show confirmation: card details + auto-populated asking price from inventory
  (if card exists in inventory) or market price (if not)
- Price field editable
- Confirm → creates `transaction` (type=sale) + `transaction_item` (direction=out)
  + decrements `inventory_items.quantity`
- If quantity hits 0, soft delete the inventory item

### Scan → log purchase (buy from customer)
New scan mode ("Buy" action button):
- Scan identifies card
- Show: market price + auto-calculated offer (market × vendor buying_rate)
- Vendor adjusts offer if needed
- Confirm → creates `transaction` (type=purchase) + `transaction_item` (direction=in)
  + creates new `inventory_items` row with cost_basis = offer made

---

## Task 5 — Shows (public + vendor)
**File:** `tasks/task-05-shows.md`
**Depends on:** Task 1 (app shell), Task 3 (inventory, for show tagging)
**Estimated effort:** Large

### 5a — Public shows listing (`/shows`)
- List of upcoming card shows sorted by date
- Filter by state/region
- Each show card: name, date, venue, city, # of registered vendors
- Links to show detail page
- No auth required

### 5b — Public show detail (`/shows/[showId]`)
- Show info: name, date, venue, address
- Registered vendors grid: avatar, display name, TCG interests, table location
- Search bar: "Find a card at this show" — searches inventory_items tagged for this show
  via show_inventory_tags, returns list of vendors who have the card with price + condition
- Links to individual vendor public profiles
- No auth required

### 5c — Vendor show registration (`/vendor/shows`)
- Two sections: My Shows (registered) + Browse Upcoming Shows
- My Shows: list of shows vendor is registered for with status, table location
- Browse: same as public shows listing but with "Register" button on each card

### 5d — Show registration flow (`/vendor/shows/[showId]/register`)
- Show details at top
- Table location text field
- Inventory tagging: searchable list of vendor's inventory with checkboxes
  to mark which items they're bringing ("show bag")
- Submit → creates `vendor_show_registrations` row + `show_inventory_tags` rows

### 5e — Show management (`/vendor/shows/[showId]/manage`)
- Active show home screen (at-show context)
- Running totals: revenue today, transactions today
- Quick action buttons: Sell, Buy, Trade (links to scan page with pre-selected action)
- Deal broadcast: text field + duration selector → saves to `active_deals` JSONB
- Show inventory: searchable list of items tagged for this show

Backend endpoints needed:
- `GET /api/v1/shows` — upcoming shows, filterable
- `GET /api/v1/shows/[showId]` — show detail + vendor list
- `GET /api/v1/shows/[showId]/inventory?q=` — cross-vendor inventory search
- `POST /api/v1/vendor/shows/[showId]/register` — register + tag inventory
- `GET /api/v1/vendor/shows/[showId]/manage` — at-show dashboard data

Admin endpoint (for seeding shows — no self-serve show creation in MVP):
- `POST /api/v1/admin/shows` — create a show (admin only, no UI needed)

---

## Task 6 — Transaction history
**File:** `tasks/task-06-transactions.md`
**Depends on:** Task 4 (scan wiring creates transactions)
**Estimated effort:** Small-Medium

### `/vendor/transactions`
- List of all vendor transactions sorted by date descending
- Each row: date, type (sale/purchase/trade), card name(s), total value
- Expandable row or detail modal: shows individual transaction_items
- Filter: by type, by date range, by show
- Total summary at top: total revenue, total spent, net

Backend endpoints needed:
- `GET /api/v1/vendor/transactions` — paginated, filterable
- `GET /api/v1/vendor/transactions/[txId]` — single transaction with items

---

## Task 7 — Collector dashboard + collection
**File:** `tasks/task-07-collector.md`
**Depends on:** Task 1 (app shell)
**Estimated effort:** Medium

### 7a — Collector dashboard (`/collector/dashboard`)
- Upcoming shows near their ZIP (filtered by proximity)
- Wishlist matches: vendors attending upcoming shows who have wishlist cards
- Recently viewed vendors (stored client-side in localStorage)
- Quick links: Browse Shows, My Collection, My Wishlist

### 7b — Collection (`/collector/collection`)
- Same table layout as vendor inventory but for `customer_inventory`
- Add cards: same catalog search flow as vendor add
- Mark each card: is_for_trade, is_for_sale, asking_price
- Privacy toggle: make collection public (is_public on customer_profiles)

### 7c — Wishlist (`/collector/wishlist`)
- Add cards by searching catalog
- Each wishlist item: card image, name, set, max_price (optional),
  preferred_condition (optional)
- Remove from wishlist
- "Find at shows" button per item: queries `/shows` for vendors attending
  upcoming shows who have this card in show-tagged inventory

Backend endpoints needed:
- `GET /api/v1/collector/dashboard` — nearby shows + wishlist matches
- `GET/POST/DELETE /api/v1/collector/collection`
- `GET/POST/DELETE /api/v1/collector/wishlist`

---

## Task 8 — Vendor + collector profiles
**File:** `tasks/task-08-profiles.md`
**Depends on:** Tasks 2-7 (all the data that populates profiles)
**Estimated effort:** Medium

### 8a — Vendor public profile (`/vendors/[vendorId]`)
- Avatar, display name, bio
- TCG interests tags
- Buying rate + trade rate
- Upcoming shows with table locations
- Public inventory slice (items marked for sale/trade, not show-filtered)
- No auth required to view

### 8b — Vendor profile settings (`/vendor/profile`)
- Edit all vendor_profiles fields: display name, bio, interests, buying rate,
  trade rate, avatar
- Toggle which inventory items appear on public profile
- "Preview as customer" toggle to see the public-facing view

### 8c — Collector profile settings (`/collector/profile`)
- Edit customer_profiles fields: display name, interests, avatar
- Privacy toggle: make collection public/private
- ZIP code update

### 8d — Account settings (`/settings`)
- Email change
- Password change
- Delete account (soft delete with confirmation)
- Notification preferences (stub for MVP — full push notifications are v2)

---

## Task 9 — Card detail + global search
**File:** `tasks/task-09-cards.md`
**Depends on:** Catalog seed (Phase 0)
**Estimated effort:** Small-Medium

### 9a — Global search (`/search`)
- Search input querying `GET /api/v1/cards/search?q=`
- Results: card image, name, set, rarity, market price
- Click result → card detail page
- No auth required

### 9b — Card detail (`/cards/[cardId]`)
- Card image (TCGdex CDN), full card details (HP, attacks, abilities, etc.)
- Market price section: TCGPlayer price by variant, Cardmarket EUR (secondary)
- "Who has this card?" — vendors at upcoming shows with this card in
  show-tagged inventory (links to vendor profile)
- "Add to wishlist" button (if logged in as collector)
- No auth required to view

Backend endpoints needed:
- `GET /api/v1/cards/[cardId]` — full card + latest price snapshot
- `GET /api/v1/cards/[cardId]/vendors` — vendors at upcoming shows with this card

---

## Task 10 — Landing page
**File:** `tasks/task-10-landing.md`
**Depends on:** Nothing (can be built anytime)
**Estimated effort:** Small

### `/` Landing page
- Hero: headline, subheadline, CTA buttons (Browse Shows, Sign Up)
- Three-column value props: For Vendors, For Collectors, At the Show
- Upcoming shows preview (pull 3 nearest shows from API — no ZIP needed,
  just most recent)
- Sign up CTA at bottom
- Public nav (no sidebar)
- This page is the only truly marketing-facing page in MVP

---

## Recommended build order

Given what's already complete (catalog, scans, onboarding in-progress):

```
Onboarding (in progress)
  → Task 1: App shell + nav        ← unblocks everything
    → Task 3: Inventory management ← core vendor value
      → Task 4: Wire scans → inventory + transactions
        → Task 2: Vendor dashboard ← now has real data
        → Task 6: Transactions
        → Task 5: Shows
          → Task 7: Collector features
            → Task 8: Profiles
              → Task 9: Card detail + search
                → Task 10: Landing page
```

First working end-to-end demo is achievable after Tasks 1 + 3 + 4 + 5a/5b:
a vendor can sign up, add inventory, register for a show, and a customer can
browse that show and find the card they're looking for.
