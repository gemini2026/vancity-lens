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
import random
import time
from datetime import date
from typing import Any, Optional

import asyncpg

from .embeddings import hybrid_search, sparse_search
from .k2_client import k2_fallback_to_local_enabled, k2_search_chunks
from .query_planner import is_multi_hop, multi_hop_search

logger = logging.getLogger(__name__)

_K2_SHADOW_VALIDATE_SEMAPHORE: asyncio.Semaphore | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def k2_shadow_validate_enabled() -> bool:
    """Enable K2 shadow validation logging (off by default)."""

    return _env_bool("K2_SHADOW_VALIDATE", False)


def k2_shadow_validate_sample_rate() -> float:
    """Traffic sample rate for shadow validation logs (0.0 - 1.0)."""

    rate = _env_float("K2_SHADOW_VALIDATE_SAMPLE_RATE", 0.05)
    if rate < 0.0:
        return 0.0
    if rate > 1.0:
        return 1.0
    return rate


def k2_shadow_validate_local_mode() -> str:
    """Local retrieval mode used for comparison.

    - sparse: BM25 only (cheap, no external calls)
    - hybrid: pgvector+BM25 (requires Cohere; no rerank)
    - equivalent: exact Bill47 local path (may multi-hop + rerank)
    """

    mode = (os.environ.get("K2_SHADOW_VALIDATE_LOCAL_MODE") or "sparse").strip().lower()
    if mode not in {"sparse", "hybrid", "equivalent"}:
        return "sparse"
    return mode


def k2_shadow_validate_timeout_seconds() -> float:
    return max(_env_float("K2_SHADOW_VALIDATE_TIMEOUT_SECONDS", 8.0), 1.0)


def _k2_shadow_validate_semaphore() -> asyncio.Semaphore:
    global _K2_SHADOW_VALIDATE_SEMAPHORE
    if _K2_SHADOW_VALIDATE_SEMAPHORE is None:
        max_conc = max(_env_int("K2_SHADOW_VALIDATE_MAX_CONCURRENCY", 2), 1)
        _K2_SHADOW_VALIDATE_SEMAPHORE = asyncio.Semaphore(max_conc)
    return _K2_SHADOW_VALIDATE_SEMAPHORE


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _top_urls(chunks: list[dict[str, Any]], *, limit: int) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for c in chunks:
        u = _normalize_url(str(c.get("source_url") or ""))
        if not u or u in seen:
            continue
        urls.append(u)
        seen.add(u)
        if len(urls) >= limit:
            break
    return urls


async def _shadow_validate_k2_vs_local(
    db_pool: asyncpg.Pool,
    *,
    query: str,
    search_mode: str,
    cohere_api_key: Optional[str],
    neighborhood_filter: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    k2_chunks: list[dict[str, Any]],
    k2_latency_ms: float,
) -> None:
    sem = _k2_shadow_validate_semaphore()

    # Drop comparisons when we are already saturated; don't enqueue endlessly.
    if sem.locked():
        return

    await sem.acquire()
    try:
        local_mode = k2_shadow_validate_local_mode()
        timeout_s = k2_shadow_validate_timeout_seconds()

        async def _run_local() -> list[dict[str, Any]]:
            if local_mode == "equivalent":
                return await _retrieve_local(
                    db_pool,
                    query=query,
                    search_mode=search_mode,
                    cohere_api_key=cohere_api_key,
                    neighborhood_filter=neighborhood_filter,
                    date_from=date_from,
                    date_to=date_to,
                )

            if local_mode == "hybrid" and cohere_api_key:
                # No rerank: reduces cost but still reflects hybrid retrieval behaviour.
                return await hybrid_search(
                    db_pool,
                    query,
                    cohere_api_key,
                    limit=10,
                    use_rerank=False,
                )

            # Default: sparse BM25 only.
            return await sparse_search(
                db_pool,
                query,
                limit=10,
                neighborhood=neighborhood_filter,
                date_from=date_from,
                date_to=date_to,
            )

        t0 = time.perf_counter()
        try:
            local_chunks = await asyncio.wait_for(_run_local(), timeout=timeout_s)
        except Exception as exc:
            logger.info(
                "k2_shadow_validate",
                extra={
                    "shadow_error": str(exc),
                    "shadow_query": query[:200],
                    "shadow_search_mode": search_mode,
                    "shadow_local_mode": local_mode,
                    "shadow_k2_latency_ms": round(float(k2_latency_ms), 1),
                },
            )
            return

        local_latency_ms = (time.perf_counter() - t0) * 1000.0

        # Compare top URLs to keep logs small and actionable.
        top_n = max(_env_int("K2_SHADOW_VALIDATE_TOP_N", 5), 1)
        k2_urls = _top_urls(k2_chunks, limit=top_n)
        local_urls = _top_urls(local_chunks, limit=top_n)
        overlap = len(set(k2_urls) & set(local_urls))

        logger.info(
            "k2_shadow_validate",
            extra={
                "shadow_query": query[:200],
                "shadow_search_mode": search_mode,
                "shadow_local_mode": local_mode,
                "shadow_neighborhood_filter": neighborhood_filter,
                "shadow_date_from": date_from.isoformat() if date_from else None,
                "shadow_date_to": date_to.isoformat() if date_to else None,
                "shadow_k2_latency_ms": round(float(k2_latency_ms), 1),
                "shadow_local_latency_ms": round(float(local_latency_ms), 1),
                "shadow_top_n": top_n,
                "shadow_k2_top_urls": k2_urls,
                "shadow_local_top_urls": local_urls,
                "shadow_overlap_at_n": overlap,
            },
        )
    finally:
        sem.release()


def _maybe_start_shadow_validation(
    db_pool: asyncpg.Pool,
    *,
    query: str,
    search_mode: str,
    cohere_api_key: Optional[str],
    neighborhood_filter: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    k2_chunks: list[dict[str, Any]],
    k2_latency_ms: float,
) -> None:
    if not k2_shadow_validate_enabled():
        return

    rate = k2_shadow_validate_sample_rate()
    if rate <= 0.0:
        return

    if random.random() > rate:
        return

    try:
        asyncio.create_task(
            _shadow_validate_k2_vs_local(
                db_pool,
                query=query,
                search_mode=search_mode,
                cohere_api_key=cohere_api_key,
                neighborhood_filter=neighborhood_filter,
                date_from=date_from,
                date_to=date_to,
                k2_chunks=k2_chunks,
                k2_latency_ms=k2_latency_ms,
            )
        )
    except RuntimeError:
        # No running loop: should not happen in FastAPI request handling, but keep
        # this safe for unit tests and scripts.
        return


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
    t0 = time.perf_counter()
    try:
        k2_chunks = await asyncio.to_thread(k2_search_chunks, query)
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

    k2_latency_ms = (time.perf_counter() - t0) * 1000.0
    _maybe_start_shadow_validation(
        db_pool,
        query=query,
        search_mode=search_mode,
        cohere_api_key=cohere_api_key,
        neighborhood_filter=neighborhood_filter,
        date_from=date_from,
        date_to=date_to,
        k2_chunks=k2_chunks,
        k2_latency_ms=k2_latency_ms,
    )
    return k2_chunks
