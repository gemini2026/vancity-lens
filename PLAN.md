# VanCity Lens — Technical Backlog & Action Plan

> **Last updated:** Feb 8, 2026 — Consolidated from VanCity_Lens_Review_Plan.docx + VALIDATION_V2_PLAN.md + PERFORMANCE_SCALABILITY_REVIEW.md + codebase analysis
> **Current state:** 405 tests passing | 3 Docker services | 92K parcels | 22 neighborhoods scored
> **Git:** `4ce4929` on `main` (Tier 0+1 security hardening complete)
> **Source documents:** VanCity_Lens_Review_Plan.docx (4-dimension review), VALIDATION_V2_PLAN.md (11 new checks), PERFORMANCE_SCALABILITY_REVIEW.md (8 critical findings), REVIEW_SUMMARY.txt

---

## Status Legend

| Tag | Meaning |
|-----|---------|
| `✅ DONE` | Implemented, tested, merged to main |
| `🔧 IN PROGRESS` | Partially implemented or needs verification |
| `📋 TODO` | Not started |
| `🧊 DEFERRED` | Intentionally postponed (low ROI or blocked) |
| `✂️ CUT` | Removed from scope |

---

## Epic Overview

| Epic | ID Prefix | Items | Done | Remaining |
|------|-----------|-------|------|-----------|
| Security & Auth | `SEC` | 12 | 5 | 7 |
| Performance & Scalability | `PERF` | 18 | 4 | 14 |
| Test Coverage & Quality | `TEST` | 14 | 6 | 8 |
| Data Pipeline & Seeding | `DATA` | 9 | 2 | 7 |
| Validation Engine V2 | `VAL` | 14 | 6 | 8 |
| Intelligence Layer | `INTEL` | 10 | 5 | 5 |
| Frontend & UX | `FE` | 12 | 5 | 7 |
| Infrastructure & DevOps | `INFRA` | 12 | 3 | 9 |
| Business Value & Monetization | `BIZ` | 16 | 0 | 16 |
| **TOTAL** | | **117** | **36** | **81** |

---

## Cross-Reference: VanCity_Lens_Review_Plan.docx → PLAN.md

This table maps every item from the docx consolidated action plan (42 items across 6 tiers) to its PLAN.md backlog item, ensuring 100% coverage.

| Docx # | Docx Item | PLAN.md ID | Status |
|--------|-----------|------------|--------|
| 0.1 | Admin endpoint authentication | SEC-001 | ✅ DONE |
| 0.2 | Remove hardcoded DB credentials | SEC-002 | ✅ DONE |
| 0.3 | Entitlement engine unit tests | TEST-001 | ✅ DONE |
| 0.4 | Tighten CORS configuration | SEC-003 | ✅ DONE |
| 0.5 | Deep health check | SEC-005 | ✅ DONE |
| 1.1 | Seed 200+ real Vancouver gov documents | DATA-001 + DATA-002 | 📋 TODO |
| 1.2 | N+1 query fix for scorecards | PERF-002 + PERF-003 | ✅ DONE |
| 1.3 | Database integration tests | TEST-006 | 📋 TODO |
| 1.4 | E2E pipeline validation test | TEST-012 | 📋 TODO (NEW) |
| 1.5 | Connection pool configuration | PERF-001 | ✅ DONE |
| 1.6 | Security headers middleware | SEC-004 | ✅ DONE |
| 2.1 | Response caching (Redis) | PERF-005 | 📋 TODO |
| 2.2 | Comparable sales baseline | BIZ-011 + DATA-009 | 📋 TODO (NEW) |
| 2.3 | API contract tests | TEST-010 | 📋 TODO |
| 2.4 | Admin + hidden costs tests | TEST-002 + TEST-003 | ✅ DONE |
| 2.5 | Automated document refresh | DATA-004 | 📋 TODO |
| 2.6 | Rate limiting | SEC-008 | 📋 TODO |
| 2.7 | Address-based parcel search | BIZ-012 + FE-011 | 📋 TODO (NEW) |
| 3.1 | Financing calculator / deal modeling | BIZ-013 | 📋 TODO (NEW) |
| 3.2 | Entitlement confidence scoring | BIZ-014 | 📋 TODO (NEW) |
| 3.3 | Parallel document processing | PERF-006 + PERF-007 | 📋 TODO |
| 3.4 | Structured logging (structlog) | INFRA-008 | 📋 TODO |
| 3.5 | External service failure tests | TEST-013 | 📋 TODO (NEW) |
| 3.6 | Frontend E2E hardening | TEST-014 | 📋 TODO (NEW) |
| 4.1 | Multi-stage Docker build | INFRA-012 | 📋 TODO (NEW) |
| 4.2 | Community opposition scoring | VAL-009 | 📋 TODO |
| 4.3 | Supply pipeline tracking | INTEL-010 | 📋 TODO (NEW) |
| 4.4 | Weekly digest email | INTEL-007 | 📋 TODO |
| 4.5 | Batch embedding optimization | PERF-017 | 📋 TODO (NEW) |
| 5.1 | Pricing tiers + Stripe integration | BIZ-002 + BIZ-003 | 📋 TODO |
| 5.2 | API access (developer tier) | BIZ-010 | 📋 TODO |
| 5.3 | Bulk parcel upload + analysis | BIZ-015 | 📋 TODO (NEW) |
| 5.4 | CRM integration (Zapier/Slack) | BIZ-016 | 📋 TODO (NEW) |
| 5.5 | Observability (Prometheus/Grafana) | INFRA-007 | 📋 TODO |

**Performance review additional items:**
| Perf Review Item | PLAN.md ID | Status |
|------------------|------------|--------|
| Pool size configuration | PERF-001 | ✅ DONE |
| N+1 scorecards query | PERF-002 | ✅ DONE |
| Response caching layer | PERF-005 | 📋 TODO |
| Compound indexes | PERF-004 | 📋 TODO |
| Parallel document processing | PERF-006 + PERF-007 | 📋 TODO |
| Batch Cohere embedding calls | PERF-017 | 📋 TODO (NEW) |
| Cursor-based pagination | PERF-018 | 📋 TODO (NEW) |

---

## EPIC 1: Security & Auth (`SEC`)

### SEC-001: Admin endpoint API key authentication `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 0
- **Docx ref:** Item 0.1
- **Description:** All admin endpoints (`/admin/scrape`, `/admin/process`, `/admin/feeds`, `/admin/status`, `/admin/scrape-opendata`) must require authentication via `X-Admin-Key` header.
- **Files changed:**
  - `api/auth.py` — NEW: `require_admin` dependency using `APIKeyHeader`
  - `api/admin.py` — Added `dependencies=[Depends(require_admin)]` to router
  - `api/intelligence/routes.py` — Added `dependencies=[Depends(require_admin)]` to 5 admin endpoints
- **Acceptance criteria:**
  - [x] `GET /api/v1/admin/*` returns 401 without header
  - [x] `GET /api/v1/admin/*` returns 403 with wrong key
  - [x] `GET /api/v1/admin/*` returns 200 with correct key
  - [x] Dev mode: warns but allows access if `ADMIN_API_KEY` not set
  - [x] Production mode: requires valid key, rejects all unauthenticated requests

### SEC-002: Remove hardcoded database credentials `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 0
- **Docx ref:** Item 0.2
- **Description:** Database URL must come from environment. Production must fail loudly if `DATABASE_URL` not set.
- **Files changed:**
  - `api/db.py` — Added `_get_database_url()` with env-aware fallback
- **Acceptance criteria:**
  - [x] `VANCITY_ENV=production` without `DATABASE_URL` → `RuntimeError`
  - [x] Development mode uses default with warning log
  - [x] `DATABASE_URL` env var takes priority when set

### SEC-003: Tighten CORS configuration `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 0
- **Docx ref:** Item 0.4
- **Description:** Replace wildcard `allow_methods=["*"]` and `allow_headers=["*"]` with explicit whitelist.
- **Files changed:**
  - `api/main.py` — Restricted to `["GET", "POST", "PUT", "DELETE", "OPTIONS"]` and `["Content-Type", "Authorization", "X-Admin-Key"]`
- **Acceptance criteria:**
  - [x] Only listed HTTP methods allowed
  - [x] Only listed headers accepted
  - [x] `allow_origins` still configurable for dev vs production

### SEC-004: Add security response headers `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 0
- **Docx ref:** Item 1.6
- **Description:** Add standard security headers to all API responses.
- **Files changed:**
  - `api/main.py` — Added `SecurityHeadersMiddleware` (Starlette `BaseHTTPMiddleware`)
- **Acceptance criteria:**
  - [x] `X-Content-Type-Options: nosniff` on all responses
  - [x] `X-Frame-Options: DENY` on all responses
  - [x] `X-XSS-Protection: 1; mode=block` on all responses
  - [x] `Referrer-Policy: strict-origin-when-cross-origin` on all responses
  - [x] `Strict-Transport-Security: max-age=31536000; includeSubDomains` in production only

### SEC-005: Deep health check with DB verification `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 0
- **Docx ref:** Item 0.5
- **Description:** Health endpoint must verify database connectivity, not just return static JSON.
- **Files changed:**
  - `api/main.py` — Health endpoint now queries `information_schema.tables`
- **Acceptance criteria:**
  - [x] Returns `{"status": "ok", "db": "connected", "tables": N}` when healthy
  - [x] Returns `{"status": "degraded", "db": "error: ..."}` when DB down
  - [x] Docker healthcheck can use this endpoint

### SEC-006: Environment-based CORS origins `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** `allow_origins` should read from `ALLOWED_ORIGINS` env var. Production should NOT use `["*"]`.
- **Files to change:** `api/main.py`
- **Acceptance criteria:**
  - [ ] `ALLOWED_ORIGINS=https://app.vancitylens.com,https://staging.vancitylens.com`
  - [ ] Falls back to `["http://localhost:3000"]` in dev mode
  - [ ] Wildcard `*` only allowed when `VANCITY_ENV != production`

### SEC-007: Input validation & sanitization on chat endpoint `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** Chat query input has no length limit or sanitization. A malicious 100KB query goes straight to Claude API.
- **Files to change:** `api/intelligence/routes.py`, `api/intelligence/models.py`
- **Acceptance criteria:**
  - [ ] `ChatRequest.query` max length: 2000 characters (Pydantic `max_length`)
  - [ ] Strip leading/trailing whitespace
  - [ ] Reject empty queries (400 response)
  - [ ] Log input length for monitoring

### SEC-008: Rate limiting on chat and extraction endpoints `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Docx ref:** Item 2.6
- **Description:** Chat endpoint calls Anthropic + Cohere APIs. Without rate limiting, a burst of requests can exhaust API quotas. Docx specifies "60 req/min" for public endpoints.
- **Files to create:** `api/middleware/rate_limit.py`
- **Files to change:** `api/main.py`
- **Acceptance criteria:**
  - [ ] Chat endpoint: 10 requests/minute per client IP
  - [ ] Admin endpoints: 5 requests/minute per client IP
  - [ ] Signal feed: 60 requests/minute per client IP
  - [ ] Returns 429 with `Retry-After` header when exceeded
  - [ ] `X-RateLimit-Remaining` header on all responses
- **Suggested library:** `slowapi` or custom `asyncio.Semaphore`-based middleware

### SEC-009: API versioning strategy `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** Current routes use `/api/v1/` prefix but there's no versioning middleware. Breaking changes will break existing clients.
- **Files to change:** `api/main.py`
- **Acceptance criteria:**
  - [ ] Version negotiation via URL path (`/api/v1/`, `/api/v2/`)
  - [ ] Deprecation headers (`Sunset`, `Deprecation`) for old versions
  - [ ] Version-specific routers that can coexist

### SEC-010: Secrets management for production `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** API keys stored in `.env` file. Production needs proper secrets management (GCP Secret Manager or AWS Secrets Manager).
- **Files to change:** `docker-compose.yml`, deployment scripts
- **Acceptance criteria:**
  - [ ] `ANTHROPIC_API_KEY` loaded from secret manager in production
  - [ ] `COHERE_API_KEY` loaded from secret manager in production
  - [ ] `DATABASE_URL` loaded from secret manager in production
  - [ ] `ADMIN_API_KEY` loaded from secret manager in production
  - [ ] `.env` file explicitly in `.gitignore`

### SEC-011: Add `/ready` readiness probe endpoint `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** Separate `/ready` endpoint that checks ALL dependencies (DB, cache, API keys). Different from `/health` (liveness).
- **Files to change:** `api/main.py`
- **Acceptance criteria:**
  - [ ] Checks: database pool, Redis cache (if present), Anthropic key set, Cohere key set
  - [ ] Returns 200 when all checks pass; 503 when any fail
  - [ ] Response: `{"ready": true/false, "checks": {"database": true, "cache": true, ...}}`
  - [ ] Kubernetes can use as readiness probe

### SEC-012: Audit logging for admin operations `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** All admin operations (scrape, process, data loads) should be logged with who/when/what for audit trail.
- **Files to create:** `api/audit.py`
- **Files to change:** `api/admin.py`, `api/intelligence/routes.py`
- **Acceptance criteria:**
  - [ ] Log table: `admin_audit_log (id, action, actor, params, timestamp, status)`
  - [ ] Every admin endpoint writes an audit record
  - [ ] `GET /api/v1/admin/audit` returns recent audit entries

---

## EPIC 2: Performance & Scalability (`PERF`)

### PERF-001: Configurable database connection pool `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 0
- **Docx ref:** Item 1.5 + Performance Table R1
- **Description:** Pool size configurable via `DB_POOL_MIN` and `DB_POOL_MAX` env vars. Default raised from max=10 to max=25. Docx notes: "min_size=2, max_size=10 → pool exhaustion at 20+ concurrent users."
- **Files changed:** `api/db.py`
- **Acceptance criteria:**
  - [x] `DB_POOL_MIN` env var (default: 2)
  - [x] `DB_POOL_MAX` env var (default: 25)
  - [x] Pool uses configurable values at startup

### PERF-002: Fix N+1 queries in neighborhood scorecards `✅ DONE`
- **Type:** Bug | **Priority:** P0-Blocker | **Sprint:** Tier 1
- **Docx ref:** Item 1.2 + Performance Table R2
- **Description:** `compare_neighborhoods()` executed 4 queries × N neighborhoods (up to 16 for 4 slugs). Now uses 3 batched queries regardless of count. Docx: "88 individual queries for 22 neighborhoods → collapse into single query with JOINs."
- **Files changed:** `api/intelligence/neighborhoods.py`
- **Acceptance criteria:**
  - [x] `compare_neighborhoods` uses `ANY($1)` for batch lookups
  - [x] 3 queries total: neighborhoods+composites, category scores, signal stats
  - [x] `get_neighborhood_scorecard` uses CTE (4 queries → 3)
  - [x] Extracted `_format_scorecard()` helper to eliminate code duplication

### PERF-003: Fix N+1 in `get_all_neighborhood_summaries` `✅ DONE`
- **Type:** Bug | **Priority:** P0-Blocker | **Sprint:** Tier 1
- **Description:** Already uses a single query with correlated subquery (fixed in prior session).
- **Files changed:** `api/intelligence/neighborhoods.py`
- **Acceptance criteria:**
  - [x] Single query with LEFT JOIN for all 22 neighborhoods
  - [x] Per-neighborhood `MAX(period_start)` subquery

### PERF-004: Add compound database indexes `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** Performance Table R4
- **Description:** Missing compound indexes cause sequential scans on most-common query patterns. Docx: "Add indexes: intelligence_signals(neighborhood, event_date), document_chunks(document_id, chunk_index)."
- **Files to change:** `db/007_intelligence_layer.sql` (or new migration `db/010_compound_indexes.sql`)
- **Acceptance criteria:**
  - [ ] `idx_signals_feed_combined ON intelligence_signals(neighborhood, signal_type, event_date DESC) WHERE event_date IS NOT NULL`
  - [ ] `idx_documents_unprocessed_batch ON documents(processed_at, id) WHERE processed_at IS NULL AND raw_text IS NOT NULL`
  - [ ] `idx_chunks_document_index ON document_chunks(document_id, chunk_index)`
  - [ ] `idx_documents_source_type_date ON documents(source_type, published_date DESC, source_url)`
  - [ ] `idx_scores_neighborhood_category ON neighborhood_scores(neighborhood_id, category, period_start DESC)`
  - [ ] EXPLAIN ANALYZE before/after showing index usage
- **Expected impact:** Signal feed queries 500ms → 50ms (10×)

### PERF-005: Redis caching layer `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Docx ref:** Item 2.1 + Performance Table R3
- **Description:** Add Redis for response caching. Docx: "TOA GeoJSON, scorecards, and opportunities regenerate every request." High-value cache targets: TOA GeoJSON (24hr TTL), neighborhood scorecards (1hr TTL), signal stats (5min TTL).
- **Files to create:** `api/cache.py`
- **Files to change:** `api/main.py` (lifespan), `docker-compose.yml` (add redis service)
- **Acceptance criteria:**
  - [ ] Redis 7 Alpine service in docker-compose with `maxmemory 500m`, `allkeys-lru` policy
  - [ ] `Cache` class with `get()`, `set()`, `delete()` methods
  - [ ] Graceful degradation: if Redis unavailable, skip cache (no errors)
  - [ ] Cache key pattern: `{entity}:{identifier}:{version}`
  - [ ] Cache invalidation on admin operations (scrape, process)
- **Cache targets:**
  - [ ] `GET /api/v1/toa/geojson` → TTL 24hr (static data, changes at most monthly)
  - [ ] `GET /api/v1/intel/neighborhoods/scorecards` → TTL 1hr (was 15min in docx, expanded since scores computed weekly)
  - [ ] `GET /api/v1/intel/stats` → TTL 5min
  - [ ] `GET /api/v1/intel/signals/geojson` → TTL 15min
  - [ ] `GET /api/v1/intel/opportunities` → TTL 5min

### PERF-006: Parallel chunk embedding with `asyncio.gather()` `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Item 3.3 (parallel document processing)
- **Description:** Currently embeds chunks serially per document. Need parallel batch inserts with `asyncio.Semaphore` for concurrency control. Docx: "asyncio.gather with semaphore-bounded concurrency (5–10 parallel documents)."
- **Files to change:** `api/intelligence/embeddings.py`
- **Acceptance criteria:**
  - [ ] `asyncio.Semaphore(10)` for max 10 concurrent DB inserts
  - [ ] `asyncio.Semaphore(3)` for max 3 concurrent Cohere API calls
  - [ ] Replace `asyncio.sleep(0.3)` blocking rate limit with semaphore
  - [ ] Error handling: partial failures logged, successful inserts counted
- **Expected impact:** 100 chunks: 10s → 1s (10× faster)

### PERF-007: Parallel LLM extraction with concurrency control `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Item 3.3 (parallel document processing)
- **Description:** `_background_process_task` forces `batch_size=1` for Claude extraction. Need parallel processing with semaphore.
- **Files to change:** `api/intelligence/routes.py` (lines 419-471)
- **Acceptance criteria:**
  - [ ] `asyncio.Semaphore(5)` for concurrent Cohere calls
  - [ ] `asyncio.Semaphore(3)` for concurrent Claude calls
  - [ ] Multiple documents processed in parallel (up to `batch_size` workers)
  - [ ] Per-document error isolation (one failure doesn't stop batch)
- **Expected impact:** 1000 chunks: 3000s → 300-600s (5-10× faster)

### PERF-008: Streaming GeoJSON responses `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** `/api/v1/intel/signals/geojson` loads entire FeatureCollection into memory. At 10K signals: 20MB payload, 1-2s serialization.
- **Files to change:** `api/intelligence/signals.py`, `api/intelligence/routes.py`
- **Acceptance criteria:**
  - [ ] New endpoint: `GET /api/v1/intel/signals/geojson/stream` (NDJSON)
  - [ ] Uses `StreamingResponse` with async cursor
  - [ ] Linear memory usage regardless of dataset size
  - [ ] Old endpoint remains for backward compatibility (with `limit=200` default)

### PERF-009: Response compression (gzip/brotli) `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** GeoJSON and signal feed responses are large JSON payloads. No compression configured.
- **Files to change:** `api/main.py`
- **Acceptance criteria:**
  - [ ] `GZipMiddleware` with `minimum_size=1000` (compress responses >1KB)
  - [ ] Brotli support via `BrotliMiddleware` if client supports it
  - [ ] Verify compression ratio on `/api/v1/toa/geojson` (expect 5-10× smaller)

### PERF-010: Prepared statements for dynamic signal queries `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** `signals.py` uses string formatting for dynamic WHERE clauses. PostgreSQL re-parses every time.
- **Files to change:** `api/intelligence/signals.py`
- **Acceptance criteria:**
  - [ ] Severity filtering uses parameterized integer values instead of inline CASE
  - [ ] Add `severity_order` column to `intelligence_signals` table (integer 0-4)
  - [ ] Or: create `severity_enum` type in PostgreSQL with proper ordering
  - [ ] Query plan caching works (verify with `EXPLAIN`)

### PERF-011: Materialized view for neighborhood composite scores `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Pre-compute neighborhood scores into a materialized view, refresh on data updates.
- **Files to change:** `db/009_neighborhood_scorecards.sql`
- **Acceptance criteria:**
  - [ ] `CREATE MATERIALIZED VIEW mv_neighborhood_scorecards AS SELECT ...`
  - [ ] Includes: name, slug, overall_score, rank, category_scores JSONB, top/bottom categories
  - [ ] `REFRESH MATERIALIZED VIEW CONCURRENTLY` after score recomputation
  - [ ] Scorecard endpoints read from materialized view instead of joining 3 tables

### PERF-012: Frontend pagination enforcement `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** Frontend `getSignalFeed()` has no `maxResults` protection. A missing filter could request all signals.
- **Files to change:** `frontend/src/lib/intel-api.ts`
- **Acceptance criteria:**
  - [ ] Default `limit=20` always sent as query param
  - [ ] Maximum `limit=100` enforced client-side
  - [ ] Infinite scroll or "Load more" pattern instead of loading all data

### PERF-013: Connection pool monitoring `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** No visibility into pool utilization. Need metrics for pool size, active connections, wait time.
- **Files to change:** `api/db.py`, `api/main.py`
- **Acceptance criteria:**
  - [ ] `GET /api/v1/admin/pool-stats` returns pool size, free connections, min/max
  - [ ] Log warning when pool utilization >80%
  - [ ] Prometheus metric: `db_pool_active_connections`, `db_pool_waiting_queries`

### PERF-014: PgBouncer connection pooling proxy `📋 TODO`
- **Type:** Story | **Priority:** P3-Low | **Sprint:** Tier 5
- **Description:** At 100× scale, direct connection pooling is insufficient. PgBouncer sits between API and PostgreSQL for efficient connection sharing.
- **Files to change:** `docker-compose.yml`, deployment configs
- **Acceptance criteria:**
  - [ ] PgBouncer service in docker-compose
  - [ ] Transaction-level pooling mode
  - [ ] API connects to PgBouncer, not directly to PostgreSQL
  - [ ] Supports 100+ concurrent connections with 25 backend connections

### PERF-015: Background job queue (Celery + Redis) `📋 TODO`
- **Type:** Story | **Priority:** P3-Low | **Sprint:** Tier 5
- **Description:** `BackgroundTasks` don't survive server restart. Document processing needs persistent job queue.
- **Files to create:** `api/tasks/worker.py`, `api/tasks/processing.py`
- **Acceptance criteria:**
  - [ ] Celery worker with Redis broker
  - [ ] Scraping and processing tasks as Celery tasks
  - [ ] Job status tracking (`GET /api/v1/admin/jobs/{job_id}`)
  - [ ] Retry logic with exponential backoff
  - [ ] Dead letter queue for failed tasks

### PERF-016: Read replicas for reporting queries `🧊 DEFERRED`
- **Type:** Story | **Priority:** P3-Low | **Sprint:** Tier 5+
- **Description:** Separate read replica for heavy reporting queries (scorecards, stats) to avoid impacting write path.
- **Rationale for deferral:** Not needed until sustained 100+ concurrent users

### PERF-017: Batch Cohere embedding API calls (96 texts/call) `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Performance Table R6 — "Batch embedding API calls (Cohere allows 96 texts per call) instead of one-at-a-time" + Item 4.5
- **Description:** Currently sends individual Cohere embed requests per chunk. Cohere's embed endpoint supports up to 96 texts in a single call. Batch reduces API round-trips by 96×.
- **Files to change:** `api/intelligence/embeddings.py`
- **Acceptance criteria:**
  - [ ] Group chunks into batches of up to 96 for single Cohere API call
  - [ ] Handle partial batch failures (some chunks fail, others succeed)
  - [ ] Maintain embedding quality (same model/parameters as individual calls)
  - [ ] Rate limit: max 3 concurrent batch calls via semaphore
  - [ ] Log: "Embedded {n} chunks in {batches} batches ({elapsed}s)"
- **Expected impact:** 1000 chunks: ~1000 API calls → ~11 API calls (90× fewer)

### PERF-018: Cursor-based pagination on opportunity endpoints `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Performance Table R7 — "Add cursor-based pagination instead of LIMIT/OFFSET for large result sets"
- **Description:** Current LIMIT/OFFSET pagination degrades at high offsets (PostgreSQL scans and discards all skipped rows). Opportunities and signal endpoints need cursor-based pagination.
- **Files to change:** `api/intelligence/signals.py`, `api/intelligence/routes.py`
- **Acceptance criteria:**
  - [ ] Replace OFFSET with keyset pagination: `WHERE (event_date, id) < ($1, $2) ORDER BY event_date DESC, id DESC LIMIT $3`
  - [ ] Response includes `next_cursor` (base64-encoded event_date+id) and `has_more` boolean
  - [ ] Frontend sends `cursor` query parameter instead of `page`
  - [ ] Backward compatible: `page` parameter still works but logs deprecation warning
- **Expected impact:** Page 100 of results: O(n) → O(1) query time

---

## EPIC 3: Test Coverage & Quality (`TEST`)

### TEST-001: Entitlement engine unit tests `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 0
- **Docx ref:** Item 0.3 — "Core business logic is completely untested. Any bug here is a liability."
- **Description:** 35 tests covering `compute_entitlement`, value estimation, hidden costs integration, validation engine.
- **Files created:** `tests/test_entitlement.py` (953 lines)
- **Acceptance criteria:**
  - [x] Tests: single TOA tier, multiple tiers, outside TOA, zoning exceeds Bill 47
  - [x] Tests: value estimation with asking price, assessed-only fallback, zero lot area
  - [x] Tests: hidden costs integration and validation engine (grade A/F, execution difficulty)
  - [x] Tests: three-scenario pro forma (bull/base/bear), gap analysis
  - [x] Tests: neighborhood economics (premium/value/neutral/unknown)

### TEST-002: Hidden costs estimator tests `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 0
- **Docx ref:** Item 2.4 (partial) — "Hidden cost estimation untested. Risk of incorrect dollar amounts."
- **Description:** 65 tests covering all 6 hidden cost functions with edge cases.
- **Files created:** `tests/test_hidden_costs.py` (727 lines)
- **Acceptance criteria:**
  - [x] Demolition: asbestos premiums, low value, large lots, clamping
  - [x] Environmental: gas station ($500K), dry cleaner ($350K), auto ($200K), partial matches, precedence
  - [x] Tenant displacement: linear scaling, zero/negative
  - [x] Rezoning: CD-1 ($250K), complex ($200K), standard ($0)
  - [x] Soft soil: all tier thresholds, all known soft zones
  - [x] Total aggregation

### TEST-003: Admin security tests `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 0
- **Docx ref:** Item 2.4 (partial) — "Admin routes completely untested"
- **Description:** 30 tests for auth module, security headers, admin router structure.
- **Files created:** `tests/test_admin_security.py` (482 lines)
- **Acceptance criteria:**
  - [x] Router structure verification (prefix, tags, dependencies)
  - [x] Auth readiness documentation
  - [x] Security header requirements
  - [x] Admin helper function tests

### TEST-004: Existing test suites maintained `✅ DONE`
- **Type:** Maintenance | **Priority:** P0-Blocker | **Sprint:** Ongoing
- **Description:** All 275 pre-existing tests continue to pass after Tier 0+1 changes.
- **Test counts (405 total):**
  - [x] test_models.py — 41 tests
  - [x] test_chunker.py — 44 tests
  - [x] test_extractor.py — 18 tests
  - [x] test_scrapers.py — 23 tests
  - [x] test_chat.py — 18 tests
  - [x] test_signals.py — 31 tests (incl. GeoJSON)
  - [x] test_routes.py — 38 tests
  - [x] test_e2e_pipeline.py — 11 tests
  - [x] test_parser.py — 8 tests
  - [x] test_scraper_news.py — 22 tests
  - [x] test_neighborhoods.py — 21 tests
  - [x] test_entitlement.py — 35 tests (NEW)
  - [x] test_hidden_costs.py — 65 tests (NEW)
  - [x] test_admin_security.py — 30 tests (NEW)

### TEST-005: Playwright E2E test suite `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Phase 4.5
- **Description:** 21 Playwright tests covering app shell, intelligence tab, map, API health, full user journey.
- **Files:** `frontend/e2e/*.spec.ts`
- **Acceptance criteria:**
  - [x] Chrome + Mobile Chrome (Pixel 5) configurations
  - [x] CI-optimized: retries, parallel workers, screenshots on failure

### TEST-006: Database integration tests `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Docx ref:** Item 1.3 + Testing Table R2 — "All DB interactions are mocked. Must validate actual SQL against real PostGIS."
- **Description:** Current tests all use mocks. Need integration tests that run against real PostgreSQL (Docker test container).
- **Files to create:** `tests/test_db_integration.py`
- **Acceptance criteria:**
  - [ ] Use `pytest-docker` or `testcontainers-python` for ephemeral Postgres
  - [ ] Test: connection pool initialization and lifecycle
  - [ ] Test: migration scripts execute successfully (001-009)
  - [ ] Test: parcel spatial queries return correct results
  - [ ] Test: intelligence signal CRUD with real asyncpg
  - [ ] Test: neighborhood scorecard queries return expected structure
  - [ ] Test: PostGIS spatial operations (ST_Intersects, ST_DWithin) on real geometry
  - [ ] Test: pgvector similarity search with real embeddings
  - [ ] Separate pytest marker: `@pytest.mark.integration`

### TEST-007: Load testing with k6 `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** No load testing exists. Need to validate performance at 10×, 100× scale.
- **Files to create:** `tests/load/k6_scenarios.js`, `tests/load/run_load_tests.sh`
- **Acceptance criteria:**
  - [ ] Scenario 1: Ramp 0→100 users over 5min, hold 10min, ramp down
  - [ ] Scenario 2: Burst — 200 concurrent requests to `/api/v1/intel/signals`
  - [ ] Scenario 3: Chat stress — 50 concurrent `/api/v1/intel/chat` requests
  - [ ] Pass criteria: p95 < 5s for chat, p95 < 500ms for signals, 0% error rate
  - [ ] Results captured in `tests/load/results/` for comparison

### TEST-008: Validation engine regression tests `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** `validation.py` is 1,156 lines with 21+ risk checks but limited unit test coverage. Known bug: pre-1960 asbestos check (40%) never triggers because pre-1980 check (25%) catches it first.
- **Files to create:** `tests/test_validation.py`
- **Acceptance criteria:**
  - [ ] Test each of 21 risk checks independently with parametrized data
  - [ ] Test grade computation (A-F) boundary conditions
  - [ ] Test three-scenario pro forma (bull/base/bear) with realistic inputs
  - [ ] Fix and test asbestos premium ordering bug in `hidden_costs.py`
  - [ ] Test execution difficulty scoring (1-10 scale)
  - [ ] Test gap analysis narrative generation

### TEST-009: Asbestos premium ordering bug fix `📋 TODO`
- **Type:** Bug | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** In `hidden_costs.py`, pre-1960 asbestos check (40% premium) never triggers because pre-1980 check (25%) catches all buildings older than 1960 first.
- **Files to change:** `api/hidden_costs.py`
- **Acceptance criteria:**
  - [ ] Check pre-1960 BEFORE pre-1980 (or use elif chain with most restrictive first)
  - [ ] Unit test: building from 1955 gets 40% premium (not 25%)
  - [ ] Unit test: building from 1975 gets 25% premium
  - [ ] Unit test: building from 1985 gets 0% premium

### TEST-010: Contract tests for API endpoints `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Item 2.3 + Testing Table R3 — "Test every endpoint for correct status codes, response schema validation, error format."
- **Description:** Ensure API response schemas don't break frontend TypeScript types.
- **Files to create:** `tests/test_api_contracts.py`
- **Acceptance criteria:**
  - [ ] For each endpoint: verify response matches Pydantic model
  - [ ] Generate OpenAPI spec and diff against saved version
  - [ ] Alert on breaking changes (removed fields, type changes)
  - [ ] Verify error response format consistency (all errors return `{"detail": "..."}`)
  - [ ] Parameter validation tests (invalid types, out-of-range values)

### TEST-011: CI pipeline running all tests on push `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** Tests should run automatically on every push to main and on PRs.
- **Files to create:** `.github/workflows/test.yml`
- **Acceptance criteria:**
  - [ ] Trigger: push to main, PR to main
  - [ ] Job 1: `pytest tests/ -v` (unit tests)
  - [ ] Job 2: Playwright E2E (with Docker services)
  - [ ] Pass/fail status on GitHub PR
  - [ ] Badge in README.md

### TEST-012: E2E pipeline validation test (full flow) `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** Item 1.4 + Testing Table R7 — "Full flow: ingest real PDF → parse → chunk → embed → extract signals → store → chat query → verify citation references correct document."
- **Description:** The complete intelligence flow from document ingestion through to a chat response citing that document has NEVER been validated end-to-end. Docx calls this "the highest-risk gap because the intelligence chat is the primary differentiator."
- **Files to create:** `tests/test_full_pipeline.py`
- **Acceptance criteria:**
  - [ ] Ingest a real test PDF document (council minutes or rezoning application)
  - [ ] Parse → chunk → verify chunk count and quality
  - [ ] Embed → verify vectors stored in pgvector with correct dimensions
  - [ ] Extract → verify signals created with correct types, geocoding, neighborhoods
  - [ ] Chat query → verify response cites the ingested document
  - [ ] Citation accuracy: referenced text exists in source document
  - [ ] Requires real PostGIS + pgvector + Cohere API (mark `@pytest.mark.e2e_pipeline`)
  - [ ] Estimated effort: 4 days (docx estimate)

### TEST-013: External service failure tests `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Item 3.5 + Testing Table R6 — "Mock Cohere/Claude API failures. Verify graceful degradation."
- **Description:** No tests for Cohere API failures, Anthropic API timeout, or degraded-mode behavior. System should degrade gracefully, not crash.
- **Files to create:** `tests/test_external_failures.py`
- **Acceptance criteria:**
  - [ ] Cohere embed API timeout → return error without crashing, log warning
  - [ ] Cohere embed API 429 (rate limit) → back off and retry (up to 3 attempts)
  - [ ] Anthropic chat API timeout → return "service unavailable" to user with retry guidance
  - [ ] Anthropic chat API 500 → return degraded response ("unable to process, try again")
  - [ ] Cohere reranker failure → fall back to RRF-only ranking (no rerank)
  - [ ] All external calls have configurable timeout (default 30s for chat, 10s for embed)
  - [ ] User-facing error messages are helpful, not stack traces

### TEST-014: Frontend E2E hardening `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Item 3.6 + Testing Table R8 — "Add strict assertions: verify parcel data values, scorecard numbers, map marker counts. Current tests are too loose."
- **Description:** Existing Playwright tests verify page loads but don't assert on data correctness. Need strict value assertions.
- **Files to change:** `frontend/e2e/*.spec.ts`
- **Acceptance criteria:**
  - [ ] Assert: parcel popup shows correct zoning, entitlement, grade (not just "popup appeared")
  - [ ] Assert: scorecard shows numeric scores within expected ranges
  - [ ] Assert: signal feed items have required fields (date, type, severity, text)
  - [ ] Assert: map marker count matches API response count
  - [ ] Assert: chat response contains citation references
  - [ ] Visual regression: screenshot comparison for key views
  - [ ] Performance assertion: page load <3s, API responses <1s

---

## EPIC 4: Data Pipeline & Seeding (`DATA`)

### DATA-001: Seed production data — run scrapers against live sources `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** Item 1.1 — "Intelligence layer has zero production documents. Chat returns nothing useful. Must seed 200+ real Vancouver council/rezoning docs."
- **Description:** Database has 92K parcels but zero intelligence documents. Need to scrape real Vancouver government documents. Docx: "Intelligence layer is demo-only without real data."
- **Existing infrastructure:** Scrapers built (`scraper_council.py`, `scraper_rezoning.py`, `scraper_dpb.py`, `scraper_news.py`)
- **Acceptance criteria:**
  - [ ] Scrape 100+ council minutes (6 months lookback)
  - [ ] Scrape all active rezoning applications
  - [ ] Scrape DPB minutes (12 months)
  - [ ] Scrape 6 RSS news feeds
  - [ ] Verify: 100+ documents in `documents` table
  - [ ] Verify: document sizes and text quality
- **Estimated effort:** 6 days (docx estimate)

### DATA-002: Process scraped documents through AI pipeline `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Depends on:** DATA-001
- **Description:** Run chunking → embedding → extraction pipeline on all scraped documents.
- **Acceptance criteria:**
  - [ ] Process all unprocessed documents
  - [ ] Generate 500+ intelligence signals
  - [ ] Verify: geocoding accuracy >80%
  - [ ] Verify: signal type distribution across all categories
  - [ ] Verify: chat returns grounded answers for test queries ("What did council decide about...?")

### DATA-003: Scraper deduplication logic `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** Open data scrapers have no deduplication. Re-running a scraper creates duplicate entries.
- **Files to change:** `api/intelligence/scraper_opendata.py`
- **Acceptance criteria:**
  - [ ] Check `source_url` uniqueness before inserting documents
  - [ ] Upsert metrics (ON CONFLICT UPDATE) instead of blind INSERT
  - [ ] Log: "X new, Y duplicates skipped"
  - [ ] Index: `CREATE UNIQUE INDEX ON documents(source_url)`

### DATA-004: Automated daily scraping cron `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Item 2.5 — "Cron-based daily/weekly scraping with deduplication."
- **Description:** Scrapers must run automatically, not manually via admin endpoints. Docx: "One-time scrape is not a product. Need daily/weekly automated ingestion with freshness guarantees."
- **Files to create:** `scripts/cron_scrape.py`, crontab or APScheduler config
- **Acceptance criteria:**
  - [ ] Council minutes: weekly (every Monday 6am)
  - [ ] News feeds: daily (every day 8am)
  - [ ] Open data metrics: weekly (every Sunday midnight)
  - [ ] Processing: daily after scraping completes
  - [ ] Email/Slack notification on failure
  - [ ] Data freshness indicator: `GET /api/v1/admin/data-freshness` returns last scrape timestamps

### DATA-005: Geocoding accuracy improvement `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** Current geocoding: fuzzy match against parcels table + BC Open Data fallback. Accuracy unknown.
- **Files to change:** `api/intelligence/extractor.py`
- **Acceptance criteria:**
  - [ ] Measure: geocoding success rate on 100 extracted signals
  - [ ] Add: street address normalization (abbrev expansion: "St" → "Street")
  - [ ] Add: neighborhood assignment via PostGIS `ST_Contains` (not bounding box)
  - [ ] Fallback: if geocoding fails, assign to neighborhood centroid

### DATA-006: Seed E2E test data refresh `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Phase 4.5
- **Description:** `db/008_e2e_seed.sql` provides 5 documents, 6 chunks, 5 signals for E2E testing.
- **Acceptance criteria:**
  - [x] Idempotent (ON CONFLICT DO NOTHING)
  - [x] Covers 3 neighborhoods: Mount Pleasant, Grandview-Woodland, Renfrew-Collingwood
  - [x] `scripts/seed_e2e.sh` runs seed SQL

### DATA-007: Open data neighborhood metrics refresh pipeline `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Phase 5
- **Description:** `scraper_opendata.py` scrapes VPD crime, CoV parks, TransLink transit, CoV permits, CoV property tax.
- **Acceptance criteria:**
  - [x] 5 data source scrapers
  - [x] Metrics stored in `neighborhood_metrics` table
  - [x] Scores computed and stored in `neighborhood_scores` table
  - [x] Composite scores computed in `neighborhood_composite_scores` table

### DATA-008: VSB school data scraper `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Schools category in scorecards lacks real data. Need VSB enrolment/capacity data.
- **Files to create:** `api/intelligence/scraper_schools.py`
- **Acceptance criteria:**
  - [ ] Scrape VSB Open Data for enrolment/capacity per school
  - [ ] Map schools to neighborhoods via school catchment GeoJSON
  - [ ] Compute school quality metric: capacity utilization + student-to-teacher ratio
  - [ ] Store in `neighborhood_metrics` with `category='schools'`

### DATA-009: Comparable sales data pipeline `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** Item 2.2 + Business Table R2 — "Colin's #1 question: 'Is this price fair?' No market comps exist. Need 12 months of transaction data."
- **Description:** The review identified comparable sales as CRITICAL for user trust. Currently no market transaction data exists in the platform. Need to source and load residential land transaction data for Vancouver.
- **Files to create:** `api/intelligence/scraper_sales.py`, `db/011_comparable_sales.sql`
- **Possible data sources:**
  - BC Assessment Authority (public property assessments)
  - BC Land Title Survey Authority (title transfer records)
  - MLS data (requires partnership with brokerage)
  - CoV property tax data (assessed values as proxy)
- **Acceptance criteria:**
  - [ ] `comparable_sales` table: `(id, address, pid, sale_price, sale_date, lot_area, zoning, building_type, geom)`
  - [ ] 12+ months of residential land sales loaded
  - [ ] Spatial query: "Find 5 nearest comparable sales within 500m, same zoning category"
  - [ ] Metric: price per sqft for lot, price per buildable sqft
  - [ ] API endpoint: `GET /api/v1/parcels/{pid}/comparables` → returns 3-5 nearest sales
  - [ ] Pro forma uses comparable sale data for revenue validation
- **Note:** This may require partnership with a data provider or manual data collection initially. Even BC Assessment assessed values serve as a baseline until transaction data available.

---

## EPIC 5: Validation Engine V2 (`VAL`)

> **Note on docx conflicts:** VanCity_Lens_Review_Plan.docx Section 7 recommends deferring view cones ("Add only after validating 20%+ parcels affected") and non-market housing ("Year 2"). VALIDATION_V2_PLAN.md flags view cones as P0 deal-killer and NMH as P1. This plan follows VALIDATION_V2_PLAN.md priorities because: (a) view cones fundamentally change entitled height, making all pro formas for affected parcels misleading; (b) the implementation effort is low (2 hours per docx). However, both items include a data validation step to confirm real-world impact before full rollout.

### VAL-001: View cone intersection (deal-killer) `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx conflict:** Docx Section 7 says "defer until 20%+ parcels affected." VALIDATION_V2 says P0 deal-killer. Resolution: implement but **validate impact** — if <5% of parcels affected, deprioritize UI treatment.
- **Dataset:** `view-cones` (23 protected view corridors from CoV Open Data)
- **Files to create:** `db/010_v2_view_cones.sql`
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [ ] Load 23 view cones into `view_cones` table with PostGIS geometry
  - [ ] `ST_Intersects(parcel.geom, view_cone.geom)` check in validation
  - [ ] If intersecting: cap entitled height to view cone max height
  - [ ] Recalculate buildable sqft using capped height
  - [ ] Flag as RED risk: "View cone restriction — entitled height capped"
  - [ ] Admin endpoint: `POST /api/v1/admin/load-view-cones`
  - [ ] **Validation step:** After loading, count how many of 92K parcels intersect. Log result.

### VAL-002: Neighborhood revenue adjustment `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** VALIDATION_V2_PLAN.md item 17 — "flat pricing is misleading"
- **Description:** Pro forma uses flat revenue/sqft ($1,100/$950/$850). Kitsilano sells at $1,300/sqft while Renfrew-Collingwood at $850/sqft. This alone can flip a grade.
- **Files to change:** `api/neighborhood_economics.py`, `api/validation.py`
- **Multiplier table:**
  - West End / Coal Harbour: 1.25 (premium waterfront)
  - Kitsilano / Point Grey: 1.20 (established west side)
  - Mount Pleasant / Cambie: 1.10 (trendy, transit-rich)
  - Marpole / Oakridge: 1.05 (emerging, new transit)
  - Renfrew / Killarney: 0.90 (east side discount)
  - Southeast Van: 0.85 (value market)
- **Acceptance criteria:**
  - [ ] Neighborhood multiplier table (22 areas × multiplier 0.85-1.25)
  - [ ] Revenue per sqft = base × neighborhood multiplier
  - [ ] Pro forma scenarios use adjusted revenue
  - [ ] UI shows neighborhood adjustment in pro forma breakdown
  - [ ] Unit tests: Kitsilano A → Renfrew-Collingwood C for same parcel

### VAL-003: Holding cost / time value of money `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** VALIDATION_V2_PLAN.md item 18 — "ignoring time value is amateur"
- **Description:** Pro forma ignores 18-36 month rezoning timeline. Developer holding $3M at 6% for 2 years burns $360K.
- **Files to create:** `api/holding_costs.py`
- **Files to change:** `api/validation.py`
- **Holding periods by tier:**
  - Tier 1 concrete: 30 months (rezoning + permit + preconstruction)
  - Tier 2 midrise: 24 months
  - Tier 3 lowrise: 18 months
- **Acceptance criteria:**
  - [ ] Cost = `asking_price × interest_rate × holding_months / 12`
  - [ ] Interest rate: configurable (default 6.5% — current Canadian prime + spread)
  - [ ] Deducted from pro forma as a line item
  - [ ] Unit tests: $3M × 6.5% × 30/12 = $487,500

### VAL-004: Protected tree count `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** Vancouver tree protection bylaw: trees >20cm diameter need permits. Large trees (>50cm) cost $5K-25K each.
- **Dataset:** `public-trees` (185K trees with diameter, species, location)
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [ ] Load trees >30cm into `protected_trees` table
  - [ ] Count trees within 15m of parcel centroid
  - [ ] YELLOW: 1-3 large trees | RED: 4+ large trees
  - [ ] Cost impact: $5K-25K per tree in hidden costs
  - [ ] Admin endpoint: `POST /api/v1/admin/load-trees`

### VAL-005: Building permit activity (competing supply) `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** Multiple large permits ($5M+) within 500m in last 2 years = supply saturation risk.
- **Dataset:** `issued-building-permits` (50K+ permits)
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [ ] Count permits within 500m where `projectvalue > 5_000_000` and issued in last 2 years
  - [ ] YELLOW: 3-5 competing projects | RED: 6+ competing projects
  - [ ] Include in risk assessment section
  - [ ] Data loaded from CoV Open Data API

### VAL-006: Non-market housing proximity `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx conflict:** Docx Section 7 says "Year 2 — interesting for policy analysis but not for investment use case." VALIDATION_V2 says P1 because Rental Replacement Policy is a real cost ($50K-150K/unit). Resolution: implement as risk flag but not in the initial free-tier validation. Gate behind Pro subscription.
- **Dataset:** `non-market-housing` (641 locations)
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [ ] Load NMH into `non_market_housing` table
  - [ ] `ST_DWithin(parcel.geom, nmh.geom, 100m)`
  - [ ] YELLOW: within 100m | RED: on the parcel itself
  - [ ] Cost impact: $50K-150K per unit of rental replacement

### VAL-007: CD-1 zoning detection `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** CD-1 zones have site-specific bylaws. Standard Bill 47 entitlement calculations may not apply.
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [ ] Check if parcel falls within `zoning_category = 'CD-1'` zone
  - [ ] YELLOW flag: "CD-1 zone — requires manual review of site-specific bylaw"
  - [ ] Link to specific CD-1 bylaw number for manual review
  - [ ] Note: already partially detected in `hidden_costs.py` rezoning cost

### VAL-008: Building age assessment `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Dataset:** `property-tax-report` (`year_built` field)
- **Files to change:** `api/validation.py`, parcel data model
- **Acceptance criteria:**
  - [ ] Fetch `year_built` from property tax data
  - [ ] GREEN: >50 years (natural teardown) | YELLOW: 15-50 years (moderate improvement value) | RED: <15 years (unlikely teardown)
  - [ ] Add context alongside existing land-to-improvement ratio

### VAL-009: Community opposition score `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Docx ref:** Item 4.2
- **Description:** Composite risk score based on proximity to NIMBY triggers: community gardens, heritage sites, social housing.
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [ ] Load community gardens (170 locations) into PostGIS table
  - [ ] Composite score: community garden <200m + heritage <100m + NMH <100m
  - [ ] YELLOW: 1 factor | RED: 3+ factors ("hot zone")
  - [ ] Add to risk assessment narrative

### VAL-010: Title due diligence checklist `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Generate per-parcel "Title Due Diligence Checklist" with items to verify at LTSA.
- **Files to change:** `api/validation.py`, `api/models.py`
- **Acceptance criteria:**
  - [ ] Checklist items: CPL, restrictive covenants, SRW, mortgages, strata status
  - [ ] Each item has: description, LTSA lookup URL, risk level
  - [ ] Included in validation response as `due_diligence_checklist` field
  - [ ] Frontend: collapsible "Due Diligence" section in popup

### VAL-011: Contamination risk indicator `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Dataset:** BC Data Catalogue (`environmental-remediation-sites`)
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [ ] Download BC contaminated sites KML/CSV
  - [ ] Load into PostGIS table
  - [ ] RED: confirmed contaminated site on parcel | YELLOW: within 200m
  - [ ] Cost impact: $500K-5M+ (Environmental Site Assessment required)

### VAL-012: Multi-axis grading system (Economics/Friction/Confidence) `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** Replace single A-F grade with 3-axis assessment.
- **Files to change:** `api/models.py`, `api/validation.py`, frontend popup
- **Acceptance criteria:**
  - [ ] **Economics** (A-F): pro forma alpha, price/buildable sqft, neighborhood-adjusted revenue
  - [ ] **Friction** (Low/Med/High): heritage, view cones, trees, CD-1, easements, contamination, opposition
  - [ ] **Confidence** (★☆☆ to ★★★): % of checks returning data vs "unknown"
  - [ ] Single-letter grade stays as headline
  - [ ] Example: `Economics: A | Friction: Low | Confidence: ★★★` → "Strong buy — clean path"
  - [ ] Example: `Economics: A | Friction: High | Confidence: ★★☆` → "High alpha but significant obstacles"

### VAL-013: Validation V2 migration script `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Files to create:** `db/010_v2_risk_layers_extended.sql`
- **Acceptance criteria:**
  - [ ] `view_cones` table (23 records expected)
  - [ ] `protected_trees` table (filtered >30cm diameter)
  - [ ] `non_market_housing` table (641 records expected)
  - [ ] `community_gardens` table (170 records expected)
  - [ ] `ALTER TABLE parcels ADD COLUMN year_built INT, geo_local_area TEXT`
  - [ ] Spatial indexes on all geometry columns

### VAL-014: Admin endpoints for V2 data loading `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Files to change:** `api/admin.py`
- **Acceptance criteria:**
  - [ ] `POST /api/v1/admin/load-view-cones` — from `view-cones` dataset
  - [ ] `POST /api/v1/admin/load-trees` — from `public-trees` (filter diameter >30cm)
  - [ ] `POST /api/v1/admin/load-non-market-housing` — from `non-market-housing`
  - [ ] `POST /api/v1/admin/load-community-gardens` — from `community-gardens-and-food-trees`
  - [ ] `POST /api/v1/admin/load-year-built` — from `property-tax-report`
  - [ ] All endpoints auth-protected via `require_admin`

---

## EPIC 6: Intelligence Layer (`INTEL`)

### INTEL-001: Document ingestion pipeline `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Phase 1
- **Files:** `scraper_council.py`, `scraper_rezoning.py`, `scraper_dpb.py`, `scraper_news.py`, `chunker.py`, `embeddings.py`, `extractor.py`

### INTEL-002: Hybrid search (dense + BM25 + RRF + rerank) `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Phase 2
- **Files:** `embeddings.py`, `chat.py`

### INTEL-003: RAG chat interface `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Phase 3
- **Files:** `chat.py`, `routes.py`, `IntelPage.tsx`

### INTEL-004: Signal feed with filtering `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Phase 3
- **Files:** `signals.py`, `routes.py`

### INTEL-005: Map-intelligence bridge `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Phase 4
- **Files:** `MapView.tsx`, `signals.py`

### INTEL-006: Alert system with watchlist `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 4
- **Description:** Colin marks neighborhoods/addresses to monitor. System generates alerts when new signals match watchlist.
- **Files to create:** `api/intelligence/alerts.py`, `api/intelligence/watchlist.py`
- **Acceptance criteria:**
  - [ ] `POST /api/v1/watchlist` — add address/neighborhood to watchlist
  - [ ] `GET /api/v1/watchlist` — list watched items
  - [ ] `DELETE /api/v1/watchlist/{id}` — remove item
  - [ ] `GET /api/v1/alerts` — "3 new signals since your last visit"
  - [ ] Diff engine: compare new scrape results vs previous
  - [ ] Alert generation: new signals matching watchlist criteria
  - [ ] In-app notification feed

### INTEL-007: Weekly digest generator `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Docx ref:** Item 4.4
- **Description:** Automated weekly summary of intelligence signals by neighborhood.
- **Files to create:** `api/intelligence/digest.py`, `scripts/generate_digest.py`
- **Acceptance criteria:**
  - [ ] Cron job: every Monday 8am
  - [ ] Aggregate week's signals by neighborhood
  - [ ] "Top 10 signals this week" + neighborhood summaries
  - [ ] Output: HTML email or downloadable PDF
  - [ ] Delivery: SendGrid/SES integration (stretch)

### INTEL-008: Chat session persistence and history `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Chat sessions are created but history isn't loaded on page refresh.
- **Files to change:** `api/intelligence/chat.py`, `frontend/src/components/IntelPage.tsx`
- **Acceptance criteria:**
  - [ ] `GET /api/v1/intel/chat/sessions` — list user's sessions
  - [ ] `GET /api/v1/intel/chat/sessions/{id}/messages` — load session history
  - [ ] Frontend: session selector dropdown
  - [ ] Previous messages shown when session loaded

### INTEL-009: Proactive opportunity alerts `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Description:** System-generated alerts: "3 adjacent RS-1 lots near newly approved rezoning — possible assembly."
- **Files to create:** `api/intelligence/opportunities.py`
- **Acceptance criteria:**
  - [ ] Detect: new rezoning approval signal near RS-1 parcels
  - [ ] Detect: council vote outcome on watched area
  - [ ] Detect: price drops on parcels in hot zones
  - [ ] Generate opportunity alert with action recommendation
  - [ ] Push to alert feed

### INTEL-010: Supply pipeline tracking `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Docx ref:** Item 4.3 + Business Table R7 — "Answer: 'How many units are under construction in this neighborhood?' Market saturation check."
- **Description:** Track active development projects by neighborhood. Show competing supply that could affect pre-sale absorption and pricing.
- **Files to create:** `api/intelligence/supply_pipeline.py`
- **Acceptance criteria:**
  - [ ] Aggregate active building permits ($5M+) by neighborhood
  - [ ] Track: project count, total estimated units, total project value
  - [ ] API endpoint: `GET /api/v1/intel/neighborhoods/{slug}/pipeline` → active projects
  - [ ] Include in neighborhood scorecard as "Development Pipeline" section
  - [ ] Historical tracking: show pipeline growth over time (monthly snapshots)
  - [ ] Cross-reference with VAL-005 (building permit activity check)

---

## EPIC 7: Frontend & UX (`FE`)

### FE-001: Tab navigation (Map / Intelligence) `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Phase 3
- **Files:** `frontend/src/app/page.tsx`

### FE-002: Intelligence page (Chat + Signal Feed) `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Phase 3
- **Files:** `frontend/src/components/IntelPage.tsx`

### FE-003: Map signal overlay + popup bridge `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Phase 4
- **Files:** `frontend/src/components/MapView.tsx`

### FE-004: Neighborhood scorecards page `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Phase 5
- **Files:** `frontend/src/components/NeighborhoodPage.tsx`

### FE-005: Neighborhood comparison mode `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Phase 5

### FE-006: Friction meter + Confidence stars in popup `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Depends on:** VAL-012
- **Description:** Show multi-axis grade (Economics / Friction / Confidence) in parcel popup.
- **Files to change:** `frontend/src/components/MapView.tsx`
- **Acceptance criteria:**
  - [ ] Friction meter: Low (green bar) / Med (yellow bar) / High (red bar)
  - [ ] Confidence stars: ★☆☆ to ★★★
  - [ ] Color-coded pro forma if neighborhood adjustment applied
  - [ ] Holding cost as line item in pro forma section

### FE-007: Due diligence checklist in popup `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Depends on:** VAL-010
- **Description:** Collapsible "Due Diligence Checklist" section at bottom of parcel popup.
- **Files to change:** `frontend/src/components/MapView.tsx`
- **Acceptance criteria:**
  - [ ] Collapsible section with title checklist items
  - [ ] Each item: description + risk level badge + LTSA lookup link
  - [ ] Default collapsed (expandable)

### FE-008: Dark mode refinement `📋 TODO`
- **Type:** Story | **Priority:** P3-Low | **Sprint:** Tier 5
- **Files to change:** `frontend/src/components/*.tsx`
- **Acceptance criteria:**
  - [ ] All components render correctly in dark mode
  - [ ] Signal feed severity colors visible in dark mode
  - [ ] Scorecard bar charts readable in dark mode

### FE-009: Mobile responsive layout `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Files to change:** `frontend/src/components/IntelPage.tsx`
- **Acceptance criteria:**
  - [ ] Stack columns vertically on screens <768px
  - [ ] Signal feed below chat on mobile
  - [ ] Scorecard cards stack vertically
  - [ ] Map takes full width on mobile

### FE-010: Alert notification badge `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Depends on:** INTEL-006
- **Files to change:** `frontend/src/app/page.tsx`
- **Acceptance criteria:**
  - [ ] Red badge with count on "Alerts" tab
  - [ ] Count fetched from `GET /api/v1/alerts/count`
  - [ ] Badge disappears when all alerts viewed

### FE-011: Address search bar in map view `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Docx ref:** Item 2.7 — "Investors know addresses, not PIDs. Add civic address search."
- **Description:** Currently parcels are found by PID lookup or clicking the map. Most investors know addresses (e.g., "3456 Main Street"), not PIDs. Need a search bar with autocomplete.
- **Files to change:** `frontend/src/components/MapView.tsx`, `api/admin.py` or new `api/search.py`
- **Acceptance criteria:**
  - [ ] Search bar at top of map view with autocomplete
  - [ ] Backend: `GET /api/v1/parcels/search?q=3456+Main` → fuzzy match on civic address
  - [ ] Backend: uses `pg_trgm` extension for trigram similarity matching
  - [ ] Results show: address, zoning, lot area, asking price (if available)
  - [ ] Clicking result centers map on parcel and opens popup
  - [ ] Fallback: if no exact match, show "Did you mean...?" suggestions
  - [ ] Performance: <200ms for autocomplete (index on civic_address)

### FE-012: Export signal feed and scorecards to CSV `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Users want to export intelligence data for offline analysis in Excel. No export functionality exists.
- **Files to change:** `frontend/src/components/IntelPage.tsx`, `frontend/src/components/NeighborhoodPage.tsx`
- **Acceptance criteria:**
  - [ ] "Export CSV" button on signal feed → downloads current filtered signals
  - [ ] "Export CSV" button on neighborhood comparison → downloads comparison table
  - [ ] CSV includes all visible fields plus metadata (source URL, confidence)
  - [ ] Filename includes date and filter context (e.g., `signals_mount_pleasant_2026-02-08.csv`)

---

## EPIC 8: Infrastructure & DevOps (`INFRA`)

### INFRA-001: Docker Compose stack `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Phase 4.5
- **Files:** `docker-compose.yml`, `Dockerfile`, `Dockerfile.db`, `frontend/Dockerfile.dev`

### INFRA-002: Makefile developer workflow `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Phase 4.5
- **Files:** `Makefile`

### INFRA-003: Playwright E2E in Docker `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Phase 4.5
- **Files:** `frontend/Dockerfile.e2e`, `frontend/playwright.config.ts`

### INFRA-004: Docker resource limits `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** No memory/CPU limits in docker-compose.yml. Uncontrolled resource consumption.
- **Files to change:** `docker-compose.yml`
- **Acceptance criteria:**
  - [ ] DB: 2 CPU / 4GB RAM limit, 1 CPU / 2GB reservation
  - [ ] API: 2 CPU / 2GB RAM limit, 1 CPU / 1GB reservation
  - [ ] Frontend: 1 CPU / 1GB RAM limit, 0.5 CPU / 512MB reservation
  - [ ] Redis (when added): 1 CPU / 1GB limit, 0.5 CPU / 512MB reservation

### INFRA-005: GitHub Actions CI/CD pipeline `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** Automated build, test, and deploy on push to main.
- **Files to create:** `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`
- **Acceptance criteria:**
  - [ ] CI: lint → unit tests → E2E tests → build Docker images
  - [ ] CD: push to main → build → deploy to staging
  - [ ] CD: tag release → deploy to production
  - [ ] Status badges in README

### INFRA-006: Sentry error tracking `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** No error monitoring. Exceptions logged to stdout only.
- **Files to change:** `api/main.py`, `requirements.txt`
- **Acceptance criteria:**
  - [ ] `pip install sentry-sdk[fastapi]`
  - [ ] `sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), ...)` in app startup
  - [ ] Unhandled exceptions reported to Sentry
  - [ ] Transaction traces for slow endpoints
  - [ ] Source maps for frontend (stretch)

### INFRA-007: Prometheus metrics + Grafana dashboards `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Docx ref:** Item 5.5
- **Description:** Observability for request latency, DB pool, cache hit rate, API call counts.
- **Files to create:** `api/metrics.py`
- **Files to change:** `docker-compose.yml` (add prometheus, grafana services)
- **Acceptance criteria:**
  - [ ] `GET /metrics` Prometheus endpoint
  - [ ] Metrics: request_duration_seconds, db_pool_size, cache_hit_ratio, api_calls_total
  - [ ] Grafana dashboard with: request rate, latency p50/p95/p99, error rate, pool utilization
  - [ ] Alert rules: p95 > 5s, error rate > 5%, pool exhaustion

### INFRA-008: Structured JSON logging `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Item 3.4 — "Replace print() with structlog. Add request_id, latency, error tracking."
- **Description:** Current logging uses unstructured text. JSON logs enable search/analysis in log aggregators.
- **Files to change:** `api/main.py` (logging config)
- **Acceptance criteria:**
  - [ ] JSON log format with: timestamp, level, module, message, request_id, duration_ms
  - [ ] Request correlation ID (middleware adds `X-Request-ID`)
  - [ ] Log sensitive fields redacted (API keys, passwords)
  - [ ] Library: `structlog` (as recommended in docx)

### INFRA-009: GCP production deployment `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 4
- **Description:** Deploy to Google Cloud: Cloud Run (API) + Cloud SQL (PostgreSQL) + Cloudflare Pages (frontend).
- **Files:** `scripts/deploy_gcp.sh`, `scripts/deploy_frontend.sh` (already exist, need verification)
- **Acceptance criteria:**
  - [ ] Cloud SQL PostgreSQL 16 with PostGIS + pgvector
  - [ ] Cloud Run with min 0, max 5 instances
  - [ ] Cloudflare Pages with Next.js standalone output
  - [ ] GCP Secret Manager for all API keys
  - [ ] Custom domain: `api.vancitylens.com` + `app.vancitylens.com`

### INFRA-010: Terraform infrastructure-as-code `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Description:** Terraform configs exist (`terraform/`) but haven't been applied.
- **Files:** `terraform/*.tf` (already exist)
- **Acceptance criteria:**
  - [ ] `terraform plan` shows clean diff
  - [ ] `terraform apply` provisions all GCP resources
  - [ ] State stored in GCS backend
  - [ ] Documented in `DEPLOYMENT_GUIDE.md`

### INFRA-011: Production database backup and restore `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 4
- **Files to create:** `scripts/backup_db.sh`, `scripts/restore_db.sh`
- **Acceptance criteria:**
  - [ ] Daily automated pg_dump to GCS bucket
  - [ ] 30-day retention policy
  - [ ] Restore script tested and documented
  - [ ] Cloud SQL automated backups enabled

### INFRA-012: Multi-stage Docker build `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Item 4.1 — "Reduce API image from ~800MB to ~200MB. Separate build and runtime stages."
- **Description:** Current API Docker image installs all dependencies including build tools. Multi-stage build separates compile-time from runtime dependencies.
- **Files to change:** `Dockerfile`
- **Acceptance criteria:**
  - [ ] Stage 1 (builder): install Python build dependencies, compile C extensions
  - [ ] Stage 2 (runtime): copy only compiled wheels, slim Python base image
  - [ ] Final image size: <300MB (down from ~800MB)
  - [ ] Verify: all API endpoints work correctly in slim image
  - [ ] Verify: PostGIS and pgvector Python bindings still function
  - [ ] Build time: acceptable (<5min on CI)

---

## EPIC 9: Business Value & Monetization (`BIZ`)

### BIZ-001: User authentication and accounts `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** No user auth. Currently single-tenant. Multi-user support needed before monetization.
- **Files to create:** `api/users.py`, `api/auth_users.py`, `db/011_users.sql`
- **Acceptance criteria:**
  - [ ] User registration (email + password, bcrypt hashing)
  - [ ] JWT token-based authentication
  - [ ] Login/logout endpoints
  - [ ] Protected endpoints require valid JWT
  - [ ] Frontend: login/register pages

### BIZ-002: Tiered subscription model `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Docx ref:** Revenue model table — Freemium through Enterprise tiers
- **Depends on:** BIZ-001
- **Tier structure (from docx):**
  - Free: 3 Bill 47 lookups/month, map view, 1 neighborhood scorecard
  - Starter ($99–$199/mo): 20 analyses/month, intelligence chat (50 queries), signal feed, email alerts
  - Professional ($399–$599/mo): unlimited analyses + chat, comparable sales, weekly digest PDF, CSV export
  - Enterprise ($1.5K–$3K/mo): API access, bulk upload (100 parcels), custom scorecard weights, Slack/Zapier integration
- **Acceptance criteria:**
  - [ ] Feature gates enforced in API middleware
  - [ ] Usage tracking (lookups/month, chat queries/month)
  - [ ] Tier-specific response: Free tier gets basic grade only; Pro gets full validation
  - [ ] Admin: `GET /api/v1/admin/usage-stats` shows per-user usage
  - [ ] Stripe integration for payment processing

### BIZ-003: Stripe payment integration `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Docx ref:** Item 5.1
- **Depends on:** BIZ-002
- **Acceptance criteria:**
  - [ ] Stripe Checkout for subscription creation
  - [ ] Webhook handler for payment events (created, failed, cancelled)
  - [ ] Subscription status stored in user profile
  - [ ] Grace period on failed payment (7 days)

### BIZ-004: Usage analytics dashboard `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Track how users interact with the platform. Essential for product decisions.
- **Acceptance criteria:**
  - [ ] Track: parcel lookups, chat queries, signal views, scorecard views
  - [ ] Track: most searched neighborhoods, most viewed signals
  - [ ] Admin dashboard: active users, daily/weekly/monthly metrics
  - [ ] Consider: PostHog or Mixpanel integration

### BIZ-005: "Colin flow" — end-to-end user journey `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Section 4.4 User Journey Gap Analysis — "Discovery → Analysis → Intelligence → Decision → Action"
- **Description:** The docx identified 5 stages in Colin's investor workflow. Currently the platform handles Discovery (partially) and Analysis. Gaps exist at every stage:
  - **Discovery:** Works via PID but not address (see BIZ-012)
  - **Analysis:** Entitlement works. No comparable sales means Colin can't validate price fairness (see BIZ-011)
  - **Intelligence:** Chat returns nothing useful without real data (see DATA-001)
  - **Decision:** No financing model, no IRR calculation, no sensitivity analysis (see BIZ-013)
  - **Action:** No deal tracking, no CRM integration, no watchlist alerts (see INTEL-006, BIZ-016)
- **Acceptance criteria:**
  - [ ] Export parcel analysis as PDF report (branded letterhead) → BIZ-006
  - [ ] Share analysis via unique link
  - [ ] Save favorite parcels (parcel bookmarking)
  - [ ] Quick comparison: compare 2-3 parcels side-by-side
  - [ ] "Next steps" CTA: generate LOI template, connect to mortgage calculator

### BIZ-006: PDF report export `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** Export parcel validation report as professional PDF for client presentations.
- **Files to create:** `api/report_generator.py`
- **Acceptance criteria:**
  - [ ] VanCity Lens branded header
  - [ ] Parcel info: address, PID, zoning, entitlement
  - [ ] Pro forma summary (three scenarios)
  - [ ] Risk assessment with color-coded flags
  - [ ] Due diligence checklist
  - [ ] Comparable sales (when available)
  - [ ] Sources cited with links
  - [ ] `GET /api/v1/parcels/{pid}/report.pdf`

### BIZ-007: Demo scenarios with real data `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Depends on:** DATA-001, DATA-002
- **Acceptance criteria:**
  - [ ] "What rezoning applications were approved in the last 3 months?" → grounded answers
  - [ ] "Are there properties near Broadway Plan stations facing community opposition?" → spatial + NLP
  - [ ] "What did council decide about [specific address]?" → exact document citation
  - [ ] "Show me all density increases approved in Mount Pleasant this year" → filtered intelligence
  - [ ] Scorecard for 5+ neighborhoods with real data
  - [ ] Demo script document for Colin presentation

### BIZ-008: Landing page and product positioning `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Description:** Marketing site explaining the product value proposition.
- **Acceptance criteria:**
  - [ ] Landing page at `vancitylens.com`
  - [ ] Value prop: "AI analyst that reads everything City Hall publishes"
  - [ ] Feature comparison table (vs manual research, vs competitors)
  - [ ] Pricing page with tier comparison
  - [ ] "Book a demo" CTA

### BIZ-009: TAM validation — BC real estate professional outreach `📋 TODO`
- **Type:** Research | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Docx ref:** Section 4.2 — "Estimated TAM in BC ~$4M annually"
- **Description:** Validate $4M TAM estimate. Interview 5-10 realtors/developers on willingness to pay.
- **Acceptance criteria:**
  - [ ] 5+ interviews with Vancouver realtors/developers
  - [ ] Pricing sensitivity analysis
  - [ ] Feature priority ranking from actual users
  - [ ] Written findings document

### BIZ-010: API access for third-party integrations `📋 TODO`
- **Type:** Story | **Priority:** P3-Low | **Sprint:** Tier 5+
- **Docx ref:** Item 5.2
- **Depends on:** BIZ-001, BIZ-002
- **Acceptance criteria:**
  - [ ] API key management (per-user keys)
  - [ ] Rate limiting per API key tier
  - [ ] OpenAPI documentation (Swagger UI — FastAPI auto-generates, needs polish)
  - [ ] SDKs: Python, JavaScript (stretch)

### BIZ-011: Comparable sales analysis `📋 TODO`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** Item 2.2 + Business Table R2 — "CRITICAL for user trust. Must answer: 'Is this price fair?'"
- **Depends on:** DATA-009
- **Description:** Colin's #1 question: "Is this price fair?" No market comps exist. Need to show recent comparable sales near each parcel to validate asking prices. The docx specifically calls this CRITICAL.
- **Files to create:** `api/comparables.py`
- **Files to change:** `api/validation.py` (add comps to validation response), `frontend/src/components/MapView.tsx` (show comps in popup)
- **Acceptance criteria:**
  - [ ] Given a parcel, find 3-5 nearest land sales within 500m, same zoning category, last 12 months
  - [ ] Show: sale price, price/sqft, price/buildable sqft, sale date, distance
  - [ ] Median comp price displayed prominently: "Comparable land sells at $X/buildable sqft"
  - [ ] Asking price vs median comp: "Asking 15% above comparable median" (green/yellow/red)
  - [ ] API: `GET /api/v1/parcels/{pid}/comparables` returns sorted comparables
  - [ ] Frontend: "Comparable Sales" section in parcel popup with mini-map showing comp locations
  - [ ] Estimated effort: 6 days (docx)

### BIZ-012: Address-based parcel search `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Docx ref:** Item 2.7 — "Investors know addresses, not PIDs"
- **Description:** Currently parcels are found only by PID lookup or map click. Real investors know addresses from listings on REW.ca, Realtor.ca etc. Need address-to-parcel lookup.
- **Files to change:** `api/admin.py` or new `api/search.py`
- **Acceptance criteria:**
  - [ ] `GET /api/v1/parcels/search?q=3456+Main+Street` → fuzzy match on civic address
  - [ ] Use `pg_trgm` extension for similarity matching
  - [ ] Return top 5 matches with: address, PID, zoning, lot area
  - [ ] Frontend counterpart: FE-011 (search bar in map view)
  - [ ] Performance: <200ms response time (trigram index on civic_address column)
  - [ ] Estimated effort: 2 days (docx)

### BIZ-013: Financing calculator / deal modeling `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Item 3.1 + Business Table R3 — "Move from 'land value' to 'deal IRR.' Converts browser into buyer."
- **Description:** Move beyond "land value = $X" to actual deal modeling. The docx says the platform "informs but doesn't close" — Colin must use a spreadsheet for the actual investment decision. A financing calculator bridges this gap.
- **Files to create:** `api/financing.py`
- **Files to change:** `api/validation.py`, frontend popup
- **Acceptance criteria:**
  - [ ] Inputs: land acquisition cost, construction cost/sqft, equity %, debt interest rate, construction period
  - [ ] Outputs: total development cost, equity required, debt required, projected revenue, profit, ROE, IRR
  - [ ] Three scenarios: conservative (bear), base, aggressive (bull)
  - [ ] Sensitivity analysis: show how IRR changes with ±10% revenue or ±20% construction cost
  - [ ] Frontend: "Deal Analysis" tab in parcel popup (Pro tier feature)
  - [ ] Export: include financing analysis in PDF report (BIZ-006)
  - [ ] Estimated effort: 3 days (docx)

### BIZ-014: Entitlement confidence scoring `📋 TODO`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Item 3.2 + Business Table R4 — "Instead of '12 storeys guaranteed,' show '12 storeys (87% probability based on council voting patterns).'"
- **Description:** Currently entitlement shows a single number ("12 storeys"). In reality, council approval is probabilistic. Confidence scoring shows likelihood of achieving entitled height based on historical council voting patterns for similar parcels/zones.
- **Files to create:** `api/entitlement_confidence.py`
- **Files to change:** `api/entitlement.py`, `api/validation.py`
- **Acceptance criteria:**
  - [ ] Historical baseline: analyze council votes on rezoning by zone type and tier
  - [ ] Confidence score: 0-100% based on: zone type approval rate, proximity to opposition triggers, recent precedent
  - [ ] Display: "12 storeys (87% confidence)" instead of "12 storeys"
  - [ ] Factors: recent approvals nearby (+confidence), heritage proximity (-confidence), view cone (-confidence)
  - [ ] Frontend: confidence badge next to entitlement number
  - [ ] Requires: intelligence data seeded (DATA-001/002) for historical voting pattern analysis
  - [ ] Estimated effort: 4 days (docx)

### BIZ-015: Bulk parcel upload + analysis `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Docx ref:** Item 5.3 — "Analyze 50–100 parcels in one batch"
- **Depends on:** BIZ-001, BIZ-002 (Enterprise tier feature)
- **Description:** Enterprise users (developers, investors with portfolios) need to analyze 50-100 parcels at once. Upload a CSV of PIDs or addresses and get back a ranked analysis.
- **Files to create:** `api/bulk_analysis.py`
- **Acceptance criteria:**
  - [ ] `POST /api/v1/parcels/bulk-analyze` accepts CSV upload (PID or address column)
  - [ ] Process in background (job queue — PERF-015)
  - [ ] Return: `job_id` with status polling endpoint
  - [ ] Result: ranked parcels with grade, pro forma summary, key risks
  - [ ] Export: CSV + PDF summary report
  - [ ] Limit: 100 parcels per batch (Enterprise tier)

### BIZ-016: CRM integration (Zapier/Slack) `📋 TODO`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Docx ref:** Item 5.4 — "Alert → Slack/Airtable/Salesforce. Embed in workflow."
- **Depends on:** INTEL-006 (alert system)
- **Description:** Enterprise users want alerts pushed into their existing workflow tools. Integration with Zapier enables connection to hundreds of apps.
- **Acceptance criteria:**
  - [ ] Zapier webhook: push new alerts to Zapier trigger URL
  - [ ] Slack integration: post alerts to designated Slack channel
  - [ ] Webhook format: JSON with parcel info, signal summary, grade, link to VanCity Lens
  - [ ] Configuration: per-user webhook URL in account settings
  - [ ] Pre-built Zapier templates: VanCity Lens → Slack, VanCity Lens → Airtable, VanCity Lens → Email

---

## Execution Timeline

| Phase | Sprint | Duration | Focus | Key Deliverables |
|-------|--------|----------|-------|------------------|
| **Phase A** | Tier 0 | ✅ DONE | Security hardening | Admin auth, hardcoded creds, CORS, security headers, health check |
| **Phase A** | Tier 1 | ✅ DONE | Critical perf fixes | N+1 scorecards, pool config, 130 new tests |
| **Phase B** | Tier 2 | 2-3 weeks | Data, indexes, key features | Compound indexes, real data seeding, Redis cache, CI pipeline, view cones, comparable sales, address search |
| **Phase C** | Tier 3 | 3-4 weeks | Performance + product completeness | Parallel processing, rate limiting, validation V2 (trees, permits, NMH), user auth, financing calc, confidence scoring, PDF export |
| **Phase D** | Tier 4 | 3 weeks | Polish + business features | Alerts, monitoring, GCP deploy, supply pipeline, mobile responsive, CSV export |
| **Phase E** | Tier 5 | 4 weeks | Monetization | Stripe, weekly digest, landing page, TAM validation, bulk upload, CRM integration |
| **Phase F** | Tier 5+ | Ongoing | Scale | PgBouncer, Celery, read replicas, Kubernetes, API marketplace |

**Docx timeline mapping:**
- Phase 0 (Validate & Harden, Weeks 1-2) → Phase A: ✅ DONE
- Phase 1 (Seed & Test, Weeks 3-6) → Phase B (Tier 2)
- Phase 2 (Product Completeness, Weeks 7-10) → Phase C (Tier 3)
- Phase 3 (Differentiate & Launch, Weeks 11-14) → Phase C + D (Tier 3-4)
- Phase 4 (Scale, Weeks 15-18) → Phase E (Tier 5)

---

## Features Cut / Deferred

| Feature | Source | Reason | Revisit When |
|---------|--------|--------|--------------|
| Read replicas | Perf review | Not needed until 100+ concurrent users | Post-launch traffic data |
| Kubernetes autoscaling | Perf review | Overkill for POC/MVP | After Stripe revenue > $5K MRR |
| Custom RAG framework (k2-lite) | Original plan | Current pipeline sufficient | If retrieval quality degrades |
| CanLII court decision scraper | Original plan | Low priority, complex parsing | Phase 6+ |
| Shape Your City scraper | Original plan | Low signal-to-noise ratio | Phase 6+ |
| Real-time WebSocket signal feed | Original plan | Polling is sufficient for now | If alert latency becomes issue |
| White-label multi-tenant | Original plan | Enterprise feature only | After first Enterprise customer |
| Walkability index integration | Original plan | UBC dataset access unclear | When dataset confirmed available |
| Predictive zoning change modeling | Docx Section 7 | Requires historical zoning data + time series ML. High effort, uncertain value. | Year 2 |
| Construction cost database | Docx Section 7 | Contractors already have this. Low marginal value. | Year 2 |
| Mobile native app | Docx Section 7 | Responsive web is sufficient for alpha. Native app only if demand warrants. | Year 2+ |
| Advanced scorecard weight customization | Docx Section 7 | Build generic weights first. Power-user customization later. | Year 2 |

---

## Architecture Notes

### Current Stack
- **API:** FastAPI 0.115.6, Python 3.12, Pydantic v2
- **Database:** PostgreSQL 16 + PostGIS 3.4 + pgvector 0.8.1
- **Frontend:** Next.js 15, React 19, TypeScript strict mode
- **AI:** Cohere (embed + rerank), Anthropic Claude (extraction + chat)
- **Search:** Hybrid: dense vectors (pgvector) + BM25 (tsvector) + RRF + rerank
- **Infrastructure:** Docker Compose (3 services), GCP project provisioned

### Competitive Moat (from Docx Section 4.2)
> VanCity Lens has one genuine moat: the combination of Bill 47 automation and government document intelligence extraction. No Canadian competitor (CoStar, Zonda, Altus) is doing this at the parcel level. However, the moat is time-limited — a well-funded competitor could replicate the core engine in 3–4 months for approximately $200K.
>
> Defensibility Strategy: Move fast, seed real data, build a community of early-adopter investors who contribute deal outcomes and market intelligence. The network effect of community data is harder to replicate than the software itself.

### Key Metrics (Current)
- 92,046 parcels loaded (92K)
- 419 parcels with asking prices
- 22 neighborhoods with composite scores
- 405 backend tests passing
- 0 intelligence documents (needs real data seeding)

---

## Quick Reference — What Changed This Session

### Files Created
- `api/auth.py` — Admin API key authentication
- `tests/test_entitlement.py` — 35 entitlement engine tests
- `tests/test_hidden_costs.py` — 65 hidden cost tests
- `tests/test_admin_security.py` — 30 admin/security tests
- `VanCity_Lens_Review_Plan.docx` — Comprehensive 4-dimension review

### Files Modified
- `api/main.py` — Security headers middleware, CORS hardening, deep health check
- `api/db.py` — Env-aware credentials, configurable pool sizing
- `api/admin.py` — Router-level auth dependency
- `api/intelligence/routes.py` — Auth on 5 admin endpoints
- `api/intelligence/neighborhoods.py` — N+1 fix (batch queries), `_format_scorecard` helper

### Git
- Commit: `4ce4929` — "harden security, fix N+1 queries, add 130 tests"
- Pushed to: `https://github.com/gemini2026/vancity-lens` main branch

---

*Generated from comprehensive review covering: VanCity_Lens_Review_Plan.docx (performance/scalability, security, testing, business value — 42 action items), VALIDATION_V2_PLAN.md (11 new validation checks, multi-axis grading), PERFORMANCE_SCALABILITY_REVIEW.md (8 critical findings, scalability gaps), and codebase analysis. All 42 docx items mapped to backlog — see cross-reference table above.*
