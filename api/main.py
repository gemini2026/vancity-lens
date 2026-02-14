"""
VanCity Lens — FastAPI Application
Bill 47 Entitlement Engine API
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .audit import AuditMiddleware
from .compression import CompressionMiddleware
from .db import db
from .cache import CacheManager
from .entitlement import ParcelNotFoundError, compute_entitlement
from .models import ParcelEntitlementResponse
from .admin import router as admin_router
from .intelligence.routes import router as intelligence_router
from .intelligence.digest_routes import admin_router as digest_admin_router
from .intelligence.pipeline_routes import admin_router as pipeline_admin_router
from .auth_routes import router as auth_router
from .api_key_routes import router as api_key_router
from .analytics_routes import router as analytics_router
from .checklist import router as checklist_router
from .comparable_sales_routes import router as comparable_sales_router
from .csv_export_routes import router as csv_export_router
from .metrics_routes import router as metrics_router
from .parcel_search import router as parcel_search_router
from .due_diligence_routes import router as due_diligence_router
from .report_routes import router as report_router
from .stripe_routes import router as stripe_router
from .subscription_routes import router as subscription_router
from .subscription_routes import admin_router as subscription_admin_router
from .view_cones_routes import router as view_cones_router
from .financing_routes import router as financing_router
from .webhook_routes import router as webhook_router
from .bulk_analysis_routes import router as bulk_analysis_router
from .geocoding import router as geocoding_router
from .tasks.routes import router as jobs_router
from .share_routes import router as share_router
from .saved_views_routes import router as saved_views_router
from .org_routes import router as org_router
from .rate_limit import rate_limit_general
from .json_logging import setup_json_logging
from .versioning import APIVersionMiddleware, get_api_versions
from .error_tracking import init_error_tracking, get_sentry_middleware
from .streaming import (
    StreamingGeoJSONResponse,
    StreamingJSONResponse,
    async_geojson_generator,
    async_json_generator,
)
from .pagination import MaxPageSizeMiddleware, paginate

logger = logging.getLogger(__name__)


# ── Security Headers Middleware ───────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if os.getenv("VANCITY_ENV") == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


# ── Rate Limiting Middleware ──────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit general API endpoints (30 req/min per IP)."""

    async def dispatch(self, request: Request, call_next):
        # Apply rate limiting to general API endpoints only
        # LLM endpoints will use stricter limits via Depends()
        try:
            await rate_limit_general(request)
        except HTTPException as e:
            if e.status_code == 429:
                # Pass through rate limit errors with headers
                return Response(
                    content=e.detail,
                    status_code=429,
                    headers=e.headers,
                )
            raise

        response = await call_next(request)
        return response


# ── Request ID Middleware ─────────────────────────────────────

class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate and add request_id to each request for tracing."""

    async def dispatch(self, request: Request, call_next):
        # Generate or use existing request_id
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Add to request state for use in route handlers
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request_id to response headers
        response.headers["X-Request-ID"] = request_id

        return response


# ── Lifespan ─────────────────────────────────────────────────

def _configure_audit_logger():
    """Configure the dedicated audit logger with JSON-lines handler."""
    audit_logger = logging.getLogger("audit")

    # Clear any existing handlers
    audit_logger.handlers = []

    # Set up a file handler for audit events
    audit_log_path = os.getenv("AUDIT_LOG_PATH", "logs/audit.log")

    # Ensure logs directory exists
    log_dir = os.path.dirname(audit_log_path)
    if log_dir and not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create audit log directory: {e}")
            return

    try:
        handler = logging.FileHandler(audit_log_path)
        # Use JSON formatter (audit messages are already JSON)
        handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger.addHandler(handler)
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False
        logger.info(f"Audit logger configured: {audit_log_path}")
    except Exception as e:
        logger.warning(f"Could not configure audit logger: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize error tracking first (before other initialization)
    init_error_tracking()
    # Configure JSON logging
    setup_json_logging()

    # Initialize cache manager (PERF-005)
    cache_manager = CacheManager()
    await cache_manager.initialize()
    app.state.cache = cache_manager

    await db.connect()
    # Expose the pool on app.state so intelligence routes can access it
    app.state.pool = db.pool
    # Start pool monitor background check (VCL-87 / PERF-013)
    if db.monitor:
        await db.monitor.start_background_check()
    # Configure audit logging
    _configure_audit_logger()
    logger.info("VanCity Lens API started")

    # Start scheduled materialized view refresh (VCL-79 / PERF-011)
    from .intelligence.materialized_views import ScheduledRefresh
    scheduled_refresh = ScheduledRefresh(
        db_pool=db.pool,
        interval_seconds=int(os.getenv("MV_REFRESH_INTERVAL_SECONDS", "3600"))
    )
    await scheduled_refresh.start()
    app.state.scheduled_refresh = scheduled_refresh

    # Start scraper scheduler (VCL-80 / DATA-004)
    from .intelligence.scheduler import ScraperScheduler
    scheduler = ScraperScheduler(db.pool)

    # Register actual scraper functions (use correct function names per module)
    from .intelligence.scraper_council import scrape_and_store as scrape_council
    from .intelligence.scraper_dpb import download_and_store as scrape_dpb
    from .intelligence.scraper_rezoning import scrape_and_store as scrape_rezoning
    from .intelligence.scraper_news import scrape_news_feeds as scrape_news
    from .intelligence.scraper_opendata import run_all_scrapers as scrape_opendata

    scheduler.register_scraper("council", scrape_council, "0 6 * * *", enabled=True)
    scheduler.register_scraper("dpb", scrape_dpb, "0 7 * * *", enabled=True)
    scheduler.register_scraper("rezoning", scrape_rezoning, "0 8 * * *", enabled=True)
    scheduler.register_scraper("news", scrape_news, "0 */6 * * *", enabled=True)
    scheduler.register_scraper("opendata", scrape_opendata, "0 3 * * 1", enabled=True)

    # Start background loop if enabled
    if os.getenv("SCRAPER_SCHEDULER_ENABLED", "false").lower() == "true":
        await scheduler.start_background_loop()

    app.state.scheduler = scheduler

    yield

    # Stop scheduler on shutdown
    try:
        await scheduler.stop()
    except Exception as e:
        logger.warning(f"Error stopping scheduler: {e}")

    # Stop scheduled refresh on shutdown
    try:
        await scheduled_refresh.stop()
    except Exception as e:
        logger.warning(f"Error stopping scheduled refresh: {e}")

    # Stop pool monitor on shutdown (VCL-87 / PERF-013)
    if db.monitor:
        try:
            await db.monitor.stop_background_check()
        except Exception as e:
            logger.warning(f"Error stopping pool monitor: {e}")

    # Shutdown cache manager
    await cache_manager.shutdown()
    await db.disconnect()
    logger.info("VanCity Lens API shutdown")


# ── App ──────────────────────────────────────────────────────

app = FastAPI(
    title="VanCity Lens — Bill 47 Engine",
    description=(
        "Geospatial entitlement engine for Vancouver real estate. "
        "Identifies density uplift from BC's Transit-Oriented Areas legislation."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: environment-based origins (SEC-006 / VCL-15)
# Production MUST use explicit origins from ALLOWED_ORIGINS env var.
# Wildcard "*" is only allowed in non-production environments.
_env = os.getenv("VANCITY_ENV", "development")
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "")
_cors_origins_env = os.environ.get("CORS_ORIGINS", "")
_dev_origins = ["http://localhost:3000", "http://localhost:3001",
                "http://localhost:3002", "http://localhost:3003"]

if _allowed_origins_env:
    _cors_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
elif _cors_origins_env:
    _cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    _cors_origins = _dev_origins

# Block wildcard in production
if _env == "production" and "*" in _cors_origins:
    logger.warning("CORS wildcard '*' rejected in production — using empty origins list")
    _cors_origins = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Key"],
)

# Response compression for JSON/GeoJSON (VCL-71 / PERF-009)
app.add_middleware(CompressionMiddleware)

# Security headers on all responses
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting for general API endpoints (VCL-20 / SEC-008)
app.add_middleware(RateLimitMiddleware)

# Request ID middleware for request tracing (VCL-53 / INFRA-008)
app.add_middleware(RequestIdMiddleware)

# API versioning strategy (VCL-23 / SEC-009)
app.add_middleware(APIVersionMiddleware)

# Audit logging for admin operations (VCL-35 / SEC-012)
app.add_middleware(AuditMiddleware)

# Sentry error tracking (VCL-45 / INFRA-006)
sentry_middleware = get_sentry_middleware()
if sentry_middleware:
    app.add_middleware(sentry_middleware)

# Frontend pagination enforcement (VCL-83 / PERF-012)
app.add_middleware(MaxPageSizeMiddleware)

app.include_router(admin_router)
app.include_router(intelligence_router)
app.include_router(auth_router)
app.include_router(api_key_router)
app.include_router(analytics_router)
app.include_router(checklist_router)
app.include_router(comparable_sales_router)
app.include_router(csv_export_router)
app.include_router(metrics_router)
app.include_router(parcel_search_router)
app.include_router(due_diligence_router)
app.include_router(report_router)
app.include_router(stripe_router)
app.include_router(subscription_router)
app.include_router(subscription_admin_router)
app.include_router(digest_admin_router, prefix="/api/v1/admin")
app.include_router(pipeline_admin_router, prefix="/api/v1/admin")
app.include_router(view_cones_router)
app.include_router(financing_router)
app.include_router(webhook_router)
app.include_router(bulk_analysis_router)
app.include_router(geocoding_router)
app.include_router(jobs_router)
app.include_router(share_router)
app.include_router(saved_views_router)
app.include_router(org_router)


# ── Routes ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Deep liveness check — verifies database connectivity."""
    checks = {"engine": "bill47"}
    try:
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 AS ok, count(*) AS tables "
                "FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            checks["db"] = "connected"
            checks["tables"] = row["tables"]
    except Exception as e:
        checks["db"] = f"error: {str(e)[:100]}"
        return {"status": "degraded", **checks}

    # Include pool health (VCL-87 / PERF-013)
    if db.monitor:
        pool_health = db.monitor.get_health_status()
        checks["pool"] = {
            "status": pool_health["status"],
            "utilization_pct": round(pool_health["utilization_pct"], 1),
        }

    checks["status"] = "ok"
    return checks


@app.get("/ready")
async def ready(response: Response):
    """Readiness check — returns 503 when dependencies are missing/unavailable."""
    checks: dict[str, object] = {"engine": "bill47"}

    # External keys: required for the intelligence endpoints to function.
    checks["anthropic_key"] = bool(os.getenv("ANTHROPIC_API_KEY"))
    checks["cohere_key"] = bool(os.getenv("COHERE_API_KEY"))

    # Cache health check (PERF-005)
    try:
        cache_manager = getattr(app.state, "cache", None)
        if cache_manager:
            cache_health = await cache_manager.health_check()
            checks["cache"] = "healthy" if cache_health else "unhealthy"
        else:
            checks["cache"] = "not_initialized"
    except Exception as e:
        checks["cache"] = f"error: {str(e)[:100]}"

    try:
        async with db.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = True
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"

    # Check pool health status (VCL-87 / PERF-013)
    if db.monitor:
        pool_health = db.monitor.get_health_status()
        checks["pool_health"] = pool_health["status"]
        # Fail readiness if pool is unhealthy
        if pool_health["status"] == "unhealthy":
            checks["database"] = f"error: pool unhealthy ({pool_health['reason']})"

    is_ready = (
        checks.get("database") is True
        and checks.get("anthropic_key") is True
        and checks.get("cohere_key") is True
    )

    response.status_code = 200 if is_ready else 503
    return {"ready": is_ready, "checks": checks}


@app.get(
    "/api/versions",
    summary="List available API versions",
    description=(
        "Returns information about all available API versions, including "
        "deprecation status, sunset dates, and URL prefixes. "
        "Used by clients to negotiate API version compatibility."
    ),
    tags=["versioning"],
)
async def list_api_versions():
    """List all available API versions with their metadata (VCL-23 / SEC-009)."""
    return await get_api_versions()


@app.get(
    "/api/v1/parcels/{pid}/entitlement",
    response_model=ParcelEntitlementResponse,
    summary="Get Bill 47 entitlement for a parcel",
    description=(
        "The Magic Trick endpoint. Given a BC Land Title PID, returns:\n"
        "- Which TOA tier(s) the parcel falls in\n"
        "- Entitled height (storeys) and FSR\n"
        "- Estimated land value vs. asking price\n"
        "- A traffic-light signal (high_alpha / moderate / low / none)"
    ),
)
async def get_entitlement(
    pid: str,
    price_per_sqft: Decimal = Query(
        default=Decimal("800"),
        ge=100,
        le=3000,
        description="$/sqft of buildable area for value estimation",
    ),
    response: Response = None,
):
    """
    **The Red Dot** — Colin clicks a listing, sees the hidden value.
    """
    if response:
        response.headers["X-API-Version"] = "1"
    async with db.acquire() as conn:
        try:
            result = await compute_entitlement(conn, pid, price_per_sqft)
        except ParcelNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Parcel {pid} not found in our fabric. Is the PID correct?"
            )
    return result


@app.get(
    "/api/v1/parcels/nearest",
    summary="Find nearest parcel to a coordinate",
)
async def nearest_parcel(
    lng: float = Query(..., description="Longitude"),
    lat: float = Query(..., description="Latitude"),
    radius_m: int = Query(default=100, description="Search radius in metres"),
    response: Response = None,
):
    """Given a map click coordinate, find the nearest parcel."""
    if response:
        response.headers["X-API-Version"] = "1"
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT pid, civic_address, current_zoning,
                ROUND(ST_Distance(
                    ST_Transform(ST_Centroid(geom), 3005),
                    ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 3005)
                )::numeric, 1) AS distance_m,
                ST_X(ST_Centroid(geom)) AS centroid_lng,
                ST_Y(ST_Centroid(geom)) AS centroid_lat
            FROM parcels
            WHERE ST_DWithin(
                ST_Transform(geom, 3005),
                ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 3005),
                $3
            )
            ORDER BY ST_Distance(
                ST_Transform(ST_Centroid(geom), 3005),
                ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 3005)
            )
            LIMIT 1
        """, lng, lat, radius_m)
        if not row:
            raise HTTPException(status_code=404, detail="No parcel found within radius")
        return dict(row)


@app.get(
    "/api/v1/opportunities",
    summary="Top alpha opportunities for map markers",
)
async def top_opportunities(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    limit: int = Query(default=None, le=500, description="(Deprecated: use page_size instead) Legacy limit parameter"),
    response: Response = None,
):
    """Returns top alpha parcels for rendering as markers on the map.
    Prioritises parcels with asking prices, then ranks by storey uplift.
    Uses a CTE to properly deduplicate (pick best tier per parcel)
    before applying the final sort + limit.

    Supports both new pagination (page/page_size) and legacy (limit/offset) parameters.
    """
    if response:
        response.headers["X-API-Version"] = "1"

    # Backward compatibility: if legacy limit is provided, use it as page_size
    if limit is not None:
        page_size = min(limit, 500)

    # Compute offset from page and page_size
    offset = (page - 1) * page_size

    async with db.acquire() as conn:
        # Get total count of opportunities
        count_row = await conn.fetchrow("""
            WITH deduped AS (
                SELECT DISTINCT ON (p.pid)
                    p.pid
                FROM parcels p
                JOIN toa_buffers b ON ST_Intersects(p.geom, b.geom)
                JOIN transit_stations s ON s.id = b.station_id
                WHERE p.lot_area_sqm BETWEEN 200 AND 10000
                ORDER BY p.pid, b.tier
            )
            SELECT count(*) as total FROM deduped
        """)
        total_count = count_row['total'] if count_row else 0

        # Fetch paginated results
        rows = await conn.fetch("""
            WITH deduped AS (
                SELECT DISTINCT ON (p.pid)
                    p.pid, p.civic_address, p.current_zoning, p.asking_price,
                    p.assessed_value, p.lot_area_sqm,
                    ST_X(ST_Centroid(p.geom)) AS lng,
                    ST_Y(ST_Centroid(p.geom)) AS lat,
                    b.station_name, b.tier, b.max_storeys, b.max_fsr,
                    COALESCE(p.current_height, 0) AS current_height,
                    COALESCE(p.current_fsr, 0) AS current_fsr_val,
                    GREATEST(b.max_storeys, COALESCE(p.current_height, 0)) AS effective_storeys,
                    GREATEST(b.max_fsr, COALESCE(p.current_fsr, 0)) AS effective_fsr,
                    GREATEST(0, b.max_storeys - COALESCE(p.current_height, 0)) AS storey_uplift,
                    ROUND(ST_Distance(
                        ST_Transform(ST_Centroid(p.geom), 3005),
                        ST_Transform(s.geom, 3005)
                    )::numeric, 0) AS dist_m,
                    ROUND((p.lot_area_sqm * GREATEST(b.max_fsr, COALESCE(p.current_fsr, 0)) * 10.7639 * 800)::numeric, 0) AS est_value,
                    (COALESCE(p.current_height, 0) > b.max_storeys
                     OR COALESCE(p.current_fsr, 0) > b.max_fsr) AS already_exceeds
                FROM parcels p
                JOIN toa_buffers b ON ST_Intersects(p.geom, b.geom)
                JOIN transit_stations s ON s.id = b.station_id
                WHERE p.lot_area_sqm BETWEEN 200 AND 10000
                ORDER BY p.pid, b.tier
            )
            SELECT * FROM deduped
            ORDER BY
                (asking_price IS NOT NULL) DESC,
                storey_uplift DESC,
                est_value DESC NULLS LAST
            LIMIT $1 OFFSET $2
        """, page_size, offset)

        return paginate(
            items=[dict(r) for r in rows],
            total=total_count,
            page=page,
            page_size=page_size,
        )


@app.get(
    "/api/v1/parcels/{pid}/nearby-stations",
    summary="List nearest transit stations to a parcel",
)
async def nearby_stations(pid: str, response: Response = None):
    """Debug helper: see which stations are near a parcel."""
    if response:
        response.headers["X-API-Version"] = "1"
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.name, s.line, s.type::text,
                ROUND(ST_Distance(
                    ST_Transform(ST_Centroid(p.geom), 3005),
                    ST_Transform(s.geom, 3005)
                )::numeric, 0) AS distance_m
            FROM parcels p, transit_stations s
            WHERE p.pid = $1
            ORDER BY ST_Distance(
                ST_Transform(ST_Centroid(p.geom), 3005),
                ST_Transform(s.geom, 3005)
            )
            LIMIT 5
            """,
            pid,
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Parcel {pid} not found")
        return [dict(r) for r in rows]


@app.get(
    "/api/v1/toa/geojson",
    summary="TOA buffer zones as GeoJSON (for map overlay)",
)
async def toa_geojson(response: Response = None):
    """Returns all TOA buffer polygons as a GeoJSON FeatureCollection."""
    if response:
        response.headers["X-API-Version"] = "1"
    async with db.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                station_name,
                tier,
                max_storeys,
                max_fsr,
                ST_AsGeoJSON(geom)::json AS geometry
            FROM toa_buffers
            ORDER BY station_name, tier
        """)
        features = [
            {
                "type": "Feature",
                "properties": {
                    "station": r["station_name"],
                    "tier": r["tier"],
                    "max_storeys": r["max_storeys"],
                    "max_fsr": float(r["max_fsr"]),
                },
                "geometry": r["geometry"],
            }
            for r in rows
        ]
        return {
            "type": "FeatureCollection",
            "features": features,
        }


# ── Streaming GeoJSON Endpoints (VCL-67 / PERF-008) ──────────────────


@app.get(
    "/api/v1/toa/geojson/stream",
    summary="TOA buffer zones as streaming GeoJSON (memory-efficient)",
    description=(
        "Streams TOA buffer polygons as GeoJSON FeatureCollection. "
        "More memory-efficient than /api/v1/toa/geojson for large datasets. "
        "Uses server-side cursor to avoid loading all features into memory."
    ),
)
async def toa_geojson_stream(response: Response = None):
    """
    Stream all TOA buffer polygons as a GeoJSON FeatureCollection incrementally.

    Unlike the non-streaming endpoint, this does not load all features into memory
    before responding, making it suitable for large datasets.
    """
    if response:
        response.headers["X-API-Version"] = "1"

    async def generate():
        query = """
            SELECT
                station_name,
                tier,
                max_storeys,
                max_fsr,
                ST_AsGeoJSON(geom)::json AS geometry
            FROM toa_buffers
            ORDER BY station_name, tier
        """

        async for row in async_geojson_generator(db.pool, query):
            # Transform row into proper GeoJSON Feature
            yield {
                "type": "Feature",
                "properties": {
                    "station": row["station_name"],
                    "tier": row["tier"],
                    "max_storeys": row["max_storeys"],
                    "max_fsr": float(row["max_fsr"]),
                },
                "geometry": row["geometry"],
            }

    return StreamingGeoJSONResponse(generate())


@app.get(
    "/api/v1/opportunities/stream",
    summary="Top alpha opportunities as streaming JSON (memory-efficient)",
    description=(
        "Streams top alpha parcels for map markers. "
        "Uses server-side cursor for memory efficiency on large result sets."
    ),
)
async def top_opportunities_stream(
    limit: int = Query(default=50, le=500),
    response: Response = None,
):
    """
    Stream top alpha parcels for rendering as markers on the map.

    Prioritises parcels with asking prices, then ranks by storey uplift.
    Streams results incrementally without loading all into memory.
    """
    if response:
        response.headers["X-API-Version"] = "1"

    async def generate():
        query = """
            WITH deduped AS (
                SELECT DISTINCT ON (p.pid)
                    p.pid, p.civic_address, p.current_zoning, p.asking_price,
                    p.assessed_value, p.lot_area_sqm,
                    ST_X(ST_Centroid(p.geom)) AS lng,
                    ST_Y(ST_Centroid(p.geom)) AS lat,
                    b.station_name, b.tier, b.max_storeys, b.max_fsr,
                    COALESCE(p.current_height, 0) AS current_height,
                    COALESCE(p.current_fsr, 0) AS current_fsr_val,
                    GREATEST(b.max_storeys, COALESCE(p.current_height, 0)) AS effective_storeys,
                    GREATEST(b.max_fsr, COALESCE(p.current_fsr, 0)) AS effective_fsr,
                    GREATEST(0, b.max_storeys - COALESCE(p.current_height, 0)) AS storey_uplift,
                    ROUND(ST_Distance(
                        ST_Transform(ST_Centroid(p.geom), 3005),
                        ST_Transform(s.geom, 3005)
                    )::numeric, 0) AS dist_m,
                    ROUND((p.lot_area_sqm * GREATEST(b.max_fsr, COALESCE(p.current_fsr, 0)) * 10.7639 * 800)::numeric, 0) AS est_value,
                    (COALESCE(p.current_height, 0) > b.max_storeys
                     OR COALESCE(p.current_fsr, 0) > b.max_fsr) AS already_exceeds
                FROM parcels p
                JOIN toa_buffers b ON ST_Intersects(p.geom, b.geom)
                JOIN transit_stations s ON s.id = b.station_id
                WHERE p.lot_area_sqm BETWEEN 200 AND 10000
                ORDER BY p.pid, b.tier
            )
            SELECT * FROM deduped
            ORDER BY
                (asking_price IS NOT NULL) DESC,
                storey_uplift DESC,
                est_value DESC NULLS LAST
            LIMIT $1
        """

        async for row in async_json_generator(db.pool, query, params=[limit]):
            yield dict(row)

    return StreamingJSONResponse(generate())


@app.get(
    "/api/v1/intel/signals/geojson/stream",
    summary="Intelligence signals as streaming GeoJSON",
    description=(
        "Streams intelligence signals with spatial data as GeoJSON FeatureCollection. "
        "Uses server-side cursor for memory efficiency on large signal datasets."
    ),
)
async def signals_geojson_stream(
    neighborhood: Optional[str] = Query(None, description="Filter by neighborhood"),
    signal_type: Optional[str] = Query(None, description="Filter by signal type"),
    severity_min: Optional[str] = Query(None, description="Minimum severity level"),
    date_from: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    limit: int = Query(default=100, le=1000, description="Maximum number of signals"),
    response: Response = None,
):
    """
    Stream intelligence signals with spatial data as a GeoJSON FeatureCollection.

    Supports filtering by neighborhood, signal type, severity, and date range.
    Results streamed incrementally without loading all signals into memory.
    """
    if response:
        response.headers["X-API-Version"] = "1"

    async def generate():
        # Build WHERE clause dynamically based on filters
        where_clauses = []
        params = []
        param_count = 1

        if neighborhood:
            where_clauses.append(f"s.neighborhood = ${param_count}")
            params.append(neighborhood)
            param_count += 1

        if signal_type:
            where_clauses.append(f"s.signal_type = ${param_count}")
            params.append(signal_type)
            param_count += 1

        if severity_min:
            severity_levels = ["info", "low", "medium", "high", "critical"]
            if severity_min in severity_levels:
                min_index = severity_levels.index(severity_min)
                where_clauses.append(
                    f"(s.severity = ANY(${param_count}::text[]))"
                )
                params.append(severity_levels[min_index:])
                param_count += 1

        if date_from:
            where_clauses.append(f"s.event_date >= ${param_count}::date")
            params.append(date_from)
            param_count += 1

        if date_to:
            where_clauses.append(f"s.event_date <= ${param_count}::date")
            params.append(date_to)
            param_count += 1

        where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"
        params.append(limit)

        query = f"""
            SELECT
                s.id,
                s.signal_type,
                s.summary,
                s.headline,
                s.neighborhood,
                s.severity,
                s.confidence,
                s.event_date,
                s.source_title,
                s.source_url,
                ST_AsGeoJSON(
                    ST_DWithin(
                        ST_SetSRID(ST_MakePoint(
                            COALESCE(s.lng, 0),
                            COALESCE(s.lat, 0)
                        ), 4326),
                        ST_SetSRID(ST_MakePoint(0, 0), 4326),
                        100
                    ) AS dummy
                ) AS geometry
            FROM signals s
            WHERE {where_clause}
            ORDER BY s.event_date DESC
            LIMIT ${param_count}
        """

        async for row in async_geojson_generator(db.pool, query, params=params):
            # Transform row into GeoJSON Feature
            yield {
                "type": "Feature",
                "properties": {
                    "id": row.get("id"),
                    "signal_type": row.get("signal_type"),
                    "summary": row.get("summary"),
                    "headline": row.get("headline"),
                    "neighborhood": row.get("neighborhood"),
                    "severity": row.get("severity"),
                    "confidence": row.get("confidence"),
                    "event_date": str(row.get("event_date")) if row.get("event_date") else None,
                    "source_title": row.get("source_title"),
                    "source_url": row.get("source_url"),
                },
                "geometry": row.get("geometry"),
            }

    return StreamingGeoJSONResponse(generate())
