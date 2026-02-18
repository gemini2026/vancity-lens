"""Development Clustering API Routes.

Endpoint:
- GET /clusters -- Detect and return active development clusters
"""

import logging

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request

from .clustering import detect_clusters

logger = logging.getLogger(__name__)

router = APIRouter(tags=["clustering"])


def _get_pool(request: Request):
    pool = getattr(request.app.state, "pool", None)
    if not pool:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Database connection not available")
    return pool


@router.get("/clusters")
async def get_clusters(
    request: Request,
    radius_m: int = Query(500, ge=100, le=2000),
    window_days: int = Query(90, ge=30, le=365),
    min_apps: int = Query(3, ge=2, le=10),
):
    """Detect development application clusters."""
    pool = _get_pool(request)
    try:
        clusters = await detect_clusters(
            pool,
            radius_m=radius_m,
            window_days=window_days,
            min_apps=min_apps,
        )
    except asyncpg.UndefinedTableError:
        raise HTTPException(
            status_code=503,
            detail="Pipeline data not yet available. Run the pipeline ingestion first.",
        )
    except asyncpg.PostgresError as e:
        logger.error("Failed to detect clusters: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to detect development clusters.",
        )
    return {
        "count": len(clusters),
        "clusters": [c.model_dump() for c in clusters],
        "params": {
            "radius_m": radius_m,
            "window_days": window_days,
            "min_apps": min_apps,
        },
    }
