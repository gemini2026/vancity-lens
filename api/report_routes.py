"""
VanCity Lens — PDF Report Routes (VCL-94 / BIZ-006)

FastAPI routes for report generation, preview, and batch operations.
"""

import logging
from typing import Optional
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
import asyncpg

from .db import db
from .report_generator import (
    generate_parcel_report,
    ParcelReport,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["reports"])


# ────────────────────────────────────────────────────────────────────────────
# Response Models
# ────────────────────────────────────────────────────────────────────────────


class ReportPreviewResponse(ParcelReport):
    """Report data for frontend preview (JSON)."""

    pass


class BatchReportJob:
    """Background job for batch report generation."""

    def __init__(self, job_id: str, pids: list[str]):
        self.job_id = job_id
        self.pids = pids
        self.status = "pending"
        self.completed = 0
        self.failed = 0
        self.results = {}
        self.errors = {}
        self.started_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None


# In-memory job tracking (in production, use Redis or database)
_batch_jobs: dict[str, BatchReportJob] = {}


# ────────────────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────────────────


@router.get(
    "/parcels/{pid}/report.pdf",
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Download parcel validation report as PDF",
    description="Generate and download a professional PDF report for a parcel including branded header, parcel overview, entitlement analysis, pro forma, risk assessment, due diligence checklist, and sources.",
)
async def download_parcel_report_pdf(
    pid: str,
    request=None,
    pool: asyncpg.Pool = Depends(lambda: db.pool),
) -> StreamingResponse:
    """
    Generate and download a PDF report for a parcel.

    Args:
        pid: Parcel ID (BC Land Title PID)
        request: HTTP request (for potential auth)
        pool: Database connection pool

    Returns:
        PDF file as streaming response

    Raises:
        404: Parcel not found
        500: PDF generation error
    """
    if not pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        # Generate PDF
        pdf_bytes = await generate_parcel_report(pool, pid, user_id=None)

        # Return as downloadable attachment
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=report_{pid}.pdf"},
        )
    except ValueError:
        logger.warning(f"Parcel not found: {pid}")
        raise HTTPException(status_code=404, detail=f"Parcel {pid} not found")
    except Exception as e:
        logger.exception(f"Error generating report for {pid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate report")


@router.get(
    "/parcels/{pid}/report/preview",
    response_model=ReportPreviewResponse,
    summary="Get report data as JSON preview",
    description="Retrieve report data in JSON format for frontend preview before downloading PDF.",
)
async def preview_parcel_report(
    pid: str,
    pool: asyncpg.Pool = Depends(lambda: db.pool),
) -> ReportPreviewResponse:
    """
    Get report data in JSON format for frontend preview.

    Args:
        pid: Parcel ID (BC Land Title PID)
        pool: Database connection pool

    Returns:
        Report data as JSON

    Raises:
        404: Parcel not found
        500: Data fetch error
    """
    if not pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        from .report_generator import ReportGenerator

        generator = ReportGenerator()
        parcel_data = await generator._fetch_parcel_data(pool, pid)

        if not parcel_data:
            raise HTTPException(status_code=404, detail=f"Parcel {pid} not found")

        return parcel_data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching report preview for {pid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch report data")


@router.post(
    "/reports/batch",
    summary="Generate reports for multiple parcels",
    description="Start a background job to generate PDF reports for multiple parcels. Returns job ID for polling status.",
)
async def start_batch_report_generation(
    pids: list[str] = Query(..., description="List of parcel IDs"),
    pool: asyncpg.Pool = Depends(lambda: db.pool),
) -> dict:
    """
    Start a batch report generation job.

    Args:
        pids: List of parcel IDs to generate reports for
        pool: Database connection pool

    Returns:
        Job info with job_id for status polling

    Raises:
        400: Invalid input
        500: Job creation error
    """
    if not pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    if not pids or len(pids) == 0:
        raise HTTPException(status_code=400, detail="At least one PID required")

    if len(pids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 parcels per batch")

    try:
        # Create batch job
        job_id = str(uuid4())
        job = BatchReportJob(job_id, pids)
        _batch_jobs[job_id] = job

        # Start background processing (in production, use Celery/RQ)
        # For now, just mark as pending
        job.status = "pending"

        logger.info(f"Created batch job {job_id} for {len(pids)} parcels")

        return {
            "job_id": job_id,
            "status": "pending",
            "pids_count": len(pids),
            "created_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.exception(f"Error creating batch job: {e}")
        raise HTTPException(status_code=500, detail="Failed to create batch job")


@router.get(
    "/reports/batch/{job_id}",
    summary="Check batch report job status",
    description="Poll the status of a batch report generation job.",
)
async def get_batch_report_status(job_id: str) -> dict:
    """
    Get status of a batch report job.

    Args:
        job_id: Batch job ID

    Returns:
        Job status details

    Raises:
        404: Job not found
    """
    job = _batch_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {
        "job_id": job_id,
        "status": job.status,
        "pids_count": len(job.pids),
        "completed": job.completed,
        "failed": job.failed,
        "created_at": job.started_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get(
    "/reports/batch/{job_id}/results",
    summary="Get batch report results",
    description="Download generated PDF reports from a completed batch job.",
)
async def get_batch_report_results(job_id: str) -> dict:
    """
    Get results from a batch job (after completion).

    Args:
        job_id: Batch job ID

    Returns:
        Results mapping PID to download URL

    Raises:
        404: Job not found
        400: Job not completed
    """
    job = _batch_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job status is {job.status}, not completed",
        )

    return {
        "job_id": job_id,
        "status": "completed",
        "results": job.results,
        "errors": job.errors,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
