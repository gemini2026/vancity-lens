"""
VanCity Lens — CSV Export Routes (VCL-101 / FE-012)

FastAPI endpoints for exporting signals, neighborhood comparisons, and parcels to CSV.
"""

import logging
import os
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse
import asyncpg

from .db import db
from .csv_export import (
    CSVExporter,
    SignalExportFilters,
    ParcelExportFilters,
)
from .user_auth import get_optional_user_from_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/export", tags=["csv_export"])


# ────────────────────────────────────────────────────────────────────────────
# Helper: Get database pool from request or module
# ────────────────────────────────────────────────────────────────────────────


def get_db_pool(request: Request) -> asyncpg.Pool:
    """
    Resolve asyncpg pool from request.app.state or global db module.

    Usage in route dependencies:
        pool: asyncpg.Pool = Depends(get_db_pool)

    Args:
        request: FastAPI Request object

    Returns:
        asyncpg.Pool instance

    Raises:
        HTTPException: 503 if pool is unavailable
    """
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        pool = db.pool
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail="Database not available",
        )
    return pool


def _require_auth_in_production(user: Optional[dict]) -> None:
    """CSV exports are public in non-production (demo/dev), authenticated in production."""
    if os.getenv("VANCITY_ENV", "development").lower() == "production" and user is None:
        raise HTTPException(status_code=401, detail="Missing authorization credentials")


# ────────────────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────────────────


@router.get(
    "/signals",
    responses={200: {"content": {"text/csv": {}}}},
    summary="Export filtered signals as CSV",
    description="Download signals matching filters as CSV file with all visible fields, source URLs, and confidence scores.",
)
async def export_signals(
    request: Request,
    neighborhood: Optional[str] = Query(None, description="Filter by neighborhood"),
    category: Optional[str] = Query(None, description="Filter by signal category/type"),
    signal_type: Optional[str] = Query(
        None, description="Alias for category (matches UI filter param)"
    ),
    date_from: Optional[date] = Query(
        None, description="Export signals from this date onwards"
    ),
    date_to: Optional[date] = Query(None, description="Export signals up to this date"),
    date_range: Optional[str] = Query(
        None,
        description="Convenience lookback window: 7d|30d|90d|all (matches UI filter param)",
    ),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
    limit: int = Query(1000, ge=1, le=10000, description="Max rows to export"),
    user: Optional[dict] = Depends(get_optional_user_from_request),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> StreamingResponse:
    """
    Export filtered signals as CSV.

    Returns CSV file with all visible signal fields plus metadata (source URL, confidence).
    Filename format: signals_{neighborhood}_{YYYY-MM-DD}.csv

    Args:
        request: FastAPI Request
        neighborhood: Optional neighborhood filter
        category: Optional signal category filter
        date_from: Optional start date for signal events
        date_to: Optional end date for signal events
        severity: Optional severity filter
        limit: Max rows to export (1-10000, default 1000)
        user: Authenticated user (required)
        pool: Database connection pool

    Returns:
        StreamingResponse with CSV file as attachment

    Raises:
        401: User not authenticated
        503: Database unavailable
        500: Export generation error
    """
    try:
        _require_auth_in_production(user)

        effective_category = category or signal_type
        effective_date_from = date_from
        effective_date_to = date_to
        if effective_date_from is None and effective_date_to is None and date_range:
            dr = date_range.strip().lower()
            if dr != "all":
                # Accept "7d" / "30d" / "90d"
                try:
                    days = int(dr[:-1]) if dr.endswith("d") else int(dr)
                    effective_date_from = date.today() - timedelta(days=days)
                    effective_date_to = date.today()
                except ValueError:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid date_range: {date_range}"
                    )

        # Build filters
        filters = SignalExportFilters(
            neighborhood=neighborhood,
            category=effective_category,
            date_from=effective_date_from,
            date_to=effective_date_to,
            severity=severity,
            limit=limit,
        )

        # Export signals
        csv_buffer, filename = await CSVExporter.export_signals(pool, filters)

        # Get content for response
        content = csv_buffer.getvalue()

        # Return as downloadable CSV
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Rows": str(len(content.splitlines()) - 1),  # Exclude header
            },
        )
    except ValueError as e:
        logger.warning(f"Invalid export parameters: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error exporting signals: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate CSV export")


@router.get(
    "/neighborhoods",
    responses={200: {"content": {"text/csv": {}}}},
    summary="Export neighborhood comparison scorecard as CSV",
    description="Download side-by-side neighborhood comparison with all scorecard metrics.",
)
async def export_neighborhood_comparison(
    request: Request,
    neighborhoods: Optional[str] = Query(
        None,
        description=(
            "Optional comma-separated list of neighborhood names to compare. "
            "If omitted, exports the full neighborhood scorecard summary table."
        ),
    ),
    user: Optional[dict] = Depends(get_optional_user_from_request),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> StreamingResponse:
    """
    Export neighborhood comparison scorecard as CSV.

    Returns CSV file with neighborhoods as columns and metrics as rows.
    Filename format: neighborhood_comparison_{hood1}_vs_{hood2}_{YYYY-MM-DD}.csv

    Args:
        request: FastAPI Request
        neighborhoods: Comma-separated neighborhood names
        user: Authenticated user (required)
        pool: Database connection pool

    Returns:
        StreamingResponse with CSV file as attachment

    Raises:
        400: Invalid input (no neighborhoods, too many neighborhoods)
        401: User not authenticated
        503: Database unavailable
        500: Export generation error
    """
    try:
        _require_auth_in_production(user)

        neighborhood_list: list[str] = []
        if neighborhoods:
            neighborhood_list = [
                n.strip() for n in neighborhoods.split(",") if n.strip()
            ]

        if neighborhood_list:
            if len(neighborhood_list) > 10:
                raise HTTPException(
                    status_code=400,
                    detail="Maximum 10 neighborhoods allowed for comparison",
                )

            # Export comparison
            csv_buffer, filename = await CSVExporter.export_neighborhood_comparison(
                pool,
                neighborhood_list,
            )
        else:
            # Export full summary table
            csv_buffer, filename = await CSVExporter.export_neighborhood_summaries(pool)

        # Get content for response
        content = csv_buffer.getvalue()

        # Return as downloadable CSV
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Neighborhoods": str(
                    len(neighborhood_list) if neighborhood_list else "all"
                ),
            },
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid export parameters: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error exporting neighborhood comparison: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate CSV export")


@router.get(
    "/parcels",
    responses={200: {"content": {"text/csv": {}}}},
    summary="Export parcel data as CSV",
    description="Download parcel data matching filters with entitlement analysis, valuation, and zoning information.",
)
async def export_parcels(
    request: Request,
    neighborhood: Optional[str] = Query(None, description="Filter by neighborhood"),
    zoning: Optional[str] = Query(None, description="Filter by zoning code"),
    min_lot_sqft: Optional[float] = Query(
        None, ge=0, description="Minimum lot size in sqft"
    ),
    max_lot_sqft: Optional[float] = Query(
        None, ge=0, description="Maximum lot size in sqft"
    ),
    limit: int = Query(1000, ge=1, le=5000, description="Max rows to export"),
    user: Optional[dict] = Depends(get_optional_user_from_request),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> StreamingResponse:
    """
    Export parcel data as CSV.

    Returns CSV file with all parcel fields, zoning, valuation, and entitlement analysis.
    Filename format: parcels_{neighborhood}_{YYYY-MM-DD}.csv

    Args:
        request: FastAPI Request
        neighborhood: Optional neighborhood filter
        zoning: Optional zoning code filter
        min_lot_sqft: Optional minimum lot size filter
        max_lot_sqft: Optional maximum lot size filter
        limit: Max rows to export (1-5000, default 1000)
        user: Authenticated user (required)
        pool: Database connection pool

    Returns:
        StreamingResponse with CSV file as attachment

    Raises:
        400: Invalid input
        401: User not authenticated
        503: Database unavailable
        500: Export generation error
    """
    try:
        _require_auth_in_production(user)

        # Build filters
        filters = ParcelExportFilters(
            neighborhood=neighborhood,
            zoning=zoning,
            min_lot_sqft=min_lot_sqft,
            max_lot_sqft=max_lot_sqft,
            limit=limit,
        )

        # Export parcels
        csv_buffer, filename = await CSVExporter.export_parcels(pool, filters)

        # Get content for response
        content = csv_buffer.getvalue()

        # Return as downloadable CSV
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Rows": str(len(content.splitlines()) - 1),  # Exclude header
            },
        )
    except ValueError as e:
        logger.warning(f"Invalid export parameters: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error exporting parcels: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate CSV export")
