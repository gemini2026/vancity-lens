"""Job management resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, Iterator, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import JobListResponse, JobResponse, JobStatusResponse, ReconcileJobsResponse


class JobsMixin(RequesterMixin):
    def get_job(self, job_id: str) -> JobResponse:
        """Retrieve details of a single job.

        Args:
            job_id: Unique identifier of the job.

        Returns:
            The job record including type, status, and metadata.

        Raises:
            NotFoundError: If the job does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", f"/v1/jobs/{job_id}")
        return cast("JobResponse", data)

    def list_jobs(
        self,
        *,
        corpus_id: str | None = None,
        job_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> JobListResponse:
        """List jobs with optional filters.

        Args:
            corpus_id: Filter to jobs belonging to this corpus.
            job_type: Filter by job type (e.g. ``"ingest"``, ``"index"``,
                ``"train"``).
            status: Filter by job status (e.g. ``"pending"``,
                ``"running"``, ``"completed"``, ``"failed"``).
            limit: Maximum number of jobs to return per page.
            offset: Number of jobs to skip for pagination.

        Returns:
            A paginated list of job records.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if corpus_id:
            params["corpus_id"] = corpus_id
        if job_type:
            params["job_type"] = job_type
        if status:
            params["status"] = status
        data = self._request("GET", "/v1/jobs", params=params)
        return cast("JobListResponse", data)

    def iter_jobs(
        self,
        *,
        corpus_id: str | None = None,
        job_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> Iterator[dict[str, Any]]:
        """Iterate over jobs, automatically paginating.

        Args:
            corpus_id: Filter to jobs belonging to this corpus.
            job_type: Filter by job type.
            status: Filter by job status.
            limit: Page size used for each underlying API request.

        Yields:
            Individual job dicts.

        Raises:
            Knowledge2Error: If any underlying API request fails.
        """
        params: dict[str, Any] = {}
        if corpus_id:
            params["corpus_id"] = corpus_id
        if job_type:
            params["job_type"] = job_type
        if status:
            params["status"] = status
        return self._paginate(
            "GET", "/v1/jobs", items_key="jobs", params=params or None, limit=limit
        )

    def cancel_job(self, job_id: str) -> JobStatusResponse:
        """Cancel a running or pending job.

        Args:
            job_id: Unique identifier of the job to cancel.

        Returns:
            The updated job status after cancellation.

        Raises:
            NotFoundError: If the job does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("POST", f"/v1/jobs/{job_id}:cancel")
        return cast("JobStatusResponse", data)

    def retry_job(self, job_id: str) -> JobStatusResponse:
        """Retry a failed job.

        Args:
            job_id: Unique identifier of the job to retry.

        Returns:
            The updated job status after scheduling the retry.

        Raises:
            NotFoundError: If the job does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("POST", f"/v1/jobs/{job_id}:retry")
        return cast("JobStatusResponse", data)

    def reconcile_jobs(self) -> ReconcileJobsResponse:
        """Reconcile stale or stuck jobs across the platform.

        Returns:
            A summary of reconciled jobs (e.g. counts of requeued or
            cancelled jobs).

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("POST", "/v1/jobs:reconcile")
        return cast("ReconcileJobsResponse", data)
