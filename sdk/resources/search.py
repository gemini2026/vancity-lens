"""Search resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
    EmbeddingsResponse,
    FeedbackResponse,
    SearchBatchResponse,
    SearchGenerateResponse,
    SearchResponse,
)
from sdk.types.search import (
    SearchGenerationConfig,
    SearchGraphRagConfig,
    SearchHybridConfig,
    SearchRerankConfig,
    SearchReturnConfig,
)


class SearchMixin(RequesterMixin):
    def search(
        self,
        corpus_id: str,
        query: str,
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        hybrid: SearchHybridConfig | dict[str, Any] | None = None,
        graph_rag: SearchGraphRagConfig | dict[str, Any] | None = None,
        rerank: SearchRerankConfig | dict[str, Any] | None = None,
        return_config: SearchReturnConfig | dict[str, Any] | None = None,
    ) -> SearchResponse:
        """Search a corpus for relevant chunks.

        Args:
            corpus_id: The corpus to search.
            query: The search query text.
            top_k: Maximum number of results to return.
            filters: Optional metadata filters to narrow results.
            hybrid: Hybrid search configuration (dense/sparse weighting).
            graph_rag: GraphRAG configuration for graph-augmented retrieval.
            rerank: Reranking configuration applied after initial retrieval.
            return_config: Controls which fields are included in the
                response (e.g. text, metadata, provenance).

        Returns:
            Search results with scored chunks, metadata, and text.

        Raises:
            NotFoundError: If the corpus does not exist.
            Knowledge2Error: If the API request fails.

        Example:
            >>> results = client.search("corpus-123", "machine learning basics", top_k=5)
            >>> for chunk in results["chunks"]:
            ...     print(chunk["score"], chunk["text"][:80])
        """
        payload: dict[str, Any] = {"query": query, "top_k": top_k}
        if filters is not None:
            payload["filters"] = filters
        if hybrid is not None:
            payload["hybrid"] = hybrid
        if graph_rag is not None:
            payload["graph_rag"] = graph_rag
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
        hybrid: SearchHybridConfig | dict[str, Any] | None = None,
        graph_rag: SearchGraphRagConfig | dict[str, Any] | None = None,
        rerank: SearchRerankConfig | dict[str, Any] | None = None,
        return_config: SearchReturnConfig | dict[str, Any] | None = None,
    ) -> SearchBatchResponse:
        """Execute multiple search queries against a corpus in a single request.

        Args:
            corpus_id: The corpus to search.
            queries: List of search query texts.
            top_k: Maximum number of results to return per query.
            filters: Optional metadata filters applied to all queries.
            hybrid: Hybrid search configuration (dense/sparse weighting).
            graph_rag: GraphRAG configuration for graph-augmented retrieval.
            rerank: Reranking configuration applied after initial retrieval.
            return_config: Controls which fields are included in each
                query's results.

        Returns:
            Batch search results — one result set per input query.

        Raises:
            NotFoundError: If the corpus does not exist.
            Knowledge2Error: If the API request fails.
        """
        payload: dict[str, Any] = {"queries": queries, "top_k": top_k}
        if filters is not None:
            payload["filters"] = filters
        if hybrid is not None:
            payload["hybrid"] = hybrid
        if graph_rag is not None:
            payload["graph_rag"] = graph_rag
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
        hybrid: SearchHybridConfig | dict[str, Any] | None = None,
        graph_rag: SearchGraphRagConfig | dict[str, Any] | None = None,
        rerank: SearchRerankConfig | dict[str, Any] | None = None,
        return_config: SearchReturnConfig | dict[str, Any] | None = None,
        generation: SearchGenerationConfig | dict[str, Any] | None = None,
    ) -> SearchGenerateResponse:
        """Search a corpus and generate an LLM answer grounded in the results.

        Combines retrieval with LLM generation (RAG) in a single call.

        Args:
            corpus_id: The corpus to search.
            query: The search query text.
            top_k: Maximum number of retrieval results fed to the generator.
            filters: Optional metadata filters to narrow retrieval results.
            hybrid: Hybrid search configuration (dense/sparse weighting).
            graph_rag: GraphRAG configuration for graph-augmented retrieval.
            rerank: Reranking configuration applied after initial retrieval.
            return_config: Controls which fields are included in the
                retrieval results.
            generation: LLM generation settings (model, temperature,
                system prompt, etc.).

        Returns:
            The generated answer together with the supporting retrieval
            results.

        Raises:
            NotFoundError: If the corpus does not exist.
            Knowledge2Error: If the API request fails.
        """
        payload: dict[str, Any] = {"query": query, "top_k": top_k}
        if filters is not None:
            payload["filters"] = filters
        if hybrid is not None:
            payload["hybrid"] = hybrid
        if graph_rag is not None:
            payload["graph_rag"] = graph_rag
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
        """Generate vector embeddings for the given texts.

        Args:
            model: Name or ID of the embedding model to use.
            inputs: List of text strings to embed.
            embed_type: Embedding type — ``"query"`` for search queries
                or ``"document"`` for corpus documents.

        Returns:
            Embedding vectors for each input text.

        Raises:
            Knowledge2Error: If the API request fails.
        """
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
        """Submit relevance feedback for a search query.

        Feedback is used to improve training data and evaluate retrieval
        quality.

        Args:
            corpus_id: The corpus the query was executed against.
            query: The original search query text.
            clicked_chunk_ids: IDs of chunks the user found relevant.
            rating: Overall relevance rating for the result set.
            abstained: If ``True``, indicates the user chose not to
                rate the results.

        Returns:
            Confirmation that the feedback was recorded.

        Raises:
            NotFoundError: If the corpus does not exist.
            Knowledge2Error: If the API request fails.
        """
        payload: dict[str, Any] = {
            "query": query,
            "clicked_chunk_ids": clicked_chunk_ids,
            "rating": rating,
            "abstained": abstained,
        }
        data = self._request("POST", f"/v1/corpora/{corpus_id}/feedback", json=payload)
        return cast("FeedbackResponse", data)
