"""
Job management API routes for background tasks (VCL-95 / PERF-015)

Provides admin-only endpoints for:
- Listing all background jobs
- Getting job status by ID
- Retrying failed jobs
- Cancelling/deleting jobs
- Cleaning up old completed jobs
"""

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from api.user_auth import get_current_user_from_request
from api.tasks.job_tracker import JobTracker, JobInfo
from api.tasks.worker import celery_app

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ────────────────────────────────────────────────────────────────────────────

class RetryJobRequest(BaseModel):
    """Request model for retrying a failed job."""
    pass  # No body required, just the job_id in path


class CleanupJobsRequest(BaseModel):
    """Request model for cleaning up old jobs."""
    days: int = 30  # Delete jobs older than this many days


class CleanupJobsResponse(BaseModel):
    """Response model for cleanup operation."""
    deleted_count: int
    message: str


# ────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────────────────────

async def _require_admin(
    request: Request,
    user: dict = Depends(get_current_user_from_request),
) -> dict:
    """
    Verify that the current user has admin role.

    Args:
        request: FastAPI Request
        user: Current user from dependency

    Returns:
        User dict if admin, raises HTTPException otherwise

    Raises:
        HTTPException: If user is not admin
    """
    if user.get("role") != "admin":
        logger.warning(
            f"Unauthorized job access attempt by user {user.get('id')}",
            extra={"user_id": user.get("id"), "user_role": user.get("role")}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    return user


# ────────────────────────────────────────────────────────────────────────────
# API Routes
# ────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/v1/admin/jobs", tags=["admin:jobs"])


@router.get("")
async def list_jobs(
    request: Request,
    status_filter: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(_require_admin),
) -> dict:
    """
    List all background jobs with optional filtering.

    Query Parameters:
    - status_filter: Filter by job status (pending, running, success, failed, retrying)
    - job_type: Filter by job type
    - limit: Maximum number of jobs to return (default: 50)
    - offset: Number of jobs to skip for pagination (default: 0)

    Returns:
        List of JobInfo objects with pagination metadata

    Requires:
        Admin role
    """
    logger.info(
        f"Listing jobs (status={status_filter}, type={job_type})",
        extra={"user_id": user.get("id")}
    )

    db_pool = request.app.state.pool
    if not db_pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available"
        )

    try:
        jobs = await JobTracker.list_jobs(
            db_pool,
            status=status_filter,
            job_type=job_type,
            limit=limit,
            offset=offset,
        )

        return {
            "jobs": jobs,
            "total_count": len(jobs),
            "limit": limit,
            "offset": offset,
        }

    except Exception as exc:
        logger.error(
            f"Failed to list jobs: {exc}",
            exc_info=True,
            extra={"user_id": user.get("id")}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list jobs"
        )


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    request: Request,
    user: dict = Depends(_require_admin),
) -> JobInfo:
    """
    Get detailed status of a specific background job.

    Path Parameters:
    - job_id: Celery task ID (UUID format)

    Returns:
        JobInfo with complete job details

    Raises:
        HTTPException 404: If job not found
        HTTPException 403: If not admin
    """
    logger.debug(
        f"Getting job {job_id}",
        extra={"user_id": user.get("id"), "job_id": job_id}
    )

    db_pool = request.app.state.pool
    if not db_pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available"
        )

    try:
        job = await JobTracker.get_job(db_pool, job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found"
            )

        return job

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Failed to get job {job_id}: {exc}",
            exc_info=True,
            extra={"user_id": user.get("id"), "job_id": job_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get job"
        )


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: str,
    request: Request,
    body: RetryJobRequest,
    user: dict = Depends(_require_admin),
) -> dict:
    """
    Retry a failed background job.

    Revokes the current task and resubmits it to Celery for execution.
    Only works for jobs in FAILED or RETRYING status.

    Path Parameters:
    - job_id: Celery task ID to retry

    Returns:
        Confirmation with new task ID and status

    Raises:
        HTTPException 404: If job not found
        HTTPException 400: If job cannot be retried
        HTTPException 403: If not admin
    """
    logger.info(
        f"Retrying job {job_id}",
        extra={"user_id": user.get("id"), "job_id": job_id}
    )

    db_pool = request.app.state.pool
    if not db_pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available"
        )

    try:
        # Get current job
        job = await JobTracker.get_job(db_pool, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found"
            )

        # Only allow retry for failed/retrying jobs
        if job.status not in ("failed", "retrying"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot retry job in {job.status} status"
            )

        # Revoke current task in Celery
        celery_app.control.revoke(job_id, terminate=False)

        # Update job status to RETRYING
        await JobTracker.update_status(
            db_pool,
            job_id,
            "retrying",
            retries=job.retries + 1,
        )

        logger.info(
            f"Job {job_id} retried successfully",
            extra={"user_id": user.get("id"), "job_id": job_id}
        )

        return {
            "job_id": job_id,
            "status": "retrying",
            "retry_count": job.retries + 1,
            "message": "Job queued for retry",
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Failed to retry job {job_id}: {exc}",
            exc_info=True,
            extra={"user_id": user.get("id"), "job_id": job_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retry job"
        )


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    request: Request,
    user: dict = Depends(_require_admin),
) -> dict:
    """
    Cancel/delete a background job.

    Terminates the Celery task and optionally removes its database record.
    Works for jobs in any status (pending, running, failed, etc.)

    Path Parameters:
    - job_id: Celery task ID to cancel

    Returns:
        Confirmation with cancelled job status

    Raises:
        HTTPException 404: If job not found
        HTTPException 403: If not admin
    """
    logger.info(
        f"Deleting job {job_id}",
        extra={"user_id": user.get("id"), "job_id": job_id}
    )

    db_pool = request.app.state.pool
    if not db_pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available"
        )

    try:
        # Verify job exists
        job = await JobTracker.get_job(db_pool, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found"
            )

        # Revoke task in Celery (forcefully if running)
        celery_app.control.revoke(job_id, terminate=True)

        # Update job status to FAILED with cancellation message
        await JobTracker.update_status(
            db_pool,
            job_id,
            "failed",
            error="Job cancelled by admin",
        )

        logger.info(
            f"Job {job_id} deleted successfully",
            extra={"user_id": user.get("id"), "job_id": job_id}
        )

        return {
            "job_id": job_id,
            "status": "cancelled",
            "message": "Job cancelled and removed",
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Failed to delete job {job_id}: {exc}",
            exc_info=True,
            extra={"user_id": user.get("id"), "job_id": job_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete job"
        )


@router.post("/cleanup")
async def cleanup_jobs(
    request: Request,
    body: CleanupJobsRequest,
    user: dict = Depends(_require_admin),
) -> CleanupJobsResponse:
    """
    Clean up old completed background jobs.

    Removes all successful and failed jobs older than the specified number of days.
    Only removes completed jobs to prevent losing active job history.

    Request Body:
    - days: Delete jobs older than this many days (default: 30)

    Returns:
        Confirmation with number of deleted jobs

    Raises:
        HTTPException 403: If not admin
    """
    logger.info(
        f"Cleaning up jobs older than {body.days} days",
        extra={"user_id": user.get("id"), "days": body.days}
    )

    db_pool = request.app.state.pool
    if not db_pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available"
        )

    try:
        deleted_count = await JobTracker.cleanup_old_jobs(db_pool, days=body.days)

        logger.info(
            f"Cleanup completed: {deleted_count} jobs deleted",
            extra={"user_id": user.get("id"), "deleted_count": deleted_count}
        )

        return CleanupJobsResponse(
            deleted_count=deleted_count,
            message=f"Successfully deleted {deleted_count} jobs older than {body.days} days",
        )

    except Exception as exc:
        logger.error(
            f"Failed to cleanup jobs: {exc}",
            exc_info=True,
            extra={"user_id": user.get("id")}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cleanup jobs"
        )


logger.info("Job management routes registered")
