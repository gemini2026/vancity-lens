from __future__ import annotations

from typing import TypedDict


class TrainingDataBuildResponse(TypedDict):
    job_id: str
    dataset_id: str


class TrainingDatasetResponse(TypedDict, total=False):
    id: str
    corpus_id: str
    sample_count: int
    dataset_hash: str
    created_at: str | None


class TrainingDatasetListResponse(TypedDict):
    datasets: list[TrainingDatasetResponse]


class TuningRunResponse(TypedDict):
    run_id: str
    status: str
    job_id: str


class TuningRunBuildResponse(TypedDict):
    run_id: str
    status: str
    build_job_id: str
    dataset_id: str


class TuningRunDetailResponse(TypedDict, total=False):
    run_id: str
    status: str
    metrics: dict


class TuningRunLogsResponse(TypedDict):
    lines: list[str]


class TuningRunListResponse(TypedDict):
    runs: list[TuningRunDetailResponse]


class PromoteResponse(TypedDict):
    model_id: str


class CancelTuningRunResponse(TypedDict):
    status: str
