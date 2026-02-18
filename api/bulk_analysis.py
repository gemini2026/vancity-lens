"""
VanCity Lens -- Bulk Parcel Analysis (BIZ-015)

Business logic for bulk parcel upload and analysis.
Accepts lists of PIDs or addresses, processes them asynchronously,
and returns ranked results with deal scores and summary statistics.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ITEMS = 100
GRADE_THRESHOLDS = {"A": 80, "B": 60, "C": 40, "D": 20}


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    """Lifecycle states for a bulk-analysis job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BulkAnalysisRequest(BaseModel):
    """Inbound request body for bulk parcel analysis."""

    model_config = ConfigDict(str_strip_whitespace=True)

    pids: list[str] = Field(default_factory=list, max_length=100)
    addresses: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def check_at_least_one_input(self) -> "BulkAnalysisRequest":
        """Ensure at least one PID or address is provided."""
        if not self.pids and not self.addresses:
            raise ValueError("At least one PID or address must be provided")
        return self

    @model_validator(mode="after")
    def check_max_total(self) -> "BulkAnalysisRequest":
        """Ensure total items do not exceed MAX_ITEMS."""
        total = len(self.pids) + len(self.addresses)
        if total > MAX_ITEMS:
            raise ValueError(f"Total items ({total}) exceeds maximum of {MAX_ITEMS}")
        return self

    @model_validator(mode="after")
    def strip_empty_strings(self) -> "BulkAnalysisRequest":
        """Remove blank strings from lists after whitespace stripping."""
        self.pids = [p for p in self.pids if p]
        self.addresses = [a for a in self.addresses if a]
        if not self.pids and not self.addresses:
            raise ValueError("At least one non-empty PID or address must be provided")
        return self


class ParcelResult(BaseModel):
    """Analysis result for a single parcel."""

    model_config = ConfigDict(str_strip_whitespace=True)

    identifier: str
    identifier_type: str  # "pid" or "address"
    deal_score: float = Field(ge=0, le=100)
    grade: str  # A / B / C / D / F
    zoning: Optional[str] = None
    lot_area_sqm: Optional[float] = None
    assessed_value: Optional[float] = None
    max_storeys: Optional[int] = None
    max_fsr: Optional[float] = None
    storey_uplift: Optional[int] = None
    error: Optional[str] = None


class BulkAnalysisSummary(BaseModel):
    """Aggregate statistics for a completed bulk-analysis job."""

    model_config = ConfigDict(str_strip_whitespace=True)

    avg_score: float
    min_score: float
    max_score: float
    median_score: float
    count_by_grade: dict[str, int]
    total_analyzed: int
    total_errors: int


class BulkAnalysisResult(BaseModel):
    """Full result object for a bulk-analysis job."""

    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str
    status: str  # maps to JobStatus values
    total: int
    completed: int
    results: list[dict] = Field(default_factory=list)
    summary: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# In-memory job store (MVP -- no database needed)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}


def get_jobs_store() -> dict[str, dict]:
    """Return a reference to the in-memory jobs store (useful for testing)."""
    return _jobs


def clear_jobs_store() -> None:
    """Clear all jobs (useful for testing)."""
    _jobs.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_to_grade(score: float) -> str:
    """Map a numeric deal_score (0-100) to a letter grade."""
    for grade, threshold in GRADE_THRESHOLDS.items():
        if score >= threshold:
            return grade
    return "F"


def _compute_median(values: list[float]) -> float:
    """Compute median of a list of floats."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
    return sorted_vals[mid]


def _generate_summary(results: list[dict]) -> dict:
    """Build summary statistics from a list of parcel results."""
    successful = [r for r in results if r.get("error") is None]
    errors = [r for r in results if r.get("error") is not None]

    if not successful:
        return BulkAnalysisSummary(
            avg_score=0.0,
            min_score=0.0,
            max_score=0.0,
            median_score=0.0,
            count_by_grade={"A": 0, "B": 0, "C": 0, "D": 0, "F": 0},
            total_analyzed=0,
            total_errors=len(errors),
        ).model_dump()

    scores = [r["deal_score"] for r in successful]
    grades = [r["grade"] for r in successful]

    count_by_grade = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for g in grades:
        count_by_grade[g] = count_by_grade.get(g, 0) + 1

    return BulkAnalysisSummary(
        avg_score=round(sum(scores) / len(scores), 2),
        min_score=min(scores),
        max_score=max(scores),
        median_score=_compute_median(scores),
        count_by_grade=count_by_grade,
        total_analyzed=len(successful),
        total_errors=len(errors),
    ).model_dump()


# ---------------------------------------------------------------------------
# Mock scoring (placeholder for real entitlement engine integration)
# ---------------------------------------------------------------------------


def _mock_score_parcel(identifier: str, identifier_type: str) -> ParcelResult:
    """
    Generate a placeholder deal score for a parcel.

    In a production implementation this would call compute_entitlement(),
    look up assessed values, TOA overlays, etc. For the MVP we deterministically
    derive a score from the identifier so tests are predictable.
    """
    # Deterministic hash-based score so results are reproducible
    hash_val = abs(hash(identifier))
    deal_score = round((hash_val % 10001) / 100.0, 2)  # 0.00 -- 100.00

    return ParcelResult(
        identifier=identifier,
        identifier_type=identifier_type,
        deal_score=deal_score,
        grade=_score_to_grade(deal_score),
        zoning="RS-1" if deal_score > 50 else "RM-4",
        lot_area_sqm=round(300 + (hash_val % 700), 1),
        assessed_value=round(500_000 + (hash_val % 2_000_000), 0),
        max_storeys=6 if deal_score > 60 else 4,
        max_fsr=round(2.0 + (hash_val % 30) / 10.0, 2),
        storey_uplift=3 if deal_score > 60 else 1,
    )


# ---------------------------------------------------------------------------
# Core async processor
# ---------------------------------------------------------------------------


async def create_bulk_analysis_job(request: BulkAnalysisRequest) -> str:
    """
    Create a new bulk-analysis job and return its ID.

    The job starts in PENDING status. Call ``process_bulk_analysis_job``
    to advance it through PROCESSING -> COMPLETED / FAILED.
    """
    job_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()

    total = len(request.pids) + len(request.addresses)

    _jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.PENDING.value,
        "total": total,
        "completed": 0,
        "results": [],
        "summary": None,
        "created_at": now,
        "updated_at": now,
        "error": None,
        "request": request.model_dump(),
    }

    logger.info("Bulk analysis job %s created with %d items", job_id, total)
    return job_id


async def process_bulk_analysis_job(job_id: str) -> None:
    """
    Process all parcels for a given job, updating status as we go.

    This is designed to be run as a background task (``BackgroundTasks``).
    """
    job = _jobs.get(job_id)
    if not job:
        logger.error("Job %s not found in store", job_id)
        return

    job["status"] = JobStatus.PROCESSING.value
    job["updated_at"] = datetime.now(tz=timezone.utc).isoformat()

    request_data = job["request"]
    results: list[dict] = []

    try:
        # Process PIDs
        for pid in request_data.get("pids", []):
            try:
                result = _mock_score_parcel(pid, "pid")
                results.append(result.model_dump())
            except Exception as exc:
                results.append(
                    ParcelResult(
                        identifier=pid,
                        identifier_type="pid",
                        deal_score=0.0,
                        grade="F",
                        error=str(exc),
                    ).model_dump()
                )
            job["completed"] = len(results)
            job["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
            # Yield control so other tasks can run
            await asyncio.sleep(0)

        # Process addresses
        for address in request_data.get("addresses", []):
            try:
                result = _mock_score_parcel(address, "address")
                results.append(result.model_dump())
            except Exception as exc:
                results.append(
                    ParcelResult(
                        identifier=address,
                        identifier_type="address",
                        deal_score=0.0,
                        grade="F",
                        error=str(exc),
                    ).model_dump()
                )
            job["completed"] = len(results)
            job["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
            await asyncio.sleep(0)

        # Rank by deal_score descending
        results.sort(key=lambda r: r["deal_score"], reverse=True)

        job["results"] = results
        job["summary"] = _generate_summary(results)
        job["status"] = JobStatus.COMPLETED.value

    except Exception as exc:
        logger.exception("Bulk analysis job %s failed: %s", job_id, exc)
        job["status"] = JobStatus.FAILED.value
        job["error"] = str(exc)
        job["results"] = results

    job["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    logger.info(
        "Bulk analysis job %s finished with status=%s, %d results",
        job_id,
        job["status"],
        len(results),
    )


def get_job_result(job_id: str) -> Optional[BulkAnalysisResult]:
    """
    Retrieve the current state of a bulk-analysis job.

    Returns ``None`` if the job does not exist.
    """
    job = _jobs.get(job_id)
    if not job:
        return None

    return BulkAnalysisResult(
        job_id=job["job_id"],
        status=job["status"],
        total=job["total"],
        completed=job["completed"],
        results=job["results"],
        summary=job["summary"],
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
        error=job.get("error"),
    )
