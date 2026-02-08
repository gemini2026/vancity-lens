"""
VCL-100: Comparable Sales API Routes
FastAPI routes for comparable sales queries and market analytics
"""
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from typing import List, Optional
import asyncpg
from logging import getLogger

from api.intelligence.comparable_sales import (
    ComparableSalesService,
    ComparableResult,
    MarketStats,
    PriceTrend,
    ComparableSale
)
from api.user_auth import get_current_user_from_request

logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["comparable_sales"])


def get_db_pool(request: Request) -> asyncpg.Pool:
    """Get asyncpg connection pool from request app state."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        try:
            from api.db import db
            pool = db.pool
        except ImportError:
            pass

    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool


@router.get("/parcels/{pid}/comparables", response_model=ComparableResult)
async def get_comparables(
    pid: str,
    radius_m: int = Query(500, ge=100, le=2000, description="Search radius in meters"),
    limit: int = Query(5, ge=1, le=20, description="Maximum number of results"),
    same_zoning: bool = Query(True, description="Filter to same zoning category"),
    months: int = Query(12, ge=1, le=60, description="Lookback period in months"),
    request: Request = None,
) -> ComparableResult:
    """
    Find comparable sales near a parcel.

    Returns 3-5 nearest comparable sales within the specified radius and time period.
    Optionally filters to same zoning category.

    **Query Parameters:**
    - `radius_m`: Search radius in meters (100-2000, default 500)
    - `limit`: Maximum results to return (1-20, default 5)
    - `same_zoning`: Filter to same zoning if true (default true)
    - `months`: Include sales from last N months (1-60, default 12)

    **Returns:**
    - `parcel_pid`: The queried parcel ID
    - `comparables`: List of comparable sales with distance and pricing metrics
    - `market_stats`: Summary statistics for the zoning category
    - `query_radius_m`: The search radius used
    - `count`: Number of results returned
    """
    pool = get_db_pool(request)

    try:
        result = await ComparableSalesService.find_comparables(
            pool=pool,
            pid=pid,
            radius_m=radius_m,
            limit=limit,
            same_zoning=same_zoning,
            months=months
        )

        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Parcel with PID '{pid}' not found"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding comparables for PID {pid}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while finding comparable sales"
        )


@router.get("/market/stats/{zoning}", response_model=MarketStats)
async def get_market_stats(
    zoning: str,
    neighborhood: Optional[str] = Query(None, description="Optional neighborhood filter"),
    months: int = Query(12, ge=1, le=60, description="Lookback period in months"),
    request: Request = None,
) -> MarketStats:
    """
    Get market statistics for a zoning category.

    Returns aggregate pricing and volume metrics for a zoning category,
    optionally filtered by neighborhood.

    **Path Parameters:**
    - `zoning`: Zoning category code (e.g., RS1, RS2, C-2)

    **Query Parameters:**
    - `neighborhood`: Optional neighborhood name to filter
    - `months`: Include sales from last N months (1-60, default 12)

    **Returns:**
    - `zoning`: The zoning category
    - `count`: Number of sales in period
    - `avg_price`, `median_price`: Average and median sale prices
    - `avg_price_per_lot_sqft`: Price per square foot of lot
    - And other aggregated metrics
    """
    pool = get_db_pool(request)

    try:
        stats = await ComparableSalesService.get_market_stats(
            pool=pool,
            zoning=zoning,
            months=months,
            neighborhood=neighborhood
        )

        if stats is None:
            raise HTTPException(
                status_code=404,
                detail=f"No comparable sales data found for zoning '{zoning}'" +
                       (f" in neighborhood '{neighborhood}'" if neighborhood else "")
            )

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting market stats for zoning {zoning}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while retrieving market statistics"
        )


@router.get("/market/trends/{zoning}", response_model=List[PriceTrend])
async def get_price_trends(
    zoning: str,
    neighborhood: Optional[str] = Query(None, description="Optional neighborhood filter"),
    months: int = Query(24, ge=1, le=60, description="Lookback period in months"),
    request: Request = None,
) -> List[PriceTrend]:
    """
    Get monthly price trends for a zoning category.

    Returns monthly aggregated pricing data showing price trends over time.

    **Path Parameters:**
    - `zoning`: Zoning category code (e.g., RS1, RS2, C-2)

    **Query Parameters:**
    - `neighborhood`: Optional neighborhood name to filter
    - `months`: Include data from last N months (1-60, default 24)

    **Returns:**
    - Array of monthly price trend records with:
      - `year_month`: Year-month in YYYY-MM format
      - `avg_price`: Average sale price
      - `median_price`: Median sale price
      - `sale_count`: Number of sales that month
      - `avg_price_per_lot_sqft`: Average price per lot square foot
    """
    pool = get_db_pool(request)

    try:
        trends = await ComparableSalesService.get_price_trends(
            pool=pool,
            zoning=zoning,
            months=months,
            neighborhood=neighborhood
        )

        if not trends:
            raise HTTPException(
                status_code=404,
                detail=f"No price trend data found for zoning '{zoning}'" +
                       (f" in neighborhood '{neighborhood}'" if neighborhood else "")
            )

        return trends

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting price trends for zoning {zoning}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while retrieving price trends"
        )


@router.post("/admin/comparable-sales/ingest")
async def ingest_comparable_sales(
    data: dict,
    request: Request = None,
    current_user = Depends(get_current_user_from_request)
):
    """
    Bulk ingest comparable sales records (Admin only).

    Requires admin authentication. Accepts a list of sales records and
    bulk loads them into the comparable_sales table.

    **Request Body:**
    ```json
    {
        "records": [
            {
                "address": "123 Main St, Vancouver, BC",
                "pid": "0123456789",
                "sale_price": 850000,
                "sale_date": "2023-06-15",
                "lot_area_sqft": 4500,
                "zoning": "RS1",
                "building_type": "Single Family",
                "latitude": 49.2827,
                "longitude": -123.1207,
                "neighborhood": "Kitsilano"
            }
        ]
    }
    ```

    **Returns:**
    - `inserted`: Number of records successfully inserted
    - `failed`: Number of records that failed
    - `total`: Total number of records in request
    """
    # Check admin authorization
    if not hasattr(current_user, 'is_admin') or not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Admin authentication required"
        )

    pool = get_db_pool(request)

    try:
        records = data.get("records", [])

        if not records:
            raise HTTPException(
                status_code=400,
                detail="Request must include 'records' list"
            )

        result = await ComparableSalesService.ingest_sales_data(
            pool=pool,
            records=records
        )

        return {
            "status": "success",
            "inserted": result["inserted"],
            "failed": result["failed"],
            "total": result["total"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting comparable sales data: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while ingesting data"
        )
