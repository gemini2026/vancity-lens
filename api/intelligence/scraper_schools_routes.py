"""
VCL-96 [DATA-008] VSB School Data Scraper Routes

Admin and public endpoints for school data scraping and metrics retrieval.

Endpoints:
- POST /api/v1/admin/scrapers/schools/run — Trigger school scrape (admin)
- GET /api/v1/admin/scrapers/schools/status — Last scrape status (admin)
- GET /api/v1/intel/schools/metrics — Get school metrics for all neighborhoods (public)
- GET /api/v1/intel/schools/metrics/{neighborhood} — Get specific neighborhood (public)
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .scraper_schools import VSBSchoolScraper
from ..auth import require_admin
from ..db import db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["schools"])


# ── Request/Response Models ────────────────────────────────────


class ScrapeRunRequest(BaseModel):
    """Request to trigger a scrape run."""

    pass


class SchoolMetricsResponse(BaseModel):
    """School metrics for a neighborhood."""

    neighborhood: str
    school_count: int
    elementary_count: int
    secondary_count: int
    total_enrollment: int
    total_capacity: int
    avg_capacity_utilization: Optional[float]
    avg_student_teacher_ratio: Optional[float]
    quality_score: Optional[float]
    period_start: str
    period_end: str


class SchoolMetricsListResponse(BaseModel):
    """List of school metrics across neighborhoods."""

    neighborhoods: List[SchoolMetricsResponse]
    total_neighborhoods: int
    updated_at: str


class ScrapeRunResponse(BaseModel):
    """Response from a scrape run."""

    started_at: str
    completed_at: str
    schools_found: int
    schools_saved: int
    neighborhoods_updated: int
    status: str
    errors: List[str]


class ScrapeStatusResponse(BaseModel):
    """Status of the last scrape run."""

    last_run_at: Optional[str]
    schools_found: int
    schools_saved: int
    neighborhoods_updated: int
    status: str
    errors: List[str]


# ── Admin Endpoints ────────────────────────────────────────────


@router.post(
    "/admin/scrapers/schools/run",
    response_model=ScrapeRunResponse,
    dependencies=[Depends(require_admin)],
)
async def trigger_school_scrape(
    request: ScrapeRunRequest,
) -> Dict[str, Any]:
    """
    Trigger immediate VSB school data scrape.

    Requires admin authentication via X-Admin-Key header.

    Returns:
        ScrapeRunResponse with run statistics
    """
    try:
        logger.info("Admin triggered school data scrape")
        started_at = datetime.now()

        # Get connection pool
        pool = db.pool
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database pool not available",
            )

        # Run scraper
        scraper = VSBSchoolScraper()
        try:
            schools = await scraper.scrape()
            stats = await scraper.save_to_db(pool, schools)
        finally:
            await scraper.close()

        completed_at = datetime.now()

        # Store run in database
        errors = []
        scrape_status = "success" if stats["schools_saved"] > 0 else "partial"

        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO scraper_schools_runs
                    (started_at, completed_at, schools_found, schools_saved,
                     neighborhoods_updated, errors, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    started_at,
                    completed_at,
                    stats["schools_found"],
                    stats["schools_saved"],
                    stats["neighborhoods_updated"],
                    errors,
                    scrape_status,
                )
        except Exception as e:
            logger.error(f"Error storing scrape run: {e}")

        logger.info(
            f"School scrape completed: {stats['schools_found']} found, "
            f"{stats['schools_saved']} saved, "
            f"{stats['neighborhoods_updated']} neighborhoods updated"
        )

        return {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "schools_found": stats["schools_found"],
            "schools_saved": stats["schools_saved"],
            "neighborhoods_updated": stats["neighborhoods_updated"],
            "status": scrape_status,
            "errors": errors,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in trigger_school_scrape: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run school scraper",
        )


@router.get(
    "/admin/scrapers/schools/status",
    response_model=ScrapeStatusResponse,
    dependencies=[Depends(require_admin)],
)
async def get_school_scrape_status() -> Dict[str, Any]:
    """
    Get status of the last school data scrape run.

    Requires admin authentication via X-Admin-Key header.

    Returns:
        ScrapeStatusResponse with last run details
    """
    try:
        pool = db.pool
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database pool not available",
            )

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT started_at, completed_at, schools_found, schools_saved,
                       neighborhoods_updated, status, errors
                FROM scraper_schools_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )

        if not row:
            return {
                "last_run_at": None,
                "schools_found": 0,
                "schools_saved": 0,
                "neighborhoods_updated": 0,
                "status": "never_run",
                "errors": [],
            }

        return {
            "last_run_at": row["started_at"].isoformat() if row["started_at"] else None,
            "schools_found": row["schools_found"] or 0,
            "schools_saved": row["schools_saved"] or 0,
            "neighborhoods_updated": row["neighborhoods_updated"] or 0,
            "status": row["status"] or "unknown",
            "errors": row["errors"] or [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_school_scrape_status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scrape status",
        )


# ── Public Endpoints ───────────────────────────────────────────


@router.get("/schools/metrics", response_model=SchoolMetricsListResponse)
async def get_all_school_metrics() -> Dict[str, Any]:
    """
    Get school metrics for all neighborhoods.

    Returns the latest school metrics (capacity utilization, student-teacher ratios,
    quality scores) for all Vancouver neighborhoods.

    Returns:
        SchoolMetricsListResponse with metrics for all neighborhoods
    """
    try:
        pool = db.pool
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database pool not available",
            )

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (neighborhood)
                    neighborhood, school_count, elementary_count, secondary_count,
                    total_enrollment, total_capacity, avg_capacity_utilization,
                    avg_student_teacher_ratio, quality_score, period_start, period_end
                FROM school_metrics
                ORDER BY neighborhood, period_start DESC
                """
            )

        metrics_list = []
        for row in rows:
            metrics_list.append(
                SchoolMetricsResponse(
                    neighborhood=row["neighborhood"],
                    school_count=row["school_count"],
                    elementary_count=row["elementary_count"],
                    secondary_count=row["secondary_count"],
                    total_enrollment=row["total_enrollment"],
                    total_capacity=row["total_capacity"],
                    avg_capacity_utilization=row["avg_capacity_utilization"],
                    avg_student_teacher_ratio=row["avg_student_teacher_ratio"],
                    quality_score=row["quality_score"],
                    period_start=str(row["period_start"])
                    if row["period_start"]
                    else "",
                    period_end=str(row["period_end"]) if row["period_end"] else "",
                )
            )

        # Sort by neighborhood name
        metrics_list.sort(key=lambda x: x.neighborhood)

        return {
            "neighborhoods": metrics_list,
            "total_neighborhoods": len(metrics_list),
            "updated_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_all_school_metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve school metrics",
        )


@router.get(
    "/schools/metrics/{neighborhood}",
    response_model=SchoolMetricsResponse,
)
async def get_neighborhood_school_metrics(neighborhood: str) -> Dict[str, Any]:
    """
    Get school metrics for a specific neighborhood.

    Args:
        neighborhood: Neighborhood name (e.g., 'Kitsilano', 'Downtown')

    Returns:
        SchoolMetricsResponse with metrics for the specified neighborhood

    Raises:
        HTTPException: 404 if neighborhood not found in metrics
    """
    try:
        pool = db.pool
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database pool not available",
            )

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT neighborhood, school_count, elementary_count, secondary_count,
                       total_enrollment, total_capacity, avg_capacity_utilization,
                       avg_student_teacher_ratio, quality_score, period_start, period_end
                FROM school_metrics
                WHERE LOWER(neighborhood) = LOWER($1)
                ORDER BY period_start DESC
                LIMIT 1
                """,
                neighborhood,
            )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No school metrics found for neighborhood '{neighborhood}'",
            )

        return SchoolMetricsResponse(
            neighborhood=row["neighborhood"],
            school_count=row["school_count"],
            elementary_count=row["elementary_count"],
            secondary_count=row["secondary_count"],
            total_enrollment=row["total_enrollment"],
            total_capacity=row["total_capacity"],
            avg_capacity_utilization=row["avg_capacity_utilization"],
            avg_student_teacher_ratio=row["avg_student_teacher_ratio"],
            quality_score=row["quality_score"],
            period_start=str(row["period_start"]) if row["period_start"] else "",
            period_end=str(row["period_end"]) if row["period_end"] else "",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_neighborhood_school_metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve school metrics",
        )
