from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class SearchHybridConfig(TypedDict, total=False):
    enabled: bool
    fusion_mode: str
    rrf_k: int
    dense_weight: float
    sparse_weight: float


class SearchRerankConfig(TypedDict, total=False):
    enabled: bool
    top_k: int


class SearchReturnConfig(TypedDict, total=False):
    include_text: bool
    include_scores: bool
    include_provenance: bool


class SearchGenerationConfig(TypedDict, total=False):
    model: str
    thinking_budget: int | None
    temperature: float
    max_tokens: int
    context_top_k: int


class SearchOptions(TypedDict, total=False):
    query: str
    top_k: int
    filters: dict[str, Any]
    hybrid: SearchHybridConfig
    rerank: SearchRerankConfig
    return_config: SearchReturnConfig


class SearchGenerateOptions(TypedDict, total=False):
    query: str
    top_k: int
    filters: dict[str, Any]
    hybrid: SearchHybridConfig
    rerank: SearchRerankConfig
    return_config: SearchReturnConfig
    generation: SearchGenerationConfig


class SearchBatchOptions(TypedDict, total=False):
    queries: list[str]
    top_k: int
    filters: dict[str, Any]
    hybrid: SearchHybridConfig
    rerank: SearchRerankConfig
    return_config: SearchReturnConfig


class SearchResult(TypedDict, total=False):
    chunk_id: str
    score: float | None
    raw_score: float | None
    text: str | None
    metadata: dict | None
    offset_start: int | None
    offset_end: int | None
    page_start: int | None
    page_end: int | None


class SearchResponse(TypedDict):
    results: list[SearchResult]


class SearchBatchResponse(TypedDict):
    responses: list[SearchResponse]


class SearchGenerateResponse(TypedDict):
    answer: str
    model: str
    thinking_budget: int | None
    results: list[SearchResult]
    used_sources: list[str]
