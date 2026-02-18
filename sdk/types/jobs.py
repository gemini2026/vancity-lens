from __future__ import annotations

from typing import List, Optional, TypedDict


class JobResponse(TypedDict, total=False):
    id: str
    job_type: str
    status: str
    payload: dict
    result: dict
    error_message: str | None
    created_at: str | None
    updated_at: str | None
    heartbeat_at: str | None
    requeue_count: int | None
    run_after: str | None


class JobListItem(TypedDict, total=False):
    id: str
    job_type: str
    status: str
    payload: dict
    result: dict
    error_message: str | None
    created_at: str | None
    updated_at: str | None
    heartbeat_at: str | None
    requeue_count: int | None
    run_after: str | None


class JobListResponse(TypedDict):
    jobs: list[JobListItem]


class JobStatusResponse(TypedDict):
    status: str


class ReconcileJobsResponse(TypedDict):
    reconciled: int
