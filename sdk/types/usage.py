from __future__ import annotations

from typing import List, Optional, TypedDict


class UsageSeriesPoint(TypedDict):
    date: str
    count: int


class UsageSummaryResponse(TypedDict, total=False):
    range: str
    total_requests: int
    daily: list[UsageSeriesPoint]
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    error_rate: float | None


class UsageByCorpusItem(TypedDict, total=False):
    corpus_id: str
    corpus_name: str | None
    requests: int


class UsageByCorpusResponse(TypedDict):
    items: list[UsageByCorpusItem]


class UsageByKeyItem(TypedDict, total=False):
    key_id: str
    name: str | None
    requests: int


class UsageByKeyResponse(TypedDict):
    items: list[UsageByKeyItem]
