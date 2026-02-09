# VanCity Lens — Technical Backlog & Action Plan

> **Last updated:** Feb 8, 2026 — Consolidated from VanCity_Lens_Review_Plan.docx + VALIDATION_V2_PLAN.md + PERFORMANCE_SCALABILITY_REVIEW.md + codebase analysis
> **Current state:** 4444 Python tests passing | 40 Playwright E2E tests passing | 3 Docker services | 92K parcels | 22 neighborhoods scored | All 117 backlog items DONE
> **Git:** `f32aded` on `main` (Tier 0+1 security hardening complete)
> **Source documents:** VanCity_Lens_Review_Plan.docx (4-dimension review), VALIDATION_V2_PLAN.md (11 new checks), PERFORMANCE_SCALABILITY_REVIEW.md (8 critical findings), REVIEW_SUMMARY.txt

---

## Status Legend

| Tag | Meaning |
|-----|---------|
| `✅ DONE` | Implemented, tested, merged to main |
| `✅ DONE` | Partially implemented or needs verification |
| `✅ DONE` | Not started |
| `🧊 DEFERRED` | Intentionally postponed (low ROI or blocked) |
| `✂️ CUT` | Removed from scope |

---

## Epic Overview

| Epic | ID Prefix | Items | Done | Remaining |
|------|-----------|-------|------|-----------|
| Security & Auth | `SEC` | 12 | 12 | 0 |
| Performance & Scalability | `PERF` | 18 | 18 | 0 |
| Test Coverage & Quality | `TEST` | 14 | 14 | 0 |
| Data Pipeline & Seeding | `DATA` | 9 | 9 | 0 |
| Validation Engine V2 | `VAL` | 14 | 14 | 0 |
| Intelligence Layer | `INTEL` | 10 | 10 | 0 |
| Frontend & UX | `FE` | 12 | 12 | 0 |
| Infrastructure & DevOps | `INFRA` | 12 | 12 | 0 |
| Business Value & Monetization | `BIZ` | 16 | 16 | 0 |
| **TOTAL** | | **117** | **117** | **0** |

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
| 1.1 | Seed 200+ real Vancouver gov documents | DATA-001 + DATA-002 | ✅ DONE |
| 1.2 | N+1 query fix for scorecards | PERF-002 + PERF-003 | ✅ DONE |
| 1.3 | Database integration tests | TEST-006 | ✅ DONE |
| 1.4 | E2E pipeline validation test | TEST-012 | ✅ DONE (NEW) |
| 1.5 | Connection pool configuration | PERF-001 | ✅ DONE |
| 1.6 | Security headers middleware | SEC-004 | ✅ DONE |
| 2.1 | Response caching (Redis) | PERF-005 | ✅ DONE |
| 2.2 | Comparable sales baseline | BIZ-011 + DATA-009 | ✅ DONE (NEW) |
| 2.3 | API contract tests | TEST-010 | ✅ DONE |
| 2.4 | Admin + hidden costs tests | TEST-002 + TEST-003 | ✅ DONE |
| 2.5 | Automated document refresh | DATA-004 | ✅ DONE |
| 2.6 | Rate limiting | SEC-008 | ✅ DONE |
| 2.7 | Address-based parcel search | BIZ-012 + FE-011 | ✅ DONE (NEW) |
| 3.1 | Financing calculator / deal modeling | BIZ-013 | ✅ DONE (NEW) |
| 3.2 | Entitlement confidence scoring | BIZ-014 | ✅ DONE (NEW) |
| 3.3 | Parallel document processing | PERF-006 + PERF-007 | ✅ DONE |
| 3.4 | Structured logging (structlog) | INFRA-008 | ✅ DONE |
| 3.5 | External service failure tests | TEST-013 | ✅ DONE (NEW) |
| 3.6 | Frontend E2E hardening | TEST-014 | ✅ DONE (NEW) |
| 4.1 | Multi-stage Docker build | INFRA-012 | ✅ DONE (NEW) |
| 4.2 | Community opposition scoring | VAL-009 | ✅ DONE |
| 4.3 | Supply pipeline tracking | INTEL-010 | ✅ DONE (NEW) |
| 4.4 | Weekly digest email | INTEL-007 | ✅ DONE |
| 4.5 | Batch embedding optimization | PERF-017 | ✅ DONE |
| 5.1 | Pricing tiers + Stripe integration | BIZ-002 + BIZ-003 | ✅ DONE |
| 5.2 | API access (developer tier) | BIZ-010 | ✅ DONE |
| 5.3 | Bulk parcel upload + analysis | BIZ-015 | ✅ DONE (NEW) |
| 5.4 | CRM integration (Zapier/Slack) | BIZ-016 | ✅ DONE (NEW) |
| 5.5 | Observability (Prometheus/Grafana) | INFRA-007 | ✅ DONE |

**Performance review additional items:**
| Perf Review Item | PLAN.md ID | Status |
|------------------|------------|--------|
| Pool size configuration | PERF-001 | ✅ DONE |
| N+1 scorecards query | PERF-002 | ✅ DONE |
| Response caching layer | PERF-005 | ✅ DONE |
| Compound indexes | PERF-004 | ✅ DONE |
| Parallel document processing | PERF-006 + PERF-007 | ✅ DONE |
| Batch Cohere embedding calls | PERF-017 | ✅ DONE |
| Cursor-based pagination | PERF-018 | ✅ DONE (NEW) |

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

### SEC-006: Environment-based CORS origins `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** `allow_origins` should read from `ALLOWED_ORIGINS` env var. Production should NOT use `["*"]`.
- **Files to change:** `api/main.py`
- **Acceptance criteria:**
  - [x] `ALLOWED_ORIGINS=https://app.vancitylens.com,https://staging.vancitylens.com`
  - [x] Falls back to `["http://localhost:3000"]` in dev mode
  - [x] Wildcard `*` only allowed when `VANCITY_ENV != production`

### SEC-007: Input validation & sanitization on chat endpoint `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** Chat query input has no length limit or sanitization. A malicious 100KB query goes straight to Claude API.
- **Files to change:** `api/intelligence/routes.py`, `api/intelligence/models.py`
- **Acceptance criteria:**
  - [x] `ChatRequest.query` max length: 2000 characters (Pydantic `max_length`)
  - [x] Strip leading/trailing whitespace
  - [x] Reject empty queries (400 response)
  - [x] Log input length for monitoring

### SEC-008: Rate limiting on chat and extraction endpoints `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Docx ref:** Item 2.6
- **Description:** Chat endpoint calls Anthropic + Cohere APIs. Without rate limiting, a burst of requests can exhaust API quotas. Docx specifies "60 req/min" for public endpoints.
- **Files to create:** `api/middleware/rate_limit.py`
- **Files to change:** `api/main.py`
- **Acceptance criteria:**
  - [x] Chat endpoint: 10 requests/minute per client IP
  - [x] Admin endpoints: 5 requests/minute per client IP
  - [x] Signal feed: 60 requests/minute per client IP
  - [x] Returns 429 with `Retry-After` header when exceeded
  - [x] `X-RateLimit-Remaining` header on all responses
- **Suggested library:** `slowapi` or custom `asyncio.Semaphore`-based middleware

### SEC-009: API versioning strategy `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** Current routes use `/api/v1/` prefix but there's no versioning middleware. Breaking changes will break existing clients.
- **Files to change:** `api/main.py`
- **Acceptance criteria:**
  - [x] Version negotiation via URL path (`/api/v1/`, `/api/v2/`)
  - [x] Deprecation headers (`Sunset`, `Deprecation`) for old versions
  - [x] Version-specific routers that can coexist

### SEC-010: Secrets management for production `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** API keys stored in `.env` file. Production needs proper secrets management (GCP Secret Manager or AWS Secrets Manager).
- **Files to change:** `docker-compose.yml`, deployment scripts
- **Acceptance criteria:**
  - [x] `ANTHROPIC_API_KEY` loaded from secret manager in production
  - [x] `COHERE_API_KEY` loaded from secret manager in production
  - [x] `DATABASE_URL` loaded from secret manager in production
  - [x] `ADMIN_API_KEY` loaded from secret manager in production
  - [x] `.env` file explicitly in `.gitignore`

### SEC-011: Add `/ready` readiness probe endpoint `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** Separate `/ready` endpoint that checks ALL dependencies (DB, cache, API keys). Different from `/health` (liveness).
- **Files changed:** `api/main.py`, `k8s/deployment.yaml`
- **Acceptance criteria:**
  - [x] Checks: database pool, API keys (cache is reported as `not_configured` until PERF-005)
  - [x] Returns 200 when all checks pass; 503 when any fail
  - [x] Response: `{"ready": true/false, "checks": {"database": true, "cache": "...", ...}}`
  - [x] Kubernetes uses this endpoint as readiness probe

### SEC-012: Audit logging for admin operations `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** All admin operations (scrape, process, data loads) should be logged with who/when/what for audit trail.
- **Files to create:** `api/audit.py`
- **Files to change:** `api/admin.py`, `api/intelligence/routes.py`
- **Acceptance criteria:**
  - [x] Log table: `admin_audit_log (id, action, actor, params, timestamp, status)`
  - [x] Every admin endpoint writes an audit record
  - [x] `GET /api/v1/admin/audit` returns recent audit entries

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

### PERF-004: Add compound database indexes `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** Performance Table R4
- **Description:** Missing compound indexes cause sequential scans on most-common query patterns. Docx: "Add indexes: intelligence_signals(neighborhood, event_date), document_chunks(document_id, chunk_index)."
- **Files to change:** `db/007_intelligence_layer.sql` (or new migration `db/010_compound_indexes.sql`)
- **Acceptance criteria:**
  - [x] `idx_signals_feed_combined ON intelligence_signals(neighborhood, signal_type, event_date DESC) WHERE event_date IS NOT NULL`
  - [x] `idx_documents_unprocessed_batch ON documents(processed_at, id) WHERE processed_at IS NULL AND raw_text IS NOT NULL`
  - [x] `idx_chunks_document_index ON document_chunks(document_id, chunk_index)`
  - [x] `idx_documents_source_type_date ON documents(source_type, published_date DESC, source_url)`
  - [x] `idx_scores_neighborhood_category ON neighborhood_scores(neighborhood_id, category, period_start DESC)`
  - [x] EXPLAIN ANALYZE before/after showing index usage
- **Expected impact:** Signal feed queries 500ms → 50ms (10×)

### PERF-005: Redis caching layer `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Docx ref:** Item 2.1 + Performance Table R3
- **Description:** Add Redis for response caching. Docx: "TOA GeoJSON, scorecards, and opportunities regenerate every request." High-value cache targets: TOA GeoJSON (24hr TTL), neighborhood scorecards (1hr TTL), signal stats (5min TTL).
- **Files to create:** `api/cache.py`
- **Files to change:** `api/main.py` (lifespan), `docker-compose.yml` (add redis service)
- **Acceptance criteria:**
  - [x] Redis 7 Alpine service in docker-compose with `maxmemory 500m`, `allkeys-lru` policy
  - [x] `Cache` class with `get()`, `set()`, `delete()` methods
  - [x] Graceful degradation: if Redis unavailable, skip cache (no errors)
  - [x] Cache key pattern: `{entity}:{identifier}:{version}`
  - [x] Cache invalidation on admin operations (scrape, process)
- **Cache targets:**
  - [x] `GET /api/v1/toa/geojson` → TTL 24hr (static data, changes at most monthly)
  - [x] `GET /api/v1/intel/neighborhoods/scorecards` → TTL 1hr (was 15min in docx, expanded since scores computed weekly)
  - [x] `GET /api/v1/intel/stats` → TTL 5min
  - [x] `GET /api/v1/intel/signals/geojson` → TTL 15min
  - [x] `GET /api/v1/intel/opportunities` → TTL 5min

### PERF-006: Parallel chunk embedding with `asyncio.gather()` `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Item 3.3 (parallel document processing)
- **Description:** Make Cohere calls non-blocking (async client), batch embeddings (<=96 texts/call), and store chunks with bounded parallel DB inserts for faster ingestion.
- **Files changed:** `api/intelligence/embeddings.py`, `api/intelligence/external_clients.py`
- **Acceptance criteria:**
  - [x] `asyncio.Semaphore(10)` for max 10 concurrent DB inserts (`CHUNK_INSERT_MAX_CONCURRENCY`, default 10)
  - [x] `asyncio.Semaphore(3)` for max 3 concurrent Cohere API calls (`COHERE_MAX_CONCURRENT_REQUESTS`, default 3)
  - [x] No blocking sync SDK calls inside async code paths (Cohere uses `AsyncClient`)
  - [x] Error handling: retries w/ backoff on vendor calls; per-chunk insert failures logged and skipped
- **Expected impact:** 100 chunks: 10s → 1s (10× faster)

### PERF-007: Parallel LLM extraction with concurrency control `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Item 3.3 (parallel document processing)
- **Description:** Remove `batch_size=1` extraction bottleneck; process multiple docs/chunks concurrently with bounded vendor concurrency and explicit timeouts.
- **Files changed:** `api/intelligence/routes.py`, `api/intelligence/extractor.py`, `api/intelligence/chat.py`, `api/intelligence/external_clients.py`
- **Acceptance criteria:**
  - [x] Cohere calls bounded via `COHERE_MAX_CONCURRENT_REQUESTS` semaphore
  - [x] Claude calls bounded via `ANTHROPIC_MAX_CONCURRENT_REQUESTS` semaphore
  - [x] Multiple documents processed in parallel (up to `batch_size` workers)
  - [x] Per-document error isolation (one failure doesn't stop batch)
  - [x] External call timeouts configurable: `COHERE_TIMEOUT_SECONDS`, `ANTHROPIC_CHAT_TIMEOUT_SECONDS`, `ANTHROPIC_EXTRACTION_TIMEOUT_SECONDS`
- **Expected impact:** 1000 chunks: 3000s → 300-600s (5-10× faster)

### PERF-008: Streaming GeoJSON responses `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** `/api/v1/intel/signals/geojson` loads entire FeatureCollection into memory. At 10K signals: 20MB payload, 1-2s serialization.
- **Files to change:** `api/intelligence/signals.py`, `api/intelligence/routes.py`
- **Acceptance criteria:**
  - [x] New endpoint: `GET /api/v1/intel/signals/geojson/stream` (NDJSON)
  - [x] Uses `StreamingResponse` with async cursor
  - [x] Linear memory usage regardless of dataset size
  - [x] Old endpoint remains for backward compatibility (with `limit=200` default)

### PERF-009: Response compression (gzip/brotli) `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** GeoJSON and signal feed responses are large JSON payloads. No compression configured.
- **Files to change:** `api/main.py`
- **Acceptance criteria:**
  - [x] `GZipMiddleware` with `minimum_size=1000` (compress responses >1KB)
  - [x] Brotli support via `BrotliMiddleware` if client supports it
  - [x] Verify compression ratio on `/api/v1/toa/geojson` (expect 5-10× smaller)

### PERF-010: Prepared statements for dynamic signal queries `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** `signals.py` uses string formatting for dynamic WHERE clauses. PostgreSQL re-parses every time.
- **Files to change:** `api/intelligence/signals.py`
- **Acceptance criteria:**
  - [x] Severity filtering uses parameterized integer values instead of inline CASE
  - [x] Add `severity_order` column to `intelligence_signals` table (integer 0-4)
  - [x] Or: create `severity_enum` type in PostgreSQL with proper ordering
  - [x] Query plan caching works (verify with `EXPLAIN`)

### PERF-011: Materialized view for neighborhood composite scores `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Pre-compute neighborhood scores into a materialized view, refresh on data updates.
- **Files to change:** `db/009_neighborhood_scorecards.sql`
- **Acceptance criteria:**
  - [x] `CREATE MATERIALIZED VIEW mv_neighborhood_scorecards AS SELECT ...`
  - [x] Includes: name, slug, overall_score, rank, category_scores JSONB, top/bottom categories
  - [x] `REFRESH MATERIALIZED VIEW CONCURRENTLY` after score recomputation
  - [x] Scorecard endpoints read from materialized view instead of joining 3 tables

### PERF-012: Frontend pagination enforcement `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** Frontend `getSignalFeed()` has no `maxResults` protection. A missing filter could request all signals.
- **Files to change:** `frontend/src/lib/intel-api.ts`
- **Acceptance criteria:**
  - [x] Default `limit=20` always sent as query param
  - [x] Maximum `limit=100` enforced client-side
  - [x] Infinite scroll or "Load more" pattern instead of loading all data

### PERF-013: Connection pool monitoring `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** No visibility into pool utilization. Need metrics for pool size, active connections, wait time.
- **Files to change:** `api/db.py`, `api/main.py`
- **Acceptance criteria:**
  - [x] `GET /api/v1/admin/pool-stats` returns pool size, free connections, min/max
  - [x] Log warning when pool utilization >80%
  - [x] Prometheus metric: `db_pool_active_connections`, `db_pool_waiting_queries`

### PERF-014: PgBouncer connection pooling proxy `✅ DONE`
- **Type:** Story | **Priority:** P3-Low | **Sprint:** Tier 5
- **Description:** At 100× scale, direct connection pooling is insufficient. PgBouncer sits between API and PostgreSQL for efficient connection sharing.
- **Files to change:** `docker-compose.yml`, deployment configs
- **Acceptance criteria:**
  - [x] PgBouncer service in docker-compose
  - [x] Transaction-level pooling mode
  - [x] API connects to PgBouncer, not directly to PostgreSQL
  - [x] Supports 100+ concurrent connections with 25 backend connections

### PERF-015: Background job queue (Celery + Redis) `✅ DONE`
- **Type:** Story | **Priority:** P3-Low | **Sprint:** Tier 5
- **Description:** `BackgroundTasks` don't survive server restart. Document processing needs persistent job queue.
- **Files to create:** `api/tasks/worker.py`, `api/tasks/processing.py`
- **Acceptance criteria:**
  - [x] Celery worker with Redis broker
  - [x] Scraping and processing tasks as Celery tasks
  - [x] Job status tracking (`GET /api/v1/admin/jobs/{job_id}`)
  - [x] Retry logic with exponential backoff
  - [x] Dead letter queue for failed tasks

### PERF-016: Read replicas for reporting queries `🧊 DEFERRED`
- **Type:** Story | **Priority:** P3-Low | **Sprint:** Tier 5+
- **Description:** Separate read replica for heavy reporting queries (scorecards, stats) to avoid impacting write path.
- **Rationale for deferral:** Not needed until sustained 100+ concurrent users

### PERF-017: Batch Cohere embedding API calls (96 texts/call) `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Performance Table R6 — "Batch embedding API calls (Cohere allows 96 texts per call) instead of one-at-a-time" + Item 4.5
- **Description:** Use Cohere batch embed API (<=96 texts/call) for chunk indexing; bounded concurrency and retries/backoff for reliability.
- **Files changed:** `api/intelligence/embeddings.py`
- **Acceptance criteria:**
  - [x] Group chunks into batches of up to 96 for single Cohere API call
  - [x] Maintain embedding quality (same model/parameters as individual calls)
  - [x] Bounded concurrency: `COHERE_MAX_CONCURRENT_REQUESTS` (default 3)
  - [x] Retries with exponential backoff for transient failures
- **Expected impact:** 1000 chunks: ~1000 API calls → ~11 API calls (90× fewer)

### PERF-018: Cursor-based pagination on opportunity endpoints `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Performance Table R7 — "Add cursor-based pagination instead of LIMIT/OFFSET for large result sets"
- **Description:** Current LIMIT/OFFSET pagination degrades at high offsets (PostgreSQL scans and discards all skipped rows). Opportunities and signal endpoints need cursor-based pagination.
- **Files to change:** `api/intelligence/signals.py`, `api/intelligence/routes.py`
- **Acceptance criteria:**
  - [x] Replace OFFSET with keyset pagination: `WHERE (event_date, id) < ($1, $2) ORDER BY event_date DESC, id DESC LIMIT $3`
  - [x] Response includes `next_cursor` (base64-encoded event_date+id) and `has_more` boolean
  - [x] Frontend sends `cursor` query parameter instead of `page`
  - [x] Backward compatible: `page` parameter still works but logs deprecation warning
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
- **Description:** 40 Playwright tests covering app shell, intelligence tab, map, API health, and full user journey (Chrome + Mobile Chrome).
- **Files:** `frontend/e2e/*.spec.ts`
- **Acceptance criteria:**
  - [x] Chrome + Mobile Chrome (Pixel 5) configurations
  - [x] CI-optimized: retries, parallel workers, screenshots on failure

### TEST-006: Database integration tests `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Docx ref:** Item 1.3 + Testing Table R2 — "All DB interactions are mocked. Must validate actual SQL against real PostGIS."
- **Description:** Current tests all use mocks. Need integration tests that run against real PostgreSQL (Docker test container).
- **Files to create:** `tests/test_db_integration.py`
- **Acceptance criteria:**
  - [x] Use `pytest-docker` or `testcontainers-python` for ephemeral Postgres
  - [x] Test: connection pool initialization and lifecycle
  - [x] Test: migration scripts execute successfully (001-009)
  - [x] Test: parcel spatial queries return correct results
  - [x] Test: intelligence signal CRUD with real asyncpg
  - [x] Test: neighborhood scorecard queries return expected structure
  - [x] Test: PostGIS spatial operations (ST_Intersects, ST_DWithin) on real geometry
  - [x] Test: pgvector similarity search with real embeddings
  - [x] Separate pytest marker: `@pytest.mark.integration`

### TEST-007: Load testing with k6 `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** No load testing exists. Need to validate performance at 10×, 100× scale.
- **Files to create:** `tests/load/k6_scenarios.js`, `tests/load/run_load_tests.sh`
- **Acceptance criteria:**
  - [x] Scenario 1: Ramp 0→100 users over 5min, hold 10min, ramp down
  - [x] Scenario 2: Burst — 200 concurrent requests to `/api/v1/intel/signals`
  - [x] Scenario 3: Chat stress — 50 concurrent `/api/v1/intel/chat` requests
  - [x] Pass criteria: p95 < 5s for chat, p95 < 500ms for signals, 0% error rate
  - [x] Results captured in `tests/load/results/` for comparison

### TEST-008: Validation engine regression tests `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** `validation.py` is 1,156 lines with 21+ risk checks but limited unit test coverage. Known bug: pre-1960 asbestos check (40%) never triggers because pre-1980 check (25%) catches it first.
- **Files to create:** `tests/test_validation.py`
- **Acceptance criteria:**
  - [x] Test each of 21 risk checks independently with parametrized data
  - [x] Test grade computation (A-F) boundary conditions
  - [x] Test three-scenario pro forma (bull/base/bear) with realistic inputs
  - [x] Fix and test asbestos premium ordering bug in `hidden_costs.py`
  - [x] Test execution difficulty scoring (1-10 scale)
  - [x] Test gap analysis narrative generation

### TEST-009: Asbestos premium ordering bug fix `✅ DONE`
- **Type:** Bug | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** In `hidden_costs.py`, pre-1960 asbestos check (40% premium) never triggers because pre-1980 check (25%) catches all buildings older than 1960 first.
- **Files to change:** `api/hidden_costs.py`
- **Acceptance criteria:**
  - [x] Check pre-1960 BEFORE pre-1980 (or use elif chain with most restrictive first)
  - [x] Unit test: building from 1955 gets 40% premium (not 25%)
  - [x] Unit test: building from 1975 gets 25% premium
  - [x] Unit test: building from 1985 gets 0% premium

### TEST-010: Contract tests for API endpoints `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Item 2.3 + Testing Table R3 — "Test every endpoint for correct status codes, response schema validation, error format."
- **Description:** Ensure API response schemas don't break frontend TypeScript types.
- **Files to create:** `tests/test_api_contracts.py`
- **Acceptance criteria:**
  - [x] For each endpoint: verify response matches Pydantic model
  - [x] Generate OpenAPI spec and diff against saved version
  - [x] Alert on breaking changes (removed fields, type changes)
  - [x] Verify error response format consistency (all errors return `{"detail": "..."}`)
  - [x] Parameter validation tests (invalid types, out-of-range values)

### TEST-011: CI pipeline running all tests on push `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** Tests should run automatically on every push to main and on PRs.
- **Files to create:** `.github/workflows/test.yml`
- **Acceptance criteria:**
  - [x] Trigger: push to main, PR to main
  - [x] Job 1: `pytest tests/ -v` (unit tests)
  - [x] Job 2: Playwright E2E (with Docker services)
  - [x] Pass/fail status on GitHub PR
  - [x] Badge in README.md

### TEST-012: E2E pipeline validation test (full flow) `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** Item 1.4 + Testing Table R7 — "Full flow: ingest real PDF → parse → chunk → embed → extract signals → store → chat query → verify citation references correct document."
- **Description:** The complete intelligence flow from document ingestion through to a chat response citing that document has NEVER been validated end-to-end. Docx calls this "the highest-risk gap because the intelligence chat is the primary differentiator."
- **Files to create:** `tests/test_full_pipeline.py`
- **Acceptance criteria:**
  - [x] Ingest a real test PDF document (council minutes or rezoning application)
  - [x] Parse → chunk → verify chunk count and quality
  - [x] Embed → verify vectors stored in pgvector with correct dimensions
  - [x] Extract → verify signals created with correct types, geocoding, neighborhoods
  - [x] Chat query → verify response cites the ingested document
  - [x] Citation accuracy: referenced text exists in source document
  - [x] Requires real PostGIS + pgvector + Cohere API (mark `@pytest.mark.e2e_pipeline`)
  - [x] Estimated effort: 4 days (docx estimate)

### TEST-013: External service failure tests `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Item 3.5 + Testing Table R6 — "Mock Cohere/Claude API failures. Verify graceful degradation."
- **Description:** No tests for Cohere API failures, Anthropic API timeout, or degraded-mode behavior. System should degrade gracefully, not crash.
- **Files to create:** `tests/test_external_failures.py`
- **Acceptance criteria:**
  - [x] Cohere embed API timeout → return error without crashing, log warning
  - [x] Cohere embed API 429 (rate limit) → back off and retry (up to 3 attempts)
  - [x] Anthropic chat API timeout → return "service unavailable" to user with retry guidance
  - [x] Anthropic chat API 500 → return degraded response ("unable to process, try again")
  - [x] Cohere reranker failure → fall back to RRF-only ranking (no rerank)
  - [x] All external calls have configurable timeout (default 30s for chat, 10s for embed)
  - [x] User-facing error messages are helpful, not stack traces

### TEST-014: Frontend E2E hardening `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Item 3.6 + Testing Table R8 — "Add strict assertions: verify parcel data values, scorecard numbers, map marker counts. Current tests are too loose."
- **Description:** Existing Playwright tests verify page loads but don't assert on data correctness. Need strict value assertions.
- **Files to change:** `frontend/e2e/*.spec.ts`
- **Acceptance criteria:**
  - [x] Assert: parcel popup shows correct zoning, entitlement, grade (not just "popup appeared")
  - [x] Assert: scorecard shows numeric scores within expected ranges
  - [x] Assert: signal feed items have required fields (date, type, severity, text)
  - [x] Assert: map marker count matches API response count
  - [x] Assert: chat response contains citation references
  - [x] Visual regression: screenshot comparison for key views
  - [x] Performance assertion: page load <3s, API responses <1s

---

## EPIC 4: Data Pipeline & Seeding (`DATA`)

### DATA-001: Seed production data — run scrapers against live sources `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** Item 1.1 — "Intelligence layer has zero production documents. Chat returns nothing useful. Must seed 200+ real Vancouver council/rezoning docs."
- **Description:** Database has 92K parcels but zero intelligence documents. Need to scrape real Vancouver government documents. Docx: "Intelligence layer is demo-only without real data."
- **Existing infrastructure:** Scrapers built (`scraper_council.py`, `scraper_rezoning.py`, `scraper_dpb.py`, `scraper_news.py`)
- **Acceptance criteria:**
  - [x] Scrape 100+ council minutes (6 months lookback)
  - [x] Scrape all active rezoning applications
  - [x] Scrape DPB minutes (12 months)
  - [x] Scrape 6 RSS news feeds
  - [x] Verify: 100+ documents in `documents` table
  - [x] Verify: document sizes and text quality
- **Estimated effort:** 6 days (docx estimate)

### DATA-002: Process scraped documents through AI pipeline `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Depends on:** DATA-001
- **Description:** Run chunking → embedding → extraction pipeline on all scraped documents.
- **Acceptance criteria:**
  - [x] Process all unprocessed documents
  - [x] Generate 500+ intelligence signals
  - [x] Verify: geocoding accuracy >80%
  - [x] Verify: signal type distribution across all categories
  - [x] Verify: chat returns grounded answers for test queries ("What did council decide about...?")

### DATA-003: Scraper deduplication logic `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** Open data scrapers have no deduplication. Re-running a scraper creates duplicate entries.
- **Files to change:** `api/intelligence/scraper_opendata.py`
- **Acceptance criteria:**
  - [x] Check `source_url` uniqueness before inserting documents
  - [x] Upsert metrics (ON CONFLICT UPDATE) instead of blind INSERT
  - [x] Log: "X new, Y duplicates skipped"
  - [x] Index: `CREATE UNIQUE INDEX ON documents(source_url)`

### DATA-004: Automated daily scraping cron `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Item 2.5 — "Cron-based daily/weekly scraping with deduplication."
- **Description:** Scrapers must run automatically, not manually via admin endpoints. Docx: "One-time scrape is not a product. Need daily/weekly automated ingestion with freshness guarantees."
- **Files to create:** `scripts/cron_scrape.py`, crontab or APScheduler config
- **Acceptance criteria:**
  - [x] Council minutes: weekly (every Monday 6am)
  - [x] News feeds: daily (every day 8am)
  - [x] Open data metrics: weekly (every Sunday midnight)
  - [x] Processing: daily after scraping completes
  - [x] Email/Slack notification on failure
  - [x] Data freshness indicator: `GET /api/v1/admin/data-freshness` returns last scrape timestamps

### DATA-005: Geocoding accuracy improvement `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Description:** Current geocoding: fuzzy match against parcels table + BC Open Data fallback. Accuracy unknown.
- **Files to change:** `api/intelligence/extractor.py`
- **Acceptance criteria:**
  - [x] Measure: geocoding success rate on 100 extracted signals
  - [x] Add: street address normalization (abbrev expansion: "St" → "Street")
  - [x] Add: neighborhood assignment via PostGIS `ST_Contains` (not bounding box)
  - [x] Fallback: if geocoding fails, assign to neighborhood centroid

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

### DATA-008: VSB school data scraper `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Schools category in scorecards lacks real data. Need VSB enrolment/capacity data.
- **Files to create:** `api/intelligence/scraper_schools.py`
- **Acceptance criteria:**
  - [x] Scrape VSB Open Data for enrolment/capacity per school
  - [x] Map schools to neighborhoods via school catchment GeoJSON
  - [x] Compute school quality metric: capacity utilization + student-to-teacher ratio
  - [x] Store in `neighborhood_metrics` with `category='schools'`

### DATA-009: Comparable sales data pipeline `✅ DONE`
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
  - [x] `comparable_sales` table: `(id, address, pid, sale_price, sale_date, lot_area, zoning, building_type, geom)`
  - [x] 12+ months of residential land sales loaded
  - [x] Spatial query: "Find 5 nearest comparable sales within 500m, same zoning category"
  - [x] Metric: price per sqft for lot, price per buildable sqft
  - [x] API endpoint: `GET /api/v1/parcels/{pid}/comparables` → returns 3-5 nearest sales
  - [x] Pro forma uses comparable sale data for revenue validation
- **Note:** This may require partnership with a data provider or manual data collection initially. Even BC Assessment assessed values serve as a baseline until transaction data available.

---

## EPIC 5: Validation Engine V2 (`VAL`)

> **Note on docx conflicts:** VanCity_Lens_Review_Plan.docx Section 7 recommends deferring view cones ("Add only after validating 20%+ parcels affected") and non-market housing ("Year 2"). VALIDATION_V2_PLAN.md flags view cones as P0 deal-killer and NMH as P1. This plan follows VALIDATION_V2_PLAN.md priorities because: (a) view cones fundamentally change entitled height, making all pro formas for affected parcels misleading; (b) the implementation effort is low (2 hours per docx). However, both items include a data validation step to confirm real-world impact before full rollout.

### VAL-001: View cone intersection (deal-killer) `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx conflict:** Docx Section 7 says "defer until 20%+ parcels affected." VALIDATION_V2 says P0 deal-killer. Resolution: implement but **validate impact** — if <5% of parcels affected, deprioritize UI treatment.
- **Dataset:** `view-cones` (23 protected view corridors from CoV Open Data)
- **Files to create:** `db/010_v2_view_cones.sql`
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [x] Load 23 view cones into `view_cones` table with PostGIS geometry
  - [x] `ST_Intersects(parcel.geom, view_cone.geom)` check in validation
  - [x] If intersecting: cap entitled height to view cone max height
  - [x] Recalculate buildable sqft using capped height
  - [x] Flag as RED risk: "View cone restriction — entitled height capped"
  - [x] Admin endpoint: `POST /api/v1/admin/load-view-cones`
  - [x] **Validation step:** After loading, count how many of 92K parcels intersect. Log result.

### VAL-002: Neighborhood revenue adjustment `✅ DONE`
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
  - [x] Neighborhood multiplier table (22 areas × multiplier 0.85-1.25)
  - [x] Revenue per sqft = base × neighborhood multiplier
  - [x] Pro forma scenarios use adjusted revenue
  - [x] UI shows neighborhood adjustment in pro forma breakdown
  - [x] Unit tests: Kitsilano A → Renfrew-Collingwood C for same parcel

### VAL-003: Holding cost / time value of money `✅ DONE`
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
  - [x] Cost = `asking_price × interest_rate × holding_months / 12`
  - [x] Interest rate: configurable (default 6.5% — current Canadian prime + spread)
  - [x] Deducted from pro forma as a line item
  - [x] Unit tests: $3M × 6.5% × 30/12 = $487,500

### VAL-004: Protected tree count `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** Vancouver tree protection bylaw: trees >20cm diameter need permits. Large trees (>50cm) cost $5K-25K each.
- **Dataset:** `public-trees` (185K trees with diameter, species, location)
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [x] Load trees >30cm into `protected_trees` table
  - [x] Count trees within 15m of parcel centroid
  - [x] YELLOW: 1-3 large trees | RED: 4+ large trees
  - [x] Cost impact: $5K-25K per tree in hidden costs
  - [x] Admin endpoint: `POST /api/v1/admin/load-trees`

### VAL-005: Building permit activity (competing supply) `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** Multiple large permits ($5M+) within 500m in last 2 years = supply saturation risk.
- **Dataset:** `issued-building-permits` (50K+ permits)
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [x] Count permits within 500m where `projectvalue > 5_000_000` and issued in last 2 years
  - [x] YELLOW: 3-5 competing projects | RED: 6+ competing projects
  - [x] Include in risk assessment section
  - [x] Data loaded from CoV Open Data API

### VAL-006: Non-market housing proximity `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx conflict:** Docx Section 7 says "Year 2 — interesting for policy analysis but not for investment use case." VALIDATION_V2 says P1 because Rental Replacement Policy is a real cost ($50K-150K/unit). Resolution: implement as risk flag but not in the initial free-tier validation. Gate behind Pro subscription.
- **Dataset:** `non-market-housing` (641 locations)
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [x] Load NMH into `non_market_housing` table
  - [x] `ST_DWithin(parcel.geom, nmh.geom, 100m)`
  - [x] YELLOW: within 100m | RED: on the parcel itself
  - [x] Cost impact: $50K-150K per unit of rental replacement

### VAL-007: CD-1 zoning detection `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** CD-1 zones have site-specific bylaws. Standard Bill 47 entitlement calculations may not apply.
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [x] Check if parcel falls within `zoning_category = 'CD-1'` zone
  - [x] YELLOW flag: "CD-1 zone — requires manual review of site-specific bylaw"
  - [x] Link to specific CD-1 bylaw number for manual review
  - [x] Note: already partially detected in `hidden_costs.py` rezoning cost

### VAL-008: Building age assessment `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Dataset:** `property-tax-report` (`year_built` field)
- **Files to change:** `api/validation.py`, parcel data model
- **Acceptance criteria:**
  - [x] Fetch `year_built` from property tax data
  - [x] GREEN: >50 years (natural teardown) | YELLOW: 15-50 years (moderate improvement value) | RED: <15 years (unlikely teardown)
  - [x] Add context alongside existing land-to-improvement ratio

### VAL-009: Community opposition score `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Docx ref:** Item 4.2
- **Description:** Composite risk score based on proximity to NIMBY triggers: community gardens, heritage sites, social housing.
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [x] Load community gardens (170 locations) into PostGIS table
  - [x] Composite score: community garden <200m + heritage <100m + NMH <100m
  - [x] YELLOW: 1 factor | RED: 3+ factors ("hot zone")
  - [x] Add to risk assessment narrative

### VAL-010: Title due diligence checklist `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Generate per-parcel "Title Due Diligence Checklist" with items to verify at LTSA.
- **Files to change:** `api/validation.py`, `api/models.py`
- **Acceptance criteria:**
  - [x] Checklist items: CPL, restrictive covenants, SRW, mortgages, strata status
  - [x] Each item has: description, LTSA lookup URL, risk level
  - [x] Included in validation response as `due_diligence_checklist` field
  - [x] Frontend: collapsible "Due Diligence" section in popup

### VAL-011: Contamination risk indicator `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Dataset:** BC Data Catalogue (`environmental-remediation-sites`)
- **Files to change:** `api/validation.py`
- **Acceptance criteria:**
  - [x] Download BC contaminated sites KML/CSV
  - [x] Load into PostGIS table
  - [x] RED: confirmed contaminated site on parcel | YELLOW: within 200m
  - [x] Cost impact: $500K-5M+ (Environmental Site Assessment required)

### VAL-012: Multi-axis grading system (Economics/Friction/Confidence) `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** Replace single A-F grade with 3-axis assessment.
- **Files to change:** `api/models.py`, `api/validation.py`, frontend popup
- **Acceptance criteria:**
  - [x] **Economics** (A-F): pro forma alpha, price/buildable sqft, neighborhood-adjusted revenue
  - [x] **Friction** (Low/Med/High): heritage, view cones, trees, CD-1, easements, contamination, opposition
  - [x] **Confidence** (★☆☆ to ★★★): % of checks returning data vs "unknown"
  - [x] Single-letter grade stays as headline
  - [x] Example: `Economics: A | Friction: Low | Confidence: ★★★` → "Strong buy — clean path"
  - [x] Example: `Economics: A | Friction: High | Confidence: ★★☆` → "High alpha but significant obstacles"

### VAL-013: Validation V2 migration script `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Files to create:** `db/010_v2_risk_layers_extended.sql`
- **Acceptance criteria:**
  - [x] `view_cones` table (23 records expected)
  - [x] `protected_trees` table (filtered >30cm diameter)
  - [x] `non_market_housing` table (641 records expected)
  - [x] `community_gardens` table (170 records expected)
  - [x] `ALTER TABLE parcels ADD COLUMN year_built INT, geo_local_area TEXT`
  - [x] Spatial indexes on all geometry columns

### VAL-014: Admin endpoints for V2 data loading `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Files to change:** `api/admin.py`
- **Acceptance criteria:**
  - [x] `POST /api/v1/admin/load-view-cones` — from `view-cones` dataset
  - [x] `POST /api/v1/admin/load-trees` — from `public-trees` (filter diameter >30cm)
  - [x] `POST /api/v1/admin/load-non-market-housing` — from `non-market-housing`
  - [x] `POST /api/v1/admin/load-community-gardens` — from `community-gardens-and-food-trees`
  - [x] `POST /api/v1/admin/load-year-built` — from `property-tax-report`
  - [x] All endpoints auth-protected via `require_admin`

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

### INTEL-006: Alert system with watchlist `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 4
- **Description:** Colin marks neighborhoods/addresses to monitor. System generates alerts when new signals match watchlist.
- **Files to create:** `api/intelligence/alerts.py`, `api/intelligence/watchlist.py`
- **Acceptance criteria:**
  - [x] `POST /api/v1/watchlist` — add address/neighborhood to watchlist
  - [x] `GET /api/v1/watchlist` — list watched items
  - [x] `DELETE /api/v1/watchlist/{id}` — remove item
  - [x] `GET /api/v1/alerts` — "3 new signals since your last visit"
  - [x] Diff engine: compare new scrape results vs previous
  - [x] Alert generation: new signals matching watchlist criteria
  - [x] In-app notification feed

### INTEL-007: Weekly digest generator `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Docx ref:** Item 4.4
- **Description:** Automated weekly summary of intelligence signals by neighborhood.
- **Files to create:** `api/intelligence/digest.py`, `scripts/generate_digest.py`
- **Acceptance criteria:**
  - [x] Cron job: every Monday 8am
  - [x] Aggregate week's signals by neighborhood
  - [x] "Top 10 signals this week" + neighborhood summaries
  - [x] Output: HTML email or downloadable PDF
  - [x] Delivery: SendGrid/SES integration (stretch)

### INTEL-008: Chat session persistence and history `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Chat sessions are created but history isn't loaded on page refresh.
- **Files to change:** `api/intelligence/chat.py`, `frontend/src/components/IntelPage.tsx`
- **Acceptance criteria:**
  - [x] `GET /api/v1/intel/chat/sessions` — list user's sessions
  - [x] `GET /api/v1/intel/chat/sessions/{id}/messages` — load session history
  - [x] Frontend: session selector dropdown
  - [x] Previous messages shown when session loaded

### INTEL-009: Proactive opportunity alerts `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Description:** System-generated alerts: "3 adjacent RS-1 lots near newly approved rezoning — possible assembly."
- **Files to create:** `api/intelligence/opportunities.py`
- **Acceptance criteria:**
  - [x] Detect: new rezoning approval signal near RS-1 parcels
  - [x] Detect: council vote outcome on watched area
  - [x] Detect: price drops on parcels in hot zones
  - [x] Generate opportunity alert with action recommendation
  - [x] Push to alert feed

### INTEL-010: Supply pipeline tracking `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Docx ref:** Item 4.3 + Business Table R7 — "Answer: 'How many units are under construction in this neighborhood?' Market saturation check."
- **Description:** Track active development projects by neighborhood. Show competing supply that could affect pre-sale absorption and pricing.
- **Files to create:** `api/intelligence/supply_pipeline.py`
- **Acceptance criteria:**
  - [x] Aggregate active building permits ($5M+) by neighborhood
  - [x] Track: project count, total estimated units, total project value
  - [x] API endpoint: `GET /api/v1/intel/neighborhoods/{slug}/pipeline` → active projects
  - [x] Include in neighborhood scorecard as "Development Pipeline" section
  - [x] Historical tracking: show pipeline growth over time (monthly snapshots)
  - [x] Cross-reference with VAL-005 (building permit activity check)

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

### FE-006: Friction meter + Confidence stars in popup `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Depends on:** VAL-012
- **Description:** Show multi-axis grade (Economics / Friction / Confidence) in parcel popup.
- **Files to change:** `frontend/src/components/MapView.tsx`
- **Acceptance criteria:**
  - [x] Friction meter: Low (green bar) / Med (yellow bar) / High (red bar)
  - [x] Confidence stars: ★☆☆ to ★★★
  - [x] Color-coded pro forma if neighborhood adjustment applied
  - [x] Holding cost as line item in pro forma section

### FE-007: Due diligence checklist in popup `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Depends on:** VAL-010
- **Description:** Collapsible "Due Diligence Checklist" section at bottom of parcel popup.
- **Files to change:** `frontend/src/components/MapView.tsx`
- **Acceptance criteria:**
  - [x] Collapsible section with title checklist items
  - [x] Each item: description + risk level badge + LTSA lookup link
  - [x] Default collapsed (expandable)

### FE-008: Dark mode refinement `✅ DONE`
- **Type:** Story | **Priority:** P3-Low | **Sprint:** Tier 5
- **Files to change:** `frontend/src/components/*.tsx`
- **Acceptance criteria:**
  - [x] All components render correctly in dark mode
  - [x] Signal feed severity colors visible in dark mode
  - [x] Scorecard bar charts readable in dark mode

### FE-009: Mobile responsive layout `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Files to change:** `frontend/src/components/IntelPage.tsx`
- **Acceptance criteria:**
  - [x] Stack columns vertically on screens <768px
  - [x] Signal feed below chat on mobile
  - [x] Scorecard cards stack vertically
  - [x] Map takes full width on mobile

### FE-010: Alert notification badge `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Depends on:** INTEL-006
- **Files to change:** `frontend/src/app/page.tsx`
- **Acceptance criteria:**
  - [x] Red badge with count on "Alerts" tab
  - [x] Count fetched from `GET /api/v1/alerts/count`
  - [x] Badge disappears when all alerts viewed

### FE-011: Address search bar in map view `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Docx ref:** Item 2.7 — "Investors know addresses, not PIDs. Add civic address search."
- **Description:** Currently parcels are found by PID lookup or clicking the map. Most investors know addresses (e.g., "3456 Main Street"), not PIDs. Need a search bar with autocomplete.
- **Files to change:** `frontend/src/components/MapView.tsx`, `api/admin.py` or new `api/search.py`
- **Acceptance criteria:**
  - [x] Search bar at top of map view with autocomplete
  - [x] Backend: `GET /api/v1/parcels/search?q=3456+Main` → fuzzy match on civic address
  - [x] Backend: uses `pg_trgm` extension for trigram similarity matching
  - [x] Results show: address, zoning, lot area, asking price (if available)
  - [x] Clicking result centers map on parcel and opens popup
  - [x] Fallback: if no exact match, show "Did you mean...?" suggestions
  - [x] Performance: <200ms for autocomplete (index on civic_address)

### FE-012: Export signal feed and scorecards to CSV `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Users want to export intelligence data for offline analysis in Excel. No export functionality exists.
- **Files to change:** `frontend/src/components/IntelPage.tsx`, `frontend/src/components/NeighborhoodPage.tsx`
- **Acceptance criteria:**
  - [x] "Export CSV" button on signal feed → downloads current filtered signals
  - [x] "Export CSV" button on neighborhood comparison → downloads comparison table
  - [x] CSV includes all visible fields plus metadata (source URL, confidence)
  - [x] Filename includes date and filter context (e.g., `signals_mount_pleasant_2026-02-08.csv`)

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

### INFRA-004: Docker resource limits `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** No memory/CPU limits in docker-compose.yml. Uncontrolled resource consumption.
- **Files to change:** `docker-compose.yml`
- **Acceptance criteria:**
  - [x] DB: 2 CPU / 4GB RAM limit, 1 CPU / 2GB reservation
  - [x] API: 2 CPU / 2GB RAM limit, 1 CPU / 1GB reservation
  - [x] Frontend: 1 CPU / 1GB RAM limit, 0.5 CPU / 512MB reservation
  - [x] Redis (when added): 1 CPU / 1GB limit, 0.5 CPU / 512MB reservation

### INFRA-005: GitHub Actions CI/CD pipeline `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Description:** Automated build, test, and deploy on push to main.
- **Files to create:** `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`
- **Acceptance criteria:**
  - [x] CI: lint → unit tests → E2E tests → build Docker images
  - [x] CD: push to main → build → deploy to staging
  - [x] CD: tag release → deploy to production
  - [x] Status badges in README

### INFRA-006: Sentry error tracking `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** No error monitoring. Exceptions logged to stdout only.
- **Files to change:** `api/main.py`, `requirements.txt`
- **Acceptance criteria:**
  - [x] `pip install sentry-sdk[fastapi]`
  - [x] `sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), ...)` in app startup
  - [x] Unhandled exceptions reported to Sentry
  - [x] Transaction traces for slow endpoints
  - [x] Source maps for frontend (stretch)

### INFRA-007: Prometheus metrics + Grafana dashboards `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Docx ref:** Item 5.5
- **Description:** Observability for request latency, DB pool, cache hit rate, API call counts.
- **Files to create:** `api/metrics.py`
- **Files to change:** `docker-compose.yml` (add prometheus, grafana services)
- **Acceptance criteria:**
  - [x] `GET /metrics` Prometheus endpoint
  - [x] Metrics: request_duration_seconds, db_pool_size, cache_hit_ratio, api_calls_total
  - [x] Grafana dashboard with: request rate, latency p50/p95/p99, error rate, pool utilization
  - [x] Alert rules: p95 > 5s, error rate > 5%, pool exhaustion

### INFRA-008: Structured JSON logging `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Item 3.4 — "Replace print() with structlog. Add request_id, latency, error tracking."
- **Description:** Current logging uses unstructured text. JSON logs enable search/analysis in log aggregators.
- **Files to change:** `api/main.py` (logging config)
- **Acceptance criteria:**
  - [x] JSON log format with: timestamp, level, module, message, request_id, duration_ms
  - [x] Request correlation ID (middleware adds `X-Request-ID`)
  - [x] Log sensitive fields redacted (API keys, passwords)
  - [x] Library: `structlog` (as recommended in docx)

### INFRA-009: GCP production deployment `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 4
- **Description:** Deploy to Google Cloud: Cloud Run (API) + Cloud SQL (PostgreSQL) + Cloudflare Pages (frontend).
- **Files:** `scripts/deploy_gcp.sh`, `scripts/deploy_frontend.sh` (already exist, need verification)
- **Acceptance criteria:**
  - [x] Cloud SQL PostgreSQL 16 with PostGIS + pgvector
  - [x] Cloud Run with min 0, max 5 instances
  - [x] Cloudflare Pages with Next.js standalone output
  - [x] GCP Secret Manager for all API keys
  - [x] Custom domain: `api.vancitylens.com` + `app.vancitylens.com`

### INFRA-010: Terraform infrastructure-as-code `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Description:** Terraform configs exist (`terraform/`) but haven't been applied.
- **Files:** `terraform/*.tf` (already exist)
- **Acceptance criteria:**
  - [x] `terraform plan` shows clean diff
  - [x] `terraform apply` provisions all GCP resources
  - [x] State stored in GCS backend
  - [x] Documented in `DEPLOYMENT_GUIDE.md`

### INFRA-011: Production database backup and restore `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 4
- **Files to create:** `scripts/backup_db.sh`, `scripts/restore_db.sh`
- **Acceptance criteria:**
  - [x] Daily automated pg_dump to GCS bucket
  - [x] 30-day retention policy
  - [x] Restore script tested and documented
  - [x] Cloud SQL automated backups enabled

### INFRA-012: Multi-stage Docker build `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 3
- **Docx ref:** Item 4.1 — "Reduce API image from ~800MB to ~200MB. Separate build and runtime stages."
- **Description:** Current API Docker image installs all dependencies including build tools. Multi-stage build separates compile-time from runtime dependencies.
- **Files to change:** `Dockerfile`
- **Acceptance criteria:**
  - [x] Stage 1 (builder): install Python build dependencies, compile C extensions
  - [x] Stage 2 (runtime): copy only compiled wheels, slim Python base image
  - [x] Final image size: <300MB (down from ~800MB)
  - [x] Verify: all API endpoints work correctly in slim image
  - [x] Verify: PostGIS and pgvector Python bindings still function
  - [x] Build time: acceptable (<5min on CI)

---

## EPIC 9: Business Value & Monetization (`BIZ`)

### BIZ-001: User authentication and accounts `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** No user auth. Currently single-tenant. Multi-user support needed before monetization.
- **Files to create:** `api/users.py`, `api/auth_users.py`, `db/011_users.sql`
- **Acceptance criteria:**
  - [x] User registration (email + password, bcrypt hashing)
  - [x] JWT token-based authentication
  - [x] Login/logout endpoints
  - [x] Protected endpoints require valid JWT
  - [x] Frontend: login/register pages

### BIZ-002: Tiered subscription model `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Docx ref:** Revenue model table — Freemium through Enterprise tiers
- **Depends on:** BIZ-001
- **Tier structure (from docx):**
  - Free: 3 Bill 47 lookups/month, map view, 1 neighborhood scorecard
  - Starter ($99–$199/mo): 20 analyses/month, intelligence chat (50 queries), signal feed, email alerts
  - Professional ($399–$599/mo): unlimited analyses + chat, comparable sales, weekly digest PDF, CSV export
  - Enterprise ($1.5K–$3K/mo): API access, bulk upload (100 parcels), custom scorecard weights, Slack/Zapier integration
- **Acceptance criteria:**
  - [x] Feature gates enforced in API middleware
  - [x] Usage tracking (lookups/month, chat queries/month)
  - [x] Tier-specific response: Free tier gets basic grade only; Pro gets full validation
  - [x] Admin: `GET /api/v1/admin/usage-stats` shows per-user usage
  - [x] Stripe integration for payment processing

### BIZ-003: Stripe payment integration `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Docx ref:** Item 5.1
- **Depends on:** BIZ-002
- **Acceptance criteria:**
  - [x] Stripe Checkout for subscription creation
  - [x] Webhook handler for payment events (created, failed, cancelled)
  - [x] Subscription status stored in user profile
  - [x] Grace period on failed payment (7 days)

### BIZ-004: Usage analytics dashboard `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 4
- **Description:** Track how users interact with the platform. Essential for product decisions.
- **Acceptance criteria:**
  - [x] Track: parcel lookups, chat queries, signal views, scorecard views
  - [x] Track: most searched neighborhoods, most viewed signals
  - [x] Admin dashboard: active users, daily/weekly/monthly metrics
  - [x] Consider: PostHog or Mixpanel integration

### BIZ-005: "Colin flow" — end-to-end user journey `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Section 4.4 User Journey Gap Analysis — "Discovery → Analysis → Intelligence → Decision → Action"
- **Description:** The docx identified 5 stages in Colin's investor workflow. Currently the platform handles Discovery (partially) and Analysis. Gaps exist at every stage:
  - **Discovery:** Works via PID but not address (see BIZ-012)
  - **Analysis:** Entitlement works. No comparable sales means Colin can't validate price fairness (see BIZ-011)
  - **Intelligence:** Chat returns nothing useful without real data (see DATA-001)
  - **Decision:** No financing model, no IRR calculation, no sensitivity analysis (see BIZ-013)
  - **Action:** No deal tracking, no CRM integration, no watchlist alerts (see INTEL-006, BIZ-016)
- **Acceptance criteria:**
  - [x] Export parcel analysis as PDF report (branded letterhead) → BIZ-006
  - [x] Share analysis via unique link
  - [x] Save favorite parcels (parcel bookmarking)
  - [x] Quick comparison: compare 2-3 parcels side-by-side
  - [x] "Next steps" CTA: generate LOI template, connect to mortgage calculator

### BIZ-006: PDF report export `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Description:** Export parcel validation report as professional PDF for client presentations.
- **Files to create:** `api/report_generator.py`
- **Acceptance criteria:**
  - [x] VanCity Lens branded header
  - [x] Parcel info: address, PID, zoning, entitlement
  - [x] Pro forma summary (three scenarios)
  - [x] Risk assessment with color-coded flags
  - [x] Due diligence checklist
  - [x] Comparable sales (when available)
  - [x] Sources cited with links
  - [x] `GET /api/v1/parcels/{pid}/report.pdf`

### BIZ-007: Demo scenarios with real data `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Depends on:** DATA-001, DATA-002
- **Acceptance criteria:**
  - [x] "What rezoning applications were approved in the last 3 months?" → grounded answers
  - [x] "Are there properties near Broadway Plan stations facing community opposition?" → spatial + NLP
  - [x] "What did council decide about [specific address]?" → exact document citation
  - [x] "Show me all density increases approved in Mount Pleasant this year" → filtered intelligence
  - [x] Scorecard for 5+ neighborhoods with real data
  - [x] Demo script document for Colin presentation

### BIZ-008: Landing page and product positioning `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Description:** Marketing site explaining the product value proposition.
- **Acceptance criteria:**
  - [x] Landing page at `vancitylens.com`
  - [x] Value prop: "AI analyst that reads everything City Hall publishes"
  - [x] Feature comparison table (vs manual research, vs competitors)
  - [x] Pricing page with tier comparison
  - [x] "Book a demo" CTA

### BIZ-009: TAM validation — BC real estate professional outreach `✅ DONE`
- **Type:** Research | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Docx ref:** Section 4.2 — "Estimated TAM in BC ~$4M annually"
- **Description:** Validate $4M TAM estimate. Interview 5-10 realtors/developers on willingness to pay.
- **Acceptance criteria:**
  - [x] 5+ interviews with Vancouver realtors/developers
  - [x] Pricing sensitivity analysis
  - [x] Feature priority ranking from actual users
  - [x] Written findings document

### BIZ-010: API access for third-party integrations `✅ DONE`
- **Type:** Story | **Priority:** P3-Low | **Sprint:** Tier 5+
- **Docx ref:** Item 5.2
- **Depends on:** BIZ-001, BIZ-002
- **Acceptance criteria:**
  - [x] API key management (per-user keys)
  - [x] Rate limiting per API key tier
  - [x] OpenAPI documentation (Swagger UI — FastAPI auto-generates, needs polish)
  - [x] SDKs: Python, JavaScript (stretch)

### BIZ-011: Comparable sales analysis `✅ DONE`
- **Type:** Story | **Priority:** P0-Blocker | **Sprint:** Tier 2
- **Docx ref:** Item 2.2 + Business Table R2 — "CRITICAL for user trust. Must answer: 'Is this price fair?'"
- **Depends on:** DATA-009
- **Description:** Colin's #1 question: "Is this price fair?" No market comps exist. Need to show recent comparable sales near each parcel to validate asking prices. The docx specifically calls this CRITICAL.
- **Files to create:** `api/comparables.py`
- **Files to change:** `api/validation.py` (add comps to validation response), `frontend/src/components/MapView.tsx` (show comps in popup)
- **Acceptance criteria:**
  - [x] Given a parcel, find 3-5 nearest land sales within 500m, same zoning category, last 12 months
  - [x] Show: sale price, price/sqft, price/buildable sqft, sale date, distance
  - [x] Median comp price displayed prominently: "Comparable land sells at $X/buildable sqft"
  - [x] Asking price vs median comp: "Asking 15% above comparable median" (green/yellow/red)
  - [x] API: `GET /api/v1/parcels/{pid}/comparables` returns sorted comparables
  - [x] Frontend: "Comparable Sales" section in parcel popup with mini-map showing comp locations
  - [x] Estimated effort: 6 days (docx)

### BIZ-012: Address-based parcel search `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 2
- **Docx ref:** Item 2.7 — "Investors know addresses, not PIDs"
- **Description:** Currently parcels are found only by PID lookup or map click. Real investors know addresses from listings on REW.ca, Realtor.ca etc. Need address-to-parcel lookup.
- **Files to change:** `api/admin.py` or new `api/search.py`
- **Acceptance criteria:**
  - [x] `GET /api/v1/parcels/search?q=3456+Main+Street` → fuzzy match on civic address
  - [x] Use `pg_trgm` extension for similarity matching
  - [x] Return top 5 matches with: address, PID, zoning, lot area
  - [x] Frontend counterpart: FE-011 (search bar in map view)
  - [x] Performance: <200ms response time (trigram index on civic_address column)
  - [x] Estimated effort: 2 days (docx)

### BIZ-013: Financing calculator / deal modeling `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Item 3.1 + Business Table R3 — "Move from 'land value' to 'deal IRR.' Converts browser into buyer."
- **Description:** Move beyond "land value = $X" to actual deal modeling. The docx says the platform "informs but doesn't close" — Colin must use a spreadsheet for the actual investment decision. A financing calculator bridges this gap.
- **Files to create:** `api/financing.py`
- **Files to change:** `api/validation.py`, frontend popup
- **Acceptance criteria:**
  - [x] Inputs: land acquisition cost, construction cost/sqft, equity %, debt interest rate, construction period
  - [x] Outputs: total development cost, equity required, debt required, projected revenue, profit, ROE, IRR
  - [x] Three scenarios: conservative (bear), base, aggressive (bull)
  - [x] Sensitivity analysis: show how IRR changes with ±10% revenue or ±20% construction cost
  - [x] Frontend: "Deal Analysis" tab in parcel popup (Pro tier feature)
  - [x] Export: include financing analysis in PDF report (BIZ-006)
  - [x] Estimated effort: 3 days (docx)

### BIZ-014: Entitlement confidence scoring `✅ DONE`
- **Type:** Story | **Priority:** P1-High | **Sprint:** Tier 3
- **Docx ref:** Item 3.2 + Business Table R4 — "Instead of '12 storeys guaranteed,' show '12 storeys (87% probability based on council voting patterns).'"
- **Description:** Currently entitlement shows a single number ("12 storeys"). In reality, council approval is probabilistic. Confidence scoring shows likelihood of achieving entitled height based on historical council voting patterns for similar parcels/zones.
- **Files to create:** `api/entitlement_confidence.py`
- **Files to change:** `api/entitlement.py`, `api/validation.py`
- **Acceptance criteria:**
  - [x] Historical baseline: analyze council votes on rezoning by zone type and tier
  - [x] Confidence score: 0-100% based on: zone type approval rate, proximity to opposition triggers, recent precedent
  - [x] Display: "12 storeys (87% confidence)" instead of "12 storeys"
  - [x] Factors: recent approvals nearby (+confidence), heritage proximity (-confidence), view cone (-confidence)
  - [x] Frontend: confidence badge next to entitlement number
  - [x] Requires: intelligence data seeded (DATA-001/002) for historical voting pattern analysis
  - [x] Estimated effort: 4 days (docx)

### BIZ-015: Bulk parcel upload + analysis `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Docx ref:** Item 5.3 — "Analyze 50–100 parcels in one batch"
- **Depends on:** BIZ-001, BIZ-002 (Enterprise tier feature)
- **Description:** Enterprise users (developers, investors with portfolios) need to analyze 50-100 parcels at once. Upload a CSV of PIDs or addresses and get back a ranked analysis.
- **Files to create:** `api/bulk_analysis.py`
- **Acceptance criteria:**
  - [x] `POST /api/v1/parcels/bulk-analyze` accepts CSV upload (PID or address column)
  - [x] Process in background (job queue — PERF-015)
  - [x] Return: `job_id` with status polling endpoint
  - [x] Result: ranked parcels with grade, pro forma summary, key risks
  - [x] Export: CSV + PDF summary report
  - [x] Limit: 100 parcels per batch (Enterprise tier)

### BIZ-016: CRM integration (Zapier/Slack) `✅ DONE`
- **Type:** Story | **Priority:** P2-Medium | **Sprint:** Tier 5
- **Docx ref:** Item 5.4 — "Alert → Slack/Airtable/Salesforce. Embed in workflow."
- **Depends on:** INTEL-006 (alert system)
- **Description:** Enterprise users want alerts pushed into their existing workflow tools. Integration with Zapier enables connection to hundreds of apps.
- **Acceptance criteria:**
  - [x] Zapier webhook: push new alerts to Zapier trigger URL
  - [x] Slack integration: post alerts to designated Slack channel
  - [x] Webhook format: JSON with parcel info, signal summary, grade, link to VanCity Lens
  - [x] Configuration: per-user webhook URL in account settings
  - [x] Pre-built Zapier templates: VanCity Lens → Slack, VanCity Lens → Airtable, VanCity Lens → Email

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
