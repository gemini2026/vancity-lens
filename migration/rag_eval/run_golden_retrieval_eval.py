#!/usr/bin/env python3
"""Retrieval-only evaluation on a shared golden-chunk dataset.

Compares local retrieval vs K2 retrieval on the exact same queries and
ground-truth rows. Reports both:
- URL-level hit/rank (expected source URL in top-k)
- Golden-chunk hit/rank (expected URL + chunk text match via anchor/overlap)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk import Knowledge2  # noqa: E402
from sdk.errors import Knowledge2Error  # noqa: E402

from api.intelligence.local_rag.embeddings import hybrid_search, sparse_search  # noqa: E402


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _normalize_text(text: str) -> str:
    lowered = (text or "").lower()
    lowered = re.sub(r"[^a-z0-9\s]+", " ", lowered)
    return " ".join(lowered.split())


def _tokenize(text: str) -> set[str]:
    return {tok.lower() for tok in re.findall(r"[A-Za-z]{3,}", text or "")}


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def _k2_client_from_env() -> Knowledge2:
    api_host = (os.environ.get("K2_API_HOST") or "https://api-dev.knowledge2.ai").strip().rstrip("/")
    api_key = _require_env("K2_API_KEY")
    return Knowledge2(api_host=api_host, api_key=api_key)


def _resolve_k2_corpus_id(client: Knowledge2, corpus_ref: str) -> str:
    corpus_ref = corpus_ref.strip()
    if not corpus_ref:
        raise SystemExit("K2_CORPUS_ID is empty")

    corpora = (client.list_corpora(limit=200, offset=0) or {}).get("corpora") or []
    for corpus in corpora:
        if corpus.get("id") == corpus_ref:
            return corpus_ref

    matches = [c for c in corpora if c.get("name") == corpus_ref and c.get("id")]
    if len(matches) == 1:
        return str(matches[0]["id"])
    if len(matches) > 1:
        raise SystemExit(f"Ambiguous corpus name '{corpus_ref}'. Set K2_CORPUS_ID to UUID.")
    raise SystemExit(f"K2 corpus not found: '{corpus_ref}'")


def _k2_search_chunks(client: Knowledge2, corpus_id: str, query: str, *, top_k: int) -> list[dict[str, Any]]:
    resp = client.search(
        corpus_id=corpus_id,
        query=query,
        top_k=top_k,
        return_config={"include_text": True, "include_scores": True, "include_provenance": True},
    )
    chunks: list[dict[str, Any]] = []
    for result in (resp.get("results") or [])[:top_k]:
        meta = result.get("metadata") or {}
        chunks.append(
            {
                "source_url": _normalize_url(
                    str(
                        meta.get("source_url")
                        or meta.get("url")
                        or meta.get("source_uri")
                        or ""
                    )
                ),
                "chunk_text": str(result.get("text") or ""),
                "score": result.get("score"),
                "title": str(meta.get("title") or meta.get("document_title") or ""),
            }
        )
    return chunks


def _unique_urls(chunks: list[dict[str, Any]], *, top_k: int) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for chunk in chunks[:top_k]:
        url = _normalize_url(str(chunk.get("source_url") or ""))
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _golden_match_score(
    *,
    golden_anchor_text: str,
    golden_tokens: list[str],
    candidate_text: str,
) -> tuple[bool, float]:
    candidate_norm = _normalize_text(candidate_text)
    anchor_norm = _normalize_text(golden_anchor_text)
    anchor_hit = bool(anchor_norm and anchor_norm in candidate_norm)

    golden_token_set = {tok for tok in golden_tokens if tok}
    if not golden_token_set:
        golden_token_set = _tokenize(golden_anchor_text)
    if not golden_token_set:
        return (anchor_hit, 0.0)

    overlap = len(golden_token_set & _tokenize(candidate_text))
    overlap_ratio = overlap / float(len(golden_token_set))
    return (anchor_hit, overlap_ratio)


def _first_url_rank(chunks: list[dict[str, Any]], *, expected_url: str, top_k: int) -> int | None:
    urls = _unique_urls(chunks, top_k=top_k)
    if expected_url in urls:
        return urls.index(expected_url) + 1
    return None


def _first_golden_rank(
    chunks: list[dict[str, Any]],
    *,
    expected_url: str,
    golden_anchor_text: str,
    golden_tokens: list[str],
    overlap_threshold: float,
    top_k: int,
) -> tuple[int | None, float]:
    best_overlap = 0.0
    for idx, chunk in enumerate(chunks[:top_k], start=1):
        chunk_url = _normalize_url(str(chunk.get("source_url") or ""))
        if chunk_url != expected_url:
            continue
        anchor_hit, overlap = _golden_match_score(
            golden_anchor_text=golden_anchor_text,
            golden_tokens=golden_tokens,
            candidate_text=str(chunk.get("chunk_text") or ""),
        )
        if overlap > best_overlap:
            best_overlap = overlap
        if anchor_hit or overlap >= overlap_threshold:
            return (idx, overlap)
    return (None, best_overlap)


def _rr(rank: int | None) -> float:
    if not rank:
        return 0.0
    return 1.0 / float(rank)


def _load_golden_rows(path: Path, *, n_queries: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            row = json.loads(raw)
            query = str(row.get("query") or "").strip()
            expected_url = _normalize_url(str(row.get("expected_url") or ""))
            if not query or not expected_url:
                continue
            row["query"] = query
            row["expected_url"] = expected_url
            row["golden_anchor_text"] = str(row.get("golden_anchor_text") or "")
            row["golden_tokens"] = list(row.get("golden_tokens") or [])
            rows.append(row)
            if len(rows) >= n_queries:
                break
    return rows


async def _get_db_pool(db_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(db_url, min_size=1, max_size=5)


async def _local_search_chunks(
    pool: asyncpg.Pool,
    *,
    query: str,
    local_mode: str,
    cohere_api_key: str,
    top_k: int,
) -> list[dict[str, Any]]:
    if local_mode == "hybrid":
        return await hybrid_search(
            pool,
            query,
            cohere_api_key,
            limit=top_k,
            use_rerank=False,
        )
    return await sparse_search(pool, query, limit=top_k)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Golden retrieval eval: local vs K2.")
    parser.add_argument("--golden-jsonl", required=True, help="Path to golden chunk dataset JSONL.")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL") or "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens",
        help="Postgres URL for local retrieval.",
    )
    parser.add_argument("--n-queries", type=int, default=120, help="Number of rows from golden dataset.")
    parser.add_argument("--top-k", type=int, default=10, help="Top-K depth for both backends.")
    parser.add_argument("--local-mode", choices=["sparse", "hybrid"], default="sparse")
    parser.add_argument(
        "--overlap-threshold",
        type=float,
        default=0.35,
        help="Golden chunk hit threshold when anchor is not a direct substring.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Default: migration/rag_eval/output/<timestamp>/",
    )
    args = parser.parse_args()

    n_queries = max(1, int(args.n_queries))
    top_k = max(1, min(int(args.top_k), 50))
    overlap_threshold = min(max(float(args.overlap_threshold), 0.0), 1.0)

    out_dir = Path(args.output_dir) if args.output_dir else Path("migration/rag_eval/output") / _now_ts()
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "golden_retrieval_results.jsonl"
    summary_path = out_dir / "golden_retrieval_summary.md"

    rows = _load_golden_rows(Path(args.golden_jsonl), n_queries=n_queries)
    if not rows:
        raise SystemExit("No valid rows loaded from golden JSONL.")

    if args.local_mode == "hybrid":
        cohere_api_key = (os.environ.get("COHERE_API_KEY") or "").strip()
        if not cohere_api_key:
            raise SystemExit("COHERE_API_KEY is required for --local-mode hybrid")
    else:
        cohere_api_key = ""

    client = _k2_client_from_env()
    corpus_ref = _require_env("K2_CORPUS_ID")
    corpus_id = _resolve_k2_corpus_id(client, corpus_ref)

    pool = await _get_db_pool(args.db_url)
    try:
        errors = 0

        local_url_hits = 0
        k2_url_hits = 0
        local_url_mrr = 0.0
        k2_url_mrr = 0.0

        local_chunk_hits = 0
        k2_chunk_hits = 0
        local_chunk_mrr = 0.0
        k2_chunk_mrr = 0.0

        local_latency_ms: list[float] = []
        k2_latency_ms: list[float] = []
        overlap_urls_sum = 0

        with results_path.open("w", encoding="utf-8") as out:
            for idx, row in enumerate(rows, start=1):
                query = str(row["query"])
                expected_url = _normalize_url(str(row["expected_url"]))
                anchor = str(row.get("golden_anchor_text") or "")
                golden_tokens = list(row.get("golden_tokens") or [])

                result_row: dict[str, Any] = {
                    "idx": idx,
                    "id": row.get("id"),
                    "query": query,
                    "expected_url": expected_url,
                    "expected_title": row.get("expected_title"),
                    "top_k": top_k,
                    "local_mode": args.local_mode,
                    "overlap_threshold": overlap_threshold,
                }

                local_chunks: list[dict[str, Any]] = []
                k2_chunks: list[dict[str, Any]] = []

                try:
                    t0 = time.perf_counter()
                    local_chunks = await _local_search_chunks(
                        pool,
                        query=query,
                        local_mode=args.local_mode,
                        cohere_api_key=cohere_api_key,
                        top_k=top_k,
                    )
                    local_ms = (time.perf_counter() - t0) * 1000.0
                    local_latency_ms.append(local_ms)

                    local_url_rank = _first_url_rank(local_chunks, expected_url=expected_url, top_k=top_k)
                    local_chunk_rank, local_best_overlap = _first_golden_rank(
                        local_chunks,
                        expected_url=expected_url,
                        golden_anchor_text=anchor,
                        golden_tokens=golden_tokens,
                        overlap_threshold=overlap_threshold,
                        top_k=top_k,
                    )
                    result_row.update(
                        {
                            "local_latency_ms": local_ms,
                            "local_urls": _unique_urls(local_chunks, top_k=top_k),
                            "local_url_rank": local_url_rank,
                            "local_chunk_rank": local_chunk_rank,
                            "local_chunk_best_overlap": local_best_overlap,
                        }
                    )
                    if local_url_rank:
                        local_url_hits += 1
                        local_url_mrr += _rr(local_url_rank)
                    if local_chunk_rank:
                        local_chunk_hits += 1
                        local_chunk_mrr += _rr(local_chunk_rank)
                except Exception as exc:
                    errors += 1
                    result_row["local_error"] = str(exc)

                try:
                    t0 = time.perf_counter()
                    k2_chunks = _k2_search_chunks(client, corpus_id, query, top_k=top_k)
                    k2_ms = (time.perf_counter() - t0) * 1000.0
                    k2_latency_ms.append(k2_ms)

                    k2_url_rank = _first_url_rank(k2_chunks, expected_url=expected_url, top_k=top_k)
                    k2_chunk_rank, k2_best_overlap = _first_golden_rank(
                        k2_chunks,
                        expected_url=expected_url,
                        golden_anchor_text=anchor,
                        golden_tokens=golden_tokens,
                        overlap_threshold=overlap_threshold,
                        top_k=top_k,
                    )
                    result_row.update(
                        {
                            "k2_latency_ms": k2_ms,
                            "k2_urls": _unique_urls(k2_chunks, top_k=top_k),
                            "k2_url_rank": k2_url_rank,
                            "k2_chunk_rank": k2_chunk_rank,
                            "k2_chunk_best_overlap": k2_best_overlap,
                        }
                    )
                    if k2_url_rank:
                        k2_url_hits += 1
                        k2_url_mrr += _rr(k2_url_rank)
                    if k2_chunk_rank:
                        k2_chunk_hits += 1
                        k2_chunk_mrr += _rr(k2_chunk_rank)
                except Knowledge2Error as exc:
                    errors += 1
                    result_row["k2_error"] = str(exc)

                overlap_urls = len(set(result_row.get("local_urls") or []) & set(result_row.get("k2_urls") or []))
                overlap_urls_sum += overlap_urls
                result_row["overlap_urls_at_k"] = overlap_urls

                out.write(json.dumps(result_row, ensure_ascii=True) + "\n")

        n = len(rows)
        avg_local_latency = sum(local_latency_ms) / len(local_latency_ms) if local_latency_ms else 0.0
        avg_k2_latency = sum(k2_latency_ms) / len(k2_latency_ms) if k2_latency_ms else 0.0

        summary_lines = [
            "# Golden Retrieval Eval Summary",
            "",
            f"- Timestamp (UTC): `{datetime.now(timezone.utc).isoformat()}`",
            f"- Queries evaluated: `{n}`",
            f"- Top-K: `{top_k}`",
            f"- Local mode: `{args.local_mode}`",
            f"- K2 corpus: `{corpus_ref}` (resolved `{corpus_id}`)",
            f"- Errors: `{errors}`",
            "",
            "## URL-Level Metrics",
            "",
            f"- Local recall@{top_k}: `{(local_url_hits / n):.3f}`",
            f"- K2 recall@{top_k}: `{(k2_url_hits / n):.3f}`",
            f"- Local MRR@{top_k}: `{(local_url_mrr / n):.3f}`",
            f"- K2 MRR@{top_k}: `{(k2_url_mrr / n):.3f}`",
            "",
            "## Golden-Chunk Metrics",
            "",
            f"- Match rule: `expected_url` AND (`anchor substring` OR `token overlap >= {overlap_threshold:.2f}`)",
            f"- Local golden recall@{top_k}: `{(local_chunk_hits / n):.3f}`",
            f"- K2 golden recall@{top_k}: `{(k2_chunk_hits / n):.3f}`",
            f"- Local golden MRR@{top_k}: `{(local_chunk_mrr / n):.3f}`",
            f"- K2 golden MRR@{top_k}: `{(k2_chunk_mrr / n):.3f}`",
            "",
            "## Latency and Overlap",
            "",
            f"- Avg local latency (ms): `{avg_local_latency:.1f}`",
            f"- Avg K2 latency (ms): `{avg_k2_latency:.1f}`",
            f"- Avg URL overlap@{top_k}: `{(overlap_urls_sum / n):.2f}`",
            "",
            "## Artifacts",
            "",
            f"- Results: `{results_path}`",
            f"- Summary: `{summary_path}`",
            "",
        ]
        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

        print(str(summary_path))
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
