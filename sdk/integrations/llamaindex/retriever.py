from __future__ import annotations

import asyncio
from typing import Any

from sdk import Knowledge2
from sdk.integrations._client import merge_return_config, resolve_client, resolve_corpus_id
from sdk.integrations.llamaindex.filters import llama_filters_to_k2

try:
    from llama_index.core import QueryBundle
    from llama_index.core.retrievers import BaseRetriever
    from llama_index.core.schema import NodeWithScore, TextNode
    from llama_index.core.vector_stores.types import MetadataFilters
except ImportError as exc:  # pragma: no cover - import-time dependency guard
    raise ImportError(
        "LlamaIndex integration requires llama-index-core. Install with `pip install .[llamaindex]`."
    ) from exc


class K2LlamaIndexRetriever(BaseRetriever):
    """LlamaIndex retriever backed by Knowledge2 search."""

    def __init__(
        self,
        *,
        corpus_id: str | None = None,
        client: Knowledge2 | None = None,
        api_key: str | None = None,
        api_host: str | None = None,
        top_k: int = 10,
        filters: MetadataFilters | None = None,
        hybrid: dict[str, Any] | None = None,
        graph_rag: dict[str, Any] | None = None,
        rerank: dict[str, Any] | None = None,
        return_config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._client = resolve_client(client=client, api_key=api_key, api_host=api_host)
        self._corpus_id = resolve_corpus_id(corpus_id)
        self._top_k = top_k
        self._filters = filters
        self._hybrid = hybrid
        self._graph_rag = graph_rag
        self._rerank = rerank
        self._return_config = return_config

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        query_text = query_bundle.query_str if hasattr(query_bundle, "query_str") else None
        if not query_text:
            raise ValueError("K2LlamaIndexRetriever requires a text query")

        k2_filters = llama_filters_to_k2(self._filters)
        response = self._client.search(
            self._corpus_id,
            query_text,
            top_k=self._top_k,
            filters=k2_filters,
            hybrid=self._hybrid,
            graph_rag=self._graph_rag,
            rerank=self._rerank,
            return_config=merge_return_config(
                base=self._return_config,
                override=None,
                include_text=True,
                include_scores=True,
                include_provenance=True,
            ),
        )

        nodes: list[NodeWithScore] = []
        for result in response.get("results", []):
            custom_meta = result.get("custom_metadata") or {}
            system_meta = result.get("system_metadata") or {}
            if not custom_meta and not system_meta:
                legacy = result.get("metadata")
                if isinstance(legacy, dict):
                    custom_meta = legacy
            if not isinstance(custom_meta, dict):
                custom_meta = {}
            if not isinstance(system_meta, dict):
                system_meta = {}
            chunk_metadata = {**system_meta, **custom_meta}

            chunk_id = result.get("chunk_id")
            if not chunk_id:
                continue

            node = TextNode(
                id_=chunk_id,
                text=result.get("text") or "",
                metadata={
                    **chunk_metadata,
                    "chunk_id": chunk_id,
                    "corpus_id": self._corpus_id,
                    "raw_score": result.get("raw_score"),
                    "offset_start": result.get("offset_start"),
                    "offset_end": result.get("offset_end"),
                    "page_start": result.get("page_start"),
                    "page_end": result.get("page_end"),
                },
            )
            score = result.get("score")
            if score is None:
                score = result.get("raw_score")
            nodes.append(NodeWithScore(node=node, score=score))

        return nodes

    async def _aretrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        """Async variant for event-loop-safe LlamaIndex integration."""
        return await asyncio.to_thread(self._retrieve, query_bundle)
