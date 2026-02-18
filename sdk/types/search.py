from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class SearchHybridConfig(TypedDict, total=False):
    enabled: bool
    fusion_mode: str
    rrf_k: int
    dense_weight: float
    sparse_weight: float
    metadata_sparse_enabled: bool


class SearchRerankConfig(TypedDict, total=False):
    enabled: bool
    top_k: int


class SearchGraphRagConfig(TypedDict, total=False):
    enabled: bool
    seed_chunks: int
    seed_docs: int
    max_entities_per_doc: int
    candidate_scan_limit: int
    min_entity_overlap: int
    max_related_docs: int
    max_chunks_per_doc: int
    max_docs_per_entity: int
    max_expanded_chunks: int
    timeout_ms: int
    depth_penalty: float
    score_boost: float
    shadow_mode: bool


class SearchReturnConfig(TypedDict, total=False):
    include_text: bool
    include_scores: bool
    include_provenance: bool


class MetadataFilter(TypedDict, total=False):
    """A single metadata filter predicate."""

    key: str
    op: str  # ==, !=, >, >=, <, <=, in, not_in, contains, text_match
    value: Any


class MetadataFilters(TypedDict, total=False):
    """Structured metadata filters with logical condition."""

    filters: list[MetadataFilter]
    condition: str  # "and" or "or"


class SearchGenerationConfig(TypedDict, total=False):
    model: str
    thinking_budget: int | None
    temperature: float
    max_tokens: int
    context_top_k: int


class SearchOptions(TypedDict, total=False):
    query: str
    top_k: int
    filters: dict[str, Any] | MetadataFilters
    hybrid: SearchHybridConfig
    graph_rag: SearchGraphRagConfig
    rerank: SearchRerankConfig
    return_config: SearchReturnConfig


class SearchGenerateOptions(TypedDict, total=False):
    query: str
    top_k: int
    filters: dict[str, Any] | MetadataFilters
    hybrid: SearchHybridConfig
    graph_rag: SearchGraphRagConfig
    rerank: SearchRerankConfig
    return_config: SearchReturnConfig
    generation: SearchGenerationConfig


class SearchBatchOptions(TypedDict, total=False):
    queries: list[str]
    top_k: int
    filters: dict[str, Any] | MetadataFilters
    hybrid: SearchHybridConfig
    graph_rag: SearchGraphRagConfig
    rerank: SearchRerankConfig
    return_config: SearchReturnConfig


class SearchResult(TypedDict, total=False):
    chunk_id: str
    score: float | None
    raw_score: float | None
    text: str | None
    custom_metadata: dict | None
    system_metadata: dict | None
    offset_start: int | None
    offset_end: int | None
    page_start: int | None
    page_end: int | None


class SearchColdStartMeta(TypedDict, total=False):
    likely: bool
    dense_cache_hit: bool | None
    sparse_cache_hit: bool | None
    graph_cache_hit: bool | None


class SearchGraphRagMeta(TypedDict, total=False):
    enabled: bool
    applied: bool
    shadow_mode: bool
    expanded_chunks: int
    related_docs: int
    source: str | None
    fallback_used: bool
    fallback_reason: str | None
    timed_out: bool


class SearchMeta(TypedDict, total=False):
    cold_start: SearchColdStartMeta | None
    graph_rag: SearchGraphRagMeta | None


class SearchResponse(TypedDict, total=False):
    results: list[SearchResult]
    meta: SearchMeta


class SearchBatchResponse(TypedDict, total=False):
    responses: list[SearchResponse]


class SearchGenerateResponse(TypedDict, total=False):
    answer: str
    model: str
    thinking_budget: int | None
    results: list[SearchResult]
    meta: SearchMeta
    used_sources: list[str]
