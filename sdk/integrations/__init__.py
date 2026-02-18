"""Framework integrations for the Knowledge2 SDK.

These imports are lazy so users can install only one framework extra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "K2LangChainRetriever",
    "K2LlamaIndexRetriever",
    "K2LlamaIndexVectorStore",
    "create_k2_langchain_tools",
    "create_k2_llamaindex_tools",
]

if TYPE_CHECKING:  # pragma: no cover
    # These are resolved lazily at runtime via __getattr__ so optional dependencies
    # (langchain-core / llama-index-core) are not required for base installs.
    from sdk.integrations.langchain import K2LangChainRetriever, create_k2_langchain_tools
    from sdk.integrations.llamaindex import (
        K2LlamaIndexRetriever,
        K2LlamaIndexVectorStore,
        create_k2_llamaindex_tools,
    )


def __getattr__(name: str):
    if name in {"K2LangChainRetriever", "create_k2_langchain_tools"}:
        from sdk.integrations.langchain import K2LangChainRetriever, create_k2_langchain_tools

        mapping = {
            "K2LangChainRetriever": K2LangChainRetriever,
            "create_k2_langchain_tools": create_k2_langchain_tools,
        }
        return mapping[name]

    if name in {
        "K2LlamaIndexRetriever",
        "K2LlamaIndexVectorStore",
        "create_k2_llamaindex_tools",
    }:
        from sdk.integrations.llamaindex import (
            K2LlamaIndexRetriever,
            K2LlamaIndexVectorStore,
            create_k2_llamaindex_tools,
        )

        mapping = {
            "K2LlamaIndexRetriever": K2LlamaIndexRetriever,
            "K2LlamaIndexVectorStore": K2LlamaIndexVectorStore,
            "create_k2_llamaindex_tools": create_k2_llamaindex_tools,
        }
        return mapping[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
