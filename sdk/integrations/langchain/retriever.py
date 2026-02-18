from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, PrivateAttr

from sdk import Knowledge2
from sdk.integrations._client import merge_return_config, resolve_client, resolve_corpus_id
from sdk.types import SearchResult

try:
    from langchain_core.callbacks import (
        AsyncCallbackManagerForRetrieverRun,
        CallbackManagerForRetrieverRun,
    )
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
except ImportError as exc:  # pragma: no cover - import-time dependency guard
    raise ImportError(
        "LangChain integration requires langchain-core. Install with `pip install .[langchain]`."
    ) from exc


class K2LangChainRetriever(BaseRetriever):
    """LangChain retriever backed by Knowledge2 search APIs."""

    model_config: ClassVar[ConfigDict] = ConfigDict(arbitrary_types_allowed=True)

    client: Any | None = Field(default=None, exclude=True)
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    api_host: str | None = None
    corpus_id: str | None = None

    top_k: int = 10
    filters: dict[str, Any] | None = None
    hybrid: dict[str, Any] | None = None
    graph_rag: dict[str, Any] | None = None
    rerank: dict[str, Any] | None = None
    return_config: dict[str, Any] | None = None

    _client: Knowledge2 | Any = PrivateAttr()
    _corpus_id: str = PrivateAttr()

    def model_post_init(self, __context: Any) -> None:
        self._client = resolve_client(
            client=self.client, api_key=self.api_key, api_host=self.api_host
        )
        self._corpus_id = resolve_corpus_id(self.corpus_id)

    @staticmethod
    def _result_to_document(result: SearchResult, corpus_id: str) -> Document:
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
        result_metadata = {**system_meta, **custom_meta}

        metadata: dict[str, Any] = {
            "source": "knowledge2",
            "corpus_id": corpus_id,
            "chunk_id": result.get("chunk_id"),
            "score": result.get("score"),
            "raw_score": result.get("raw_score"),
            "offset_start": result.get("offset_start"),
            "offset_end": result.get("offset_end"),
            "page_start": result.get("page_start"),
            "page_end": result.get("page_end"),
        }
        metadata.update(result_metadata)

        return Document(page_content=result.get("text") or "", metadata=metadata)

    def _search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        hybrid: dict[str, Any] | None = None,
        graph_rag: dict[str, Any] | None = None,
        rerank: dict[str, Any] | None = None,
        return_config: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        payload_return_config = merge_return_config(
            base=self.return_config,
            override=return_config,
            include_text=True,
            include_scores=True,
            include_provenance=True,
        )
        response = self._client.search(
            self._corpus_id,
            query,
            top_k=top_k if top_k is not None else self.top_k,
            filters=filters if filters is not None else self.filters,
            hybrid=hybrid if hybrid is not None else self.hybrid,
            graph_rag=graph_rag if graph_rag is not None else self.graph_rag,
            rerank=rerank if rerank is not None else self.rerank,
            return_config=payload_return_config,
        )
        return response.get("results", [])

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
        **kwargs: Any,
    ) -> list[Document]:
        results = self._search(
            query,
            top_k=kwargs.get("top_k"),
            filters=kwargs.get("filters"),
            hybrid=kwargs.get("hybrid"),
            graph_rag=kwargs.get("graph_rag"),
            rerank=kwargs.get("rerank"),
            return_config=kwargs.get("return_config"),
        )
        return [self._result_to_document(result, self._corpus_id) for result in results]

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: AsyncCallbackManagerForRetrieverRun,
        **kwargs: Any,
    ) -> list[Document]:
        results = await asyncio.to_thread(
            self._search,
            query,
            top_k=kwargs.get("top_k"),
            filters=kwargs.get("filters"),
            hybrid=kwargs.get("hybrid"),
            graph_rag=kwargs.get("graph_rag"),
            rerank=kwargs.get("rerank"),
            return_config=kwargs.get("return_config"),
        )
        return [self._result_to_document(result, self._corpus_id) for result in results]
