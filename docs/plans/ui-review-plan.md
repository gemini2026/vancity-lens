# UI Review Plan

## Application overview

**VanCity Lens** is a Vancouver real estate intelligence single-page application. It provides three main views — an interactive map with parcel analysis, an AI-powered intelligence chat + signal feed, and neighborhood scorecards — all aimed at real estate investors, developers, and analysts evaluating land opportunities in Vancouver.

**Frontend stack:** Next.js 15, React 19, Tailwind CSS 4, Mapbox GL, Lucide icons, Radix UI primitives (installed but largely unused), custom components.

**Target users:** Real estate investors, property developers, urban planners, and analysts — ranging from technical to non-technical.

## Authentication strategy

No authentication is required for screenshot capture. The app is publicly accessible. All three main tabs (Map, Intelligence, Neighborhoods) load without login. Auth-gated features (watchlists, alerts, saved views) are optional — we'll capture the default unauthenticated experience.

## Data seeding strategy

The app fetches data from the backend API at `http://localhost:8080`. For populated screenshots:

- **Map tab**: Relies on TOA GeoJSON endpoints and parcel entitlement API. Should show populated map with layers.
- **Intelligence tab**: Needs intelligence signals in the database. E2E seed SQL at `db/008_e2e_seed.sql` provides sample signals.
- **Neighborhoods tab**: Needs neighborhood scorecard data from the API.

If the backend is running and seeded, all views should show populated data. No explicit seeding commands needed for this capture session — the dev stack appears to be running.

## Route inventory

This is a single-page application using hash-based routing. All views are served from `/`.

| # | Route pattern | Page component | Dynamic segments | Requires data |
|---|--------------|----------------|------------------|---------------|
| 1 | `/` (default → `#map`) | MapView | none | yes (TOA GeoJSON, parcels) |
| 2 | `/#map` | MapView | none | yes (TOA GeoJSON, parcels) |
| 3 | `/#intel` | IntelPage | none | yes (signals, neighborhoods) |
| 4 | `/#hoods` | NeighborhoodPage | none | yes (neighborhood scorecards) |

## Scenario design

Scenarios are grouped into logical user flows:

1. **Map view (default)** — land on map, capture default state with layers
2. **Map interactions** — toggle layers, click a parcel, view detail panel
3. **Intelligence tab** — switch to intel, capture chat + signal feed
4. **Intelligence interactions** — filter signals, expand a signal card
5. **Neighborhoods tab** — view list, click neighborhood detail, compare
6. **Theme switching** — light mode capture of key screens
7. **Mobile viewport** — key screens at 390×844

## Variables

| Variable | Source | Used in |
|----------|--------|---------|
| `base_url` | settings | All scenarios |

No dynamic entity IDs needed since the app uses hash-based routing and all content loads from API endpoints.

## Capture checklist

- [x] All top-level pages (Map, Intel, Hoods)
- [x] Map with layers visible
- [x] Map with parcel detail panel open
- [x] Intel chat panel + signal feed
- [x] Intel signal expanded
- [x] Neighborhoods list view
- [x] Neighborhood detail view
- [x] Neighborhood compare view
- [x] Theme: dark mode (default) + light mode
- [x] Mobile viewport for key screens (390×844)
- [x] Disclaimer banner visible

## In-page states inventory

| Route | Trigger | State name | Screenshot scenario |
|-------|---------|------------|---------------------|
| `#map` | Default load | Map with TOA layers | 01_map_default, step screenshot |
| `#map` | Click map area | Parcel detail panel | 02_map_interactions, parcel click |
| `#map` | Toggle signals | Signal markers | 02_map_interactions, toggle |
| `#intel` | Default load | Chat + Feed split | 03_intel_default |
| `#intel` | Click signal card | Signal expanded | 04_intel_interactions |
| `#intel` | Filter dropdown | Filtered signals | 04_intel_interactions |
| `#hoods` | Default load | Neighborhood list | 05_hoods_list |
| `#hoods` | Click neighborhood | Detail scorecard | 06_hoods_detail |
| `#hoods` | Select + Compare | Compare view | 07_hoods_compare |
| Global | Theme toggle | Light mode | 08_theme_light |
| Global | Disclaimer | Banner visible | 09_disclaimer |
