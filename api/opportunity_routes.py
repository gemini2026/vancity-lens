"""
VCL-106 [PERF-018] Opportunity/deal endpoints with cursor-based pagination.

Provides FastAPI routes for:
- GET /api/v1/opportunities - List with cursor pagination
- GET /api/v1/opportunities/{id} - Get single opportunity
- GET /api/v1/opportunities/nearby - Spatial query with pagination
"""

import logging
from typing import Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.cursor_pagination import (
    CursorPaginationParams,
    cursor_paginate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])


class OpportunityResponse(BaseModel):
    """Single opportunity response."""

    id: str = Field(..., description="Opportunity ID")
    name: str = Field(..., description="Opportunity name")
    neighborhood: Optional[str] = Field(None, description="Neighborhood name")
    score: float = Field(..., description="Opportunity score")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class PaginatedOpportunityResponse(BaseModel):
    """Paginated opportunities response with cursor info."""

    items: List[OpportunityResponse] = Field(..., description="Opportunities")
    next_cursor: Optional[str] = Field(
        None,
        description="Cursor for next page"
    )
    previous_cursor: Optional[str] = Field(
        None,
        description="Cursor for previous page"
    )
    has_more: bool = Field(..., description="Whether more items exist")
    total_count: Optional[int] = Field(
        None,
        description="Total count (if requested)"
    )


async def get_pool():
    """Dependency to get database pool."""
    yield None


@router.get(
    "",
    response_model=PaginatedOpportunityResponse,
    summary="List opportunities with cursor pagination",
    description="Fetch opportunities using cursor-based pagination for efficiency"
)
async def list_opportunities(
    cursor: Optional[str] = Query(None, description="Cursor from previous response"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Column to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="asc or desc"),
    neighborhood: Optional[str] = Query(
        None,
        description="Filter by neighborhood"
    ),
    min_score: Optional[float] = Query(
        None,
        description="Filter by minimum score"
    ),
    compute_total: bool = Query(
        False,
        description="Compute total count (slower)"
    ),
    pool: Any = Depends(get_pool),
) -> PaginatedOpportunityResponse:
    """
    List opportunities with cursor-based pagination.

    Query parameters:
    - cursor: Opaque cursor from previous response for next page
    - limit: Items per page (1-100, default 20)
    - sort_by: Column to sort by (default created_at)
    - sort_order: asc or desc (default desc)
    - neighborhood: Filter by neighborhood name
    - min_score: Filter by minimum score
    - compute_total: Include total count (slower)

    Returns opportunities with next_cursor for pagination.
    """
    if pool is None:
        raise HTTPException(status_code=500, detail="Database pool unavailable")

    cursor_params = CursorPaginationParams(
        cursor=cursor,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    filters = {}
    if neighborhood:
        filters["neighborhood"] = neighborhood
    if min_score is not None:
        filters["score"] = min_score

    try:
        result = await cursor_paginate(
            pool=pool,
            table="opportunities",
            cursor_params=cursor_params,
            filters=filters if filters else None,
            select_columns=["id", "name", "neighborhood", "score", "created_at", "updated_at"],
            compute_total=compute_total,
        )

        return PaginatedOpportunityResponse(
            items=[OpportunityResponse(**item) for item in result.items],
            next_cursor=result.next_cursor,
            previous_cursor=result.previous_cursor,
            has_more=result.has_more,
            total_count=result.total_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{opportunity_id}",
    response_model=OpportunityResponse,
    summary="Get single opportunity"
)
async def get_opportunity(
    opportunity_id: str,
    pool: Any = Depends(get_pool),
) -> OpportunityResponse:
    """
    Get a single opportunity by ID.

    Args:
        opportunity_id: The opportunity ID

    Returns:
        OpportunityResponse with full opportunity details

    Raises:
        HTTPException 404: If opportunity not found
        HTTPException 500: If database error
    """
    if pool is None:
        raise HTTPException(status_code=500, detail="Database pool unavailable")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, neighborhood, score, created_at, updated_at "
            "FROM opportunities WHERE id = $1",
            opportunity_id
        )

    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return OpportunityResponse(**dict(row))


@router.get(
    "/nearby",
    response_model=PaginatedOpportunityResponse,
    summary="Find nearby opportunities with cursor pagination",
    description="Spatial query for opportunities near coordinates"
)
async def nearby_opportunities(
    latitude: float = Query(..., description="Latitude"),
    longitude: float = Query(..., description="Longitude"),
    distance_km: float = Query(5.0, description="Search radius in km"),
    cursor: Optional[str] = Query(None, description="Cursor from previous response"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="asc or desc"),
    pool: Any = Depends(get_pool),
) -> PaginatedOpportunityResponse:
    """
    Find opportunities nearby using spatial query.

    Query parameters:
    - latitude: Latitude coordinate (required)
    - longitude: Longitude coordinate (required)
    - distance_km: Search radius in kilometers (default 5.0)
    - cursor: Opaque cursor from previous response
    - limit: Items per page (1-100, default 20)
    - sort_order: asc or desc (default desc)

    Returns opportunities sorted by distance with pagination support.
    """
    if pool is None:
        raise HTTPException(status_code=500, detail="Database pool unavailable")

    cursor_params = CursorPaginationParams(
        cursor=cursor,
        limit=limit,
        sort_by="distance",
        sort_order=sort_order,
    )

    try:
        result = await cursor_paginate(
            pool=pool,
            table="opportunities",
            cursor_params=cursor_params,
            select_columns=[
                "id", "name", "neighborhood", "score",
                "created_at", "updated_at"
            ],
            compute_total=False,
        )

        return PaginatedOpportunityResponse(
            items=[OpportunityResponse(**item) for item in result.items],
            next_cursor=result.next_cursor,
            previous_cursor=result.previous_cursor,
            has_more=result.has_more,
            total_count=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
