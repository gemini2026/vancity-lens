"""
VanCity Lens — Data Sources API Routes

Endpoints for querying external data source tables:
- Contaminated sites
- StatsCan demographics / population / building permits
- CMHC housing metrics
- Census geography lookup (PID → census tract / CSD)
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from .db import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["data-sources"])


# ── Contaminated Sites ──────────────────────────────────────────

@router.get("/contaminated-sites", summary="Search contaminated sites near a location")
async def search_contaminated_sites(
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
    radius_m: int = Query(500, ge=50, le=5000, description="Search radius in metres"),
    pid: Optional[str] = Query(None, description="Search by associated PID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Find contaminated sites near a location or associated with a PID."""
    offset = (page - 1) * page_size

    async with db.acquire() as conn:
        if pid:
            rows = await conn.fetch("""
                SELECT id, site_id, site_name, address, city,
                       latitude, longitude, classification, status,
                       contamination_type, date_reported, date_updated,
                       associated_pid
                FROM contaminated_sites
                WHERE associated_pid = $1
                ORDER BY date_updated DESC NULLS LAST
                LIMIT $2 OFFSET $3
            """, pid, page_size, offset)
        elif lat is not None and lng is not None:
            rows = await conn.fetch("""
                SELECT id, site_id, site_name, address, city,
                       latitude, longitude, classification, status,
                       contamination_type, date_reported, date_updated,
                       associated_pid,
                       ROUND(ST_Distance(
                           ST_Transform(geom, 3005),
                           ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 3005)
                       )::numeric, 1) AS distance_m
                FROM contaminated_sites
                WHERE geom IS NOT NULL
                  AND ST_DWithin(
                      ST_Transform(geom, 3005),
                      ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 3005),
                      $3
                  )
                ORDER BY distance_m
                LIMIT $4 OFFSET $5
            """, lng, lat, radius_m, page_size, offset)
        else:
            rows = await conn.fetch("""
                SELECT id, site_id, site_name, address, city,
                       latitude, longitude, classification, status,
                       contamination_type, date_reported, date_updated,
                       associated_pid
                FROM contaminated_sites
                ORDER BY date_updated DESC NULLS LAST
                LIMIT $1 OFFSET $2
            """, page_size, offset)

        return {
            "items": [dict(r) for r in rows],
            "page": page,
            "page_size": page_size,
        }


@router.get("/parcels/{pid}/contaminated-sites", summary="Check contaminated sites near a parcel")
async def parcel_contaminated_sites(
    pid: str,
    radius_m: int = Query(500, ge=50, le=2000),
):
    """Check for contaminated sites near a specific parcel (within radius)."""
    async with db.acquire() as conn:
        # First get parcel centroid
        parcel = await conn.fetchrow("""
            SELECT ST_X(ST_Centroid(geom)) AS lng, ST_Y(ST_Centroid(geom)) AS lat
            FROM parcels WHERE pid = $1
        """, pid)
        if not parcel:
            raise HTTPException(status_code=404, detail=f"Parcel {pid} not found")

        rows = await conn.fetch("""
            SELECT cs.id, cs.site_id, cs.site_name, cs.address,
                   cs.classification, cs.status, cs.contamination_type,
                   cs.date_reported, cs.date_updated,
                   ROUND(ST_Distance(
                       ST_Transform(cs.geom, 3005),
                       ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 3005)
                   )::numeric, 1) AS distance_m
            FROM contaminated_sites cs
            WHERE cs.geom IS NOT NULL
              AND ST_DWithin(
                  ST_Transform(cs.geom, 3005),
                  ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 3005),
                  $3
              )
            ORDER BY distance_m
        """, parcel["lng"], parcel["lat"], radius_m)

        return {
            "pid": pid,
            "radius_m": radius_m,
            "count": len(rows),
            "has_contaminated_sites": len(rows) > 0,
            "sites": [dict(r) for r in rows],
        }


# ── StatsCan Demographics ───────────────────────────────────────

@router.get("/demographics/{census_tract}", summary="Get census tract demographics")
async def get_demographics(census_tract: str):
    """Get StatsCan demographic data for a census tract."""
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM statscan_demographics
            WHERE census_tract = $1
            ORDER BY census_year DESC
            LIMIT 1
        """, census_tract)
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No demographic data for census tract {census_tract}"
            )
        result = dict(row)
        if isinstance(result.get("raw_data"), str):
            result["raw_data"] = json.loads(result["raw_data"])
        return result


@router.get("/parcels/{pid}/demographics", summary="Get demographics for a parcel's census tract")
async def parcel_demographics(pid: str):
    """Get StatsCan demographics for the census tract containing a parcel."""
    async with db.acquire() as conn:
        lookup = await conn.fetchrow("""
            SELECT census_tract, census_subdivision, census_subdivision_name,
                   distance_to_tract_boundary_m
            FROM parcel_census_lookup
            WHERE pid = $1
        """, pid)
        if not lookup:
            raise HTTPException(
                status_code=404,
                detail=f"No census geography mapping for parcel {pid}"
            )

        demographics = await conn.fetchrow("""
            SELECT * FROM statscan_demographics
            WHERE census_tract = $1
            ORDER BY census_year DESC
            LIMIT 1
        """, lookup["census_tract"])

        result = {
            "pid": pid,
            "census_tract": lookup["census_tract"],
            "census_subdivision": lookup["census_subdivision"],
            "census_subdivision_name": lookup["census_subdivision_name"],
            "distance_to_tract_boundary_m": float(lookup["distance_to_tract_boundary_m"]) if lookup["distance_to_tract_boundary_m"] else None,
            "demographics": dict(demographics) if demographics else None,
        }
        if result.get("demographics") and isinstance(result["demographics"].get("raw_data"), str):
            result["demographics"]["raw_data"] = json.loads(result["demographics"]["raw_data"])
        return result


# ── CMHC Housing ────────────────────────────────────────────────

@router.get("/housing-market", summary="Get CMHC housing market data")
async def get_housing_market(
    metric: Optional[str] = Query(None, description="Filter by metric: starts, completions, under_construction, absorptions"),
    dwelling_type: Optional[str] = Query(None, description="Filter by dwelling type"),
    months: int = Query(12, ge=1, le=120, description="Number of months of data"),
):
    """Get CMHC housing market data for Vancouver CMA."""
    async with db.acquire() as conn:
        where_clauses = ["cma_code = '933'"]
        params = []
        param_idx = 1

        if metric:
            where_clauses.append(f"metric = ${param_idx}")
            params.append(metric)
            param_idx += 1

        if dwelling_type:
            where_clauses.append(f"dwelling_type = ${param_idx}")
            params.append(dwelling_type)
            param_idx += 1

        where = " AND ".join(where_clauses)
        params.append(months)

        rows = await conn.fetch(f"""
            SELECT ref_date, metric, dwelling_type, value, retrieved_at
            FROM cmhc_housing
            WHERE {where}
            ORDER BY ref_date DESC
            LIMIT ${param_idx}
        """, *params)

        return {
            "cma": "Vancouver (933)",
            "count": len(rows),
            "data": [dict(r) for r in rows],
        }


# ── Building Permits ────────────────────────────────────────────

@router.get("/building-permits", summary="Get StatsCan building permit data")
async def get_building_permits(
    months: int = Query(12, ge=1, le=120),
    permit_type: Optional[str] = Query(None),
):
    """Get building permit data from StatsCan for Vancouver CMA."""
    async with db.acquire() as conn:
        where_clauses = ["geo_code = '933' OR geo_name LIKE '%Vancouver%'"]
        params = []
        param_idx = 1

        if permit_type:
            where_clauses.append(f"permit_type = ${param_idx}")
            params.append(permit_type)
            param_idx += 1

        where = " AND ".join(where_clauses)
        params.append(months)

        rows = await conn.fetch(f"""
            SELECT ref_date, permit_type, num_permits, value_thousands, retrieved_at
            FROM statscan_building_permits
            WHERE {where}
            ORDER BY ref_date DESC
            LIMIT ${param_idx}
        """, *params)

        return {
            "count": len(rows),
            "data": [dict(r) for r in rows],
        }


# ── Data Source Status ──────────────────────────────────────────

@router.get("/data-sources/status", summary="Data source freshness status")
async def data_source_status():
    """Check the freshness of all external data sources."""
    async with db.acquire() as conn:
        status = {}

        # Check each data source table
        tables = [
            ("contaminated_sites", "updated_at"),
            ("statscan_demographics", "retrieved_at"),
            ("statscan_population", "retrieved_at"),
            ("statscan_building_permits", "retrieved_at"),
            ("cmhc_housing", "retrieved_at"),
        ]

        for table, ts_col in tables:
            try:
                row = await conn.fetchrow(f"""
                    SELECT count(*) AS record_count,
                           MAX({ts_col}) AS last_updated
                    FROM {table}
                """)
                status[table] = {
                    "record_count": row["record_count"],
                    "last_updated": str(row["last_updated"]) if row["last_updated"] else None,
                }
            except Exception:
                status[table] = {"record_count": 0, "last_updated": None, "error": "table not found"}

        # Check documents table for scraper sources
        scraper_sources = ["provincial_legislation", "bc_gazette"]
        for src in scraper_sources:
            try:
                row = await conn.fetchrow("""
                    SELECT count(*) AS doc_count, MAX(created_at) AS last_ingested
                    FROM documents WHERE source_type = $1
                """, src)
                status[f"documents_{src}"] = {
                    "record_count": row["doc_count"],
                    "last_updated": str(row["last_ingested"]) if row["last_ingested"] else None,
                }
            except Exception:
                status[f"documents_{src}"] = {"record_count": 0, "last_updated": None}

        return {"sources": status}
