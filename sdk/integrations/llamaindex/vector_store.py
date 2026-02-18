from __future__ import annotations

import logging
import time
from typing import Any, ClassVar, Sequence

from pydantic import ConfigDict, Field, PrivateAttr

from sdk import Knowledge2
from sdk.integrations._client import merge_return_config, resolve_client, resolve_corpus_id
from sdk.integrations.llamaindex.filters import llama_filters_to_k2

try:
    from llama_index.core.schema import BaseNode, MetadataMode, TextNode
    from llama_index.core.vector_stores.types import (
        BasePydanticVectorStore,
        VectorStoreQuery,
        VectorStoreQueryResult,
    )
except ImportError as exc:  # pragma: no cover - import-time dependency guard
    raise ImportError(
        "LlamaIndex integration requires llama-index-core. Install with `pip install .[llamaindex]`."
    ) from exc


logger = logging.getLogger(__name__)


def _node_text(node: BaseNode) -> str:
    """Extract text content from a LlamaIndex node."""
    try:
        text = node.get_content(metadata_mode=MetadataMode.NONE)
    except Exception:  # pragma: no cover - defensive for node variants
        text = getattr(node, "text", "")
    return text or ""


def _resolve_source_uri(
    *,
    node: BaseNode,
    ref_doc_id: str | None,
    source_uri_prefix: str,
) -> str:
    """Resolve a deterministic source URI for document ingestion."""
    source_node = getattr(node, "source_node", None)
    source_node_id: str | None = None

    if isinstance(source_node, str):
        source_node_id = source_node.strip() or None
    elif source_node is not None:
        # LlamaIndex usually exposes RelatedNodeInfo here, but some callers may
        # surface a BaseNode-like object. Prefer stable node identifiers.
        raw_source_node_id = getattr(source_node, "node_id", None) or getattr(
            source_node, "id_", None
        )
        if raw_source_node_id:
            source_node_id = str(raw_source_node_id).strip() or None

    if source_node_id:
        if "://" in source_node_id:
            return source_node_id
        return f"{source_uri_prefix}{source_node_id}"
    if ref_doc_id:
        return f"{source_uri_prefix}{ref_doc_id}"
    return f"{source_uri_prefix}{node.node_id}"


def _resolve_result_doc_id(*, chunk_id: str, metadata: dict[str, Any]) -> str:
    """Resolve a stable document identifier from chunk metadata when available."""
    provenance = metadata.get("provenance")
    candidates: list[Any] = []
    if isinstance(provenance, dict):
        candidates.extend(
            (
                provenance.get("document_id"),
                provenance.get("doc_id"),
            )
        )
    candidates.extend(
        (
            metadata.get("document_id"),
            metadata.get("doc_id"),
        )
    )
    for candidate in candidates:
        if candidate is None:
            continue
        value = str(candidate).strip()
        if value:
            return value
    return chunk_id


class K2LlamaIndexVectorStore(BasePydanticVectorStore):
    """Doc-centric LlamaIndex VectorStore adapter for Knowledge2.

    This adapter maps LlamaIndex vector-store operations onto K2 document/search APIs.
    """

    stores_text: bool = True

    k2_client: Any | None = Field(default=None, alias="client", exclude=True)
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    api_host: str | None = None
    corpus_id: str | None = None

    top_k: int = 10
    filters: dict[str, Any] | None = None
    hybrid: dict[str, Any] | None = None
    graph_rag: dict[str, Any] | None = None
    rerank: dict[str, Any] | None = None
    return_config: dict[str, Any] | None = None

    auto_index_on_add: bool = False
    # LlamaIndex vector-store APIs are typically synchronous. K2 ingestion happens via
    # background jobs, so we optionally wait for ingest completion on add to avoid
    # surprising "no chunks to index" failures when users build indexes immediately.
    wait_for_ingest_on_add: bool = True
    ingest_poll_s: int = 2
    ingest_timeout_s: float | None = 300.0
    source_uri_prefix: str = "llamaindex://node/"

    _client: Knowledge2 | Any = PrivateAttr()
    _corpus_id: str = PrivateAttr()
    _node_to_doc_id: dict[str, str] = PrivateAttr(default_factory=dict)

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    def model_post_init(self, __context: Any) -> None:
        self._client = resolve_client(
            client=self.k2_client, api_key=self.api_key, api_host=self.api_host
        )
        self._corpus_id = resolve_corpus_id(self.corpus_id)

    @property
    def client(self) -> Any:
        """Expose the underlying Knowledge2 client per BasePydanticVectorStore contract."""
        return self._client

    def get(self, text_id: str) -> list[float]:
        """K2 does not expose direct embedding lookup by id."""
        raise NotImplementedError("K2 does not support vector lookup by text_id")

    def _wait_for_ingest_job(self, job_id: str) -> None:
        if not hasattr(self._client, "get_job"):
            logger.debug(
                "Skipping ingest wait; no public get_job method on client for job=%s",
                job_id,
            )
            return

        start = time.monotonic()
        while True:
            job = self._client.get_job(job_id)
            status = job.get("status")
            if status in {"succeeded", "failed", "canceled"}:
                if status != "succeeded":
                    error_message = job.get("error_message")
                    if not error_message:
                        error_message = f"Job {job_id} ended with status={status}"
                    raise RuntimeError(error_message)
                return

            if (
                self.ingest_timeout_s is not None
                and (time.monotonic() - start) > self.ingest_timeout_s
            ):
                raise TimeoutError(f"Timed out waiting for ingest job {job_id}")

            time.sleep(self.ingest_poll_s)

    def add(self, nodes: Sequence[BaseNode], **add_kwargs: Any) -> list[str]:
        """Add nodes by ingesting documents into K2."""
        added_doc_ids: list[str] = []
        wait_for_ingest = add_kwargs.get("wait")
        if wait_for_ingest is None:
            wait_for_ingest = self.wait_for_ingest_on_add
        wait_for_ingest = bool(wait_for_ingest)
        log_jobs = bool(add_kwargs.get("log_jobs", False))

        for node in nodes:
            node_id = node.node_id
            ref_doc_id = getattr(node, "ref_doc_id", None)
            source_uri = _resolve_source_uri(
                node=node,
                ref_doc_id=ref_doc_id,
                source_uri_prefix=self.source_uri_prefix,
            )

            metadata = dict(getattr(node, "metadata", {}) or {})
            metadata.setdefault("llama_node_id", node_id)
            if ref_doc_id:
                metadata.setdefault("llama_ref_doc_id", ref_doc_id)

            response = self._client.upload_document(
                self._corpus_id,
                raw_text=_node_text(node),
                source_uri=source_uri,
                metadata=metadata,
                auto_index=False,
            )
            doc_id = response["doc_id"]
            added_doc_ids.append(doc_id)
            self._node_to_doc_id[node_id] = doc_id
            if ref_doc_id:
                self._node_to_doc_id[ref_doc_id] = doc_id

            job_id = response.get("job_id")
            if wait_for_ingest and job_id:
                if log_jobs:
                    # Avoid noisy polling here; the smoke runner already prints job transitions.
                    # This just makes job creation visible in logs when desired.
                    logger.info(
                        "[job] job_id=%s job_type=ingest_document status=created doc_id=%s",
                        job_id,
                        doc_id,
                    )
                self._wait_for_ingest_job(job_id)

        if self.auto_index_on_add and added_doc_ids:
            self._client.build_indexes(
                self._corpus_id, dense=True, sparse=True, mode="full", wait=True
            )

        return added_doc_ids

    def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
        """Delete a document from K2 by mapped ref_doc_id or raw doc_id."""
        doc_id = self._node_to_doc_id.get(ref_doc_id, ref_doc_id)
        reindex = bool(delete_kwargs.get("reindex", False))
        self._client.delete_document(self._corpus_id, doc_id, reindex=reindex)

        drop_keys = [key for key, value in self._node_to_doc_id.items() if value == doc_id]
        for key in drop_keys:
            self._node_to_doc_id.pop(key, None)

    def query(self, query: VectorStoreQuery, **kwargs: Any) -> VectorStoreQueryResult:
        """Query K2 and return LlamaIndex vector-store query results."""
        query_str = query.query_str or kwargs.get("query_str")
        if not query_str:
            raise ValueError(
                "K2LlamaIndexVectorStore requires text queries; embedding-only VectorStoreQuery is unsupported"
            )

        query_top_k = query.similarity_top_k or kwargs.get("similarity_top_k") or self.top_k

        query_filters = kwargs.get("filters")
        if query_filters is None and query.filters is not None:
            query_filters = llama_filters_to_k2(query.filters)
        if query_filters is None:
            query_filters = self.filters

        response = self._client.search(
            self._corpus_id,
            query_str,
            top_k=int(query_top_k),
            filters=query_filters,
            hybrid=self.hybrid,
            graph_rag=self.graph_rag,
            rerank=self.rerank,
            return_config=merge_return_config(
                base=self.return_config,
                override=None,
                include_text=True,
                include_scores=True,
                include_provenance=True,
            ),
        )

        ids: list[str] = []
        nodes: list[BaseNode] = []
        similarities: list[float] = []

        for result in response.get("results", []):
            chunk_id = result.get("chunk_id")
            if not chunk_id:
                continue

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
            doc_id = _resolve_result_doc_id(chunk_id=chunk_id, metadata=chunk_metadata)

            score = result.get("score")
            if score is None:
                score = result.get("raw_score")
            if score is None:
                score = 0.0

            node = TextNode(
                id_=chunk_id,
                text=result.get("text") or "",
                metadata={
                    **chunk_metadata,
                    "document_id": doc_id,
                    "chunk_id": chunk_id,
                    "corpus_id": self._corpus_id,
                    "raw_score": result.get("raw_score"),
                },
            )

            # Keep query IDs delete-compatible with doc-centric write/delete semantics.
            ids.append(doc_id)
            nodes.append(node)
            similarities.append(float(score))

        return VectorStoreQueryResult(nodes=nodes, ids=ids, similarities=similarities)

    def persist(self, persist_path: str, fs: Any = None) -> None:
        """No-op: K2 persists state remotely in the K2 backend."""
        return
