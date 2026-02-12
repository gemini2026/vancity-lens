from __future__ import annotations

from typing import Any, Dict, Optional, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import JobListResponse, JobResponse, JobStatusResponse


class JobsMixin(RequesterMixin):
    def get_job(self, job_id: str) -> JobResponse:
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
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if corpus_id:
            params["corpus_id"] = corpus_id
        if job_type:
            params["job_type"] = job_type
        if status:
            params["status"] = status
        data = self._request("GET", "/v1/jobs", params=params)
        return cast("JobListResponse", data)

    def cancel_job(self, job_id: str) -> JobStatusResponse:
        data = self._request("POST", f"/v1/jobs/{job_id}:cancel")
        return cast("JobStatusResponse", data)

    def retry_job(self, job_id: str) -> JobStatusResponse:
        data = self._request("POST", f"/v1/jobs/{job_id}:retry")
        return cast("JobStatusResponse", data)

    def reconcile_jobs(self) -> dict[str, Any]:
        data = self._request("POST", "/v1/jobs:reconcile")
        return cast("dict[str, Any]", data)
