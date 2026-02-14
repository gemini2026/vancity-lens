from __future__ import annotations

from typing import List, TypedDict


class EmbeddingItem(TypedDict):
    embedding: list[float]
    index: int


class EmbeddingsResponse(TypedDict):
    data: list[EmbeddingItem]
    model: str
