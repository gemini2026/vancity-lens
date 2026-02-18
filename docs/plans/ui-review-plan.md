# UI Review Plan — VanCity Lens

**Generated:** 2026-02-17  
**Application:** VanCity Lens (Vancouver Development Intelligence Platform)  
**Frontend Stack:** Next.js 15, React 19, Tailwind CSS 4, Radix UI, Mapbox GL 3.9

---

## Application Overview

**VanCity Lens** is a Vancouver city planning intelligence platform that combines:
- **Interactive map** with Transit-Oriented Area (TOA) zones, development opportunities, and intelligence signals
- **RAG-powered chat** for asking questions about Vancouver development, backed by city council minutes, rezoning applications, and news
- **Neighborhood scorecards** for comparing quality-of-life metrics across 22 Vancouver neighborhoods

**Target User:** Colin — a single POC user (Vancouver resident, developer, or city planning enthusiast) who wants to:
- Find development opportunities near transit
- Understand zoning changes and political sentiment
- Track signals (rezoning applications, council decisions, permits) on a map
- Compare neighborhoods for investment/living decisions

**Key Characteristics:**
- Single-page app with hash-based routing (`#map`, `#intel`, `#hoods`)
- Mobile-responsive (bottom tab bar on mobile, top nav on desktop)
- Optional JWT authentication (POC is open-access)
- Real-time data from FastAPI backend + PostgreSQL with PostGIS and pgvector

---

## Authentication Strategy

**Authentication Type:** JWT Bearer tokens (optional for POC)

**Access Levels:**
- **Anonymous:** All three main tabs work without auth (Map, Intelligence, Neighborhoods)
- **Authenticated User:** Unlocks saved parcels, watchlists, custom alerts, share links
- **Admin:** Access to pipeline health dashboards (not in scope for UX review)

**E2E Test Credentials:**
- User: `e2e-user@test.com` / `E2eTestPass123!`
- Admin: `e2e-admin@test.com` / `E2eAdminPass123!`

**Auth Flow for Screenshots:**
1. Register test user via `POST /api/v1/auth/register` (if not exists)
2. Login via `POST /api/v1/auth/login` → get `access_token` and `refresh_token`
3. Store tokens in localStorage: `vcl_access_token`, `vcl_refresh_token`
4. Frontend `AuthProvider` context manages session restoration

**Strategy for Capture:**
- **Scenario 1-10:** Anonymous (no auth) — cover all public features
- **Scenario 11-15:** Authenticated user — cover saved parcels, watchlists, share links

---

## Data Seeding Strategy

**Seed Script:** `scripts/seed_e2e.sh` → runs `db/008_e2e_seed.sql`

**Seeded Entities:**
- **Documents:** 5 test documents (IDs 10001-10005)
- **Document Chunks:** 6 chunks (IDs 10001-10006)
- **Intelligence Signals:** 5 signals (IDs 10001-10005) with types:
  - `rezoning_decision` (2)
  - `council_vote` (1)
  - `development_permit` (1)
  - `news_article` (1)
- **Parcels:** 1 canonical test parcel (PID `100-001-009`, address `2220 Cambie Street`)

**Production Seed (for realistic screenshots):**
- Script: `python scripts/seed_data.py --status` → check if production data loaded
- If needed: `python scripts/seed_data.py` → scrape + process real documents (~15-30 min)

**ID Extraction:**
- Signal IDs: `10001-10005` (known from SQL)
- Parcel PID: `100-001-009` (known from SQL)
- Neighborhood slugs: Extract from API response `GET /api/v1/intel/neighborhoods`
- Chat session ID: Extract from API response after first chat message

**Cleanup:**
- E2E seed is idempotent (uses `ON CONFLICT DO NOTHING`)
- Production seed is persistent (no cleanup needed)

---

## Route Inventory

| # | Route Pattern | Page Component | Dynamic Segments | Requires Data | Description |
|---|---------------|----------------|------------------|---------------|-------------|
| 1 | `/` (default: `#map`) | `MapView` | None | Yes | Map tab with TOA zones, opportunities, signals |
| 2 | `/#map` | `MapView` | None | Yes | Map tab (explicit) |
| 3 | `/#intel` | `IntelPage` | None | Yes | Intelligence tab (chat + signal feed) |
| 4 | `/#hoods` | `NeighborhoodPage` | None | Yes | Neighborhoods tab (scorecards) |

**Note:** Single-page app with hash-based routing. No dynamic route segments like `/items/:id`.

---

## Scenario Design

### Scenario 1: Anonymous — Map Exploration (Desktop Dark Theme)
**Goal:** Capture the default map view with all major in-page states

**Steps:**
1. Navigate to `#map`
2. Wait for map tiles to load
3. Screenshot: Map default view (case study carousel visible)
4. Click tier 1 checkbox → Screenshot: Tier 1 layer visible
5. Click tier 2 checkbox → Screenshot: Tier 2 layer visible
6. Click tier 3 checkbox → Screenshot: Tier 3 layer visible
7. Click opportunity marker → Screenshot: Parcel detail panel open
8. Click "Deal Model" button → Screenshot: Financing calculator modal open
9. Close modal → Click "Top Deals" button → Screenshot: Top opportunities panel open
10. Toggle "Show Signals" → Screenshot: Signal markers visible
11. Toggle "Heatmap" → Screenshot: Signal density heatmap visible

### Scenario 2: Anonymous — Map Search & Parcel Analysis (Desktop Dark Theme)
**Goal:** Capture address search and parcel detail panel states

**Steps:**
1. Navigate to `#map`
2. Focus address search input → Screenshot: Search dropdown open
3. Type "Cambie" → Screenshot: Search results dropdown
4. Select "2220 Cambie Street" → Screenshot: Map flies to location, parcel detail panel open
5. Expand "Comparable Sales" section → Screenshot: Section expanded
6. Expand "Due Diligence" section → Screenshot: Section expanded

### Scenario 3: Anonymous — Intelligence Discovery (Desktop Dark Theme)
**Goal:** Capture chat + signal feed states

**Steps:**
1. Navigate to `#intel`
2. Screenshot: Chat empty + Signal feed with filters
3. Type question "What rezoning applications were approved last month?" → Send → Screenshot: Chat conversation with LLM response
4. Click filter by neighborhood → Select "Mount Pleasant" → Screenshot: Feed filtered by neighborhood
5. Click signal card → Screenshot: Signal expanded with document details
6. Click "Load more" → Screenshot: Additional signals loaded

### Scenario 4: Anonymous — Neighborhoods Comparison (Desktop Dark Theme)
**Goal:** Capture neighborhood list, detail, and comparison views

**Steps:**
1. Navigate to `#hoods`
2. Screenshot: List view with all neighborhoods
3. Type "Mount" in search → Screenshot: Filtered list by name
4. Click "Mount Pleasant" card → Screenshot: Detail scorecard view
5. Click "Back" → Check compare boxes (Mount Pleasant, Kitsilano) → Screenshot: "Compare Selected" button visible
6. Click "Compare Selected" → Screenshot: Comparison view open

### Scenario 5: Mobile — Bottom Tab Navigation (Mobile 375x812 Dark Theme)
**Goal:** Capture mobile responsive layout and navigation

**Steps:**
1. Navigate to `#map` (mobile viewport 375x812)
2. Screenshot: Map with bottom tab bar and layers FAB
3. Click layers FAB → Screenshot: Layer menu drawer open
4. Close drawer → Tap "Intel" tab → Screenshot: Intelligence tab (mobile layout)
5. Tap "Hoods" tab → Screenshot: Neighborhoods tab (mobile layout)

### Scenario 6: Anonymous — Light Theme (Desktop Light Theme)
**Goal:** Capture light theme variants of key screens

**Steps:**
1. Click theme toggle → cycle to light theme
2. Navigate to `#map` → Screenshot: Map in light theme
3. Navigate to `#intel` → Screenshot: Intelligence in light theme
4. Navigate to `#hoods` → Screenshot: Neighborhoods in light theme

### Scenario 7: Anonymous — Empty States (Desktop Dark Theme)
**Goal:** Capture empty states when no data is present

**Steps:**
1. Navigate to `#intel` → Filter by neighborhood "Test Neighborhood" (no matches) → Screenshot: "No signals found" message
2. Navigate to `#hoods` → Search "ZZZZZ" (no matches) → Screenshot: "No neighborhood data yet" message

### Scenario 8: Authenticated — Saved Parcels & Watchlists (Desktop Dark Theme)
**Goal:** Capture authenticated user features

**Pre-requisites:** Auth tokens in localStorage

**Steps:**
1. Navigate to `#map` → Click opportunity marker → Screenshot: Parcel detail panel with star icon (unsaved)
2. Click star icon → Screenshot: Parcel saved (star filled)
3. Click notifications bell → Screenshot: Alerts dropdown open
4. Navigate to watchlist panel → Screenshot: Watchlist panel with saved parcels

### Scenario 9: Mobile — Parcel Detail (Mobile 375x812 Dark Theme)
**Goal:** Capture mobile parcel detail full-screen view

**Steps:**
1. Navigate to `#map` (mobile viewport 375x812)
2. Tap opportunity marker → Screenshot: Full-screen parcel detail panel
3. Scroll down → Screenshot: All parcel detail sections visible

### Scenario 10: Desktop — Disclaimer Banner (Desktop Dark Theme)
**Goal:** Capture disclaimer banner (first visit)

**Pre-requisites:** Clear localStorage `vcl_disclaimer_dismissed`

**Steps:**
1. Navigate to `#map` → Screenshot: Disclaimer banner visible at top
2. Click "Dismiss" → Screenshot: Disclaimer banner hidden

---

## Variables

| Variable | Source | Usage | Example Value |
|----------|--------|-------|---------------|
| `base_url` | Config | Base URL for navigation | `http://localhost:3000` |
| `access_token` | Seed command output | Auth header for API calls | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` |
| `refresh_token` | Seed command output | Token refresh | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` |
| `parcel_pid` | SQL seed | Known test parcel PID | `100-001-009` |
| `signal_id` | SQL seed | Known test signal ID | `10001` |
| `neighborhood_slug` | API response | Neighborhood slug for filters | `mount-pleasant` |

---

## Capture Checklist

### Top-Level Pages
- [x] Map tab (`#map`) — desktop dark
- [x] Intelligence tab (`#intel`) — desktop dark
- [x] Neighborhoods tab (`#hoods`) — desktop dark
- [x] Map tab — desktop light
- [x] Intelligence tab — desktop light
- [x] Neighborhoods tab — desktop light
- [x] Map tab — mobile (375x812)
- [x] Intelligence tab — mobile (375x812)
- [x] Neighborhoods tab — mobile (375x812)

### In-Page State Variations — Map Tab
- [x] Map default view with case study carousel
- [x] Tier 1 layer visible
- [x] Tier 2 layer visible
- [x] Tier 3 layer visible
- [x] Parcel detail panel open (desktop)
- [x] Parcel detail panel open (mobile full-screen)
- [x] Financing calculator modal open
- [x] Top opportunities panel open
- [x] Signal markers visible
- [x] Heatmap overlay visible
- [x] Address search dropdown open
- [x] Search results dropdown
- [x] Layers menu drawer open (mobile)
- [x] Comparable Sales section expanded
- [x] Due Diligence section expanded

### In-Page State Variations — Intelligence Tab
- [x] Chat empty + Signal feed (default)
- [x] Chat conversation with LLM response
- [x] Feed filtered by neighborhood
- [x] Signal card expanded
- [x] Additional signals loaded (after "Load more")
- [x] Empty state: "No signals found"

### In-Page State Variations — Neighborhoods Tab
- [x] List view with all neighborhoods
- [x] Filtered list by search
- [x] Detail scorecard view
- [x] "Compare Selected" button visible (2+ checked)
- [x] Comparison view open
- [x] Empty state: "No neighborhood data yet"

### Global States
- [x] Disclaimer banner visible (first visit)
- [x] Light theme (all tabs)
- [x] Alerts dropdown open (authenticated)
- [x] Bottom tab bar (mobile)
- [x] Top nav (desktop)

### Authenticated States
- [x] Parcel saved (star filled)
- [x] Alerts dropdown open
- [x] Watchlist panel with saved parcels

### Empty States
- [x] Intelligence: "No signals found"
- [x] Neighborhoods: "No neighborhood data yet"

---

## In-Page States Inventory

| Route | Trigger | State Name | Screenshot Scenario |
|-------|---------|------------|---------------------|
| `#map` | Default load | Map with case study carousel | Scenario 1, Step 3 |
| `#map` | Click tier 1 checkbox | Tier 1 layer visible | Scenario 1, Step 4 |
| `#map` | Click tier 2 checkbox | Tier 2 layer visible | Scenario 1, Step 5 |
| `#map` | Click tier 3 checkbox | Tier 3 layer visible | Scenario 1, Step 6 |
| `#map` | Click opportunity marker | Parcel detail panel open (desktop) | Scenario 1, Step 7; Scenario 2, Step 4 |
| `#map` | Click "Deal Model" button | Financing calculator modal open | Scenario 1, Step 8 |
| `#map` | Click "Top Deals" button | Top opportunities panel open | Scenario 1, Step 9 |
| `#map` | Toggle "Show Signals" | Signal markers visible | Scenario 1, Step 10 |
| `#map` | Toggle "Heatmap" | Heatmap overlay visible | Scenario 1, Step 11 |
| `#map` | Focus address search input | Search dropdown open | Scenario 2, Step 2 |
| `#map` | Type in address search | Search results dropdown | Scenario 2, Step 3 |
| `#map` | Expand "Comparable Sales" | Section expanded | Scenario 2, Step 5 |
| `#map` | Expand "Due Diligence" | Section expanded | Scenario 2, Step 6 |
| `#map` | Click layers FAB (mobile) | Layer menu drawer open | Scenario 5, Step 3 |
| `#map` | Tap marker (mobile) | Parcel detail full-screen (mobile) | Scenario 9, Step 2 |
| `#intel` | Default load | Chat empty + Signal feed | Scenario 3, Step 2 |
| `#intel` | Type question + send | Chat conversation with LLM response | Scenario 3, Step 3 |
| `#intel` | Filter by neighborhood | Feed filtered | Scenario 3, Step 4 |
| `#intel` | Click signal card | Signal expanded | Scenario 3, Step 5 |
| `#intel` | Click "Load more" | Additional signals loaded | Scenario 3, Step 6 |
| `#intel` | Filter with no matches | "No signals found" | Scenario 7, Step 1 |
| `#hoods` | Default load | List view with all neighborhoods | Scenario 4, Step 2 |
| `#hoods` | Type in search | Filtered list by name | Scenario 4, Step 3 |
| `#hoods` | Click neighborhood card | Detail scorecard view | Scenario 4, Step 4 |
| `#hoods` | Check 2+ compare boxes | "Compare Selected" button visible | Scenario 4, Step 5 |
| `#hoods` | Click "Compare Selected" | Comparison view open | Scenario 4, Step 6 |
| `#hoods` | Search with no matches | "No neighborhood data yet" | Scenario 7, Step 2 |
| Global | First visit | Disclaimer banner visible | Scenario 10, Step 1 |
| Global | Click theme toggle | Light theme active | Scenario 6, Step 1 |
| Global | Click alerts bell (auth) | Alerts dropdown open | Scenario 8, Step 3 |
| Global | Mobile | Bottom tab bar visible | Scenario 5, Step 2 |
| `#map` | Click star icon (auth) | Parcel saved (star filled) | Scenario 8, Step 2 |

---

## Notes

- **Total Distinct States:** ~40+ across all tabs
- **Scenarios:** 10 scenarios covering anonymous + authenticated flows
- **Viewports:** Desktop (1280x800), Mobile (375x812)
- **Themes:** Dark (default), Light
- **Auth:** Anonymous (Scenarios 1-7, 10), Authenticated (Scenario 8-9)
- **Data Dependency:** All scenarios require E2E seed (`scripts/seed_e2e.sh`) OR production seed (`python scripts/seed_data.py`)

---

## Next Steps

1. **Validate Scenarios File:** Run `python3 .cursor/skills/review-ux/scripts/validate_scenarios.py docs/plans/ui-review-scenarios.json`
2. **Run Capture Script:** `python3 .cursor/skills/review-ux/scripts/capture_screens.py --scenario docs/plans/ui-review-scenarios.json`
3. **Verify Screenshots:** Check `docs/designs/screenshots/original/` for completeness
4. **Compress Images:** `python3 .cursor/skills/review-ux/scripts/compress_images.py --input-dir docs/designs/screenshots/original`
5. **Proceed to Phase 3:** UX Analysis
