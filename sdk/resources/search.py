from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
    EmbeddingsResponse,
    FeedbackResponse,
    SearchBatchResponse,
    SearchGenerateResponse,
    SearchResponse,
)


class SearchMixin(RequesterMixin):
    def search(
        self,
        corpus_id: str,
        query: str,
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        hybrid: dict[str, Any] | None = None,
        rerank: dict[str, Any] | None = None,
        return_config: dict[str, Any] | None = None,
    ) -> SearchResponse:
        payload: dict[str, Any] = {"query": query, "top_k": top_k}
        if filters is not None:
            payload["filters"] = filters
        if hybrid is not None:
            payload["hybrid"] = hybrid
        if rerank is not None:
            payload["rerank"] = rerank
        if return_config is not None:
            payload["return"] = return_config
        data = self._request("POST", f"/v1/corpora/{corpus_id}/search", json=payload)
        return cast("SearchResponse", data)

    def search_batch(
        self,
        corpus_id: str,
        queries: list[str],
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        hybrid: dict[str, Any] | None = None,
        rerank: dict[str, Any] | None = None,
        return_config: dict[str, Any] | None = None,
    ) -> SearchBatchResponse:
        payload: dict[str, Any] = {"queries": queries, "top_k": top_k}
        if filters is not None:
            payload["filters"] = filters
        if hybrid is not None:
            payload["hybrid"] = hybrid
        if rerank is not None:
            payload["rerank"] = rerank
        if return_config is not None:
            payload["return"] = return_config
        data = self._request("POST", f"/v1/corpora/{corpus_id}/search:batch", json=payload)
        return cast("SearchBatchResponse", data)

    def search_generate(
        self,
        corpus_id: str,
        query: str,
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        hybrid: dict[str, Any] | None = None,
        rerank: dict[str, Any] | None = None,
        return_config: dict[str, Any] | None = None,
        generation: dict[str, Any] | None = None,
    ) -> SearchGenerateResponse:
        payload: dict[str, Any] = {"query": query, "top_k": top_k}
        if filters is not None:
            payload["filters"] = filters
        if hybrid is not None:
            payload["hybrid"] = hybrid
        if rerank is not None:
            payload["rerank"] = rerank
        if return_config is not None:
            payload["return"] = return_config
        if generation is not None:
            payload["generation"] = generation
        data = self._request("POST", f"/v1/corpora/{corpus_id}/search:generate", json=payload)
        return cast("SearchGenerateResponse", data)

    def embeddings(
        self, model: str, inputs: list[str], embed_type: str = "query"
    ) -> EmbeddingsResponse:
        payload = {"model": model, "input": inputs, "type": embed_type}
        data = self._request("POST", "/v1/embeddings", json=payload)
        return cast("EmbeddingsResponse", data)

    def create_feedback(
        self,
        corpus_id: str,
        query: str,
        *,
        clicked_chunk_ids: list[str] | None = None,
        rating: int | None = None,
        abstained: bool = False,
    ) -> FeedbackResponse:
        payload: dict[str, Any] = {
            "query": query,
            "clicked_chunk_ids": clicked_chunk_ids,
            "rating": rating,
            "abstained": abstained,
        }
        data = self._request("POST", f"/v1/corpora/{corpus_id}/feedback", json=payload)
        return cast("FeedbackResponse", data)
