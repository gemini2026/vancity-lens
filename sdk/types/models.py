from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class ModelResponse(TypedDict, total=False):
    id: str
    corpus_id: str
    base_model: str
    embedding_dim: int
    max_seq_length: int
    version: int
    created_at: str


class ModelListResponse(TypedDict):
    models: list[ModelResponse]


class ModelDeleteResponse(TypedDict, total=False):
    message: str
    counts: dict[str, Any]
