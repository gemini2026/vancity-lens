"""
VanCity Lens — FastAPI Application
Bill 47 Entitlement Engine API
"""

import logging
import os
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .db import db
from .entitlement import ParcelNotFoundError, compute_entitlement
from .models import EntitlementRequest, ParcelEntitlementResponse
from .admin import router as admin_router
from .intelligence.routes import router as intelligence_router

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


# ── Lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    # Expose the pool on app.state so intelligence routes can access it
    app.state.pool = db.pool
    logger.info("VanCity Lens API started")
    yield
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

# CORS: configurable origins, restricted methods and headers
_default_origins = "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003"
_cors_origins = os.environ.get("CORS_ORIGINS", _default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Key"],
)

# Security headers on all responses
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(admin_router)
app.include_router(intelligence_router)


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

    checks["status"] = "ok"
    return checks


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
):
    """
    **The Red Dot** — Colin clicks a listing, sees the hidden value.
    """
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
):
    """Given a map click coordinate, find the nearest parcel."""
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
    limit: int = Query(default=50, le=500),
):
    """Returns top alpha parcels for rendering as markers on the map.
    Prioritises parcels with asking prices, then ranks by storey uplift.
    Uses a CTE to properly deduplicate (pick best tier per parcel)
    before applying the final sort + limit.
    """
    async with db.acquire() as conn:
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
            LIMIT $1
        """, limit)
        return [dict(r) for r in rows]


@app.get(
    "/api/v1/parcels/{pid}/nearby-stations",
    summary="List nearest transit stations to a parcel",
)
async def nearby_stations(pid: str):
    """Debug helper: see which stations are near a parcel."""
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
async def toa_geojson():
    """Returns all TOA buffer polygons as a GeoJSON FeatureCollection."""
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
