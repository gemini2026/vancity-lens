# VanCityLense PRD v1.0 — Gap Analysis & Project Plan

**Date:** February 14, 2026
**Author:** Claude (AI) — for review by Anton Mishel
**Status:** Draft for approval

---

## Executive Summary

The PRD defines 6 features across 3 phases. The current codebase already implements **a surprising amount** of what's specified — the POC has evolved well beyond a typical proof-of-concept. However, the PRD's acceptance criteria and data validation rules expose specific gaps between what's built and what's needed for a production-quality product.

**Bottom line:** ~65% of the PRD's functional requirements are already implemented. The remaining ~35% falls into three categories:

1. **Missing data sources** (BC Contaminated Sites, StatsCan, CMHC, BC Corporate Registry, Bill 44) — LTSA deferred post-demo
2. **Missing data validation & quality controls** (staleness warnings, confidence thresholds, PID format validation, audit trail)
3. **Missing sub-features** (setback calculations, community plan extraction, developer entity resolution, clustering alerts)

**LTSA Strategy:** LTSA API integration is deferred. The DD report will include a "Title & Ownership" placeholder section for demo purposes. After Realtor demo approval, apply for LTSA web service access and integrate in a future phase.

K2 is already the production RAG backend. No migration needed — just expand what gets ingested.

---

## Feature-by-Feature Assessment

### 3.1 — Automated Highest and Best Use Engine (Phase 1)

| Req ID | Requirement | Status | Gap |
|--------|-------------|--------|-----|
| FR-HBU-001 | Address/PID/legal desc input → parcel resolution | **DONE** | Legal description input not supported |
| FR-HBU-002 | Determine zoning district | **DONE** | `current_zoning` on parcels table |
| FR-HBU-003 | Bill 47 TOD tier (geodesic, 3 tiers) | **DONE** | Uses ST_Distance with EPSG:3005 transform |
| FR-HBU-004 | Bill 44 small-scale multi-unit | **NOT STARTED** | No Bill 44 logic exists anywhere |
| FR-HBU-005 | Community plan density bonuses | **NOT STARTED** | No community-plan-specific overrides |
| FR-HBU-006 | Heritage register check | **DONE** | heritage_sites table + confidence penalty |
| FR-HBU-007 | View cone height restriction | **DONE** | view_cones table + entitlement_confidence |
| FR-HBU-008 | Max buildable envelope (height, FSR, GBA, units, setbacks, site coverage) | **PARTIAL** | Height, FSR, GBA, units done. **Setbacks and site coverage not calculated** |
| FR-HBU-009 | Back-of-envelope pro forma | **DONE** | ThreeScenarioProForma in validation.py |
| FR-HBU-010 | One-page report (screen + PDF) | **DONE** | ParcelDetailPanel + report_generator.py |

| Acceptance Criteria | Status | Notes |
|---------------------|--------|-------|
| AC-HBU-001: <30s response | **DONE** | Typically ~2-5s |
| AC-HBU-002: Correct Tier 1 classification | **DONE** | |
| AC-HBU-003: Heritage flag | **DONE** | |
| AC-HBU-004: View cone height reduction | **DONE** | Confidence penalty, not hard cap on height |
| AC-HBU-005: GBA calculation ±5% | **DONE** | lot_area × FSR × 10.764 |
| AC-HBU-006: Invalid address error | **PARTIAL** | Returns 404, but no "verify address" suggestion |
| AC-HBU-007: Pro forma data timestamp | **NOT DONE** | No market data freshness timestamp displayed |
| AC-HBU-008: PDF includes all fields | **DONE** | |

| Data Validation | Status | Notes |
|-----------------|--------|-------|
| DV-HBU-001: PID format 9-digit | **NOT DONE** | No PID format validation |
| DV-HBU-002: Lot area range check | **NOT DONE** | No range validation |
| DV-HBU-003: FSR range check | **NOT DONE** | No range validation |
| DV-HBU-004: Geodesic distance (not Euclidean) | **DONE** | ST_Distance with EPSG:3005 |
| DV-HBU-005: Storey-to-metres conversion | **NOT DONE** | Only storeys, no metres calculation |
| DV-HBU-006: Assessment staleness warning | **NOT DONE** | No staleness check |
| DV-HBU-007: Construction cost source/date | **NOT DONE** | Hard-coded cost assumptions, no source citation |
| DV-HBU-008: Most restrictive constraint | **PARTIAL** | Confidence penalties, not hard caps |

**Estimated completion: ~70%**

**Remaining work:**
- Bill 44 entitlement logic (new module)
- Community plan density bonus extraction (K2 RAG + structured rules)
- Setback and site coverage calculations
- Data validation layer (PID format, range checks, staleness)
- View cone as hard height cap (not just confidence penalty)

---

### 3.2 — Regulatory Change Intelligence Engine (Phase 2)

| Req ID | Requirement | Status | Gap |
|--------|-------------|--------|-----|
| FR-REG-001 | Ingest council agendas, BC Laws, staff reports, bylaws, BC Gazette | **PARTIAL** | Council agendas + rezoning done. **BC Laws, bylaws, BC Gazette scrapers missing** |
| FR-REG-002 | NLP extraction (change type, scope, entitlement deltas, dates) | **DONE** | extractor.py with 21 fields via Anthropic |
| FR-REG-003 | Cross-reference changes against watchlisted parcels | **DONE** | alerts.py watchlist→signal matching |
| FR-REG-004 | Plain-English summaries with source citation | **DONE** | Signal summaries with source_url |
| FR-REG-005 | Personalized Intelligence Brief (daily/weekly email) | **PARTIAL** | Weekly digest exists. **Daily option and personalization not configurable** |
| FR-REG-006 | Searchable archive with filters | **DONE** | signals.py with date/type/neighborhood/severity filters |

| Acceptance Criteria | Status | Notes |
|---------------------|--------|-------|
| AC-REG-001: Ingest within 24h | **DONE** | Scheduler runs on cron |
| AC-REG-002: Before/after FSR extraction | **DONE** | NLP extracts fsr_change, height_change |
| AC-REG-003: Notification for affected parcels | **DONE** | |
| AC-REG-004: No false positive notifications | **PARTIAL** | Rule-based matching, no false-positive analysis |
| AC-REG-005: Summary <200 words, readable | **DONE** | |
| AC-REG-006: Archive searchable 24 months | **DONE** | Full-text search on signals |

| Data Validation | Status | Notes |
|-----------------|--------|-------|
| DV-REG-001: Source URL required | **DONE** | source_url field |
| DV-REG-002: NLP confidence <85% → flag for review | **NOT DONE** | No confidence-based review flagging |
| DV-REG-003: Effective date validation | **NOT DONE** | No date validity checks |
| DV-REG-004: Geographic scope resolution | **PARTIAL** | neighborhood_name extracted, not validated |
| DV-REG-005: Duplicate detection | **DONE** | dedup.py |

**Estimated completion: ~75%**

**Remaining work:**
- BC Laws scraper (bclaws.ca RSS)
- BC Gazette scraper (bclaws.ca/gazette RSS)
- Municipal bylaw amendment scraper
- NLP extraction confidence threshold + manual review queue
- Daily digest option + personalization controls

---

### 3.3 — AI-Powered Due Diligence Assembly (Phase 2)

| Req ID | Requirement | Status | Gap |
|--------|-------------|--------|-----|
| FR-DD-001 | Query 9 data sources (LTSA, BCA, CoV, Contaminated Sites, Heritage, Dev Apps, TransLink, StatsCan, CMHC) | **PARTIAL** | **BCA, Heritage, CoV, TransLink, Dev Apps: DONE. StatsCan: public REST (no auth). CMHC: Open Canada CSV (no auth). Contaminated Sites: NOT DONE. LTSA: DEFERRED post-demo** |
| FR-DD-002 | Standardized report (10 sections) | **PARTIAL** | 6 of 10 sections exist. **Missing: Title/Ownership (stub for demo), Environmental, Market Context, Demographic Profile** |
| FR-DD-003 | Auto-flag red flags | **DONE** | validation.py risk flags |
| FR-DD-004 | Professional PDF output | **DONE** | report_generator.py |
| FR-DD-005 | Data currency section | **NOT DONE** | No retrieval date/source tracking in report |

| Acceptance Criteria | Status | Notes |
|---------------------|--------|-------|
| AC-DD-001: Report in <5min | **DONE** | Typically ~10-30s |
| AC-DD-002: 7 of 9 sources, "unavailable" for missing | **NOT DONE** | No graceful "source unavailable" handling |
| AC-DD-003: Contaminated site flag | **NOT DONE** | No contaminated sites data |
| AC-DD-004: Adjacent rezoning activity | **PARTIAL** | Nearby signals exist, not scoped to 500m radius |
| AC-DD-005: PDF renders correctly | **DONE** | |
| AC-DD-006: Executive summary <300 words | **PARTIAL** | No auto-generated exec summary |

| Data Validation | Status | Notes |
|-----------------|--------|-------|
| DV-DD-001: LTSA data validation | **DEFERRED** | LTSA integration deferred post-Realtor demo |
| DV-DD-002: BCA staleness check | **NOT DONE** | No staleness warnings |
| DV-DD-003: Contaminated status enum | **NOT DONE** | |
| DV-DD-004: Dev permit record completeness | **PARTIAL** | |
| DV-DD-005: 500m radius boundary | **PARTIAL** | Distance calculations exist |
| DV-DD-006: Census tract resolution | **NOT DONE** | No census data |

**Estimated completion: ~45%**

**Remaining work:**
- ~~LTSA API integration~~ → **DEFERRED** post-Realtor demo approval
- Title/Ownership report section — stub with BC Assessment ownership data + "Full LTSA title search available in Pro tier" placeholder
- BC Contaminated Sites Registry scraper
- StatsCan WDS client (public REST, no auth — tables 9810003501, 1710014201, 3410032701)
- CMHC CSV ingestion (Open Canada bulk download, no auth — starts, completions, under construction, absorptions)
- PID→census tract + census subdivision precomputed lookup table (DI-008)
- Report sections: Environmental, Market Context (CMHC @ CSD level), Demographics (StatsCan @ census tract level)
- Auto-generated executive summary
- Data currency/source tracking section in PDF
- Graceful "source unavailable" handling

---

### 3.4 — Development Pipeline Intelligence (Phase 1)

| Req ID | Requirement | Status | Gap |
|--------|-------------|--------|-----|
| FR-PIPE-001 | Ingest dev apps, rezonings, building permits daily | **DONE** | scrapers + scheduler |
| FR-PIPE-002 | Geocode and map display | **DONE** | geocoder.py + MapView.tsx |
| FR-PIPE-003 | Classify into pipeline stages | **DONE** | 7 stages in supply_pipeline |
| FR-PIPE-004 | Display application details | **DONE** | |
| FR-PIPE-005 | Filter by stage, type, height, units, date, developer, area | **PARTIAL** | Stage/type/neighborhood filters done. **Height range, unit range, developer name, draw-polygon filters missing** |
| FR-PIPE-006 | Clustering alerts (3+ apps in 500m/90 days) | **NOT DONE** | No clustering detection |
| FR-PIPE-007 | Saved filters + automated email alerts | **PARTIAL** | Watchlists exist but not scoped to pipeline filters |

| Acceptance Criteria | Status | Notes |
|---------------------|--------|-------|
| AC-PIPE-001: Ingest within 24h | **DONE** | |
| AC-PIPE-002: 500m radius search | **DONE** | PostGIS spatial queries |
| AC-PIPE-003: Multi-criteria filter | **PARTIAL** | |
| AC-PIPE-004: Clustering alert | **NOT DONE** | |
| AC-PIPE-005: Status change alerts | **PARTIAL** | Alerts on signals, not on stage transitions |
| AC-PIPE-006: 1000+ markers < 3s | **DONE** | Mapbox GL clustering |

| Data Validation | Status | Notes |
|-----------------|--------|-------|
| DV-PIPE-001: Application number format | **NOT DONE** | |
| DV-PIPE-002: Geocode boundary check | **NOT DONE** | No Metro Vancouver boundary validation |
| DV-PIPE-003: Stage normalization | **DONE** | 7 defined stages |
| DV-PIPE-004: Height range validation | **NOT DONE** | |
| DV-PIPE-005: Date validation | **NOT DONE** | |
| DV-PIPE-006: Developer entity resolution | **NOT DONE** | No developer normalization table |

**Estimated completion: ~70%**

**Remaining work:**
- Advanced pipeline filters (height/unit range, developer name, draw-polygon)
- Clustering detection algorithm (3+ in 500m / 90 days)
- Stage transition alerts
- Developer entity resolution table + normalization
- Data validation rules

---

### 3.5 — Community Opposition & Political Risk Scoring (Phase 3)

| Req ID | Requirement | Status | Gap |
|--------|-------------|--------|-----|
| FR-OPP-001 | Ingest council transcripts, Shape Your City, news, community associations | **PARTIAL** | Council + news scrapers done. **ShapeYourCity structured submissions not parsed. Community association sites not scraped** |
| FR-OPP-002 | NLP sentiment classification (Support/Neutral/Opposed) | **DONE** | extractor.py sentiment field |
| FR-OPP-003 | Neighborhood Political Risk Score (1-10) | **NOT DONE** | Only basic opposition penalty in confidence calc |
| FR-OPP-004 | Parcel-level risk summary (score, themes, comparisons, narrative) | **NOT DONE** | |
| FR-OPP-005 | Monthly score updates | **NOT DONE** | |

| Acceptance Criteria | Status | Notes |
|---------------------|--------|-------|
| AC-OPP-001: Scores for all 22 neighborhoods | **NOT DONE** | |
| AC-OPP-002: High opposition → score ≥7 | **NOT DONE** | |
| AC-OPP-003: Low opposition → score ≤3 | **NOT DONE** | |
| AC-OPP-004: Top 3 themes from 10+ signals | **NOT DONE** | |
| AC-OPP-005: Risk narrative <150 words | **NOT DONE** | |
| AC-OPP-006: Updates within 7 days of new data | **NOT DONE** | |

**Estimated completion: ~25%**

**Remaining work:**
- Political Risk Score computation engine (neighborhood-level, 1-10 scale)
- Opposition theme extraction (K2 RAG over signals)
- Risk narrative generation (K2/Anthropic)
- Parcel-level risk summary endpoint + UI component
- ShapeYourCity submission scraper enhancement
- Community association website scrapers
- Monthly score materialization job

---

### 3.6 — Proactive Undervalued Parcel Alerts (Phase 3)

| Req ID | Requirement | Status | Gap |
|--------|-------------|--------|-----|
| FR-DEAL-001 | Calculate implied development value for all parcels | **PARTIAL** | Per-parcel value estimate exists. **Batch computation for all 92K parcels not implemented** |
| FR-DEAL-002 | Compare implied vs assessed | **DONE** | value_delta in entitlement response |
| FR-DEAL-003 | Flag undervalued (>25% below avg transaction/bldSF) | **NOT DONE** | No comparable-based undervaluation scoring |
| FR-DEAL-004 | Weekly top-20 Opportunity Alert | **NOT DONE** | Opportunity profiles exist but not this ranking |
| FR-DEAL-005 | Alert entry details (address, entitlements, discount %) | **NOT DONE** | |
| FR-DEAL-006 | User-configurable alert filters | **DONE** | opportunity_alerts.py criteria |

**Estimated completion: ~35%**

**Remaining work:**
- Batch implied-value computation (materialized view or cron job)
- Comparable transaction average per buildable SF per neighborhood+tier
- Undervaluation scoring algorithm (assessed vs. comp average)
- Weekly top-20 ranking + email delivery
- "Repeat Signal" tracking for recurring undervalued parcels
- "Active Application" exclusion from alerts

---

## Cross-Feature Requirements Assessment

| Req ID | Requirement | Status | Notes |
|--------|-------------|--------|-------|
| DI-001 | PID as universal join key | **DONE** | pid TEXT on all tables |
| DI-002 | Consistent CRS (EPSG:4326 + geodesic) | **DONE** | PostGIS with SRID 4326, ST_Distance with 3005 |
| DI-003 | UTC storage, Pacific display | **PARTIAL** | TIMESTAMPTZ used. **Frontend doesn't explicitly convert to Pacific** |
| DI-004 | Multi-source conflict precedence (BCA > CoV; LTSA deferred) | **NOT DONE** | Only one source per attribute currently; LTSA precedence added post-demo |
| DI-005 | External retrieval audit log | **NOT DONE** | Scraper runs logged, but not per-query retrieval |
| DI-006 | Data freshness dashboard | **NOT DONE** | No admin freshness dashboard |
| DI-008 | StatsCan/CMHC geographic joins via precomputed PID→census tract + CSD lookup table (EPSG:4326) | **NOT DONE** | New lookup table needed (Sprint 4.6) |

| NFR | Requirement | Status | Notes |
|-----|-------------|--------|-------|
| NFR-001 | HBU <30s, DD <5min | **DONE** | |
| NFR-002 | 92K parcels, scalable to 500K | **DONE** | PostGIS + indexes |
| NFR-003 | 99.5% uptime | **PARTIAL** | GKE deployed, no SLA monitoring |
| NFR-004 | Data currency display | **NOT DONE** | |
| NFR-005 | PDF + CSV export | **DONE** | |
| NFR-006 | Sources & methodology audit trail | **PARTIAL** | PDF has sources section, no methodology |

---

## Data Source Registry Assessment

| Source ID | Source | PRD Status | Current Status | Gap |
|-----------|--------|------------|----------------|-----|
| DS-001 | CoV Open Data | Phase 1 | **INTEGRATED** | ✅ |
| DS-002 | BC Assessment | Phase 1 | **SEEDED** | Need API for live updates |
| DS-003 | BC LTSA | Phase 2 | **DEFERRED** | Stub for demo; apply for API access after Realtor approval |
| DS-004 | TransLink GTFS | Phase 1 | **SEEDED** | Need GTFS feed auto-refresh |
| DS-005 | BC Laws | Phase 2 | **NOT STARTED** | RSS/scrape from bclaws.ca |
| DS-006 | Council Agendas | Phase 2 | **INTEGRATED** | scraper_council.py |
| DS-007 | BC Contaminated Sites | Phase 2 | **NOT STARTED** | Web scrape from gov.bc.ca |
| DS-008 | StatsCan Web Data Service | Phase 2 | **NOT STARTED** | Public REST API at `https://www150.statcan.gc.ca/t1/wds/rest/` — **no auth, no API key, no registration**. Rate limit 25 req/sec. JSON responses. |
| DS-009 | CMHC Housing Data | Phase 2 | **NOT STARTED** | Bulk CSV from Open Canada (`https://search.open.canada.ca/opendata/?owner_org=cmhc-schl`) — **no auth, no API key, no registration**. Monthly refresh. |
| DS-010 | Heritage Register | Phase 1 | **SEEDED** | ✅ |
| DS-011 | View Cones | Phase 1 | **SEEDED** | ✅ |
| DS-012 | Neighbourhood Plans | Phase 2 | **PARTIAL** | Ingested into K2 corpus, not structurally parsed |
| DS-013 | Local News | Phase 3 | **INTEGRATED** | scraper_news.py |
| DS-014 | BC Gazette | Phase 2 | **NOT STARTED** | RSS from bclaws.ca |
| DS-015 | BC Corporate Registry | Phase 3 | **NOT STARTED** | Per-query, paid |

---

## K2 Strategy

K2 is already the production GenAI backend. The plan is to **expand K2's role**, not replace anything:

| K2 Capability | Current Use | Expanded Use |
|---------------|-------------|--------------|
| **Document ingestion** | Council docs, news, policy PDFs via `k2_ingest_sources.py` | Add: BC Laws, BC Gazette, community plans, ShapeYourCity submissions |
| **RAG search** | Chat + policy excerpt retrieval | Add: opposition theme extraction, risk narrative generation, community plan bonus lookup |
| **Chunk normalization** | k2_client.py → chat.py | No change needed |
| **Fallback** | K2 → local BM25 | Keep as-is |

**New K2 integrations needed:**
1. **Opposition theme extraction** — K2 search for `"opposition {neighborhood}"` → Anthropic summarization → top 3 themes
2. **Risk narrative generation** — K2 search for precedent signals → Anthropic generates 150-word risk narrative
3. **Community plan bonus lookup** — K2 search for `"{plan_name} density bonus FSR"` → extract structured overrides
4. **Regulatory change detection** — Ingest BC Laws/Gazette into K2, search for changes mentioning zoning/density/height

No changes to `k2_client.py` or `retrieval_backend.py` needed — these already provide the abstraction layer.

---

## Realistic Project Plan

### Phase 1: POC → MVP (Current state + gaps)

**Goal:** Close the HBU Engine and Pipeline Intelligence gaps to meet PRD acceptance criteria.

#### Sprint 1 (2 weeks): Data Validation & Quality Layer

| # | Task | Effort | Files |
|---|------|--------|-------|
| 1.1 | PID format validation (9-digit NNN-NNN-NNN) | S | `api/entitlement.py`, `api/models.py` |
| 1.2 | Lot area range validation (0–500K SF, warning flag) | S | `api/validation.py` |
| 1.3 | FSR range validation (0.1–15.0, anomaly flag) | S | `api/validation.py` |
| 1.4 | Height storey-to-metres conversion (3.0m res, 3.5m commercial) | S | `api/entitlement.py`, frontend |
| 1.5 | BC Assessment staleness warning (>18 months) | S | `api/entitlement.py`, frontend |
| 1.6 | Pro forma market data timestamp | S | `api/validation.py`, frontend |
| 1.7 | Invalid address → helpful error message | S | `api/parcels_routes.py` |
| 1.8 | View cone as hard height cap (not just confidence penalty) | M | `api/entitlement.py` |
| 1.9 | Tests for all validation rules | M | `tests/` |

#### Sprint 2 (2 weeks): Setbacks, Site Coverage & Pipeline Filters

| # | Task | Effort | Files |
|---|------|--------|-------|
| 2.1 | Setback calculation (front/rear/side from zoning bylaw rules) | L | New: `api/setback_rules.py`, modify entitlement |
| 2.2 | Site coverage calculation | M | `api/entitlement.py` |
| 2.3 | Pipeline filter: height range, unit count range | M | `api/intelligence/supply_pipeline.py`, frontend |
| 2.4 | Pipeline filter: developer name search | M | Same + new developer table |
| 2.5 | Pipeline filter: draw-polygon on map | L | Frontend MapView.tsx + backend spatial query |
| 2.6 | Developer entity resolution table + normalization | M | New migration, new module |
| 2.7 | Data validation for pipeline (app number format, geocode boundary, date) | M | `api/intelligence/supply_pipeline.py` |

#### Sprint 3 (2 weeks): Bill 44 & Community Plans

| # | Task | Effort | Files |
|---|------|--------|-------|
| 3.1 | Bill 44 entitlement logic (small-scale multi-unit rules) | L | New: `api/bill44_entitlement.py`, migration |
| 3.2 | Community plan density bonus rules (structured) | L | New: `api/community_plan_rules.py`, seed data |
| 3.3 | K2 RAG integration for community plan lookups | M | `api/intelligence/` |
| 3.4 | Integrate Bill 44 + community plans into HBU response | M | `api/entitlement.py`, `api/models.py` |
| 3.5 | Frontend: display Bill 44 and community plan info | M | `ParcelDetailPanel.tsx` |
| 3.6 | Clustering alert detection (3+ apps in 500m / 90 days) | M | `api/intelligence/supply_pipeline.py` |
| 3.7 | Stage transition alerts | M | `api/intelligence/alerts.py` |

**Phase 1 total: ~6 weeks**

---

### Phase 2: MVP → Product

**Goal:** Regulatory Intelligence Engine + Due Diligence Assembly.

#### Sprint 4 (2 weeks): New Data Source Integrations

| # | Task | Effort | Files |
|---|------|--------|-------|
| 4.1 | BC Laws scraper (bclaws.ca RSS → K2 ingest) | M | New: `api/intelligence/scraper_bclaws.py` |
| 4.2 | BC Gazette scraper (RSS → K2 ingest) | M | New: `api/intelligence/scraper_gazette.py` |
| 4.3 | BC Contaminated Sites Registry scraper | M | New: `api/intelligence/scraper_contaminated.py`, migration |
| 4.4 | StatsCan WDS client (public REST, no auth). Tables: 9810003501 (census tract demographics), 1710014201 (population estimates), 3410032701 (building permits). Monthly bulk CSV + on-demand vector queries. Rate limiter at 20 req/sec. | M | New: `api/statscan_client.py` |
| 4.5 | CMHC CSV ingestion (Open Canada bulk download, no auth). Datasets: Housing Starts, Completions, Under Construction, Absorptions. Monthly download + parse. Vancouver CMA=933. | M | New: `api/cmhc_client.py` |
| 4.6 | PID→census tract + census subdivision lookup table (precomputed spatial join, DI-008) | M | New migration, PostGIS spatial join |
| 4.7 | StatsCan/CMHC data validation rules (DV-DS008-001..005, DV-DS009-001..006) | M | `api/statscan_client.py`, `api/cmhc_client.py` |
| 4.8 | Add all new sources to `pipeline/sources.yaml` + K2 ingest | S | `pipeline/sources.yaml`, `k2_ingest_sources.py` |
| 4.9 | TransLink GTFS auto-refresh job | S | New K8s CronJob |

#### Sprint 5 (2 weeks): Regulatory Intelligence Completion

| # | Task | Effort | Files |
|---|------|--------|-------|
| 5.1 | NLP extraction confidence threshold + manual review queue | M | `api/intelligence/extractor.py`, new UI |
| 5.2 | Daily digest option (currently weekly only) | S | `api/intelligence/digest.py` |
| 5.3 | Personalized brief configuration UI | M | Frontend |
| 5.4 | Geographic scope validation (resolve to valid zoning/neighborhood) | M | `api/intelligence/extractor.py` |
| 5.5 | Effective date validation rules | S | `api/intelligence/signals.py` |
| 5.6 | Municipal bylaw amendment detection (via K2 search) | M | `api/intelligence/` |

#### Sprint 6 (2 weeks): Due Diligence Report Expansion

| # | Task | Effort | Files |
|---|------|--------|-------|
| 6.1 | Report section: Title & Ownership **stub** (BCA ownership data + "LTSA available in Pro" placeholder) | S | `api/report_generator.py` |
| 6.2 | Report section: Environmental (contaminated sites) | M | `api/report_generator.py` |
| 6.3 | Report section: Market Context (CMHC). Fields: housing starts 12-mo, starts by type, completions 12-mo, under construction, absorption rate. Census Subdivision level with label "may not reflect micro-market conditions." | M | `api/report_generator.py` |
| 6.4 | Report section: Demographic Profile (StatsCan WDS). Fields: population, 5-yr growth, median household income, avg household size, owner/renter split, dominant dwelling type. Census tract level. Boundary proximity note if centroid within 100m of tract boundary. | M | `api/report_generator.py` |
| 6.5 | Auto-generated Executive Summary (<300 words) | M | `api/report_generator.py` |
| 6.6 | Data currency section (retrieval dates per source) | M | `api/report_generator.py` |
| 6.7 | Graceful "source unavailable" handling for all sections | M | `api/report_generator.py` |
| 6.8 | Surrounding development activity within 500m radius | S | `api/report_generator.py` |
| 6.9 | External retrieval audit log | M | New: `api/audit_log.py`, migration |

**Phase 2 total: ~6 weeks**

---

### Phase 3: Product → Platform

**Goal:** Opposition Risk Scoring + Undervalued Parcel Alerts.

#### Sprint 7 (2 weeks): Political Risk Score Engine

| # | Task | Effort | Files |
|---|------|--------|-------|
| 7.1 | Opposition rate calculation per neighborhood (trailing 36 months) | M | New: `api/intelligence/political_risk.py` |
| 7.2 | Delay attribution calculation (opposition-caused delays) | M | Same |
| 7.3 | Sentiment intensity weighting (recency-weighted) | M | Same |
| 7.4 | Council voting pattern analysis per neighborhood | M | Same |
| 7.5 | Composite Political Risk Score (1-10) computation | M | Same |
| 7.6 | Score materialization (monthly CronJob) | S | New K8s CronJob |
| 7.7 | DB migration for political_risk_scores table | S | New migration |

#### Sprint 8 (2 weeks): Opposition Themes & Risk Narrative

| # | Task | Effort | Files |
|---|------|--------|-------|
| 8.1 | Opposition theme extraction via K2 + Anthropic | M | `api/intelligence/political_risk.py` |
| 8.2 | Risk narrative generation (<150 words) via K2 + Anthropic | M | Same |
| 8.3 | Parcel-level risk summary endpoint | M | New route in `api/intelligence/` |
| 8.4 | ShapeYourCity structured submission parser | M | Enhance scraper |
| 8.5 | Community association website scrapers (22 neighborhoods) | L | New scrapers |
| 8.6 | Frontend: Political Risk component in ParcelDetailPanel | M | Frontend |
| 8.7 | Frontend: Neighborhood risk heatmap layer on map | M | `MapView.tsx` |
| 8.8 | Validation: confidence <0.60 exclusion, min 5 apps threshold | S | `api/intelligence/political_risk.py` |

#### Sprint 9 (2 weeks): Undervalued Parcel Alerts

| # | Task | Effort | Files |
|---|------|--------|-------|
| 9.1 | Batch implied-value computation (all parcels with entitlements) | L | New: materialized view or cron job |
| 9.2 | Comparable avg $/buildable SF per neighborhood+tier (trailing 12mo) | M | `api/intelligence/comparable_sales.py` |
| 9.3 | Undervaluation scoring (assessed vs comp avg, >25% threshold) | M | New: `api/intelligence/undervalued_scoring.py` |
| 9.4 | Weekly top-20 ranking + email delivery | M | `api/intelligence/digest.py` |
| 9.5 | "Repeat Signal" tracking | S | DB column + logic |
| 9.6 | "Active Application" exclusion | S | Join with supply_pipeline |
| 9.7 | Validation: min 3 comps, 18-month BCA limit, arm's-length filter | M | Scoring module |
| 9.8 | Caveats for contaminated/heritage parcels | S | Scoring module |
| 9.9 | Frontend: Opportunity Alert dashboard | M | New component |

#### Sprint 10 (1 week): Cross-Feature Requirements

| # | Task | Effort | Files |
|---|------|--------|-------|
| 10.1 | Data freshness admin dashboard | M | New admin page |
| 10.2 | Multi-source conflict precedence (BCA > CoV; LTSA added post-demo) | M | `api/entitlement.py` |
| 10.3 | Pacific Time display in frontend | S | Frontend utility |
| 10.4 | Sources & methodology section in all reports | M | `api/report_generator.py` |

**Phase 3 total: ~7 weeks**

---

## Summary Timeline

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| **Phase 1**: POC → MVP | 6 weeks | Data validation, setbacks, Bill 44, community plans, clustering alerts |
| **Phase 2**: MVP → Product | 6 weeks | 4 new data sources (no LTSA), regulatory intelligence, DD report with Title stub |
| **Phase 3**: Product → Platform | 7 weeks | Political risk scoring, undervalued alerts, admin dashboard |
| **Total** | **~19 weeks** | Full PRD v1.0 implementation (LTSA deferred post-demo) |

**Post-Demo Gate:** After Realtor demo approval → apply for LTSA API access → integrate Title & Ownership section with live LTSA data (estimated +2 weeks when approved).

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| ~~LTSA API access~~ | **DEFERRED** | Stub Title section for demo; apply for LTSA after Realtor approval |
| BC Contaminated Sites has no API (web scrape only) | Data freshness | Build robust scraper with change detection |
| Bill 44 rules are complex and municipality-dependent | Phase 1 accuracy | Start with Vancouver-specific rules only |
| Community plan density bonuses are in PDFs, not structured data | Phase 1 accuracy | K2 RAG extraction + manual validation of top 8 plans |
| Community association websites change frequently | Phase 3 reliability | Build generic scraper framework, not per-site scrapers |
| BC Corporate Registry is paid per-query | Phase 3 cost | Defer; developer entity resolution from free sources first |
| Comparable transaction data may be sparse for some tiers | Phase 3 accuracy | Min 3 comps threshold; expand neighborhood radius if needed |

---

## Dependencies & Blockers

| Dependency | Blocks | Action Required |
|------------|--------|-----------------|
| ~~LTSA API account~~ | ~~Phase 2~~ | **DEFERRED** — apply after Realtor demo approval |
| BC Assessment data license | Phase 2 (live BCA updates) | Evaluate BCA API pricing |
| K2 corpus expansion | Phase 2-3 (new source ingestion) | Update `pipeline/sources.yaml`, run `k2_ingest_sources.py` |
| Anthropic API budget | Phase 3 (risk narratives, theme extraction) | Estimate token usage for 22 neighborhoods × monthly |
| ~~StatsCan API key~~ | ~~Phase 2~~ | **NO BLOCKER** — public REST API, no auth required |
| ~~CMHC API key~~ | ~~Phase 2~~ | **NO BLOCKER** — Open Canada CSV downloads, no auth required |

---

## What Doesn't Need Work

These are fully implemented and match PRD requirements with no gaps:

1. **Core entitlement engine** (Bill 47 tiers, FSR, height, GBA calculation)
2. **Three-scenario pro forma** (bull/base/bear with full cost breakdown)
3. **Confidence scoring** (heritage, view cone, opposition, CD-1 penalties)
4. **PDF report generation** (professional output with all core sections)
5. **K2 RAG pipeline** (search, retrieval, citation, fallback)
6. **K2 document ingestion** (URL-based, batch, dedup, auto-index)
7. **Watchlist + alert system** (rules, matching, delivery)
8. **Opportunity profiles** (criteria, matching, scoring)
9. **Supply pipeline tracking** (7 stages, analytics, history)
10. **Map visualization** (92K parcels, clustering, filters)
11. **Authentication + multi-tenancy** (JWT, orgs, Stripe subscriptions)
12. **CSV + PDF export** (all tabular data exportable)
