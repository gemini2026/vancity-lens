"""Retrieval backend abstraction (K2 primary, local fallback).

K2 is the default production backend. Set RAG_BACKEND=local for local dev
with Cohere+pgvector (requires api.intelligence.local_rag).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import date
from typing import Optional

import asyncpg

from .k2_client import k2_fallback_to_local_enabled, k2_search_chunks

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def get_rag_backend() -> str:
    backend = (os.environ.get("RAG_BACKEND") or "k2").strip().lower()
    if backend not in {"local", "k2"}:
        return "k2"
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
    """Local retrieval using Cohere+pgvector. Lazily imports from local_rag."""
    from .local_rag.embeddings import hybrid_search, sparse_search
    from .local_rag.query_planner import is_multi_hop, multi_hop_search

    if search_mode == "full" and cohere_api_key:
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

    return await sparse_search(
        db_pool,
        query,
        limit=10,
        neighborhood=neighborhood_filter,
        date_from=date_from,
        date_to=date_to,
    )


async def _fallback_sparse(
    db_pool: asyncpg.Pool,
    query: str,
    neighborhood_filter: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """BM25-only fallback -- no external API keys needed."""
    from .local_rag.embeddings import sparse_search

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
    search_mode: str = "full",
    cohere_api_key: Optional[str] = None,
    neighborhood_filter: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """Retrieve document chunks using the configured backend."""

    backend = get_rag_backend()
    if backend == "local":
        return await _retrieve_local(
            db_pool,
            query=query,
            search_mode=search_mode,
            cohere_api_key=cohere_api_key,
            neighborhood_filter=neighborhood_filter,
            date_from=date_from,
            date_to=date_to,
        )

    # K2 retrieval path
    t0 = time.perf_counter()
    try:
        k2_chunks = await asyncio.to_thread(k2_search_chunks, query)
    except Exception as exc:
        if k2_fallback_to_local_enabled():
            logger.warning("K2 retrieval failed; falling back to BM25. error=%s", exc)
            return await _fallback_sparse(
                db_pool,
                query,
                neighborhood_filter=neighborhood_filter,
                date_from=date_from,
                date_to=date_to,
            )
        raise

    latency_ms = (time.perf_counter() - t0) * 1000.0
    logger.info("K2 search completed in %.1fms, %d chunks", latency_ms, len(k2_chunks))
    return k2_chunks
