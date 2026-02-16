# VanCityLense PRD Gap-Closure Design

**Date:** 2026-02-15
**Goal:** Close the delta between existing codebase and the 6-feature PRD, prioritizing free data sources, using Approach A (gap-close per feature in PRD phase order).

**Architecture:** Extend existing FastAPI + Next.js + PostgreSQL/PostGIS/pgvector stack. LLM extraction via existing Gemini/Anthropic backend. Ingestion via RSS + open data (primary) and Playwright headless browser (secondary for council pages). In-app notifications only (email deferred).

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Paid data sources | Deferred (LTSA, BC Corporate Registry, bulk BCA API) | User constraint: prioritize free flows |
| Scraping approach | RSS + open data primary, Playwright secondary | Reliable + maintainable; Playwright for Cloudflare-protected council pages |
| Pro forma market data | StatsCan BPPI + seeded defaults in DB table | Free, trackable, admin-editable |
| Email delivery | Deferred -- in-app only | Simplifies notification stack |
| NLP approach | LLM extraction via existing generate_chat() | Already integrated, handles nuance, approx $0.01-0.05/doc |
| Implementation approach | Gap-close per feature in PRD phase order | Delivers complete features with acceptance criteria |

---

## Phase 1: F01 HBU Engine -- Gap Closure

### F01-A: Heritage Integration

**What exists:** `heritage_sites` table with `category` (A/B/C) and `geom` (Point, 4326). Entitlement engine does NOT query it.

**Change:** Add spatial lookup in `compute_entitlement()`:
- `ST_DWithin(heritage_sites.geom, parcel_centroid, 50)` (50m buffer for address imprecision)
- Add `heritage_designation` (A/B/C/null) to `ParcelEntitlementResponse`
- If heritage found: add to `constraints_applied` with message per PRD AC-F01-004
- Heritage Category A: "Heritage Category A -- demolition unlikely to be approved"
- Heritage Category B/C: "Heritage Category [B/C] -- additional review required"

**Files:** `api/entitlement.py`, `api/models.py`

### F01-B: Market Data Pro Forma

**What exists:** Hardcoded `REVENUE_PSF_BY_NEIGHBORHOOD` dict in `api/neighborhood_revenue.py`. Static $800/sqft in entitlement calculations.

**Change:** New DB table `market_benchmarks`:
- `id SERIAL PK`
- `neighbourhood TEXT NOT NULL`
- `product_type TEXT NOT NULL` (condo, rental, commercial, townhouse)
- `revenue_per_sf NUMERIC(10,2)`
- `hard_cost_per_sf NUMERIC(10,2)`
- `source TEXT` (StatsCan BPPI, CMHC, REBGV, admin)
- `effective_date DATE`
- `created_at TIMESTAMPTZ DEFAULT NOW()`
- `UNIQUE(neighbourhood, product_type)`

Seed from existing hardcoded values. Entitlement engine queries this table. Add `market_data_timestamp` to HBU output per PRD AC-F01-009.

**HBU output additions:**
- `revenue_per_buildable_sf` -- from market_benchmarks for neighbourhood + product_type
- `hard_cost_per_sf` -- from market_benchmarks
- `estimated_gross_revenue` = gross_buildable_sf x revenue_per_buildable_sf
- `estimated_total_dev_cost` = gross_buildable_sf x hard_cost_per_sf
- `assessed_value_per_buildable_sf` = current_assessed_land_value / gross_buildable_sf

**Files:** New `db/045_market_benchmarks.sql`, `data/seed/market_benchmarks.json`, modify `api/entitlement.py`, `api/intelligence/hbu_engine.py`

### F01-C: Input Disambiguation

**What exists:** Parcel search exists but returns first match.

**Change:** Add `GET /api/v1/parcels/search?q=...` endpoint:
- If query matches exactly 1 parcel: return it
- If query matches 2-10 parcels: return disambiguation list with PID, address, zoning, lot area
- If query matches 0 parcels: return error per PRD AC-F01-007
- If query matches >10: return first 10 + "Showing 10 of N results, refine your search"

Frontend: show dropdown if disambiguation list returned.

**Files:** Modify `api/parcels_routes.py`, modify `ParcelDetailPanel.tsx` or search component

### F01-D: Staleness Warnings

**What exists:** `assessed_year` on parcels table. `data_warnings` list in entitlement response.

**Change:** Add checks in `compute_entitlement()`:
- If `assessed_year < current_year - 1`: add DataQualityWarning per DV-F01-006
- Add similar check for market_benchmarks effective_date (>12 months old) per DV-F01-007
- Frontend: render warnings as amber banners in ParcelDetailPanel

**Files:** Modify `api/entitlement.py`

---

## Phase 1: F04 Development Pipeline -- Gap Closure

### F04-A: Schema Enhancement

**What exists:** `supply_pipeline` table with `developer`, `pipeline_stage`, `pipeline_stage_history`.

**Change:** New migration:
- Add `application_id TEXT` (City of Vancouver application number)
- Add `application_type TEXT` (rezoning / development_permit / building_permit)
- Add `developer_entity_id INT REFERENCES developer_entities(id)`
- Add missing pipeline stages: "enquiry", "withdrawn"
- Map existing stages to PRD 9-stage enum

**Files:** New `db/046_pipeline_schema_v2.sql`, modify `api/intelligence/supply_pipeline.py`

### F04-B: Entity Resolution Pipeline

**What exists:** `developer_entities` table with `canonical_name`, `aliases TEXT[]`. No fuzzy matching logic.

**Change:** Add entity resolution function:
- On each ingestion cycle, for each pipeline record with unlinked `developer`:
  1. Normalize: lowercase, strip Corp/Ltd/Inc/Projects, trim
  2. Check exact match against `developer_entities.aliases`
  3. If no exact match: `pg_trgm` similarity against `canonical_name` (threshold 0.6)
  4. If match found: set `developer_entity_id`
  5. If no match: create new entity, set `requires_review = true`
- Enable `pg_trgm` extension if not already

**Files:** Modify `api/intelligence/supply_pipeline.py`, new `db/047_enable_pg_trgm.sql`

### F04-C: Clustering UI

**What exists:** `clustering.py` with spatial/temporal detection (3+ apps within 500m/90 days). Backend only.

**Change:**
- New endpoint: `GET /api/v1/intel/clusters` returns active clusters with centroid, count, member applications
- Frontend: render pulsing circles on map at cluster centroids
- Click opens panel listing clustered applications with distances
- Validate: geodesic distance per DI-002

**Files:** New route in `api/intelligence/`, modify `MapView.tsx`

### F04-D: Saved Filter Alerts

**What exists:** Watchlist/alert system with rule-based matching.

**Change:** Extend watchlist rule types:
- Add: `pipeline_stage`, `application_type`, `height_range`, `unit_range` as rule criteria
- On daily pipeline ingestion: evaluate new/updated records against all active watchlists
- Generate in-app alert per matching user
- Frontend: add "Pipeline Alert" configuration in watchlist management UI

**Files:** Modify `api/intelligence/alerts.py`, modify watchlist frontend

---

## Phase 2: F02 Regulatory Change Intelligence

### F02-A: Change Records Table

New table `change_records`:
- `change_id UUID PK DEFAULT gen_random_uuid()`
- `signal_id INT FK -> intelligence_signals`
- `change_type TEXT NOT NULL` (new_legislation, bylaw_amendment, policy_update, council_vote, staff_directive)
- `source_url TEXT NOT NULL`
- `source_document_title TEXT NOT NULL`
- `publication_date TIMESTAMPTZ`
- `effective_date TIMESTAMPTZ` (nullable)
- `geographic_scope TEXT NOT NULL` (citywide, neighbourhood, zoning_district, parcel_specific)
- `affected_areas TEXT[]`
- `entitlement_change JSONB` ({field, before_value, after_value})
- `plain_english_summary TEXT` (max 200 words)
- `nlp_confidence_score NUMERIC(3,2)`
- `extraction_timestamp TIMESTAMPTZ DEFAULT NOW()`
- `requires_manual_review BOOLEAN DEFAULT false`
- `created_at TIMESTAMPTZ DEFAULT NOW()`

Indexes: `change_type`, `publication_date`, `geographic_scope`, GIN on `affected_areas`, full-text on `plain_english_summary || source_document_title`.

**Files:** New `db/048_change_records.sql`

### F02-B: LLM Change Extraction Pipeline

After document ingestion + chunking:
1. Existing regex detects candidate chunks (bylaw amendments, FSR/height references)
2. Send candidates to LLM with structured extraction prompt requesting: change_type, geographic_scope, affected_areas, entitlement_change, plain_english_summary
3. Parse JSON response, validate fields
4. If `nlp_confidence_score < 0.85`: set `requires_manual_review = true`
5. Duplicate detection: check if same `source_url` + `entitlement_change` already exists -> merge, retain all source_urls
6. Insert into `change_records`

**Files:** New `api/intelligence/change_extraction.py`, new prompt in `api/intelligence/change_prompts.py`

### F02-C: Watchlist Matching Engine

On new `change_record` creation:
1. Query all active watchlists
2. For each, check intersection:
   - `parcel_specific` scope: affected_areas contains watchlisted PID
   - `neighbourhood` scope: affected_areas contains watchlisted neighbourhood
   - `zoning_district` scope: affected_areas contains watchlisted zoning
   - `citywide` scope: notify all users
3. Generate alert with `plain_english_summary` + affected PIDs from user's watchlist

**Files:** Modify `api/intelligence/alerts.py`

### F02-D: Regulatory Archive Search API

New endpoint: `GET /api/v1/intel/changes`
- Query params: `start_date`, `end_date`, `change_type` (csv), `geographic_scope`, `affected_areas` (text), `q` (full-text), `page`, `per_page`
- Returns paginated results sorted by `publication_date DESC`
- Retention: 24 months minimum

**Files:** New `api/intelligence/change_routes.py`, mount in `api/intelligence/routes.py`

### F02-E: Playwright Council Scraper

New scraper module using Playwright:
- Target: vancouver.ca/your-government/council-meetings.aspx
- Schedule: `"0 5 * * 1"` (weekly Monday 5 AM UTC)
- Flow: launch headless Chromium -> navigate -> extract agenda items + staff reports -> download PDFs -> feed into document ingestion pipeline
- Fallback: if Cloudflare blocks after 3 retries, log WARN and skip
- Dependency: `playwright` in requirements.txt, `playwright install chromium` in Docker

**Files:** New `api/intelligence/scraper_council_playwright.py`, modify `api/intelligence/scheduler.py`

---

## Phase 2: F03 Due Diligence Assembly -- Gap Closure

### F03-A: Red Flag Auto-Aggregation

New method `_collect_red_flags()` in report generator:
- Heritage designation not null -> High severity
- Contamination status not "Not Listed" -> High
- Non-conforming use (current use vs zoning permitted uses) -> Medium
- Active applications within 100m -> Medium
- Assessed value >2 std dev from neighbourhood median -> Medium
- Data staleness (any source older than cadence) -> Low
- Returns list of `{flag_name, severity, detail}`

LTSA-dependent flags (litigation, covenants) deferred.

**Files:** Modify `api/report_generator.py`

### F03-B: Executive Summary Enhancement

Modify `_build_executive_summary()`:
- Include: one-sentence site description (address + zoning + lot area)
- Include: key entitlement (max height + FSR)
- Include: assessed land value
- Include: red flag count from F03-A
- LLM-generated narrative capped at 300 words
- Use existing `generate_chat()` with summary-specific prompt

**Files:** Modify `api/report_generator.py`

### F03-C: Section Reordering

Reorder PDF sections to match PRD spec:
1. Executive Summary
2. Title and Ownership (placeholder: "LTSA data requires per-query license -- manual title search recommended")
3. Zoning and Entitlements
4. Environmental
5. Heritage (standalone section, currently inline)
6. Development Activity -- Subject Site
7. Development Activity -- Surrounding Area (500m radius)
8. Market Context
9. Demographic Profile
10. Red Flags Summary (new)
11. Data Currency

**Files:** Modify `api/report_generator.py`

### F03-D: Unavailability Handling

When any data source times out or errors during report generation:
- Display "Data unavailable -- [source name] timeout at [timestamp]" in that section
- Never silently omit a section
- Ensure consistent error handling across all 11 sections

**Files:** Modify `api/report_generator.py`

---

## Phase 3: F05 Political Risk -- Gap Closure

### F05-A: News RSS Ingestion

Re-enable `scraper_news.py` with 7 RSS sources:
- Vancouver Sun, The Province, Daily Hive Vancouver, The Tyee, Storeys, Business in Vancouver, Western Investor
- Schedule: every 6 hours (`"0 */6 * * *"`)
- Each article -> document ingestion -> LLM extracts signal with sentiment + neighbourhood + opposition themes
- Exclude signals with `sentiment_confidence < 0.60` from risk scoring (DV-F05-001)

**Files:** Modify `api/intelligence/scraper_news.py`, `pipeline/sources.yaml`

### F05-B: Monthly Risk Score Refresh

Scheduled job: `"0 2 1 * *"` (1st of month, 2 AM UTC)
- For each of 22 neighbourhoods: recompute 4 component scores from trailing 36 months of signals
- Upsert into `political_risk_scores`
- Minimum thresholds: <5 rezonings -> "Insufficient application history", <10 signals -> "Insufficient data for theme analysis"

**Files:** Modify `api/intelligence/political_risk.py`, `api/intelligence/scheduler.py`

### F05-C: Risk Dashboard Frontend

New frontend section:
- Map choropleth: colour neighbourhoods by risk score (green 1-3, yellow 4-6, red 7-10)
- Click neighbourhood -> panel: score, 4 components, top 3 themes, narrative, recent signals
- Parcel detail panel: risk score badge from materialized scores

**Files:** New component in `frontend/src/components/`, modify `MapView.tsx`

---

## Phase 3: F06 Undervalued Parcel Alerts -- Gap Closure

### F06-A: Weekly Scoring Cron Job

Scheduled job: `"0 15 * * 1"` (Monday 15:00 UTC = 8:00 AM Pacific)
- For all TOA parcels: calculate discount_pct via existing scoring logic
- Validation: `comparable_transaction_count >= 3` required (DV-F06-001)
- BC Assessment data must be current/prior roll year (DV-F06-002)
- Mark `is_repeat_signal = true` for parcels in prior week's results
- Upsert into `undervalued_scores`

**Files:** Modify `api/intelligence/undervalued_scoring.py`, `api/intelligence/scheduler.py`

### F06-B: User-Configurable Alert Filters

Extend watchlist system:
- New rule type: `undervalued_alert`
- Configurable: neighbourhoods, min_lot_area_sf, min_discount_pct, tod_tiers
- After weekly scoring: evaluate flagged parcels against user watchlist rules
- Generate in-app alert for matches
- Frontend: "Undervalued Alerts" config in watchlist management

**Files:** Modify `api/intelligence/alerts.py`, modify watchlist frontend

---

## Cross-Cutting Infrastructure

### DI-005: Retrieval Audit Log

New table `retrieval_log`:
- `id SERIAL PK`
- `source_id TEXT NOT NULL` (DS-001 through DS-015)
- `query_params JSONB`
- `retrieval_timestamp TIMESTAMPTZ DEFAULT NOW()`
- `http_status INT`
- `record_count INT`
- `duration_ms INT`
- 12-month retention (cleanup cron: `"0 0 1 * *"`)

Utility: `log_retrieval()` wrapper for all external data fetches.

**Files:** New `db/049_retrieval_log.sql`, new `api/retrieval_logging.py`

### DI-006: Data Freshness Monitoring

New table `data_source_freshness`:
- `source_id TEXT PK`
- `source_name TEXT`
- `expected_cadence_hours INT`
- `last_successful_retrieval TIMESTAMPTZ`

Updated by `log_retrieval()`. Cron check: if stale by >50%, log WARN.
Endpoint: `GET /api/v1/admin/data-freshness`

**Files:** New `db/050_data_freshness.sql`, modify `api/retrieval_logging.py`

### Playwright Dependency

Add `playwright` to `requirements.txt`. Docker: `RUN playwright install chromium --with-deps`.

---

## Work Summary

| Phase | Feature | Work Items | New Files | Modified Files |
|-------|---------|-----------|-----------|----------------|
| 1 | F01 HBU | 4 (heritage, pro forma, disambiguation, staleness) | 2 (migration, seed) | 4 |
| 1 | F04 Pipeline | 4 (schema, entity resolution, clustering UI, saved alerts) | 2 (migrations) | 4 |
| 2 | F02 Regulatory | 5 (change records, extraction, watchlist matching, archive, Playwright) | 5 | 3 |
| 2 | F03 Due Diligence | 4 (red flags, exec summary, reorder, unavailability) | 0 | 1 |
| 3 | F05 Political Risk | 3 (news RSS, monthly refresh, dashboard) | 1 | 4 |
| 3 | F06 Undervalued | 2 (weekly cron, user filters) | 0 | 3 |
| -- | Cross-cutting | 3 (retrieval log, freshness, Playwright dep) | 3 | 2 |
| | **Total** | **25 work items** | **13 new files** | **~21 modified files** |

---

## Implementation Order

Follow PRD phase order. Within each phase, features can be parallelized.

**Phase 1:** F01-A, F01-B, F01-C, F01-D, F04-A, F04-B, F04-C, F04-D
**Phase 2:** F02-A, F02-B, F02-C, F02-D, F02-E, F03-A, F03-B, F03-C, F03-D
**Phase 3:** F05-A, F05-B, F05-C, F06-A, F06-B
**Cross-cutting:** DI-005 + DI-006 first (used by all features), Playwright before F02-E
