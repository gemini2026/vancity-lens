"""
VCL-104 (VAL-001): View Cone API Routes
Endpoints for loading, querying, and analyzing view cone intersections.

Endpoints:
  POST   /api/v1/admin/load-view-cones      — Load view cones from GeoJSON (admin only)
  GET    /api/v1/view-cones                  — List all active view cones
  GET    /api/v1/parcels/{pid}/view-cones   — Check parcel intersection with view cones
  GET    /api/v1/admin/view-cones/impact     — View cone coverage statistics (admin only)
"""

import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request, status
import asyncpg

from .auth import require_admin
from .view_cones import (
    ViewCone,
    ViewConeImpactSummary,
    ViewConeIntersection,
    ParcelViewConeStats,
    check_view_cone_intersection,
    load_view_cones_from_geojson,
    get_all_view_cones,
    count_affected_parcels,
    generate_sample_view_cones,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["view_cones"])


# ════════════════════════════════════════════════════════════════════════════
# Database Pool Dependency
# ════════════════════════════════════════════════════════════════════════════

def get_db_pool(request: Request) -> asyncpg.Pool:
    """Extract asyncpg pool from request.app.state or fallback to default."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        from .db import db
        pool = db.pool
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool


# ════════════════════════════════════════════════════════════════════════════
# Admin Endpoints
# ════════════════════════════════════════════════════════════════════════════

@router.post(
    "/admin/load-view-cones",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Load view cones from GeoJSON",
    description="Admin endpoint to load Vancouver's 23 protected view corridors.",
    dependencies=[Depends(require_admin)],
)
async def load_view_cones(
    request: Request,
    geojson_features: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Load view cones from GeoJSON feature array.

    If geojson_features is None, loads the built-in sample of 23 Vancouver view cones.
    Returns count of cones loaded and impact summary.
    """
    pool = get_db_pool(request)

    # Use provided GeoJSON or generate sample
    features = geojson_features or generate_sample_view_cones()

    if not features:
        raise HTTPException(status_code=400, detail="No GeoJSON features provided")

    try:
        inserted_count = await load_view_cones_from_geojson(pool, features)
        logger.info(f"Loaded {inserted_count} view cones")

        # Count affected parcels after load
        stats = await count_affected_parcels(pool)

        return {
            "status": "success",
            "inserted_count": inserted_count,
            "affected_parcels": stats.affected_parcels,
            "total_parcels": stats.total_parcels,
            "affected_percentage": f"{stats.affected_percentage:.2f}%",
            "message": (
                f"Loaded {inserted_count} view cones. "
                f"{stats.affected_parcels} of {stats.total_parcels} parcels "
                f"({stats.affected_percentage:.2f}%) intersect view cones."
            ),
        }
    except Exception as e:
        logger.error(f"Failed to load view cones: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load view cones: {str(e)}")


@router.get(
    "/admin/view-cones/impact",
    response_model=ParcelViewConeStats,
    status_code=status.HTTP_200_OK,
    summary="View cone impact statistics",
    description="Count how many parcels intersect view cones (admin only).",
    dependencies=[Depends(require_admin)],
)
async def get_view_cone_impact(request: Request) -> ParcelViewConeStats:
    """
    Get view cone coverage statistics across all parcels.

    Returns total parcel count, affected count, and percentage.
    """
    pool = get_db_pool(request)

    try:
        stats = await count_affected_parcels(pool)
        return stats
    except Exception as e:
        logger.error(f"Failed to get view cone impact: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# Public Endpoints
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/view-cones",
    response_model=List[ViewCone],
    status_code=status.HTTP_200_OK,
    summary="List all active view cones",
    description="Returns all active protected view corridors.",
)
async def list_view_cones(request: Request) -> List[ViewCone]:
    """
    Fetch all active view cones.

    Returns list of ViewCone objects with geometry info.
    """
    pool = get_db_pool(request)

    try:
        cones = await get_all_view_cones(pool)
        return cones
    except Exception as e:
        logger.error(f"Failed to list view cones: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list view cones: {str(e)}")


@router.get(
    "/parcels/{pid}/view-cones",
    response_model=ViewConeImpactSummary,
    status_code=status.HTTP_200_OK,
    summary="Check parcel view cone intersection",
    description="Determine if a parcel (by PID) intersects any protected view corridors.",
)
async def check_parcel_view_cones(
    pid: str,
    request: Request,
) -> ViewConeImpactSummary:
    """
    Check if a parcel intersects any active view cones.

    Returns list of affected view cones and RED risk flag if applicable.
    """
    pool = get_db_pool(request)

    if not pid or not pid.strip():
        raise HTTPException(status_code=400, detail="PID is required")

    try:
        intersections = await check_view_cone_intersection(pool, pid)

        # Generate risk flag if any intersections
        risk_flag = None
        if intersections:
            view_cone_names = ", ".join([i.view_cone_name for i in intersections])
            risk_flag = f"RED: View cone restriction — entitled height capped by: {view_cone_names}"

        return ViewConeImpactSummary(
            pid=pid,
            intersects_view_cone=len(intersections) > 0,
            affected_cones=intersections,
            risk_flag=risk_flag,
        )
    except Exception as e:
        logger.error(f"Failed to check view cone intersection for {pid}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check view cone intersection: {str(e)}"
        )


# ════════════════════════════════════════════════════════════════════════════
# Utility Endpoint (Unauthenticated)
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/view-cones/sample",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Get sample view cone GeoJSON",
    description="Returns the 23-cone sample GeoJSON for reference or testing.",
)
async def get_sample_view_cones() -> List[Dict[str, Any]]:
    """
    Return the built-in sample of 23 Vancouver view cones as GeoJSON.

    Useful for testing, reference, or bulk-loading.
    """
    return generate_sample_view_cones()
