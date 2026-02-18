from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class CorpusResponse(TypedDict, total=False):
    id: str
    project_id: str
    name: str
    description: str | None
    is_tutorial: bool
    is_demo: bool
    current_model_id: str | None
    created_at: str | None
    org_name: str | None
    project_name: str | None
    chunking_config: dict[str, Any] | None
    graph_rag_policy: dict[str, Any] | None


class CorpusListResponse(TypedDict):
    corpora: list[CorpusResponse]


class CorpusDeleteResponse(TypedDict, total=False):
    message: str
    counts: dict[str, Any]


class CorpusStatusResponse(TypedDict, total=False):
    status: str
    search_status: str
    retrieval_ready: bool
    ingesting: bool
    indexing: bool
    document_count: int
    documents_processing: int
    dense_status: str | None
    sparse_status: str | None
    graph_status: str | None
