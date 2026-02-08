"""
Job status tracking for background tasks (VCL-95 / PERF-015)

Provides:
- JobStatus enum for task lifecycle states
- JobInfo Pydantic model for API responses
- JobTracker class for database operations
- Job creation, status updates, and listing
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Dict, Any

import asyncpg
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Job Status Enum
# ────────────────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    """Enum for background job status states."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ────────────────────────────────────────────────────────────────────────────

class JobInfo(BaseModel):
    """Response model for job information."""

    id: str = Field(..., description="Job ID (same as Celery task ID)")
    job_type: str = Field(..., description="Type of background job")
    status: str = Field(..., description="Current job status")
    progress: Optional[float] = Field(
        None, description="Progress percentage (0-100)", ge=0, le=100
    )
    params: Optional[Dict[str, Any]] = Field(None, description="Job parameters")
    result: Optional[Dict[str, Any]] = Field(None, description="Job result")
    error: Optional[str] = Field(None, description="Error message if failed")
    retries: int = Field(0, description="Number of retries attempted")
    created_at: datetime = Field(..., description="Job creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Job start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Job completion timestamp")

    class Config:
        from_attributes = True


# ────────────────────────────────────────────────────────────────────────────
# JobTracker Class
# ────────────────────────────────────────────────────────────────────────────

class JobTracker:
    """
    Tracks background job status in the database.

    Provides methods to create jobs, update their status, retrieve job info,
    and list jobs with optional filtering.
    """

    @staticmethod
    async def create_job(
        db_pool: asyncpg.Pool,
        job_id: str,
        job_type: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a new background job record.

        Args:
            db_pool: Database connection pool
            job_id: Celery task ID (unique identifier)
            job_type: Type of job (e.g., "scraper", "document_processing")
            params: Optional job parameters (stored as JSON)

        Returns:
            The job_id for the created job

        Raises:
            asyncpg.IntegrityError: If job_id already exists
        """
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO background_jobs (
                    id, job_type, status, params, progress, retries, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                job_id,
                job_type,
                JobStatus.PENDING.value,
                params,
                0.0,
                0,
                datetime.utcnow(),
            )

        logger.info(
            f"Created job {job_id} of type {job_type}",
            extra={"job_id": job_id, "job_type": job_type}
        )
        return job_id

    @staticmethod
    async def update_status(
        db_pool: asyncpg.Pool,
        job_id: str,
        status: str,
        progress: Optional[float] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        retries: Optional[int] = None,
    ) -> None:
        """
        Update job status and metadata.

        Args:
            db_pool: Database connection pool
            job_id: Job ID to update
            status: New status (pending, running, success, failed, retrying)
            progress: Optional progress percentage (0-100)
            result: Optional result data (stored as JSON)
            error: Optional error message
            retries: Optional retry count increment

        Raises:
            ValueError: If job_id is not found
        """
        async with db_pool.acquire() as conn:
            now = datetime.utcnow()
            started_at = None
            completed_at = None

            # Set timestamps based on status transitions
            if status == JobStatus.RUNNING.value:
                started_at = now
            elif status in (JobStatus.SUCCESS.value, JobStatus.FAILED.value):
                completed_at = now

            query = """
                UPDATE background_jobs
                SET status = $2,
                    started_at = COALESCE($3, started_at),
                    completed_at = COALESCE($4, completed_at)
            """
            params = [job_id, status, started_at, completed_at]

            if progress is not None:
                query += ", progress = $" + str(len(params) + 1)
                params.append(progress)

            if result is not None:
                query += ", result = $" + str(len(params) + 1)
                params.append(result)

            if error is not None:
                query += ", error = $" + str(len(params) + 1)
                params.append(error)

            if retries is not None:
                query += ", retries = $" + str(len(params) + 1)
                params.append(retries)

            query += " WHERE id = $1"

            result = await conn.execute(query, *params)

            # Check if job was found
            if result == "UPDATE 0":
                logger.warning(
                    f"Job {job_id} not found for status update",
                    extra={"job_id": job_id, "status": status}
                )
                raise ValueError(f"Job {job_id} not found")

        logger.debug(
            f"Updated job {job_id} status to {status}",
            extra={"job_id": job_id, "status": status, "progress": progress}
        )

    @staticmethod
    async def get_job(db_pool: asyncpg.Pool, job_id: str) -> Optional[JobInfo]:
        """
        Get job information by ID.

        Args:
            db_pool: Database connection pool
            job_id: Job ID to retrieve

        Returns:
            JobInfo object if found, None otherwise
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM background_jobs WHERE id = $1",
                job_id
            )

        if not row:
            return None

        return JobInfo(**dict(row))

    @staticmethod
    async def list_jobs(
        db_pool: asyncpg.Pool,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[JobInfo]:
        """
        List background jobs with optional filtering.

        Args:
            db_pool: Database connection pool
            status: Filter by status (optional)
            job_type: Filter by job type (optional)
            limit: Maximum number of jobs to return (default: 50)
            offset: Number of jobs to skip (default: 0)

        Returns:
            List of JobInfo objects
        """
        query = "SELECT * FROM background_jobs WHERE 1=1"
        params = []

        if status is not None:
            query += " AND status = $" + str(len(params) + 1)
            params.append(status)

        if job_type is not None:
            query += " AND job_type = $" + str(len(params) + 1)
            params.append(job_type)

        # Order by created_at descending (newest first)
        query += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1)
        query += " OFFSET $" + str(len(params) + 2)
        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [JobInfo(**dict(row)) for row in rows]

    @staticmethod
    async def cleanup_old_jobs(
        db_pool: asyncpg.Pool,
        days: int = 30,
    ) -> int:
        """
        Delete old completed jobs from the database.

        Only removes jobs that are:
        - In success or failed status
        - Older than the specified number of days

        Args:
            db_pool: Database connection pool
            days: Delete jobs older than this many days (default: 30)

        Returns:
            Number of jobs deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        async with db_pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM background_jobs
                WHERE status IN ($1, $2)
                  AND completed_at IS NOT NULL
                  AND completed_at < $3
                """,
                JobStatus.SUCCESS.value,
                JobStatus.FAILED.value,
                cutoff_date,
            )

        # Extract count from result string (e.g., "DELETE 5")
        deleted_count = int(result.split()[-1]) if result else 0

        logger.info(
            f"Cleaned up {deleted_count} old jobs (older than {days} days)",
            extra={"deleted_count": deleted_count, "days": days}
        )
        return deleted_count
