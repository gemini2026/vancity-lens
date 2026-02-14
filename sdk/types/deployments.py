from __future__ import annotations

from typing import Optional, TypedDict


class DeploymentResponse(TypedDict, total=False):
    id: str
    corpus_id: str
    model_id: str
    traffic_pct: int
    reindex_job_id: str | None
