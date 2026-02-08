"""
VCL-104 (VAL-001): View Cone Intersection Service
Vancouver's 23 protected view corridors — deal-killer validation layer.

Spatial queries using PostGIS ST_Intersects to cap entitled height
when parcels intersect protected view cones.
"""

import logging
from decimal import Decimal
from typing import List, Optional, Dict, Any

import asyncpg
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ════════════════════════════════════════════════════════════════════════════

class ViewCone(BaseModel):
    """A protected view corridor in Vancouver."""
    id: int
    name: str
    description: Optional[str] = None
    max_height_m: Optional[float] = None
    max_height_ft: Optional[float] = None
    source_location: Optional[str] = None
    target_location: Optional[str] = None
    cone_type: str = "protected_view"
    bylaw_reference: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ViewConeIntersection(BaseModel):
    """Impact assessment of a parcel intersecting a view cone."""
    view_cone_name: str = Field(..., description="Name of the intersecting view cone")
    max_height_m: Optional[float] = Field(None, description="Height cap imposed by view cone")
    original_height_m: Optional[float] = Field(None, description="Original entitled height")
    capped_height_m: Optional[float] = Field(None, description="Height after view cone cap applied")
    buildable_sqft_reduction_pct: float = Field(0.0, description="Percentage reduction in buildable sqft due to height cap")


class ViewConeImpactSummary(BaseModel):
    """Summary of view cone impact assessment."""
    pid: str = Field(..., description="Parcel ID")
    intersects_view_cone: bool
    affected_cones: List[ViewConeIntersection]
    risk_flag: Optional[str] = None


class ParcelViewConeStats(BaseModel):
    """Statistics on view cone coverage across all parcels."""
    total_parcels: int
    affected_parcels: int
    affected_percentage: float


# ════════════════════════════════════════════════════════════════════════════
# SQL Queries
# ════════════════════════════════════════════════════════════════════════════

SQL_CHECK_INTERSECTION = """
    SELECT
        vc.id,
        vc.name,
        vc.max_height_m,
        vc.max_height_ft
    FROM view_cones vc
    WHERE vc.is_active = TRUE
      AND ST_Intersects(vc.geom, (SELECT geom FROM parcels WHERE pid = $1))
    ORDER BY vc.name
"""

SQL_CHECK_INTERSECTION_BY_GEOM = """
    SELECT
        vc.id,
        vc.name,
        vc.max_height_m,
        vc.max_height_ft
    FROM view_cones vc
    WHERE vc.is_active = TRUE
      AND ST_Intersects(vc.geom, ST_GeomFromGeoJSON($1))
    ORDER BY vc.name
"""

SQL_COUNT_AFFECTED_PARCELS = """
    SELECT COUNT(DISTINCT p.pid) as count
    FROM parcels p
    INNER JOIN view_cones vc ON ST_Intersects(p.geom, vc.geom)
    WHERE vc.is_active = TRUE
"""

SQL_GET_ALL_VIEW_CONES = """
    SELECT
        id, name, description, max_height_m, max_height_ft,
        source_location, target_location, cone_type, bylaw_reference,
        is_active, created_at, updated_at
    FROM view_cones
    WHERE is_active = TRUE
    ORDER BY name
"""

SQL_GET_TOTAL_PARCELS = """
    SELECT COUNT(*) as count FROM parcels
"""

SQL_INSERT_VIEW_CONE = """
    INSERT INTO view_cones
        (name, description, max_height_m, max_height_ft,
         source_location, target_location, cone_type, bylaw_reference, geom, is_active)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, ST_SetSRID(ST_GeomFromGeoJSON($9), 4326), $10)
    RETURNING id
"""


# ════════════════════════════════════════════════════════════════════════════
# Service Functions
# ════════════════════════════════════════════════════════════════════════════

async def check_view_cone_intersection(
    pool: asyncpg.Pool,
    pid: str,
) -> List[ViewConeIntersection]:
    """
    Check if a parcel (by PID) intersects any active view cones.

    Returns list of ViewConeIntersection objects with height caps and impact.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(SQL_CHECK_INTERSECTION, pid)

    intersections = []
    for row in rows:
        intersection = ViewConeIntersection(
            view_cone_name=row["name"],
            max_height_m=float(row["max_height_m"]) if row["max_height_m"] else None,
            original_height_m=None,  # Computed by caller with parcel data
            capped_height_m=None,     # Computed by caller with parcel data
            buildable_sqft_reduction_pct=0.0,
        )
        intersections.append(intersection)

    return intersections


async def check_view_cone_intersection_by_geom(
    pool: asyncpg.Pool,
    geojson_geom: Dict[str, Any],
) -> List[ViewConeIntersection]:
    """
    Check if a GeoJSON geometry intersects any active view cones.

    Args:
        pool: asyncpg connection pool
        geojson_geom: GeoJSON geometry dict (must be valid GeoJSON)

    Returns list of ViewConeIntersection objects
    """
    import json

    async with pool.acquire() as conn:
        rows = await conn.fetch(SQL_CHECK_INTERSECTION_BY_GEOM, json.dumps(geojson_geom))

    intersections = []
    for row in rows:
        intersection = ViewConeIntersection(
            view_cone_name=row["name"],
            max_height_m=float(row["max_height_m"]) if row["max_height_m"] else None,
        )
        intersections.append(intersection)

    return intersections


def cap_entitled_height(
    original_height_m: float,
    view_cone_max_height_m: Optional[float],
) -> float:
    """
    Cap the entitled height if view cone max is lower.

    If view cone has no max height specified, return original.
    Returns the minimum of original or view cone max.
    """
    if view_cone_max_height_m is None:
        return original_height_m

    return min(original_height_m, view_cone_max_height_m)


def calculate_buildable_reduction(
    original_height_m: float,
    capped_height_m: float,
    floors: Optional[int] = None,
    floor_to_height_ratio: float = 3.5,
) -> Dict[str, Any]:
    """
    Calculate buildable square footage reduction due to height cap.

    Assumes linear relationship between height and buildable sqft.
    Returns dict with:
      - capped_sqft_reduction_pct: percentage reduction in buildable sqft
      - estimated_sqft_loss: estimated sqft loss (approximate)
    """
    if original_height_m <= 0:
        return {
            "capped_sqft_reduction_pct": 0.0,
            "estimated_sqft_loss": 0,
        }

    # Simple height ratio approach: reduction_pct = (height_delta / original) * 100
    height_delta = original_height_m - capped_height_m
    if height_delta <= 0:
        return {
            "capped_sqft_reduction_pct": 0.0,
            "estimated_sqft_loss": 0,
        }

    reduction_pct = (height_delta / original_height_m) * 100.0

    # If floors provided, estimate sqft loss
    estimated_loss = 0
    if floors and floors > 0:
        floors_lost = max(0, (height_delta / floor_to_height_ratio))
        estimated_loss = int(floors_lost * 3000)  # Assume ~3000 sqft per typical floor

    return {
        "capped_sqft_reduction_pct": min(100.0, max(0.0, reduction_pct)),
        "estimated_sqft_loss": estimated_loss,
    }


async def load_view_cones_from_geojson(
    pool: asyncpg.Pool,
    geojson_data: List[Dict[str, Any]],
) -> int:
    """
    Load view cones from a GeoJSON feature collection.

    Expects a list of GeoJSON features, each with:
      - geometry: Polygon geometry
      - properties: dict with name, max_height_m, etc.

    Returns count of view cones inserted.
    """
    if not geojson_data:
        return 0

    inserted_count = 0
    async with pool.acquire() as conn:
        for feature in geojson_data:
            properties = feature.get("properties", {})
            geometry = feature.get("geometry")

            if not geometry:
                logger.warning(f"Feature missing geometry: {feature}")
                continue

            import json

            try:
                view_cone_id = await conn.fetchval(
                    SQL_INSERT_VIEW_CONE,
                    properties.get("name"),
                    properties.get("description"),
                    float(properties.get("max_height_m")) if properties.get("max_height_m") else None,
                    float(properties.get("max_height_ft")) if properties.get("max_height_ft") else None,
                    properties.get("source_location"),
                    properties.get("target_location"),
                    properties.get("cone_type", "protected_view"),
                    properties.get("bylaw_reference"),
                    json.dumps(geometry),
                    properties.get("is_active", True),
                )
                if view_cone_id:
                    inserted_count += 1
                    logger.info(f"Loaded view cone: {properties.get('name')} (id={view_cone_id})")
            except Exception as e:
                logger.error(f"Failed to insert view cone {properties.get('name')}: {e}")
                continue

    return inserted_count


async def get_all_view_cones(pool: asyncpg.Pool) -> List[ViewCone]:
    """
    Fetch all active view cones from the database.

    Returns list of ViewCone objects.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(SQL_GET_ALL_VIEW_CONES)

    cones = []
    for row in rows:
        cone = ViewCone(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            max_height_m=float(row["max_height_m"]) if row["max_height_m"] else None,
            max_height_ft=float(row["max_height_ft"]) if row["max_height_ft"] else None,
            source_location=row["source_location"],
            target_location=row["target_location"],
            cone_type=row["cone_type"],
            bylaw_reference=row["bylaw_reference"],
            is_active=row["is_active"],
            created_at=str(row["created_at"]) if row["created_at"] else None,
            updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        )
        cones.append(cone)

    return cones


async def count_affected_parcels(pool: asyncpg.Pool) -> ParcelViewConeStats:
    """
    Count how many of the 92K parcels intersect at least one active view cone.

    Returns dict with total_parcels, affected_parcels, and percentage.
    """
    async with pool.acquire() as conn:
        total_result = await conn.fetchval(SQL_GET_TOTAL_PARCELS)
        affected_result = await conn.fetchval(SQL_COUNT_AFFECTED_PARCELS)

    total_parcels = total_result or 0
    affected_parcels = affected_result or 0

    affected_pct = 0.0
    if total_parcels > 0:
        affected_pct = (affected_parcels / total_parcels) * 100.0

    logger.info(
        f"View cone validation: {affected_parcels} / {total_parcels} parcels "
        f"intersect view cones ({affected_pct:.2f}%)"
    )

    return ParcelViewConeStats(
        total_parcels=total_parcels,
        affected_parcels=affected_parcels,
        affected_percentage=affected_pct,
    )


def generate_sample_view_cones() -> List[Dict[str, Any]]:
    """
    Generate 23 realistic GeoJSON features representing Vancouver's protected view corridors.

    Based on Vancouver's Official Development Plan (ODP) view corridors:
      - Queen Elizabeth Park (multiple directions)
      - Cambie Bridge
      - Granville Bridge
      - Burrard Bridge
      - Various street corridors to the North Shore mountains

    Returns list of GeoJSON features (Polygon) with properties.
    """
    cones = [
        {
            "type": "Feature",
            "properties": {
                "name": "Queen Elizabeth Park - North",
                "description": "Protected view corridor from QE Park towards North Shore mountains",
                "source_location": "Queen Elizabeth Park",
                "target_location": "North Shore Mountains",
                "max_height_m": 35.0,
                "max_height_ft": 115.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.6.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1050, 49.2380],
                    [-123.1000, 49.2450],
                    [-123.0950, 49.2400],
                    [-123.1000, 49.2330],
                    [-123.1050, 49.2380],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Queen Elizabeth Park - Northeast",
                "description": "Protected view corridor from QE Park towards northeast",
                "source_location": "Queen Elizabeth Park",
                "target_location": "North Shore Mountains",
                "max_height_m": 35.0,
                "max_height_ft": 115.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.6.2",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.0950, 49.2400],
                    [-123.0900, 49.2480],
                    [-123.0850, 49.2420],
                    [-123.0900, 49.2340],
                    [-123.0950, 49.2400],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Queen Elizabeth Park - East",
                "description": "Protected view corridor from QE Park towards east",
                "source_location": "Queen Elizabeth Park",
                "target_location": "North Shore Mountains",
                "max_height_m": 35.0,
                "max_height_ft": 115.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.6.3",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.0850, 49.2420],
                    [-123.0800, 49.2480],
                    [-123.0750, 49.2400],
                    [-123.0800, 49.2320],
                    [-123.0850, 49.2420],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Cambie Street Bridge View",
                "description": "Protected view corridor from Cambie Bridge",
                "source_location": "Cambie Bridge",
                "target_location": "North Shore Mountains",
                "max_height_m": 40.0,
                "max_height_ft": 131.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.7.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1100, 49.2280],
                    [-123.1050, 49.2360],
                    [-123.1000, 49.2300],
                    [-123.1050, 49.2220],
                    [-123.1100, 49.2280],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Granville Bridge View North",
                "description": "Protected view corridor from Granville Bridge towards north",
                "source_location": "Granville Bridge",
                "target_location": "North Shore Mountains",
                "max_height_m": 45.0,
                "max_height_ft": 148.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.8.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1380, 49.2160],
                    [-123.1330, 49.2240],
                    [-123.1280, 49.2180],
                    [-123.1330, 49.2100],
                    [-123.1380, 49.2160],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Granville Bridge View South",
                "description": "Protected view corridor from Granville Bridge towards south",
                "source_location": "Granville Bridge",
                "target_location": "Cypress Mountains",
                "max_height_m": 40.0,
                "max_height_ft": 131.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.8.2",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1330, 49.2100],
                    [-123.1280, 49.2020],
                    [-123.1230, 49.2080],
                    [-123.1280, 49.2160],
                    [-123.1330, 49.2100],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Burrard Bridge View",
                "description": "Protected view corridor from Burrard Bridge",
                "source_location": "Burrard Bridge",
                "target_location": "North Shore Mountains",
                "max_height_m": 50.0,
                "max_height_ft": 164.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.9.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1550, 49.2080],
                    [-123.1500, 49.2160],
                    [-123.1450, 49.2100],
                    [-123.1500, 49.2020],
                    [-123.1550, 49.2080],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Broadway Corridor - East",
                "description": "Protected view corridor along Broadway towards North Shore",
                "source_location": "Broadway Corridor",
                "target_location": "North Shore Mountains",
                "max_height_m": 30.0,
                "max_height_ft": 98.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.10.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.0650, 49.2620],
                    [-123.0600, 49.2700],
                    [-123.0550, 49.2640],
                    [-123.0600, 49.2560],
                    [-123.0650, 49.2620],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Broadway Corridor - West",
                "description": "Protected view corridor along Broadway towards mountains",
                "source_location": "Broadway Corridor",
                "target_location": "North Shore Mountains",
                "max_height_m": 30.0,
                "max_height_ft": 98.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.10.2",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1850, 49.2720],
                    [-123.1800, 49.2800],
                    [-123.1750, 49.2740],
                    [-123.1800, 49.2660],
                    [-123.1850, 49.2720],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Hastings Street View Corridor",
                "description": "Protected view corridor along Hastings Street towards North Shore",
                "source_location": "Hastings Street",
                "target_location": "North Shore Mountains",
                "max_height_m": 28.0,
                "max_height_ft": 92.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.11.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.0400, 49.2860],
                    [-123.0350, 49.2940],
                    [-123.0300, 49.2880],
                    [-123.0350, 49.2800],
                    [-123.0400, 49.2860],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Main Street Corridor",
                "description": "Protected view corridor along Main Street",
                "source_location": "Main Street",
                "target_location": "North Shore Mountains",
                "max_height_m": 30.0,
                "max_height_ft": 98.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.12.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1000, 49.2760],
                    [-123.0950, 49.2840],
                    [-123.0900, 49.2780],
                    [-123.0950, 49.2700],
                    [-123.1000, 49.2760],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "False Creek North - East",
                "description": "Protected view corridor from False Creek North bank",
                "source_location": "False Creek",
                "target_location": "North Shore Mountains",
                "max_height_m": 55.0,
                "max_height_ft": 180.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.13.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1200, 49.2720],
                    [-123.1150, 49.2800],
                    [-123.1100, 49.2740],
                    [-123.1150, 49.2660],
                    [-123.1200, 49.2720],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "False Creek North - West",
                "description": "Protected view corridor from False Creek North bank west",
                "source_location": "False Creek",
                "target_location": "North Shore Mountains",
                "max_height_m": 50.0,
                "max_height_ft": 164.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.13.2",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1550, 49.2700],
                    [-123.1500, 49.2780],
                    [-123.1450, 49.2720],
                    [-123.1500, 49.2640],
                    [-123.1550, 49.2700],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Seawall Pacific Spirit View",
                "description": "Protected view from Seawall towards North Shore",
                "source_location": "Seawall",
                "target_location": "North Shore Mountains",
                "max_height_m": 60.0,
                "max_height_ft": 197.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.14.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1800, 49.2460],
                    [-123.1750, 49.2540],
                    [-123.1700, 49.2480],
                    [-123.1750, 49.2400],
                    [-123.1800, 49.2460],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Georgia Street Corridor",
                "description": "Protected view corridor along Georgia Street",
                "source_location": "Georgia Street",
                "target_location": "North Shore Mountains",
                "max_height_m": 35.0,
                "max_height_ft": 115.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.15.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1150, 49.2840],
                    [-123.1100, 49.2920],
                    [-123.1050, 49.2860],
                    [-123.1100, 49.2780],
                    [-123.1150, 49.2840],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Pender Street Corridor",
                "description": "Protected view corridor along Pender Street",
                "source_location": "Pender Street",
                "target_location": "North Shore Mountains",
                "max_height_m": 32.0,
                "max_height_ft": 105.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.16.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.0950, 49.2920],
                    [-123.0900, 49.3000],
                    [-123.0850, 49.2940],
                    [-123.0900, 49.2860],
                    [-123.0950, 49.2920],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Victory Square View",
                "description": "Protected view from Victory Square towards North Shore",
                "source_location": "Victory Square",
                "target_location": "North Shore Mountains",
                "max_height_m": 36.0,
                "max_height_ft": 118.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.17.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.0730, 49.2950],
                    [-123.0680, 49.3030],
                    [-123.0630, 49.2970],
                    [-123.0680, 49.2890],
                    [-123.0730, 49.2950],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "South False Creek - East",
                "description": "Protected view from South False Creek towards North Shore",
                "source_location": "South False Creek",
                "target_location": "North Shore Mountains",
                "max_height_m": 48.0,
                "max_height_ft": 157.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.18.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1100, 49.2580],
                    [-123.1050, 49.2660],
                    [-123.1000, 49.2600],
                    [-123.1050, 49.2520],
                    [-123.1100, 49.2580],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "South False Creek - West",
                "description": "Protected view from South False Creek towards mountains",
                "source_location": "South False Creek",
                "target_location": "North Shore Mountains",
                "max_height_m": 45.0,
                "max_height_ft": 148.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.18.2",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1450, 49.2560],
                    [-123.1400, 49.2640],
                    [-123.1350, 49.2580],
                    [-123.1400, 49.2500],
                    [-123.1450, 49.2560],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Pacific Boulevard View",
                "description": "Protected view from Pacific Boulevard",
                "source_location": "Pacific Boulevard",
                "target_location": "North Shore Mountains",
                "max_height_m": 52.0,
                "max_height_ft": 170.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.19.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1300, 49.2500],
                    [-123.1250, 49.2580],
                    [-123.1200, 49.2520],
                    [-123.1250, 49.2440],
                    [-123.1300, 49.2500],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Cambie Corridor North",
                "description": "Protected view corridor along Cambie towards north",
                "source_location": "Cambie Corridor",
                "target_location": "North Shore Mountains",
                "max_height_m": 38.0,
                "max_height_ft": 125.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.20.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1050, 49.2500],
                    [-123.1000, 49.2580],
                    [-123.0950, 49.2520],
                    [-123.1000, 49.2440],
                    [-123.1050, 49.2500],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Seymour Street View",
                "description": "Protected view from Seymour Street towards North Shore",
                "source_location": "Seymour Street",
                "target_location": "North Shore Mountains",
                "max_height_m": 42.0,
                "max_height_ft": 138.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.21.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1200, 49.2860],
                    [-123.1150, 49.2940],
                    [-123.1100, 49.2880],
                    [-123.1150, 49.2800],
                    [-123.1200, 49.2860],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Richards Street Corridor",
                "description": "Protected view corridor along Richards Street",
                "source_location": "Richards Street",
                "target_location": "North Shore Mountains",
                "max_height_m": 40.0,
                "max_height_ft": 131.0,
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.22.1",
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1350, 49.2860],
                    [-123.1300, 49.2940],
                    [-123.1250, 49.2880],
                    [-123.1300, 49.2800],
                    [-123.1350, 49.2860],
                ]],
            },
        },
    ]

    return cones
