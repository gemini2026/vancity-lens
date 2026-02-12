"""
Knowledge2 (K2) client wrapper for Bill47 (VCL).

This module intentionally keeps configuration in env vars and provides a small
surface area for the rest of the app:

- Build a singleton Knowledge2 SDK client
- Run a search and normalize results into Bill47's chunk dict shape

No K2 credentials should ever be committed to the repo.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from sdk import Knowledge2, Knowledge2Error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class K2Config:
    api_host: str
    api_key: str
    corpus_id: str
    top_k: int
    timeout_seconds: float


_CLIENT: Knowledge2 | None = None
_CLIENT_CFG: K2Config | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def load_k2_config() -> K2Config:
    api_host = (os.environ.get("K2_API_HOST") or "").strip().rstrip("/")
    if not api_host:
        api_host = "https://api-dev.knowledge2.ai"

    api_key = (os.environ.get("K2_API_KEY") or "").strip()
    corpus_id = (os.environ.get("K2_CORPUS_ID") or "").strip()

    try:
        top_k = int((os.environ.get("K2_TOP_K") or "10").strip())
    except ValueError:
        top_k = 10

    try:
        timeout_seconds = float((os.environ.get("K2_TIMEOUT_SECONDS") or "20").strip())
    except ValueError:
        timeout_seconds = 20.0

    if not api_key:
        raise RuntimeError("K2_API_KEY is not set")
    if not corpus_id:
        raise RuntimeError("K2_CORPUS_ID is not set")

    return K2Config(
        api_host=api_host,
        api_key=api_key,
        corpus_id=corpus_id,
        top_k=max(top_k, 1),
        timeout_seconds=max(timeout_seconds, 1.0),
    )


def k2_fallback_to_local_enabled() -> bool:
    return _env_bool("K2_FALLBACK_TO_LOCAL", True)


def get_k2_client() -> Knowledge2:
    global _CLIENT, _CLIENT_CFG
    cfg = load_k2_config()

    # Recreate client if config changed (rare, but makes local dev less confusing).
    if _CLIENT is not None and _CLIENT_CFG == cfg:
        return _CLIENT

    _CLIENT_CFG = cfg
    _CLIENT = Knowledge2(
        api_host=cfg.api_host,
        api_key=cfg.api_key,
        timeout=cfg.timeout_seconds,
    )
    return _CLIENT


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        # Accept YYYY-MM-DD; anything else is treated as unknown.
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def k2_search_chunks(query: str, *, top_k: int | None = None) -> list[dict[str, Any]]:
    """Search K2 and normalize results to the chunk dict shape expected by chat.py."""

    cfg = load_k2_config()
    effective_top_k = cfg.top_k if top_k is None else max(int(top_k), 1)
    client = get_k2_client()

    # Always request text + provenance so we can build citations even when generation
    # happens in Bill47 (Anthropic).
    try:
        response = client.search(
            corpus_id=cfg.corpus_id,
            query=query,
            top_k=effective_top_k,
            return_config={
                "include_text": True,
                "include_scores": True,
                "include_provenance": True,
            },
        )
    except Knowledge2Error as exc:
        logger.warning("K2 search failed: %s", exc)
        raise

    results = response.get("results") or []
    normalized: list[dict[str, Any]] = []
    for r in results:
        meta = r.get("metadata") or {}
        chunk_text = (r.get("text") or "").strip()

        # Best-effort mapping: metadata keys depend on how K2 ingestion was configured.
        document_title = (
            meta.get("title")
            or meta.get("document_title")
            or meta.get("source_title")
            or "Unknown"
        )
        source_url = (
            meta.get("source_url")
            or meta.get("canonical_url")
            or meta.get("source_uri")
            or ""
        )
        source_type = meta.get("source_type") or meta.get("type") or "unknown"
        published_date = _parse_date(meta.get("published_date") or meta.get("published_at"))

        score = r.get("score")
        final_score = float(score) if isinstance(score, (int, float)) else 0.0

        normalized.append(
            {
                # Bill47 chunk shape
                "chunk_id": None,  # K2 chunk IDs are strings; DB expects INT[] for chat history
                "chunk_text": chunk_text,
                "document_id": None,  # local DB doc IDs don't exist for K2
                "section_header": meta.get("section_header"),
                "chunk_index": meta.get("chunk_index"),
                "rrf_score": final_score,
                "final_score": final_score,
                "document_title": document_title,
                "source_url": source_url,
                "source_type": source_type,
                "published_date": published_date,
                # Debug-only provenance (not part of current response contract)
                "k2_chunk_id": r.get("chunk_id"),
            }
        )

    return normalized

