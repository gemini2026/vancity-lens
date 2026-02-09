"""
VanCity Lens -- Bulk Parcel Analysis Routes (BIZ-015)

FastAPI endpoints for bulk parcel upload and analysis.
POST to submit a batch of PIDs/addresses, GET to poll for results.
"""

import logging
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from .bulk_analysis import (
    BulkAnalysisRequest,
    BulkAnalysisResult,
    create_bulk_analysis_job,
    get_job_result,
    process_bulk_analysis_job,
)
from .user_auth import get_current_user_from_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["bulk-analysis"])


# ---------------------------------------------------------------------------
# POST  /api/v1/parcels/bulk-analyze
# ---------------------------------------------------------------------------


@router.post(
    "/parcels/bulk-analyze",
    response_model=dict,
    status_code=202,
    summary="Submit a bulk parcel analysis job",
    description=(
        "Accepts a list of PIDs and/or addresses (max 100 total). "
        "Returns a job_id immediately; processing happens asynchronously. "
        "Poll GET /parcels/bulk-analyze/{job_id} for results."
    ),
)
async def submit_bulk_analysis(
    request: BulkAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(get_current_user_from_request),
):
    """
    Submit a batch of parcels for analysis.

    The endpoint validates the payload synchronously, creates a job record,
    then enqueues background processing. Clients receive the ``job_id``
    immediately and can poll the status endpoint for progress and results.
    """
    # Create the job
    job_id = await create_bulk_analysis_job(request)

    # Enqueue background processing
    background_tasks.add_task(process_bulk_analysis_job, job_id)

    logger.info(
        "User %s submitted bulk analysis job %s (%d items)",
        user.get("id", "unknown"),
        job_id,
        len(request.pids) + len(request.addresses),
    )

    return {
        "job_id": job_id,
        "status": "pending",
        "total": len(request.pids) + len(request.addresses),
        "message": "Job submitted. Poll GET /api/v1/parcels/bulk-analyze/{job_id} for results.",
    }


# ---------------------------------------------------------------------------
# GET  /api/v1/parcels/bulk-analyze/{job_id}
# ---------------------------------------------------------------------------


@router.get(
    "/parcels/bulk-analyze/{job_id}",
    response_model=BulkAnalysisResult,
    summary="Get bulk analysis job status and results",
    description=(
        "Returns the current state of a bulk-analysis job including status, "
        "progress, ranked parcel results, and summary statistics."
    ),
)
async def get_bulk_analysis_status(
    job_id: str,
    user: Dict = Depends(get_current_user_from_request),
):
    """
    Retrieve progress and results for a bulk-analysis job.

    Returns 404 if the job_id is unknown.
    """
    result = get_job_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return result
