from __future__ import annotations

from typing import Any, List, Optional, TypedDict


class IndexBuildResponse(TypedDict):
    job_id: str
    index_ids: list[str]


class IndexStatusResponse(TypedDict, total=False):
    dense_status: str | None
    sparse_status: str | None
    sparse_metadata_status: str | None
    graph_status: str | None
    dense_reason: str | None
    sparse_reason: str | None
    sparse_metadata_reason: str | None
    graph_reason: str | None


class IndexCompactResponse(TypedDict, total=False):
    archived: Any
    keep: int
