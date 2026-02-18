"""
API endpoints for supply pipeline tracking.

Provides REST endpoints for:
- Querying pipeline entries
- Managing pipeline entries (add, update, delete)
- Viewing stage history
- Getting pipeline statistics and summaries
- Ingesting from intelligence signals
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_admin
from ..db import db
from .clustering import detect_clusters
from .supply_pipeline import (
    SupplyPipelineTracker,
    PipelineEntryCreate,
    PipelineStage,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["intelligence", "supply_pipeline"],
)

admin_router = APIRouter(
    tags=["admin", "supply_pipeline"],
    dependencies=[Depends(require_admin)],
)


# ════════════════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════


@router.get("/pipeline", response_model=dict)
async def list_pipeline(
    neighborhood: Optional[str] = Query(None, description="Filter by neighborhood"),
    stage: Optional[str] = Query(None, description="Filter by pipeline stage"),
    height_min: Optional[int] = Query(
        None, ge=1, description="Minimum proposed storeys"
    ),
    height_max: Optional[int] = Query(
        None, ge=1, description="Maximum proposed storeys"
    ),
    units_min: Optional[int] = Query(None, ge=1, description="Minimum proposed units"),
    units_max: Optional[int] = Query(None, ge=1, description="Maximum proposed units"),
    developer: Optional[str] = Query(
        None, min_length=2, description="Developer name search (partial match)"
    ),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> dict:
    """
    List pipeline entries with optional filters.

    Query Parameters:
    - neighborhood: Filter by neighborhood name
    - stage: Filter by pipeline stage
    - height_min/height_max: Filter by proposed storeys range
    - units_min/units_max: Filter by proposed unit count range
    - developer: Search by developer name (partial, case-insensitive)
    - limit: Results per page (1-100, default 50)
    - offset: Pagination offset (default 0)
    """
    try:
        entries, total_count = await SupplyPipelineTracker.get_pipeline(
            db.pool,
            neighborhood=neighborhood,
            stage=stage,
            height_min=height_min,
            height_max=height_max,
            units_min=units_min,
            units_max=units_max,
            developer=developer,
            limit=limit,
            offset=offset,
        )

        has_more = (offset + limit) < total_count

        return {
            "entries": [entry.model_dump() for entry in entries],
            "total_count": total_count,
            "has_more": has_more,
            "offset": offset,
            "limit": limit,
        }

    except Exception as e:
        logger.error(f"Error listing pipeline: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list pipeline entries")


@router.post("/pipeline/search-polygon", response_model=dict)
async def search_pipeline_in_polygon(
    body: dict,
    stage: Optional[str] = Query(None, description="Filter by pipeline stage"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
) -> dict:
    """
    FR-PIPE-005: Search pipeline entries within a drawn polygon.

    Request body must contain a GeoJSON geometry:
    {
        "type": "Polygon",
        "coordinates": [[[lng, lat], [lng, lat], ...]]
    }

    Returns pipeline entries whose parcels intersect the polygon.
    """
    geom_type = body.get("type", "")
    if geom_type not in ("Polygon", "MultiPolygon"):
        raise HTTPException(
            status_code=422,
            detail=f"Expected GeoJSON Polygon or MultiPolygon, got '{geom_type}'",
        )
    if "coordinates" not in body:
        raise HTTPException(
            status_code=422, detail="Missing 'coordinates' in GeoJSON geometry"
        )

    try:
        entries = await SupplyPipelineTracker.get_pipeline_in_polygon(
            db.pool,
            geojson_polygon=body,
            stage=stage,
            limit=limit,
        )
        return {
            "entries": [entry.model_dump() for entry in entries],
            "total_count": len(entries),
        }
    except Exception as e:
        logger.error(f"Error searching pipeline in polygon: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to search pipeline in polygon"
        )


@router.get("/pipeline/summary", response_model=dict)
async def get_summary() -> dict:
    """
    Get high-level pipeline summary.

    Returns:
    - total_entries: Total pipeline entries
    - total_units: Total residential units in pipeline
    - total_sqft: Total floor space in pipeline
    - by_stage: Breakdown by pipeline stage
    - by_neighborhood: Breakdown by neighborhood
    """
    try:
        summary = await SupplyPipelineTracker.get_pipeline_summary(db.pool)

        return {
            "total_entries": summary.total_entries,
            "total_units": summary.total_units,
            "total_sqft": summary.total_sqft,
            "by_stage": [stage.model_dump() for stage in summary.by_stage],
            "by_neighborhood": summary.by_neighborhood,
        }

    except Exception as e:
        logger.error(f"Error retrieving pipeline summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve pipeline summary"
        )


@router.get("/pipeline/stats", response_model=dict)
async def get_stats(
    neighborhood: Optional[str] = Query(None, description="Filter by neighborhood"),
) -> dict:
    """
    Get detailed pipeline statistics.

    Query Parameters:
    - neighborhood: Optional filter to specific neighborhood

    Returns:
    - total_projects: Total count of projects
    - total_units: Total units in pipeline
    - total_sqft: Total floor space
    - average_units_per_project: Mean units per project
    - average_storeys_per_project: Mean storeys per project
    - projects_by_stage: Breakdown by pipeline stage
    - projects_by_neighborhood: Breakdown by neighborhood
    - near_completion_count: Projects in building_permit or under_construction stages
    """
    try:
        stats = await SupplyPipelineTracker.get_pipeline_stats(
            db.pool, neighborhood=neighborhood
        )

        return {
            "total_projects": stats.total_projects,
            "total_units": stats.total_units,
            "total_sqft": stats.total_sqft,
            "average_units_per_project": stats.average_units_per_project,
            "average_storeys_per_project": stats.average_storeys_per_project,
            "projects_by_stage": stats.projects_by_stage,
            "projects_by_neighborhood": stats.projects_by_neighborhood,
            "near_completion_count": stats.near_completion_count,
        }

    except Exception as e:
        logger.error(f"Error retrieving pipeline statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve pipeline statistics"
        )


@router.get("/pipeline/neighborhood/{neighborhood}", response_model=dict)
async def get_neighborhood_supply(neighborhood: str) -> dict:
    """
    Get detailed supply analysis for a neighborhood.

    Returns:
    - neighborhood: Neighborhood name
    - total_projects: Count of projects
    - total_units: Total units in pipeline
    - total_sqft: Total floor space
    - by_stage: Breakdown by pipeline stage
    - estimated_completion_range: Projects grouped by completion quarter
    """
    try:
        supply = await SupplyPipelineTracker.get_neighborhood_supply(
            db.pool, neighborhood
        )

        return {
            "neighborhood": supply.neighborhood,
            "total_projects": supply.total_projects,
            "total_units": supply.total_units,
            "total_sqft": supply.total_sqft,
            "by_stage": supply.by_stage,
            "estimated_completion_range": supply.estimated_completion_range,
        }

    except Exception as e:
        logger.error(f"Error retrieving neighborhood supply: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve neighborhood supply"
        )


@router.get("/pipeline/clusters", response_model=dict)
async def get_clusters(
    radius_m: int = Query(500, ge=100, le=5000, description="Cluster radius in metres"),
    window_days: int = Query(90, ge=7, le=365, description="Time window in days"),
    min_apps: int = Query(
        3, ge=2, le=20, description="Minimum applications for a cluster"
    ),
) -> dict:
    """
    FR-PIPE-006: Detect spatial/temporal clusters of development applications.

    Returns clusters where min_apps+ applications appear within radius_m
    and window_days of each other.
    """
    try:
        clusters = await detect_clusters(
            db.pool,
            radius_m=radius_m,
            window_days=window_days,
            min_apps=min_apps,
        )
        return {
            "clusters": [c.model_dump() for c in clusters],
            "total_count": len(clusters),
            "params": {
                "radius_m": radius_m,
                "window_days": window_days,
                "min_apps": min_apps,
            },
        }
    except Exception as e:
        logger.error(f"Error detecting clusters: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to detect development clusters"
        )


@router.get("/pipeline/{pipeline_id}", response_model=dict)
async def get_pipeline_entry(pipeline_id: int) -> dict:
    """
    Get a single pipeline entry by ID.

    Returns:
    - entry: PipelineEntry or null if not found
    """
    try:
        entry = await SupplyPipelineTracker.get_entry(db.pool, pipeline_id)

        if not entry:
            raise HTTPException(status_code=404, detail="Pipeline entry not found")

        return entry.model_dump()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving pipeline entry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve pipeline entry")


@router.get("/pipeline/{pipeline_id}/history", response_model=dict)
async def get_stage_history(pipeline_id: int) -> dict:
    """
    Get the stage transition history for a pipeline entry.

    Returns:
    - history: List of PipelineStageChange objects
    """
    try:
        # Verify entry exists
        entry = await SupplyPipelineTracker.get_entry(db.pool, pipeline_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Pipeline entry not found")

        history = await SupplyPipelineTracker.get_stage_history(db.pool, pipeline_id)

        return {
            "pipeline_id": pipeline_id,
            "history": [change.model_dump() for change in history],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving stage history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve stage history")


# ════════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════


@admin_router.post("/pipeline", response_model=dict)
async def create_pipeline_entry(entry: PipelineEntryCreate) -> dict:
    """
    Create a new pipeline entry (admin only).

    Request body:
    - parcel_pid: Unique parcel identifier
    - address: Street address
    - neighborhood: Vancouver neighborhood (optional)
    - pipeline_stage: Current stage in pipeline
    - current_zoning: Current zoning designation
    - proposed_zoning: Proposed zoning designation
    - proposed_storeys: Number of storeys (optional)
    - proposed_units: Number of residential units (optional)
    - proposed_sqft: Total floor space (optional)
    - developer: Developer/company name (optional)
    - estimated_completion: Estimated completion date (optional)
    - metadata: Additional project data as JSON object

    Returns:
    - Created PipelineEntry
    """
    try:
        created = await SupplyPipelineTracker.add_entry(db.pool, entry)
        return created.model_dump()

    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating pipeline entry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create pipeline entry")


@admin_router.put("/pipeline/{pipeline_id}/stage", response_model=dict)
async def update_pipeline_stage(
    pipeline_id: int,
    new_stage: PipelineStage = Query(..., description="New pipeline stage"),
    signal_id: Optional[int] = Query(None, description="Triggering signal ID"),
    notes: Optional[str] = Query(None, description="Transition notes"),
) -> dict:
    """
    Update a pipeline entry's stage (admin only).

    Path Parameters:
    - pipeline_id: ID of pipeline entry to update

    Query Parameters:
    - new_stage: New pipeline stage (required)
    - signal_id: Optional intelligence signal that triggered transition
    - notes: Optional notes about the transition

    Returns:
    - Updated PipelineEntry
    """
    try:
        updated = await SupplyPipelineTracker.update_stage(
            db.pool, pipeline_id, new_stage, signal_id=signal_id, notes=notes
        )
        return updated.model_dump()

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating pipeline stage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update pipeline stage")


@admin_router.delete("/pipeline/{pipeline_id}", response_model=dict)
async def delete_pipeline_entry(pipeline_id: int) -> dict:
    """
    Delete a pipeline entry (admin only).

    Returns:
    - success: Whether deletion was successful
    """
    try:
        deleted = await SupplyPipelineTracker.delete_entry(db.pool, pipeline_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Pipeline entry not found")

        return {"success": True, "pipeline_id": pipeline_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting pipeline entry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete pipeline entry")


@admin_router.post("/pipeline/ingest", response_model=dict)
async def ingest_from_signal(signal: dict) -> dict:
    """
    Create/update pipeline entry from intelligence signal (admin only).

    Request body should contain signal data from intelligence_signals table:
    - id: Signal ID
    - addresses: List of addresses
    - neighborhood: Neighborhood name
    - zoning_from: Current zoning
    - zoning_to: Proposed zoning
    - height_after: Proposed storeys
    - unit_count: Residential units
    - signal_type: Type of signal
    - confidence: Extraction confidence

    Returns:
    - Created or updated PipelineEntry
    """
    try:
        entry = await SupplyPipelineTracker.ingest_from_signal(db.pool, signal)
        return entry.model_dump()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error ingesting from signal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to ingest from signal")
