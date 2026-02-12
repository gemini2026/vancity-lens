"""Retrieval backend abstraction (local Postgres vs K2).

This module is the single decision point for "where do chunks come from?"

- local: current Bill47 hybrid search (pgvector + tsvector + optional Cohere rerank)
- k2:    Knowledge2 search via the K2 SDK (sync HTTP client executed in a thread)

The goal is to keep the rest of the app stable (chat, citations, UI) while
allowing a gradual cutover.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Optional

import asyncpg

from .embeddings import hybrid_search, sparse_search
from .k2_client import k2_fallback_to_local_enabled, k2_search_chunks
from .query_planner import is_multi_hop, multi_hop_search

logger = logging.getLogger(__name__)


def get_rag_backend() -> str:
    backend = (os.environ.get("RAG_BACKEND") or "local").strip().lower()
    if backend not in {"local", "k2"}:
        return "local"
    return backend


async def _retrieve_local(
    db_pool: asyncpg.Pool,
    *,
    query: str,
    search_mode: str,
    cohere_api_key: Optional[str],
    neighborhood_filter: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
) -> list[dict]:
    if search_mode == "full":
        assert cohere_api_key is not None
        if is_multi_hop(query):
            logger.info("Multi-hop query detected, using decomposed retrieval")
            return await multi_hop_search(
                db_pool,
                query,
                cohere_api_key,
                search_fn=hybrid_search,
                limit_per_hop=8,
                final_limit=12,
                use_rerank=True,
            )
        return await hybrid_search(
            db_pool,
            query,
            cohere_api_key,
            limit=10,
            use_rerank=True,
        )

    # Partial or demo mode: BM25 sparse search only (no API keys)
    return await sparse_search(
        db_pool,
        query,
        limit=10,
        neighborhood=neighborhood_filter,
        date_from=date_from,
        date_to=date_to,
    )


async def retrieve_document_chunks(
    db_pool: asyncpg.Pool,
    *,
    query: str,
    search_mode: str,
    cohere_api_key: Optional[str],
    neighborhood_filter: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """Retrieve document chunks using the configured backend."""

    backend = get_rag_backend()
    if backend != "k2":
        return await _retrieve_local(
            db_pool,
            query=query,
            search_mode=search_mode,
            cohere_api_key=cohere_api_key,
            neighborhood_filter=neighborhood_filter,
            date_from=date_from,
            date_to=date_to,
        )

    # K2 retrieval path (sync SDK -> thread). We keep Bill47's search_mode logic
    # for *generation* behavior, but retrieval no longer depends on Cohere.
    try:
        return await asyncio.to_thread(k2_search_chunks, query)
    except Exception as exc:
        if k2_fallback_to_local_enabled():
            logger.warning("K2 retrieval failed; falling back to local. error=%s", exc)
            return await _retrieve_local(
                db_pool,
                query=query,
                search_mode=search_mode,
                cohere_api_key=cohere_api_key,
                neighborhood_filter=neighborhood_filter,
                date_from=date_from,
                date_to=date_to,
            )
        raise

