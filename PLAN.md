# VanCity Lens V2 — The Pivot
## "From Napkin Geometry to AI-Powered Real Estate Intelligence"

> **IMPORTANT: The existing map (V1) stays as the primary screen.**
> Intelligence features are added as a NEW tab/screen alongside the map.
> The two screens are linked: clicking a parcel shows nearby intelligence signals.

---

### Development Methodology

> **RULE: Tests and validation first, then code, then iterate.**
> Always start with creating testing and validation frameworks before writing implementation code.

### Session Recovery Notes (Feb 7, 2026)

If this Cowork session dies, here's where we are:

**STATUS: V2 Intelligence stack fully built. 242 tests all green. Map-Intelligence bridge complete.**

**V2 Migration (completed this session):**
- Switched from OpenAI embeddings → **Cohere embed-english-v3.0** (1024 dims)
- Added **BM25 sparse search** via PostgreSQL tsvector + GIN index
- **Hybrid search**: dense + sparse + Reciprocal Rank Fusion (k=60) + Cohere rerank
- Replaced custom chunker → **semchunk** (semantic chunking)
- Replaced direct pdfplumber → **docling** (primary) + pdfplumber fallback via parser.py
- Added **news feed scraper** (6 Vancouver RSS/news sources)
- Fixed embeddings.py variable shadowing bug (rerank_results → rerank_hits)

**Files modified this session:**
```
MODIFIED:
  chunker.py               → semchunk-based with fallback
  embeddings.py            → Cohere + hybrid search + RRF + rerank
  chat.py                  → Cohere key, hybrid_search, plainto_tsquery
  routes.py                → get_cohere_api_key, news scraper, 11 endpoints
  scraper_council.py       → uses parser.parse_pdf
  scraper_rezoning.py      → uses parser.parse_pdf
  scraper_dpb.py           → uses parser.parse_pdf
  007_intelligence_layer.sql → vector(1024), chunk_tsvector, GIN, trigger
  requirements.txt         → cohere, tiktoken, semchunk, docling, feedparser

NEW:
  parser.py                → Unified docling/pdfplumber parser
  scraper_news.py          → RSS news feed scraper
```

**To resume next session:**
1. `cd bill47 && pip install -r requirements.txt`
2. `pytest tests/ -v` — all 242 tests should pass (no external calls needed)
3. Set env vars: ANTHROPIC_API_KEY, COHERE_API_KEY
4. Run scrapers: `POST /api/v1/intel/admin/scrape?source=all`
5. Process docs: `POST /api/v1/intel/admin/process`
6. Test chat: `POST /api/v1/intel/chat` with sample queries
7. Next: Phase 4.1 (seed real data) → Phase 5 (neighborhood scorecards)

**k2-lite:** User uploaded k2-lite-main.zip. Only use if custom RAG pipeline proves insufficient.

---

### The Thesis

V1 calculates spatial buffers and zoning math. Any competent surveyor or GIS analyst can do this.
The real moat is **reading the 10,000+ pages of unstructured government text that nobody reads** —
city council minutes, rezoning staff reports, public hearing decisions, court rulings, development
permit board minutes — and turning them into **actionable, location-tagged intelligence** that
a realtor like Colin can use to find deals before anyone else.

**Colin doesn't need a prettier map. He needs an AI analyst who reads everything City Hall publishes
and whispers "buy this block before Tuesday's vote."**

---

### The New Value Proposition

| Old (V1) | New (V2) |
|-----------|----------|
| "This lot is zoned for 18 storeys" | "Council voted 7-4 to approve the rezoning at 4th & Vine on Tuesday — staff report recommends 22 storeys. Three adjacent lots are still RS-1. Assembly window: 6 months before market catches up." |
| Static spatial math | Live intelligence feed from government documents |
| Reactive (user clicks a dot) | Proactive (system alerts Colin to opportunities) |
| Competes with any GIS tool | Competes with nobody — no one else is doing this |

---

### UI Architecture

**Two-screen layout (tabs or sidebar navigation):**

| Screen | Purpose | Status |
|--------|---------|--------|
| **Map** (V1 — existing) | Parcel analysis, entitlements, validation, pro forma | ✅ Already built |
| **Intelligence** (V2 — new) | Chat interface + signal feed + document explorer | 🔄 Building now |

**Bridge between screens:**
- Clicking a parcel on the Map shows "X recent signals nearby" in the popup
- Clicking a signal in the Intelligence feed centers the map on that location
- Shared navigation bar at top

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     DOCUMENT SOURCES                      │
│  Council Minutes │ Rezoning Reports │ DPB Decisions       │
│  News Feeds (6)  │ Community Plans  │ Open Data APIs      │
└──────────────┬───────────────────────┬───────────────────┘
               │ Scrapers + RSS        │
               ▼                       ▼
┌──────────────────────────────────────────────────────────┐
│                   INGESTION PIPELINE                      │
│  1. Fetch (aiohttp + feedparser)                         │
│  2. Parse (docling primary → pdfplumber/BS4 fallback)    │
│  3. Chunk (semchunk semantic splitting, ~800 tokens)     │
│  4. Extract (Claude structured extraction → JSON)        │
│  5. Geocode (tag with addresses/parcels/neighborhoods)   │
│  6. Embed (Cohere embed-english-v3.0, 1024 dims)        │
│  7. Store (pgvector dense + tsvector BM25 sparse)        │
└──────────────┬───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│                    INTELLIGENCE LAYER                      │
│  • Hybrid Search (dense+BM25+RRF + Cohere rerank)        │
│  • Structured Insights DB (events, decisions, signals)    │
│  • Geospatial Index (PostGIS for location queries)        │
│  • Neighborhood Ratings (open data — Phase 5)             │
└──────────────┬───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│                      DELIVERY LAYER                       │
│  • Chat Interface (ask questions in plain English)        │
│  • Signal Feed (chronological intelligence stream)        │
│  • Map Layer (signals on existing Mapbox map)             │
│  • Neighborhood Scorecards (Madlan-style ratings)         │
│  • Proactive Alerts + Watchlist (push to user)            │
│  • Weekly Digest (email/PDF summary)                     │
└──────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Document Ingestion Pipeline ✅ COMPLETE
> Goal: Scrape real Vancouver government documents and store them.

- [x] **1.1 Set up document storage schema**
  - `db/007_intelligence_layer.sql` — pgvector extension, documents, document_chunks, intelligence_signals, chat_sessions, chat_messages tables
  - All indexes (GIST for geometry, IVFFlat for vectors, GIN for arrays/JSONB)

- [x] **1.2 Build council minutes scraper** → `api/intelligence/scraper_council.py`
  - VancouverCouncilScraper class with discover_meetings(), scrape_meeting_page(), download_and_parse_pdf()
  - Rate-limited async scraping with aiohttp
  - Targets: council.vancouver.ca/YYYYMMDD/ (regular, special, public hearing agendas)

- [x] **1.3 Build rezoning application scraper** → `api/intelligence/scraper_rezoning.py`
  - Scrapes rezoning.vancouver.ca/applications/
  - Extracts address, status, current/proposed zoning, linked PDFs

- [x] **1.4 Build Development Permit Board scraper** → `api/intelligence/scraper_dpb.py`
  - Scrapes vancouver.ca DPB past minutes page
  - Downloads and parses PDF minutes

- [x] **1.5 Text extraction & chunking pipeline** → `api/intelligence/chunker.py`
  - Hierarchical chunking: section headers → paragraphs → sentences
  - ~800-1200 tokens per chunk with configurable overlap
  - Section header detection for government document patterns

### Phase 2: AI Intelligence Extraction ✅ COMPLETE
> Goal: Use LLM to extract structured intelligence from raw text.

- [x] **2.1 Design the intelligence extraction prompt** → in `api/intelligence/extractor.py`
  - EXTRACTION_SYSTEM_PROMPT: instructs Claude to extract 21 structured fields
  - Signal types: rezoning_decision, permit_approval, policy_change, infrastructure, legal_precedent, community_opposition, density_change, land_sale

- [x] **2.2 Implement extraction pipeline** → `api/intelligence/extractor.py`
  - extract_signals_from_chunk() — Claude Sonnet 4.5 structured extraction
  - process_document() — full pipeline: chunks → extraction → geocoding → store
  - process_all_unprocessed() — batch processing with stats
  - geocode_address() — parcels table fuzzy match + BC Open Data geocoder fallback

- [x] **2.3 Build embedding pipeline** → `api/intelligence/embeddings.py`
  - **Cohere embed-english-v3.0** (1024 dims) — replaced OpenAI
  - Hybrid search: dense (pgvector) + sparse (tsvector BM25) + RRF fusion
  - Cohere rerank-v3.5 for top-k precision
  - Batch embedding with rate limiting
  - process_document_chunks() — full pipeline: chunk → embed → store

### Phase 3: Query Interface — "Ask Colin's Analyst" ✅ COMPLETE
> Goal: Colin can ask questions and get answers grounded in real government docs.

- [x] **3.1 Build the chat logic** → `api/intelligence/chat.py`
  - handle_chat() — full RAG pipeline: embed query → vector search → retrieve context → Claude synthesis → citations
  - CHAT_SYSTEM_PROMPT: grounded answers with source citations
  - get_relevant_signals() — keyword-based signal retrieval

- [x] **3.2 Build the intelligence feed logic** → `api/intelligence/signals.py`
  - get_signal_feed() — paginated, filtered signal feed
  - get_signals_for_parcel() — PostGIS spatial query (bridge between Map and Intelligence)
  - get_signal_stats() — dashboard metrics
  - get_neighborhoods() — for filter dropdowns

- [x] **3.3 Wire up FastAPI routes** → `api/intelligence/routes.py`
  - POST /api/v1/intel/chat — chat endpoint
  - GET /api/v1/intel/signals — signal feed
  - GET /api/v1/intel/signals/{id} — single signal
  - GET /api/v1/intel/signals/parcel/{pid} — signals near parcel
  - GET /api/v1/intel/stats — dashboard stats
  - GET /api/v1/intel/neighborhoods — neighborhood list
  - POST /api/v1/intel/admin/scrape — admin: trigger scraping
  - POST /api/v1/intel/admin/process — admin: trigger AI extraction
  - POST /api/v1/intel/admin/status — admin: ingestion status
  - Included in main.py via app.include_router(intelligence_router)

- [x] **3.4 Build Intelligence frontend page** → `frontend/src/components/IntelPage.tsx`
  - Two-column layout: Chat panel (left 60%) + Signal feed (right 40%)
  - Chat: text input, response with citations, suggested starter queries
  - Feed: filterable by neighborhood, signal type, date range
  - Each signal card: headline, summary, severity badge, decision badge, source link
  - Tab navigation: Map / Intelligence in page.tsx

- [x] **3.5 Build frontend API client** → `frontend/src/lib/intel-api.ts` + `intel-types.ts`
  - TypeScript functions for all intelligence endpoints
  - Type definitions matching backend models

- [x] **3.6 Update Map popup with signals bridge**
  - When parcel popup opens, also call GET /api/v1/intel/signals/parcel/{pid}
  - Show "X intelligence signals nearby" section in popup
  - Link to Intelligence tab filtered by that area
  - Parallel fetch (entitlement + signals) in handleMapClick

### Phase 3.5: Testing & Validation Framework ✅ COMPLETE
> Goal: Comprehensive test coverage before deployment.

- [x] **3.7 Build testing framework** → `tests/` directory
  - pytest.ini configuration with asyncio_mode=auto
  - conftest.py with 20+ reusable fixtures (mock DB, mock APIs, realistic Vancouver data)
  - test_models.py — 41 tests (Pydantic validation, enums, serialization)
  - test_chunker.py — 44 tests (splitting strategies, overlap, section detection)
  - test_extractor.py — 18 tests (Claude extraction, geocoding, error handling)
  - test_scrapers.py — 23 tests (HTTP mocking, parsing, deduplication)
  - test_chat.py — 18 tests (RAG pipeline, citations, sessions)
  - test_signals.py — 31 tests (CRUD, feeds, PostGIS spatial, GeoJSON)
  - test_routes.py — 38 tests (all 12 API endpoints + GeoJSON, error handling)
  - test_e2e_pipeline.py — 11 tests (full document→chat pipeline)
  - test_parser.py — 8 tests (docling + pdfplumber fallback)
  - test_scraper_news.py — 10 tests (RSS feeds, article fetching)
  - **Total: 242 test methods, all passing, all using mocks (no external API calls)**

### Phase 4.5: Local E2E Development & Validation ✅ COMPLETE
> Goal: Full-stack local dev flow with E2E testing before cloud deployment.

- [x] **4.5.1 Full-stack Docker Compose** → `docker-compose.yml`
  - `db` — PostgreSQL 16 + PostGIS + pgvector (existing, healthchecked)
  - `api` — FastAPI with hot reload (existing, enhanced)
  - `frontend` — Next.js dev server via `Dockerfile.dev` (NEW)
  - `e2e` — Playwright test runner via `Dockerfile.e2e` (NEW, profile-gated)
  - All services wired with proper depends_on + healthchecks
  - One command: `make dev` starts everything

- [x] **4.5.2 Makefile — Unified developer workflow** → `Makefile`
  - 30+ targets organized by category: dev, logs, testing, seeding, build, shell, lint, db
  - `make dev` — full stack with hot reload
  - `make test-unit` — 242 pytest tests
  - `make test-e2e` — Playwright against local stack
  - `make test-e2e-docker` — E2E in isolated container
  - `make seed` — seed intelligence data
  - `make shell-db` — psql into database
  - `make status` — health check all services

- [x] **4.5.3 Playwright E2E test framework** → `frontend/playwright.config.ts` + `frontend/e2e/`
  - 5 test suites, 21 test cases total:
    - `app.spec.ts` — App shell, branding, navigation, dark theme (5 tests)
    - `intelligence.spec.ts` — Intel tab, chat input, filters, severity colors (5 tests)
    - `map.spec.ts` — Map container rendering, viewport sizing (2 tests)
    - `api-health.spec.ts` — Backend health, CORS, signals, stats, GeoJSON (7 tests)
    - `e2e-full.spec.ts` — Full user journey: load → navigate → chat → map (2 tests)
  - Configured for: Desktop Chrome + Mobile Chrome (Pixel 5)
  - CI-optimized: retries, parallel workers, screenshots on failure, video on retry
  - Smart webServer: auto-starts dev server locally, uses external URL in Docker/CI

- [x] **4.5.4 E2E seed data** → `db/008_e2e_seed.sql` + `scripts/seed_e2e.sh`
  - 5 representative documents (council, rezoning, DPB, news)
  - 6 document chunks (pre-split for vector/BM25)
  - 5 geocoded intelligence signals across Vancouver neighborhoods
  - Idempotent (ON CONFLICT DO NOTHING), realistic metadata
  - Covers: Mount Pleasant, Grandview-Woodland, Renfrew-Collingwood

### Phase 4: POC Demo Polish
> Goal: Make it demo-ready for Colin.

- [ ] **4.1 Seed with real data**
  - Run scrapers against live Vancouver sources
  - Process ~100+ documents through extraction pipeline
  - Generate ~500+ intelligence signals
  - Verify geocoding accuracy

- [ ] **4.2 Create "wow moment" demo scenarios**
  - Pre-load queries that showcase the value:
    - "What rezoning applications were approved in the last 3 months?"
    - "Are there any properties near Broadway Plan stations facing community opposition?"
    - "What did council decide about [specific address]?"
    - "Show me all density increases approved in Mount Pleasant this year"
  - Ensure the system returns grounded, cited answers

- [ ] **4.3 Alert system (stretch)**
  - Cron job that runs scrapers daily
  - Diff new documents against existing
  - Generate alerts for new signals
  - `GET /api/v1/alerts` — "3 new signals since your last visit"

- [x] **4.4 Integration with existing V1 map** ✅ COMPLETE
  - GET /api/v1/intel/signals/geojson endpoint for map overlay
  - Signal markers with emoji icons + severity-colored borders on map
  - Toggle control ("🧠 Show/Hide Signals") in top-right
  - Parcel popup shows nearby intelligence signals section
  - Parallel fetch (entitlement + signals) in handleMapClick
  - Legend updated with intelligence signals entry
  - 6 new tests (4 unit + 2 route) — 242 total, all passing

### Phase 5: Neighborhood Scorecards + Proactive Alerts
> Goal: Madlan.co.il-style neighborhood quality ratings + push intelligence to Colin.

- [ ] **5.1 Build open data ingestion pipeline**
  - Scraper for VPD GeoDASH crime data (weekly CSV)
  - Scraper for CoV Open Data API (property tax, parks, permits, noise)
  - Scraper for VSB school data (enrolment, catchments)
  - Scraper for TransLink GTFS (transit stop density)
  - Store in new `neighborhood_metrics` table

- [ ] **5.2 Build neighborhood scoring engine**
  - Normalize each metric to 0-10 scale per neighborhood
  - Weighted composite score (configurable weights)
  - Historical tracking (score changes over time)
  - API endpoints: GET /api/v1/neighborhoods/{name}/scorecard

- [ ] **5.3 Build scorecard frontend component**
  - Neighborhood picker (22 Vancouver local areas)
  - Visual scorecard with bar charts per metric
  - Price trend sparkline
  - Active rezonings + permits count
  - Recent news articles count
  - Comparison mode (side-by-side 2-3 neighborhoods)

- [ ] **5.4 Build proactive alerts system**
  - Watchlist: Colin marks neighborhoods/addresses to monitor
  - Diff engine: compare new scrape results against previous
  - Alert generation: new signals → alert if matches watchlist
  - Delivery: in-app notification feed + optional email digest
  - API endpoints: GET/POST /api/v1/alerts, POST /api/v1/watchlist

- [ ] **5.5 Weekly digest generator**
  - Cron job: aggregate week's signals by neighborhood
  - Generate HTML email or PDF report
  - "Top 10 signals this week" + neighborhood summaries
  - Delivery via email (SendGrid/SES) or downloadable PDF

---

## Data Sources & Access

### Tier 1 — Government Document Scrapers (✅ Built)

| Source | Scraper | Format | Est. Volume | Status |
|--------|---------|--------|-------------|--------|
| Council Minutes | `scraper_council.py` | HTML + PDF | 600/year | ✅ Built |
| Rezoning Staff Reports | `scraper_council.py` | PDF | 30-50 active | ✅ Built |
| Rezoning Applications | `scraper_rezoning.py` | HTML + PDF | 50+ | ✅ Built |
| DPB Minutes | `scraper_dpb.py` | PDF | 12-15/year | ✅ Built |

### Tier 2 — News Feed Monitoring (✅ Built)

| Source | RSS Feed | Priority | Status |
|--------|----------|----------|--------|
| City of Vancouver News | HTML scrape | High | ✅ Configured |
| Vancouver Sun Real Estate | RSS | Medium | ✅ Configured |
| Business in Vancouver | RSS | Medium | ✅ Configured |
| Daily Hive Vancouver | RSS | Low | ✅ Configured |
| BC Housing News | HTML scrape | High | ✅ Configured |
| Metro Vancouver Regional Planning | HTML scrape | Medium | ✅ Configured |

Relevance filtering: articles must match 2+ keywords from a curated list
(rezoning, density, housing, broadway plan, transit-oriented, etc.)

### Tier 3 — Open Data for Neighborhood Ratings (🔄 Phase 5)

Inspired by Madlan.co.il's neighborhood quality-of-life ratings.
All sources are free Vancouver/BC open data with APIs or CSV downloads.

| Category | Source | URL / API | Format | Granularity |
|----------|--------|-----------|--------|-------------|
| **Crime** | VPD GeoDASH | `geodash.vpd.ca/opendata/` | CSV, weekly | Neighborhood |
| **Schools** | VSB Open Data | `vsb.bc.ca/page/4965/open-data` | CSV | School catchment |
| **Schools (location)** | CoV Open Data | `opendata.vancouver.ca/explore/dataset/schools/` | JSON/CSV/SHP | Point |
| **School catchments** | CoV Open Data | `opendata.vancouver.ca/explore/dataset/elementary-school-catchment-areas/` | GeoJSON | Polygon |
| **Air quality** | Metro Vancouver AirMap | `gis.metrovancouver.org/maps/Air` | Hourly API | Station-level |
| **Air quality (archive)** | BC Gov | `ftp://ftp.env.gov.bc.ca/pub/outgoing/AIR/` | CSV | Station-level |
| **Demographics** | Statistics Canada Census | `censusmapper.ca/api` (free API key) | JSON | Census tract |
| **Demographics (local)** | CoV Census Profiles | `opendata.vancouver.ca/.../census-local-area-profiles-2016/` | CSV/JSON | 22 Local Areas |
| **Transit** | TransLink GTFS | `translink.ca/.../gtfs-data` | GTFS (CSV) | Stop/Route |
| **Walkability** | UBC/Metro Walkability Index | `atl.sites.olt.ubc.ca/research/walkability-index/` | Spatial DB | Parcel-level |
| **Property values** | CoV Property Tax Report | `opendata.vancouver.ca/.../property-tax-report/` | CSV/JSON | Address |
| **Parks** | CoV Parks Facilities | `opendata.vancouver.ca/.../parks-facilities/` | GeoJSON | Point/Polygon |
| **Noise** | CoV Noise Control Areas | `opendata.vancouver.ca/.../noise-control-areas/` | GeoJSON | Polygon |
| **Building permits** | CoV Issued Permits | `opendata.vancouver.ca/.../issued-building-permits/` | CSV/JSON | Address |

### Tier 4 — Future Document Sources (Phase 6+)

| Source | URL Pattern | Format | Priority |
|--------|-----------|--------|----------|
| Shape Your City | `shapeyourcity.ca/rezoning` | HTML | P1 |
| CanLII (Court) | `canlii.org/en/bc/` | PDF | P2 |
| Community Plans | `vancouver.ca/.../broadway-plan.aspx` | PDF | P1 |

---

## Interface Design — Beyond Chat

### The Problem

A realtor like Colin doesn't know what questions to ask. Chat is powerful but
requires the user to already know what they're looking for. The system needs
to **push intelligence to the user**, not just wait for questions.

### The Solution: Four Interface Modes

```
┌─────────────────────────────────────────────────────────────────┐
│  TAB BAR:  [Map]  [Intelligence]  [Neighborhoods]  [Alerts]    │
└─────────────────────────────────────────────────────────────────┘
```

#### Mode 1: Map (V1 — existing ✅)
Parcel analysis, entitlements, validation, pro forma.
Now enriched with intelligence signals overlay.

#### Mode 2: Intelligence Dashboard (V2 — 🔄 building)
Two-panel layout:

**Left panel — Chat ("Ask the Analyst")**
- Natural language questions about Vancouver development
- RAG-powered answers with citations
- Suggested starter questions for realtors who don't know what to ask:
  - "What rezoning decisions happened this week?"
  - "Show me neighborhoods with the most density increases"
  - "What's the sentiment around [project name]?"
  - "Where are the next public hearings?"

**Right panel — Live Signal Feed**
- Chronological feed of intelligence signals (like a Twitter/X feed for zoning)
- Filterable by neighborhood, signal type, severity, date
- Each card: headline, 2-line summary, severity badge, source link
- Click-to-map: clicking a signal centers the map on that location

#### Mode 3: Neighborhood Scorecards (Phase 5 — 📋 planned)
Inspired by Madlan.co.il. For each of Vancouver's 22 neighborhoods:

**Scorecard layout:**
```
┌──────────────────────────────────────────────────┐
│  MOUNT PLEASANT                           8.2/10 │
│  ─────────────────────────────────────────────── │
│                                                  │
│  🏫 Schools         ████████░░  8.1              │
│  🚔 Safety          ██████░░░░  6.2              │
│  🌿 Air Quality     █████████░  9.0              │
│  🚇 Transit Access  ████████░░  8.5              │
│  🏘️ Affordability   ████░░░░░░  4.1              │
│  🌳 Parks/Green     ███████░░░  7.3              │
│  📈 Development     █████████░  9.2              │
│  🔊 Noise Level     ██████░░░░  6.0              │
│                                                  │
│  📊 Price Trend: +12% YoY  │  Avg: $1,050/sqft  │
│  📋 Active Rezonings: 7    │  Permits: 23        │
│  🗞️ Recent News: 5 articles this month           │
│                                                  │
│  [View on Map]  [Read Signals]  [Compare]        │
└──────────────────────────────────────────────────┘
```

Data sources for each metric:
- Schools: VSB enrolment/capacity + BC Education performance
- Safety: VPD GeoDASH crime stats (normalized per 1000 residents)
- Air Quality: Metro Vancouver AirMap readings
- Transit: TransLink GTFS stop density + walk-to-transit time
- Affordability: CoV Property Tax Report (price/sqft trends)
- Parks: CoV Parks dataset (green space per capita)
- Development: Intelligence signals + building permits data
- Noise: CoV Noise Control Areas + port noise monitoring

**Comparison mode:** side-by-side 2-3 neighborhoods

#### Mode 4: Proactive Alerts (Phase 5 — 📋 planned)
Colin doesn't ask — the system tells him.

- **Weekly digest email/PDF**: "Here's what happened in Vancouver development this week"
- **Push alerts**: "Council just approved 22-storey rezoning at 4th & Vine"
- **Watchlist**: Colin marks neighborhoods or addresses to watch
- **Opportunity alerts**: "3 adjacent RS-1 lots near newly approved rezoning — possible assembly"

### Interface Priority

| Interface | Phase | Effort | Value |
|-----------|-------|--------|-------|
| Chat + Signal Feed | ✅ Phase 3 (built) | Done | Core |
| Map signals overlay | ✅ Phase 4 (built) | Done | High |
| Neighborhood Scorecards | Phase 5 | High | Very High (Madlan differentiator) |
| Proactive Alerts + Watchlist | Phase 5 | Medium | Very High (retention) |
| Weekly Digest | Phase 6 | Low | Medium |
| Comparison Mode | Phase 6 | Low | Medium |

---

## Tech Decisions for POC (Updated Feb 7, 2026)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| RAG framework | Custom pipeline (k2-lite available as fallback) | POC simple enough; avoid abstraction tax |
| Vector store | pgvector (PostgreSQL extension) | Already have PostGIS; no new infrastructure |
| LLM for extraction | Claude API (claude-sonnet-4-5) | Best structured extraction; we're already in the ecosystem |
| LLM for chat | Claude API (claude-sonnet-4-5) | Consistent; good at grounded answers with citations |
| Embeddings | **Cohere embed-english-v3.0** (1024 dims) | Better multilingual, native search_query/search_document types |
| Search | **Hybrid: Cohere dense + PostgreSQL BM25 (tsvector) + RRF** | Best retrieval quality; sparse catches exact terms, dense catches semantics |
| Reranking | **Cohere rerank-v3.5** | Dramatically improves top-k precision after hybrid merge |
| Chunking | **semchunk** (semantic chunking) | Preserves semantic coherence vs naive splitting |
| PDF parsing | **docling** (primary) + pdfplumber (fallback) | Superior table extraction from government PDFs |
| HTML parsing | **docling** (primary) + BeautifulSoup (fallback) | Clean text from news articles and web pages |
| News feeds | **feedparser** + aiohttp | RSS/Atom parsing for news monitoring |
| Web scraping | aiohttp + BeautifulSoup | Async, rate-limited, sufficient for government sites |
| Frontend | React components in existing Next.js app | No new framework; add tabs alongside Map |

---

## Complete File Structure

```
api/
  intelligence/
    __init__.py              ✅  Module init
    models.py                ✅  Pydantic models for intelligence layer
    parser.py                ✅  Unified doc parser (docling + pdfplumber fallback)
    scraper_council.py       ✅  Council minutes & agenda scraper
    scraper_rezoning.py      ✅  Rezoning application scraper
    scraper_dpb.py           ✅  Development Permit Board scraper
    scraper_news.py          ✅  RSS news feed scraper (6 Vancouver sources)
    chunker.py               ✅  Semantic chunking (semchunk + fallback)
    embeddings.py            ✅  Cohere embeddings + hybrid search (dense+BM25+RRF)
    extractor.py             ✅  Claude-powered signal extraction
    chat.py                  ✅  RAG chat with hybrid search
    signals.py               ✅  Intelligence signals CRUD
    routes.py                ✅  FastAPI route definitions (12 endpoints, incl GeoJSON)
  main.py                    ✅  Updated — includes intelligence_router
db/
  007_intelligence_layer.sql ✅  pgvector(1024) + tsvector + GIN + trigger
frontend/
  src/
    app/
      page.tsx               ✅  Updated — tab navigation (Map / Intelligence)
    components/
      MapView.tsx            ✅  V1 map + signal markers overlay + popup bridge
      IntelPage.tsx          ✅  Intelligence tab: chat + feed
    lib/
      api.ts                 ✅  Existing V1 API client
      intel-api.ts           ✅  V2 intelligence API client
      intel-types.ts         ✅  V2 TypeScript types
      types.ts               ✅  Existing V1 types
tests/                                  # Unit tests (pytest, 242 total)
  __init__.py                ✅
  conftest.py                ✅  20+ fixtures, realistic Vancouver data
  test_models.py             ✅  41 tests
  test_chunker.py            ✅  44 tests
  test_extractor.py          ✅  18 tests
  test_scrapers.py           ✅  23 tests
  test_chat.py               ✅  18 tests
  test_signals.py            ✅  27 tests
  test_routes.py             ✅  36 tests
  test_e2e_pipeline.py       ✅  11 tests
  test_scraper_news.py       ✅  10 tests
  test_parser.py             ✅  8 tests
pytest.ini                   ✅  Config
frontend/e2e/                           # E2E tests (Playwright, 21 total)
  app.spec.ts                ✅  5 tests (shell, nav, theme)
  intelligence.spec.ts       ✅  5 tests (intel tab, chat, filters)
  map.spec.ts                ✅  2 tests (map render, viewport)
  api-health.spec.ts         ✅  7 tests (health, CORS, signals, GeoJSON)
  e2e-full.spec.ts           ✅  2 tests (full user journey)
frontend/playwright.config.ts ✅  Chrome + Pixel 5
```

---

## Success Criteria (POC Demo)

1. **Colin asks:** "What's happening with development in Mount Pleasant?"
   → System returns 5+ grounded answers citing real council minutes and rezoning reports

2. **Colin asks:** "Are there any rezoning approvals near Commercial-Broadway station?"
   → System returns specific addresses, vote counts, and FSR/height changes with source links

3. **Colin clicks a parcel on the map**
   → Popup shows V1 validation data PLUS "3 recent council signals" with summaries

4. **Signal feed shows** 20+ recent intelligence items sorted by neighborhood and date,
   each linking to the original government document

5. **Neighborhood scorecard** shows quality-of-life ratings for at least 5 neighborhoods
   using real VPD crime data, VSB school data, and CoV open data

---

## Dependencies

```bash
# Backend (requirements.txt — updated)
fastapi==0.115.6
uvicorn[standard]==0.34.0
asyncpg==0.30.0
pydantic==2.10.4
anthropic>=0.40.0
pdfplumber>=0.11.0
aiohttp>=3.10.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
cohere>=5.0.0
tiktoken>=0.7.0
semchunk>=2.0.0
docling>=2.0.0
feedparser>=6.0.0

# Frontend (already have Next.js + Mapbox)
# No new dependencies needed — using existing React
```

**Environment variables required:**
```
ANTHROPIC_API_KEY=...
COHERE_API_KEY=your-cohere-api-key
DATABASE_URL=postgresql://...
```

---

## Deployment

### Local Development (Docker Compose + Makefile)

**Quick start (full stack with hot reload):**
```bash
cp .env.example .env          # edit with real API keys
make dev                       # starts db + api + frontend
# → API:      http://localhost:8000
# → Frontend: http://localhost:3000
```

**Developer workflow:**
```bash
make help                      # show all 30+ commands
make dev                       # full stack, hot reload, foreground logs
make up                        # same but background
make status                    # health check all services
make seed                      # seed intelligence data from scrapers
make test-unit                 # 242 pytest unit tests
make test-e2e                  # Playwright E2E against local stack
make test-e2e-docker           # E2E in isolated Docker container
make shell-db                  # psql into database
make shell-api                 # bash into API container
make db-reset                  # destroy + recreate database
make clean                     # tear down everything + volumes
```

**E2E testing:**
```bash
# Option 1: Run locally (needs Playwright installed)
cd frontend && npx playwright install chromium
make test-e2e

# Option 2: Run in Docker (no local install needed)
make test-e2e-docker

# Option 3: Interactive UI mode
make test-e2e-ui
```

**Seed E2E test data:**
```bash
make up                        # start stack
bash scripts/seed_e2e.sh       # load 5 docs, 6 chunks, 5 signals
```

### Production (Google Cloud + Cloudflare)

**Backend** (GCP Cloud Run + Cloud SQL):
```bash
export GCP_PROJECT_ID=your-project
export ANTHROPIC_API_KEY=sk-ant-...
export COHERE_API_KEY=...
bash scripts/deploy_gcp.sh
```

**Frontend** (Cloudflare Pages):
```bash
export NEXT_PUBLIC_API_URL=https://your-api.run.app
export NEXT_PUBLIC_MAPBOX_TOKEN=pk....
bash scripts/deploy_frontend.sh
```

**Seed real data:**
```bash
python scripts/seed_data.py                    # scrape all + process
python scripts/seed_data.py --status           # check database counts
python scripts/seed_data.py --scrape-only      # just scrape
python scripts/seed_data.py --process-only     # just process existing
```

### Infrastructure

| Component | Service | Details |
|-----------|---------|---------|
| Database | Cloud SQL PostgreSQL 16 | pgvector + PostGIS extensions |
| Backend API | Cloud Run | FastAPI, autoscaling 0-5 instances |
| Frontend | Cloudflare Pages | Next.js 15, edge-deployed |
| Secrets | GCP Secret Manager | API keys, DB password |
| Container Registry | Artifact Registry | Docker images |

### Files
```
# Local Development
Makefile                 # 30+ dev workflow commands
docker-compose.yml       # Full stack: db + api + frontend + e2e
Dockerfile               # FastAPI backend image
Dockerfile.db            # PostgreSQL + PostGIS + pgvector image
frontend/Dockerfile.dev  # Next.js dev server image
frontend/Dockerfile.e2e  # Playwright test runner image
.env.example             # Environment variables template
.dockerignore            # Build exclusions

# E2E Testing
frontend/playwright.config.ts  # Playwright config (Chrome + mobile)
frontend/e2e/
  app.spec.ts                  # App shell, nav, theme tests (5)
  intelligence.spec.ts         # Intel tab, chat, filters (5)
  map.spec.ts                  # Map rendering tests (2)
  api-health.spec.ts           # Backend API health tests (7)
  e2e-full.spec.ts             # Full user journey tests (2)
db/008_e2e_seed.sql            # E2E test seed data (5 docs, 5 signals)
scripts/seed_e2e.sh            # Seed runner script

# Deployment Scripts
scripts/
  deploy_gcp.sh          # Full GCP provisioning (Cloud SQL + Cloud Run)
  deploy_frontend.sh     # Cloudflare Pages deployment
  seed_data.py           # Data ingestion pipeline CLI
  seed_e2e.sh            # E2E test data seeder
frontend/
  wrangler.toml          # Cloudflare Pages config
  next.config.ts         # Next.js output: standalone

# Infrastructure (deferred — local validation first)
terraform/               # GKE Autopilot + Cloud SQL + VPC (ready, not deployed)
k8s/                     # Kubernetes manifests (ready, not deployed)
.github/workflows/       # CI/CD pipelines (ready, not deployed)
```

---

*Last updated: Feb 7, 2026 — V2 Intelligence stack complete. Local E2E dev flow built.*
*Tests: 242 unit tests (mocked) + 21 Playwright E2E tests. All green.*
*Local dev: `make dev` → full stack (db + api + frontend) with hot reload.*
*E2E: Playwright → Chrome + Mobile Chrome, with API health checks + UI flow tests.*
*Infrastructure: Terraform/K8s ready but deferred — local validation first.*
*Data sourcing: 4 government scrapers + 6 news feeds + 14 open data sources planned*
*Next: run E2E locally → seed real data → demo → then deploy to GCP.*
*Priority: validate locally → ship to prod. No cloud until it works on Docker.*
