from __future__ import annotations

from typing import TypedDict


class EvalRunResponse(TypedDict):
    eval_id: str
    status: str
    job_id: str


class EvalRunDetailResponse(TypedDict, total=False):
    eval_id: str
    status: str
    metrics: dict
