#!/usr/bin/env python3
"""Generate a shared "golden chunk" eval set for local-vs-K2 comparisons.

The generated dataset is backend-agnostic and can be reused by:
- retrieval-only evaluation (golden chunk hit + URL hit)
- end-to-end RAGAS evaluation (same queries, fair comparison)

Output schema (JSONL):
{
  "id": 1,
  "query": "...",
  "expected_url": "...",
  "expected_title": "...",
  "local_document_id": 123,
  "golden_chunk_text": "...",
  "golden_anchor_text": "...",
  "golden_tokens": ["..."],
  "source_type": "...",
  "published_date": "YYYY-MM-DD" | null
}
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk import Knowledge2  # noqa: E402


STOP_TOKENS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "your",
    "their",
    "they",
    "have",
    "will",
    "into",
    "within",
    "about",
    "because",
    "application",
    "development",
    "vancouver",
    "city",
    "project",
    "plan",
    "zoning",
    "policy",
    "share",
    "facebook",
    "twitter",
    "linkedin",
}


@dataclass(frozen=True)
class Candidate:
    document_id: int
    expected_url: str
    expected_title: str
    source_type: str
    published_date: date | None
    chunk_text: str


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _normalize_ws(text: str) -> str:
    return " ".join((text or "").split())


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


def _list_k2_document_urls(client: Knowledge2, corpus_id: str) -> set[str]:
    urls: set[str] = set()
    limit = 200
    offset = 0
    while True:
        resp = client.list_documents(corpus_id, limit=limit, offset=offset)
        docs = resp.get("documents") or []
        if not docs:
            break
        for doc in docs:
            meta = doc.get("metadata") or {}
            raw_url = (
                meta.get("source_url")
                or meta.get("url")
                or doc.get("source_uri")
                or meta.get("source_uri")
                or ""
            )
            url = _normalize_url(str(raw_url))
            if url:
                urls.add(url)
        offset += len(docs)
    return urls


async def _get_db_pool(db_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(db_url, min_size=1, max_size=5)


async def _load_candidates(pool: asyncpg.Pool, *, max_rows: int) -> list[Candidate]:
    sql = """
        SELECT
            d.id AS document_id,
            d.source_url AS expected_url,
            COALESCE(d.title, '') AS expected_title,
            COALESCE(d.source_type, 'unknown') AS source_type,
            d.published_date AS published_date,
            dc.chunk_text AS chunk_text
        FROM documents d
        JOIN LATERAL (
            SELECT chunk_text
            FROM document_chunks dc
            WHERE dc.document_id = d.id
              AND dc.chunk_text IS NOT NULL
              AND length(dc.chunk_text) > 0
            ORDER BY length(dc.chunk_text) DESC
            LIMIT 1
        ) dc ON TRUE
        WHERE d.source_url IS NOT NULL
        ORDER BY d.created_at DESC, d.id DESC
        LIMIT $1
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, max_rows)

    candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    for row in rows:
        url = _normalize_url(str(row["expected_url"] or ""))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        candidates.append(
            Candidate(
                document_id=int(row["document_id"]),
                expected_url=url,
                expected_title=str(row["expected_title"] or "").strip(),
                source_type=str(row["source_type"] or "unknown"),
                published_date=row["published_date"],
                chunk_text=_normalize_ws(str(row["chunk_text"] or "")),
            )
        )
    return candidates


def _extract_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z]{3,}", text)
    return [token.lower() for token in tokens if token.lower() not in STOP_TOKENS]


def _extract_anchor(text: str, *, min_words: int) -> str:
    text = _normalize_ws(text)
    if not text:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", text)
    ranked: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        words = sentence.split()
        if len(words) < min_words:
            continue
        if len(sentence) < 80:
            continue
        ranked.append(sentence)

    if ranked:
        ranked.sort(key=lambda s: (-len(s), s))
        return ranked[0][:280]

    # Fallback when punctuation/sentences are poor: use a deterministic prefix.
    words = text.split()
    return " ".join(words[: min(len(words), 40)])


def _build_query(tokens: list[str], df: Counter[str], *, max_query_tokens: int) -> str:
    unique = sorted(set(tokens), key=lambda token: (df[token], -len(token), token))
    selected = unique[:max_query_tokens]
    return " ".join(selected).strip()


async def main() -> int:
    parser = argparse.ArgumentParser(description="Generate golden chunk eval dataset.")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL") or "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens",
        help="Postgres URL for local documents/chunks.",
    )
    parser.add_argument("--n-queries", type=int, default=150, help="Max golden rows to write.")
    parser.add_argument(
        "--query-token-count",
        type=int,
        default=8,
        help="Number of distinctive tokens to keep in each generated query.",
    )
    parser.add_argument(
        "--min-anchor-words",
        type=int,
        default=10,
        help="Minimum words for preferred sentence-based anchor extraction.",
    )
    parser.add_argument(
        "--output-jsonl",
        default=None,
        help="Path to JSONL output. Default: migration/rag_eval/output/<timestamp>/golden_chunks.jsonl",
    )
    parser.add_argument(
        "--summary-md",
        default=None,
        help="Path to summary markdown. Default: migration/rag_eval/output/<timestamp>/golden_chunks_summary.md",
    )
    parser.add_argument(
        "--no-k2-intersection",
        action="store_true",
        help="Do not filter dataset to URLs present in K2 corpus.",
    )
    args = parser.parse_args()

    n_queries = max(1, int(args.n_queries))
    query_token_count = max(3, min(int(args.query_token_count), 20))
    min_anchor_words = max(5, min(int(args.min_anchor_words), 40))

    out_dir = Path("migration/rag_eval/output") / _now_ts()
    out_dir.mkdir(parents=True, exist_ok=True)

    output_jsonl = Path(args.output_jsonl) if args.output_jsonl else out_dir / "golden_chunks.jsonl"
    summary_md = Path(args.summary_md) if args.summary_md else out_dir / "golden_chunks_summary.md"
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    summary_md.parent.mkdir(parents=True, exist_ok=True)

    pool = await _get_db_pool(args.db_url)
    try:
        candidates = await _load_candidates(pool, max_rows=max(2000, n_queries * 20))
    finally:
        await pool.close()

    k2_urls: set[str] | None = None
    corpus_ref = ""
    corpus_id = ""
    if not args.no_k2_intersection:
        client = _k2_client_from_env()
        corpus_ref = _require_env("K2_CORPUS_ID")
        corpus_id = _resolve_k2_corpus_id(client, corpus_ref)
        k2_urls = _list_k2_document_urls(client, corpus_id)

    if k2_urls is not None:
        candidates = [candidate for candidate in candidates if candidate.expected_url in k2_urls]

    if not candidates:
        raise SystemExit("No candidates available after filtering. Check local chunks and K2 corpus intersection.")

    tokenized_candidates: list[list[str]] = []
    token_df: Counter[str] = Counter()
    for candidate in candidates:
        toks = _extract_tokens(candidate.chunk_text)
        tokenized_candidates.append(toks)
        for token in set(toks):
            token_df[token] += 1

    rows: list[dict[str, Any]] = []
    for candidate, tokens in zip(candidates, tokenized_candidates, strict=False):
        query = _build_query(tokens, token_df, max_query_tokens=query_token_count)
        if not query:
            query = candidate.expected_title
        if not query:
            continue

        anchor = _extract_anchor(candidate.chunk_text, min_words=min_anchor_words)
        if not anchor:
            continue

        row = {
            "id": len(rows) + 1,
            "query": query,
            "expected_url": candidate.expected_url,
            "expected_title": candidate.expected_title,
            "local_document_id": candidate.document_id,
            "source_type": candidate.source_type,
            "published_date": candidate.published_date.isoformat() if candidate.published_date else None,
            "golden_chunk_text": candidate.chunk_text,
            "golden_anchor_text": anchor,
            "golden_tokens": sorted(set(tokens))[:50],
            "golden_chunk_char_len": len(candidate.chunk_text),
        }
        rows.append(row)
        if len(rows) >= n_queries:
            break

    if not rows:
        raise SystemExit("No golden rows generated. Increase dataset size or relax filters.")

    with output_jsonl.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    avg_query_words = sum(len(str(r["query"]).split()) for r in rows) / len(rows)
    avg_chunk_chars = sum(int(r["golden_chunk_char_len"]) for r in rows) / len(rows)
    approx_tokens = sum(int(r["golden_chunk_char_len"]) for r in rows) / 4.0

    summary_lines = [
        "# Golden Chunk Dataset Summary",
        "",
        f"- Generated (UTC): `{datetime.now(timezone.utc).isoformat()}`",
        f"- Rows written: `{len(rows)}`",
        f"- Avg query length (words): `{avg_query_words:.1f}`",
        f"- Avg golden chunk length (chars): `{avg_chunk_chars:.1f}`",
        f"- Approx golden chunk tokens total: `~{approx_tokens:,.0f}` (`chars/4` heuristic)",
        f"- K2 intersection filter applied: `{k2_urls is not None}`",
    ]
    if k2_urls is not None:
        summary_lines.extend(
            [
                f"- K2 corpus ref: `{corpus_ref}`",
                f"- K2 corpus resolved id: `{corpus_id}`",
                f"- K2 URLs discovered: `{len(k2_urls)}`",
            ]
        )
    summary_lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Golden JSONL: `{output_jsonl}`",
            f"- Summary: `{summary_md}`",
            "",
        ]
    )
    summary_md.write_text("\n".join(summary_lines), encoding="utf-8")

    print(str(output_jsonl))
    print(str(summary_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
