"""
FastAPI routes for regulatory change records archive (F02-D).

Provides REST API access to:
- Paginated search with filters (change_type, geographic_scope, dates, full-text)
- Single change record retrieval by UUID
"""

import json
import logging
from datetime import date
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["regulatory-changes"])


class ChangeRecordResponse(BaseModel):
    """Response model for a single regulatory change record."""

    change_id: str
    signal_id: Optional[int] = None
    change_type: str
    source_url: Optional[str] = None
    source_document_title: Optional[str] = None
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    geographic_scope: Optional[str] = None
    affected_areas: list[str] = []
    entitlement_change: dict = {}
    plain_english_summary: Optional[str] = Field(None, max_length=1200)
    nlp_confidence_score: Optional[float] = None
    requires_manual_review: Optional[bool] = None
    extraction_timestamp: Optional[str] = None
    created_at: Optional[str] = None


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    page: int
    per_page: int
    total: int
    total_pages: int


class PaginatedChanges(BaseModel):
    """Paginated response for change records search."""

    results: list[ChangeRecordResponse]
    pagination: PaginationMeta


def _row_to_response(row) -> ChangeRecordResponse:
    """Convert a database row to a ChangeRecordResponse.

    Handles JSONB deserialization (asyncpg returns JSONB as strings)
    and date/datetime serialization to ISO strings.

    Args:
        row: asyncpg Record from change_records table

    Returns:
        ChangeRecordResponse instance
    """
    entitlement_change_raw = row["entitlement_change"]
    if isinstance(entitlement_change_raw, str):
        entitlement_change = json.loads(entitlement_change_raw)
    else:
        entitlement_change = entitlement_change_raw or {}

    return ChangeRecordResponse(
        change_id=str(row["change_id"]),
        signal_id=row["signal_id"],
        change_type=row["change_type"],
        source_url=row["source_url"],
        source_document_title=row["source_document_title"],
        publication_date=row["publication_date"].isoformat() if row["publication_date"] else None,
        effective_date=row["effective_date"].isoformat() if row["effective_date"] else None,
        geographic_scope=row["geographic_scope"],
        affected_areas=row["affected_areas"] or [],
        entitlement_change=entitlement_change,
        plain_english_summary=row["plain_english_summary"],
        nlp_confidence_score=float(row["nlp_confidence_score"]) if row["nlp_confidence_score"] is not None else None,
        requires_manual_review=row["requires_manual_review"],
        extraction_timestamp=row["extraction_timestamp"].isoformat() if row["extraction_timestamp"] else None,
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
    )


def get_db_pool(request: Request) -> asyncpg.Pool:
    """Get database pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if not pool:
        logger.error("Database pool not initialized")
        raise HTTPException(
            status_code=500,
            detail="Database connection not available",
        )
    return pool


@router.get(
    "/changes",
    summary="Search regulatory change records",
    description=(
        "Paginated search of regulatory change archive with filters. "
        "Supports full-text search, change type, geographic scope, date range, and affected area filtering."
    ),
    response_model=PaginatedChanges,
)
async def get_changes(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
    change_type: Optional[str] = Query(None, description="Filter by change type"),
    geographic_scope: Optional[str] = Query(None, description="Filter by geographic scope"),
    affected_area: Optional[str] = Query(None, description="Filter by affected area (case-insensitive match)"),
    start_date: Optional[date] = Query(None, description="Filter by publication date >= start_date"),
    end_date: Optional[date] = Query(None, description="Filter by publication date <= end_date"),
    q: Optional[str] = Query(None, description="Full-text search on summary and title"),
):
    """
    Search regulatory change records with pagination and filters.

    Returns paginated results with metadata (total count, page info).
    """
    try:
        db_pool = get_db_pool(request)

        # Build dynamic query
        conditions = []
        params = []
        param_idx = 1

        if change_type:
            conditions.append(f"change_type = ${param_idx}")
            params.append(change_type)
            param_idx += 1

        if geographic_scope:
            conditions.append(f"geographic_scope = ${param_idx}")
            params.append(geographic_scope)
            param_idx += 1

        if affected_area:
            conditions.append(f"EXISTS (SELECT 1 FROM unnest(affected_areas) AS a WHERE a ILIKE ${param_idx})")
            params.append(f"%{affected_area}%")
            param_idx += 1

        if start_date:
            conditions.append(f"publication_date >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            conditions.append(f"publication_date <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        if q:
            conditions.append(
                f"to_tsvector('english', coalesce(plain_english_summary, '') || ' ' || source_document_title) @@ plainto_tsquery('english', ${param_idx})"
            )
            params.append(q)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        async with db_pool.acquire() as conn:
            count_row = await conn.fetchrow(
                f"SELECT COUNT(*) as total FROM change_records WHERE {where_clause}",
                *params,
            )
            total = count_row["total"]

            # Get paginated results
            offset = (page - 1) * per_page
            rows = await conn.fetch(
                f"""
                SELECT change_id, signal_id, change_type, source_url, source_document_title,
                       publication_date, effective_date, geographic_scope, affected_areas,
                       entitlement_change, plain_english_summary, nlp_confidence_score,
                       requires_manual_review, extraction_timestamp, created_at
                FROM change_records
                WHERE {where_clause}
                ORDER BY publication_date DESC NULLS LAST, created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
                """,
                *params,
                per_page,
                offset,
            )

        # Serialize results via shared helper
        results = [_row_to_response(row) for row in rows]

        total_pages = (total + per_page - 1) // per_page

        logger.info(
            f"Change records search: page={page}, per_page={per_page}, total={total}, "
            f"filters={{change_type={change_type}, geo={geographic_scope}, area={affected_area}, "
            f"dates={start_date}..{end_date}, q={q}}}"
        )

        return PaginatedChanges(
            results=results,
            pagination=PaginationMeta(
                page=page,
                per_page=per_page,
                total=total,
                total_pages=total_pages,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching change records: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search change records: {str(e)}",
        )


@router.get(
    "/changes/{change_id}",
    summary="Get single change record",
    description="Retrieve a single regulatory change record by UUID.",
    response_model=ChangeRecordResponse,
)
async def get_change_by_id(
    request: Request,
    change_id: UUID,
):
    """
    Get a single regulatory change record by UUID.

    Returns full record details with linked signal info.
    """
    try:
        db_pool = get_db_pool(request)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT change_id, signal_id, change_type, source_url, source_document_title,
                       publication_date, effective_date, geographic_scope, affected_areas,
                       entitlement_change, plain_english_summary, nlp_confidence_score,
                       requires_manual_review, extraction_timestamp, created_at
                FROM change_records
                WHERE change_id = $1
                """,
                change_id,
            )

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Change record {change_id} not found",
            )

        result = _row_to_response(row)

        logger.info(f"Retrieved change record: {change_id}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving change record {change_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve change record: {str(e)}",
        )
