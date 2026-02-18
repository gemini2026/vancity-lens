from __future__ import annotations

from typing import Any, cast

from sdk import Knowledge2
from sdk.integrations._client import merge_return_config, resolve_client, resolve_corpus_id

try:
    from langchain_core.tools import BaseTool, tool
except ImportError as exc:  # pragma: no cover - import-time dependency guard
    raise ImportError(
        "LangChain integration requires langchain-core. Install with `pip install .[langchain]`."
    ) from exc


def create_k2_langchain_tools(
    *,
    corpus_id: str | None = None,
    client: Knowledge2 | None = None,
    api_key: str | None = None,
    api_host: str | None = None,
    default_top_k: int = 10,
    default_hybrid: dict[str, Any] | None = None,
    default_generation: dict[str, Any] | None = None,
) -> list[BaseTool]:
    """Create LangChain tools for K2 search and ingestion flows."""
    resolved_client = resolve_client(client=client, api_key=api_key, api_host=api_host)
    resolved_corpus_id = resolve_corpus_id(corpus_id)

    @tool("k2_search")
    def k2_search(
        query: str,
        top_k: int = default_top_k,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search a K2 corpus and return scored chunks."""
        return cast(
            "dict[str, Any]",
            resolved_client.search(
                resolved_corpus_id,
                query,
                top_k=top_k,
                filters=filters,
                hybrid=default_hybrid,
                return_config=merge_return_config(base=None, override=None),
            ),
        )

    @tool("k2_ingest_text")
    def k2_ingest_text(
        raw_text: str,
        source_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
        auto_index: bool = False,
    ) -> dict[str, Any]:
        """Ingest a text document into K2."""
        return cast(
            "dict[str, Any]",
            resolved_client.upload_document(
                resolved_corpus_id,
                raw_text=raw_text,
                source_uri=source_uri,
                metadata=metadata,
                auto_index=auto_index,
            ),
        )

    @tool("k2_build_indexes")
    def k2_build_indexes(
        dense: bool = True,
        sparse: bool = True,
        mode: str = "full",
        wait: bool = True,
    ) -> dict[str, Any]:
        """Trigger K2 index build for the current corpus."""
        return cast(
            "dict[str, Any]",
            resolved_client.build_indexes(
                resolved_corpus_id,
                dense=dense,
                sparse=sparse,
                mode=mode,
                wait=wait,
            ),
        )

    @tool("k2_generate_answer")
    def k2_generate_answer(
        query: str,
        top_k: int = default_top_k,
        filters: dict[str, Any] | None = None,
        generation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a grounded answer using K2 retrieval + server-side LLM generation."""
        return cast(
            "dict[str, Any]",
            resolved_client.search_generate(
                resolved_corpus_id,
                query,
                top_k=top_k,
                filters=filters,
                hybrid=default_hybrid,
                generation=generation if generation is not None else default_generation,
                return_config=merge_return_config(base=None, override=None),
            ),
        )

    return [k2_search, k2_ingest_text, k2_build_indexes, k2_generate_answer]
