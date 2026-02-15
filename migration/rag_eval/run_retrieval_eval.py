#!/usr/bin/env python3
"""Retrieval-only evaluation: local Postgres vs K2.

We can build an evaluation set from either:
  1) `intelligence_signals` (more realistic; requires signals to exist), or
  2) `documents` (title-as-query; works even if you haven't extracted signals).

Then we:
  - filter to expected URLs present in BOTH local DB and the K2 corpus
  - run retrieval for each query against:
      local sparse BM25 (default) OR local hybrid (optional)
      K2 search
  - compute recall@k, MRR, overlap@k, and latency

Outputs:
  migration/rag_eval/output/<timestamp>/{results.jsonl,summary.md}
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

# Ensure repo root is on sys.path so `import sdk` / `import api.*` works when
# running this script from anywhere.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk import Knowledge2
from sdk.errors import Knowledge2Error

from api.intelligence.local_rag.embeddings import hybrid_search, sparse_search


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _require_env(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise SystemExit(f"Missing required env var: {name}")
    return v


def _k2_client_from_env() -> Knowledge2:
    api_host = (os.environ.get("K2_API_HOST") or "https://api-dev.knowledge2.ai").strip().rstrip("/")
    api_key = _require_env("K2_API_KEY")
    return Knowledge2(api_host=api_host, api_key=api_key)


def _resolve_k2_corpus_id(client: Knowledge2, corpus_ref: str) -> str:
    """Accept a corpus UUID or a corpus name; resolve to UUID."""
    corpus_ref = corpus_ref.strip()
    if not corpus_ref:
        raise SystemExit("K2_CORPUS_ID is empty")

    corpora = (client.list_corpora(limit=200, offset=0) or {}).get("corpora") or []
    for c in corpora:
        if c.get("id") == corpus_ref:
            return corpus_ref

    matches = [c for c in corpora if c.get("name") == corpus_ref and c.get("id")]
    if len(matches) == 1:
        return matches[0]["id"]
    if len(matches) > 1:
        raise SystemExit(f"Ambiguous K2 corpus name '{corpus_ref}'. Set K2_CORPUS_ID to the corpus UUID.")
    raise SystemExit(f"K2 corpus not found: '{corpus_ref}'. Ensure your key can access it and that the name/ID is correct.")


def _list_k2_document_urls(client: Knowledge2, corpus_id: str) -> set[str]:
    urls: set[str] = set()
    limit = 200
    offset = 0
    while True:
        resp = client.list_documents(corpus_id, limit=limit, offset=offset)
        docs = resp.get("documents") or []
        if not docs:
            break
        for d in docs:
            meta = d.get("metadata") or {}
            u = (
                meta.get("source_url")
                or meta.get("url")
                or d.get("source_uri")
                or meta.get("source_uri")
                or ""
            )
            u = _normalize_url(str(u))
            if u:
                urls.add(u)
        offset += len(docs)
    return urls


def _k2_search_urls(client: Knowledge2, corpus_id: str, query: str, *, top_k: int) -> list[str]:
    resp = client.search(
        corpus_id=corpus_id,
        query=query,
        top_k=top_k,
        return_config={"include_text": False, "include_scores": True, "include_provenance": True},
    )
    urls: list[str] = []
    seen: set[str] = set()
    for r in (resp.get("results") or [])[:top_k]:
        meta = r.get("metadata") or {}
        u = (
            meta.get("source_url")
            or meta.get("url")
            or meta.get("source_uri")
            or ""
        )
        u = _normalize_url(str(u))
        if u and u not in seen:
            urls.append(u)
            seen.add(u)
    return urls


@dataclass(frozen=True)
class EvalItem:
    item_type: str  # "signal" | "document"
    item_id: int
    query_text: str
    expected_url: str
    expected_title: str


async def _get_db_pool(db_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(db_url, min_size=1, max_size=5)


async def _load_signal_eval_items(pool: asyncpg.Pool, *, max_rows: int) -> list[EvalItem]:
    # Pull more rows than needed so we can dedupe by expected_url.
    sql = """
        SELECT
            s.id AS signal_id,
            COALESCE(NULLIF(s.headline, ''), NULLIF(s.summary, '')) AS query_text,
            d.source_url AS expected_url,
            COALESCE(d.title, '') AS expected_title
        FROM intelligence_signals s
        JOIN documents d ON d.id = s.document_id
        WHERE d.source_url IS NOT NULL
          AND (s.headline IS NOT NULL OR s.summary IS NOT NULL)
          AND EXISTS (SELECT 1 FROM document_chunks dc WHERE dc.document_id = d.id)
        ORDER BY s.event_date DESC NULLS LAST, s.id DESC
        LIMIT $1
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, max_rows)

    items: list[EvalItem] = []
    seen_urls: set[str] = set()
    for r in rows:
        q = (r["query_text"] or "").strip()
        u = _normalize_url(r["expected_url"] or "")
        if not q or not u:
            continue
        if u in seen_urls:
            continue
        seen_urls.add(u)
        items.append(
            EvalItem(
                item_type="signal",
                item_id=int(r["signal_id"]),
                query_text=q,
                expected_url=u,
                expected_title=str(r["expected_title"] or ""),
            )
        )
    return items


async def _load_document_eval_items(pool: asyncpg.Pool, *, max_rows: int) -> list[EvalItem]:
    # Chunk-derived queries for documents:
    # - title mode: title-like query (shortened)
    # - phrase mode: short phrase extracted from the document chunk text (more robust for BM25)
    sql = """
        SELECT
            d.id AS document_id,
            d.source_url AS expected_url,
            COALESCE(d.title, '') AS expected_title,
            dc.chunk_text AS chunk_text
        FROM documents d
        JOIN LATERAL (
            SELECT chunk_text
            FROM document_chunks dc
            WHERE dc.document_id = d.id
            ORDER BY length(dc.chunk_text) DESC
            LIMIT 1
        ) dc ON TRUE
        WHERE d.source_url IS NOT NULL
        ORDER BY d.created_at DESC, d.id DESC
        LIMIT $1
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, max_rows)

    def _extract_tokens(text: str) -> list[str]:
        # Alphabetic tokens only: avoids mismatches on hyphenated numeric IDs.
        toks = re.findall(r"[A-Za-z]{3,}", text)
        stop = {
            # very common glue words
            "the",
            "and",
            "for",
            "with",
            "from",
            "this",
            "that",
            "your",
            # social/share boilerplate from ShapeYourCity pages
            "share",
            "facebook",
            "twitter",
            "linkedin",
            # common address suffixes
            "ave",
            "avenue",
            "st",
            "street",
            "dr",
            "drive",
            "rd",
            "road",
            "blvd",
            "boulevard",
            "way",
            # too-generic domain terms (tends to cause ties)
            "development",
            "application",
        }
        return [t.lower() for t in toks if t.lower() not in stop]

    docs: list[dict[str, Any]] = []
    per_doc_tokens: list[list[str]] = []
    df: Counter[str] = Counter()

    for r in rows:
        title = (r["expected_title"] or "").strip()
        chunk_text = (r["chunk_text"] or "").strip()
        url = _normalize_url(r["expected_url"] or "")
        if not chunk_text or not url:
            continue

        tokens = _extract_tokens(chunk_text)
        per_doc_tokens.append(tokens)
        for t in set(tokens):
            df[t] += 1
        docs.append(
            {
                "document_id": int(r["document_id"]),
                "expected_url": url,
                "expected_title": title,
            }
        )

    items: list[EvalItem] = []
    for doc, tokens in zip(docs, per_doc_tokens, strict=False):
        title = doc["expected_title"]
        url = doc["expected_url"]

        unique = sorted(set(tokens), key=lambda t: (df[t], -len(t), t))
        q_tokens = unique[:8]
        q = " ".join(q_tokens).strip()
        if not q:
            # Fallback: title is still better than an empty query.
            q = title

        q = " ".join(q.split())
        if not q:
            continue

        items.append(
            EvalItem(
                item_type="document",
                item_id=int(doc["document_id"]),
                query_text=q,
                expected_url=url,
                expected_title=title,
            )
        )
    return items


async def main() -> int:
    parser = argparse.ArgumentParser(description="Compare local retrieval vs K2 retrieval (retrieval-only).")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL") or "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens",
        help="Postgres URL for local eval dataset and local retrieval.",
    )
    parser.add_argument(
        "--eval-set",
        choices=["documents", "signals"],
        default="documents",
        help="Which local dataset to use for (query, expected_url) pairs.",
    )
    parser.add_argument("--n-queries", type=int, default=100, help="Number of eval queries to run (after filtering).")
    parser.add_argument("--top-k", type=int, default=10, help="Top-K retrieval depth for both backends.")
    parser.add_argument(
        "--local-mode",
        choices=["sparse", "hybrid"],
        default="sparse",
        help="Local retrieval mode. hybrid requires COHERE_API_KEY.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output directory. Default: migration/rag_eval/output/<timestamp>/",
    )
    args = parser.parse_args()

    top_k = max(1, min(int(args.top_k), 50))
    n_queries = max(1, int(args.n_queries))

    out_dir = Path(args.output_dir) if args.output_dir else Path("migration/rag_eval/output") / _now_ts()
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"
    summary_path = out_dir / "summary.md"

    # K2 setup (required)
    client = _k2_client_from_env()
    corpus_ref = _require_env("K2_CORPUS_ID")
    corpus_id = _resolve_k2_corpus_id(client, corpus_ref)

    # Local DB setup
    pool = await _get_db_pool(args.db_url)
    try:
        # Build eval set from local DB
        max_rows = max(2000, n_queries * 20)
        if args.eval_set == "signals":
            raw_items = await _load_signal_eval_items(pool, max_rows=max_rows)
        else:
            raw_items = await _load_document_eval_items(pool, max_rows=max_rows)

        # Filter to intersection: expected_url must exist in K2 corpus
        k2_urls = _list_k2_document_urls(client, corpus_id)
        filtered = [it for it in raw_items if it.expected_url in k2_urls]
        items = filtered[:n_queries]

        if not items:
            raise SystemExit(
                "No eval items left after filtering to K2 corpus URL intersection. "
                "Ensure (1) the K2 corpus is populated and (2) your local DB contains the same URLs."
            )

        if args.local_mode == "hybrid":
            cohere_key = (os.environ.get("COHERE_API_KEY") or "").strip()
            if not cohere_key:
                raise SystemExit("COHERE_API_KEY is required for --local-mode hybrid")
        else:
            cohere_key = ""

        # Aggregate metrics
        local_hits = 0
        k2_hits = 0
        local_rr_sum = 0.0
        k2_rr_sum = 0.0
        overlap_sum = 0
        local_latency_ms: list[float] = []
        k2_latency_ms: list[float] = []
        errors = 0

        def _rr(rank: int | None) -> float:
            if not rank:
                return 0.0
            return 1.0 / float(rank)

        with results_path.open("w", encoding="utf-8") as f:
            for idx, it in enumerate(items, start=1):
                row: dict[str, Any] = {
                    "idx": idx,
                    "item_type": it.item_type,
                    "item_id": it.item_id,
                    "query": it.query_text,
                    "expected_url": it.expected_url,
                    "expected_title": it.expected_title,
                    "top_k": top_k,
                    "local_mode": args.local_mode,
                    "eval_set": args.eval_set,
                }

                try:
                    t0 = time.perf_counter()
                    if args.local_mode == "hybrid":
                        local = await hybrid_search(
                            pool,
                            it.query_text,
                            cohere_key,
                            limit=top_k,
                            use_rerank=False,  # keep costs down; still measures hybrid retrieval quality
                        )
                    else:
                        local = await sparse_search(pool, it.query_text, limit=top_k)
                    local_ms = (time.perf_counter() - t0) * 1000.0
                    local_latency_ms.append(local_ms)

                    local_urls: list[str] = []
                    seen_local: set[str] = set()
                    for r in local[:top_k]:
                        u = _normalize_url(str(r.get("source_url") or ""))
                        if u and u not in seen_local:
                            local_urls.append(u)
                            seen_local.add(u)

                    local_rank = (local_urls.index(it.expected_url) + 1) if it.expected_url in local_urls else None
                    row.update(
                        {
                            "local_urls": local_urls,
                            "local_latency_ms": local_ms,
                            "local_rank": local_rank,
                            "local_hit": bool(local_rank),
                        }
                    )

                    if local_rank:
                        local_hits += 1
                        local_rr_sum += _rr(local_rank)
                except Exception as e:
                    errors += 1
                    row["local_error"] = str(e)
                    local_urls = []

                try:
                    t0 = time.perf_counter()
                    k2_urls_list = _k2_search_urls(client, corpus_id, it.query_text, top_k=top_k)
                    k2_ms = (time.perf_counter() - t0) * 1000.0
                    k2_latency_ms.append(k2_ms)

                    k2_rank = (k2_urls_list.index(it.expected_url) + 1) if it.expected_url in k2_urls_list else None
                    row.update(
                        {
                            "k2_urls": k2_urls_list,
                            "k2_latency_ms": k2_ms,
                            "k2_rank": k2_rank,
                            "k2_hit": bool(k2_rank),
                        }
                    )

                    if k2_rank:
                        k2_hits += 1
                        k2_rr_sum += _rr(k2_rank)
                except Knowledge2Error as e:
                    errors += 1
                    row["k2_error"] = f"{e}"
                    k2_urls_list = []

                # Overlap@K
                overlap = len(set(local_urls[:top_k]) & set(k2_urls_list[:top_k]))
                overlap_sum += overlap
                row["overlap_at_k"] = overlap

                f.write(json.dumps(row, ensure_ascii=True) + "\n")

        n = len(items)
        local_recall = local_hits / n
        k2_recall = k2_hits / n
        local_mrr = local_rr_sum / n
        k2_mrr = k2_rr_sum / n
        avg_overlap = overlap_sum / n
        avg_local_ms = (sum(local_latency_ms) / len(local_latency_ms)) if local_latency_ms else 0.0
        avg_k2_ms = (sum(k2_latency_ms) / len(k2_latency_ms)) if k2_latency_ms else 0.0

        summary_lines = [
            "# Retrieval Eval Summary",
            "",
            f"- Timestamp (UTC): `{datetime.now(timezone.utc).isoformat()}`",
            f"- K2 corpus: `{corpus_ref}` (resolved id `{corpus_id}`)",
            f"- Local mode: `{args.local_mode}`",
            f"- Eval set: `{args.eval_set}`",
            f"- Top-K: `{top_k}`",
            f"- Rows available (pre-filter): `{len(raw_items)}`",
            f"- Rows after K2 URL intersection filter: `{len(filtered)}`",
            f"- Queries evaluated: `{n}`",
            f"- Errors: `{errors}`",
            "",
            "## Metrics",
            "",
            f"- Local recall@{top_k}: `{local_recall:.3f}`",
            f"- K2 recall@{top_k}: `{k2_recall:.3f}`",
            f"- Local MRR@{top_k}: `{local_mrr:.3f}`",
            f"- K2 MRR@{top_k}: `{k2_mrr:.3f}`",
            f"- Avg overlap@{top_k} (URLs): `{avg_overlap:.2f}`",
            f"- Avg local latency (ms): `{avg_local_ms:.1f}`",
            f"- Avg K2 latency (ms): `{avg_k2_ms:.1f}`",
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
