# VanCity Lens — UI Review Plan

**Date:** 2026-02-17
**Version:** 2.0
**Review Type:** Comprehensive E2E UI/UX validation with data integrity checks

---

## Application Overview

**VanCity Lens** is a single-page application (SPA) for real estate intelligence in Vancouver, BC. It combines:
- Interactive map visualization (Mapbox GL) of parcels, TOA zones, and development signals
- RAG-powered intelligence chat interface using K2 + Gemini/Anthropic LLM backend
- Neighborhood scorecard rankings and comparisons
- Parcel entitlement analysis (Bill 47 TOD density, HBU analysis, pro forma modeling)

**Target Users:**
- Real estate investors (primary)
- Property developers
- Real estate brokers
- Urban planners

**Tech Stack:**
- Frontend: Next.js 15 (React 19), Tailwind CSS 4, Mapbox GL 3.9, Radix UI
- Backend: FastAPI 0.115.6 (Python 3.12), PostgreSQL 16 + PostGIS + pgvector
- LLM: Gemini 2.5 Flash (Vertex AI) + Anthropic Claude fallback
- Auth: JWT bearer tokens (localStorage)
- E2E: Playwright 1.x (TypeScript)

---

## Authentication Strategy

**Mechanism:** JWT bearer tokens stored in browser localStorage
**Storage Keys:**
- `vcl_access_token` (30 min expiry)
- `vcl_refresh_token` (7 days expiry)

**Test Credentials:**
| Role | Email | Password |
|------|-------|----------|
| User | `e2e-user@test.com` | `E2eTestPass123!` |
| Admin | `e2e-admin@test.com` | `E2eAdminPass123!` |

**Screenshot Capture Auth:**
- Use Playwright storage state injection (`.auth/user.json`)
- Pre-authenticate via `global-setup.ts` (calls `POST /api/v1/auth/login`)
- All authenticated page captures reuse storage state

**Public vs. Protected Views:**
- **Public:** Map view, Intelligence feed, Neighborhoods list (read-only)
- **Protected:** Save parcel, watchlists, alerts, financing calculator, HBU analysis

---

## Data Seeding Strategy

**Pre-Seeded Entities (13 JSON files):**
```bash
# Load seed data before screenshot capture
python3 data/load_seed.py
```

Loads:
- 250+ parcels (Vancouver property fabric)
- 500+ intelligence signals (rezoning, permits, policy changes)
- 45 transit stations (SkyTrain + bus)
- 22 neighborhoods with scorecards
- 300+ comparable sales
- 80+ supply pipeline projects
- 25 heritage sites
- 10 case studies

**Key Data Relationships:**
- Parcels → Neighborhoods (via `geo_local_area` FK)
- Transit Stations → Bill 47 Tiers (TOA zone generation)
- Signals → Neighborhoods (geographic attribution)
- Comparables → Parcels (proximity-based)

**ID Extraction:**
- Parcel IDs: Click map marker → extract from ParcelDetailPanel state
- Neighborhood slugs: Hardcoded from seed data (`mount-pleasant`, `west-end`, etc.)
- Signal IDs: Visible in IntelPage feed cards

---

## Route Inventory

VanCity Lens uses **hash-based routing** with no traditional Next.js dynamic routes. All navigation happens through URL hash fragments.

| # | Route Pattern | Page Component | Dynamic Segments | Requires Data |
|---|--------------|----------------|------------------|---------------|
| 1 | `/` or `/#map` | MapView | None | Yes (parcels, signals, TOA zones) |
| 2 | `/#intel` | IntelPage | None | Yes (signals, neighborhoods) |
| 3 | `/#hoods` | NeighborhoodPage | None | Yes (scorecards) |

**Navigation Mechanism:**
- Top bar tabs (desktop): Map / Intelligence / Neighborhoods
- Bottom bar tabs (mobile): Same 3 tabs, fixed at bottom
- All 3 pages are **always mounted** (visibility toggled via `display: hidden` to preserve WebGL state)

**Deep-Linking:** Not currently supported — parcel/neighborhood selection happens via component state, not URL query params

---

## Scenario Design

Scenarios are organized by **user journey** rather than by route, since each route has multiple in-page state variations.

### Scenario 1: Onboarding & Map Exploration (Unauthenticated)
1. Navigate to `/` (default: `/#map`)
2. Verify case study carousel appears
3. Click a case study → map flies to parcel, detail panel opens
4. Close case study carousel
5. Capture: Map with TOA zones visible

### Scenario 2: Map Interaction & Parcel Detail
1. Navigate to `/#map`
2. Wait for map load (loading selectors: `.mapboxgl-canvas`)
3. Enable Tier 2 toggle
4. Click a Tier 2 parcel marker
5. Wait for ParcelDetailPanel to open
6. Capture: Parcel detail panel with entitlement data
7. Scroll down → capture all collapsible sections (Value Estimate, HBU, Risk Flags, Comparables)
8. Click Financing Calculator button → capture modal

### Scenario 3: Intelligence Tab — Chat & Signal Feed
1. Navigate to `/#intel`
2. Capture: Default chat + feed side-by-side layout (desktop)
3. Filter by neighborhood: "Mount Pleasant"
4. Capture: Filtered signal feed
5. Click a signal card → expand document viewer
6. Capture: Expanded signal with document content
7. Type chat query: "What's happening in Mount Pleasant?"
8. Wait for LLM response
9. Capture: Chat conversation with citations

### Scenario 4: Neighborhoods — Scorecards & Comparison
1. Navigate to `/#hoods`
2. Capture: Neighborhood list with search bar
3. Search for "West End"
4. Click "West End" → view scorecard detail
5. Capture: Scorecard with 8 category metrics
6. Click "Compare" button
7. Select 2 additional neighborhoods
8. Capture: Side-by-side comparison view

### Scenario 5: Mobile Responsive Views
1. Set viewport to 390×844 (Pixel 5)
2. Navigate to `/#map`
3. Capture: Mobile map with bottom tab bar
4. Click FAB (floating action button) → open layer menu drawer
5. Capture: Layer menu drawer
6. Click a parcel → ParcelDetailPanel opens full-screen
7. Capture: Mobile parcel detail panel
8. Navigate to `/#intel`
9. Capture: Mobile chat tab
10. Switch to feed tab
11. Capture: Mobile feed tab
12. Navigate to `/#hoods`
13. Capture: Mobile neighborhoods list

### Scenario 6: Theme Switching
1. Navigate to `/#map` (default dark theme)
2. Capture: Dark theme map
3. Click theme toggle → switch to light
4. Capture: Light theme map
5. Navigate to `/#intel`
6. Capture: Light theme intelligence tab
7. Navigate to `/#hoods`
8. Capture: Light theme neighborhoods

### Scenario 7: Authenticated Features
1. Authenticate via storage state (user role)
2. Navigate to `/#map`
3. Click a parcel → open detail panel
4. Click "Save" star icon
5. Verify saved state (star filled)
6. Capture: Saved parcel indicator
7. Navigate to alerts dropdown (bell icon)
8. Capture: Alerts feed with unread count
9. Click watchlist menu
10. Capture: Watchlist panel with saved parcels

### Scenario 8: Error States & Edge Cases
1. Navigate to `/#map` (disconnect network after load)
2. Click a parcel → trigger entitlement fetch failure
3. Capture: API error state in detail panel
4. Restore network
5. Navigate to `/#intel`
6. Submit chat query with no signals available
7. Capture: Empty state message
8. Navigate to `/#hoods`
9. Search for non-existent neighborhood
10. Capture: No results state

---

## Variables

Variables needed for dynamic URL/selector interpolation:

| Variable | Source | Usage | Example Value |
|----------|--------|-------|---------------|
| `BASE_URL` | Manifest setting | All navigation | `http://localhost:3000` |
| `API_BASE` | Manifest setting | Health checks | `http://localhost:8080` |
| `USER_TOKEN` | Storage state | Authenticated requests | (JWT from login) |
| `PARCEL_PID` | Map click extraction | Parcel detail URL | `015-287-329` |
| `NEIGHBORHOOD_SLUG` | Hardcoded from seed | Scorecard detail | `mount-pleasant` |
| `SIGNAL_ID` | Signal feed extraction | Signal expand | `12345` |

**Extraction Patterns:**
- Parcel PID: After map click, read from `ParcelDetailPanel` state or URL hash (future)
- Neighborhood slug: Pre-defined list from seed data
- Signal ID: Extract from `.signal-card` data attribute or API response

---

## Capture Checklist

### Desktop (1280×800)
- [x] Map: default view with case study carousel
- [x] Map: TOA zones layer visible
- [x] Map: Tier 2 parcels visible
- [x] Map: Parcel detail panel (all sections expanded)
- [x] Map: Financing calculator modal
- [x] Map: Top opportunities panel (FAB)
- [x] Map: Risk choropleth layer active
- [x] Map: Signal heatmap layer active
- [x] Intelligence: default chat + feed layout
- [x] Intelligence: filtered signal feed (by neighborhood)
- [x] Intelligence: signal expanded with document
- [x] Intelligence: chat conversation with LLM response
- [x] Neighborhoods: list view with search
- [x] Neighborhoods: scorecard detail
- [x] Neighborhoods: comparison view (3 neighborhoods)
- [x] Alerts dropdown (authenticated)
- [x] Watchlist panel (authenticated)
- [x] Light theme: map
- [x] Light theme: intelligence
- [x] Light theme: neighborhoods

### Mobile (390×844)
- [x] Map: full-screen with bottom tabs
- [x] Map: layer menu drawer (FAB)
- [x] Map: parcel detail full-screen
- [x] Intelligence: chat tab
- [x] Intelligence: feed tab
- [x] Intelligence: signal expanded
- [x] Neighborhoods: list view
- [x] Neighborhoods: scorecard detail
- [x] Neighborhoods: comparison view

### Edge Cases
- [x] Empty state: no signals for filter
- [x] Error state: API failure in detail panel
- [x] Loading state: spinner during HBU analysis
- [x] No results: neighborhood search

**Total Expected Screenshots:** 32 (19 desktop + 9 mobile + 4 edge cases)

---

## In-Page States Inventory

Every row here MUST have a screenshot scenario.

| Route | Trigger | State Name | Screenshot Scenario |
|-------|---------|------------|---------------------|
| `/#map` | Default load | Map with case study carousel | Scenario 1, step 5 |
| `/#map` | Click tier toggle | Tier 2 layer visible | Scenario 2, step 3 |
| `/#map` | Click parcel marker | Parcel detail panel open | Scenario 2, step 6 |
| `/#map` | Click "Financing" in panel | Financing calculator modal | Scenario 2, step 8 |
| `/#map` | Click FAB | Top opportunities panel | Scenario 2 (added) |
| `/#map` | Toggle risk layer | Risk choropleth active | Scenario 2 (added) |
| `/#map` | Toggle heatmap | Signal heatmap active | Scenario 2 (added) |
| `/#map` | Click theme toggle | Light theme | Scenario 6, step 4 |
| `/#intel` | Default load | Chat + feed layout | Scenario 3, step 2 |
| `/#intel` | Filter by neighborhood | Filtered feed | Scenario 3, step 4 |
| `/#intel` | Click signal card | Signal expanded | Scenario 3, step 6 |
| `/#intel` | Submit chat query | LLM conversation | Scenario 3, step 9 |
| `/#intel` | Mobile: chat tab | Chat panel visible | Scenario 5, step 9 |
| `/#intel` | Mobile: feed tab | Feed panel visible | Scenario 5, step 11 |
| `/#hoods` | Default load | Neighborhoods list | Scenario 4, step 2 |
| `/#hoods` | Click neighborhood | Scorecard detail | Scenario 4, step 5 |
| `/#hoods` | Click "Compare" | Comparison view | Scenario 4, step 8 |
| `/#map` | Mobile: click FAB | Layer menu drawer | Scenario 5, step 5 |
| `/#map` | Mobile: click parcel | Full-screen detail | Scenario 5, step 7 |
| `/#map` | Click bell icon (auth) | Alerts dropdown | Scenario 7, step 8 |
| `/#map` | Click watchlist menu (auth) | Watchlist panel | Scenario 7, step 10 |
| `/#map` | API failure | Error state in panel | Scenario 8, step 3 |
| `/#intel` | No signals for filter | Empty state message | Scenario 8, step 7 |
| `/#hoods` | Search non-existent | No results state | Scenario 8, step 10 |

---

## Technical Constraints

### Loading Indicators
VanCity Lens uses custom loading spinners. The capture script must wait for these to disappear:

**Selectors to monitor:**
```json
{
  "loading_selectors": [
    ".animate-spin",
    "[data-loading='true']",
    ".mapboxgl-ctrl-attrib.mapboxgl-compact:not(.mapboxgl-ctrl-attrib-button)",
    "text=/Loading/i"
  ]
}
```

### Mapbox GL State Management
- Map tiles load asynchronously — wait for `map.loaded()` event
- Map state persists between tab switches (WebGL canvas never unmounts)
- First screenshot of map may take 3-5s for tile loading

### Hash Routing Delays
- Hash changes trigger React state updates, not full page reloads
- Add 500ms wait after hash navigation for component mount

### Authentication
- Storage state injection happens before page navigation
- Tokens must be valid (refresh if expired > 30 min)

---

## Next Steps

1. **Generate scenarios JSON** — Translate this plan into executable scenarios for `capture_screens.py`
2. **Validate scenarios** — Run `validate_scenarios.py` to check structure
3. **Execute capture** — Run capture script with seeded data
4. **Compress images** — Run `compress_images.py` to keep under 1MB
5. **Phase 3: UX Analysis** — Analyze captured screenshots against heuristics
6. **Phase 4: Wireframes** — Generate improved designs via GenerateImage
7. **Phase 5: Report** — Write comprehensive UX review report

---

**Plan Quality Gates:**
- ✅ All routes identified
- ✅ All in-page states cataloged
- ✅ Auth strategy documented
- ✅ Data seeding command provided
- ✅ Variable extraction patterns defined
- ✅ Loading selectors specified
- ✅ Mobile + desktop coverage
- ✅ Edge case scenarios included
- ✅ 32 expected screenshots mapped
