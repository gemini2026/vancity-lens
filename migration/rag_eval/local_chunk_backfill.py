#!/usr/bin/env python3
"""Backfill local `document_chunks` without embeddings (BM25-only).

Why:
- For RAG evaluation we often want a meaningful local-vs-K2 overlap set.
- The default `scripts/ingest_sources.py` (without --process) stores documents
  but does NOT create chunks.
- Full processing (`--process`) is expensive (Cohere embeddings + Anthropic extraction).

This script chunks `documents.raw_text` and stores rows in `document_chunks` with:
  - embedding = NULL
  - chunk_tsvector populated via to_tsvector('english', chunk_text)

This enables local sparse retrieval (`sparse_search`) for the same documents
without paying embedding/LLM costs.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg

# Ensure repo root is on sys.path so `import sdk` / `import api.*` works.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.intelligence.chunker import chunk_document  # noqa: E402
from sdk import Knowledge2  # noqa: E402


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
    corpus_ref = corpus_ref.strip()
    corpora = (client.list_corpora(limit=200, offset=0) or {}).get("corpora") or []
    for c in corpora:
        if c.get("id") == corpus_ref:
            return corpus_ref
    matches = [c for c in corpora if c.get("name") == corpus_ref and c.get("id")]
    if len(matches) == 1:
        return matches[0]["id"]
    raise SystemExit(f"Could not resolve K2 corpus ref: {corpus_ref}")


def _list_k2_urls(client: Knowledge2, corpus_id: str) -> set[str]:
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
            u = meta.get("source_url") or d.get("source_uri") or ""
            u = _normalize_url(str(u))
            if u:
                urls.add(u)
        offset += len(docs)
    return urls


async def _get_pool(db_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(db_url, min_size=1, max_size=5)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill document_chunks with BM25-only chunks (no embeddings).")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL") or "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens",
    )
    parser.add_argument("--limit", type=int, default=200, help="Max documents to chunk in this run.")
    parser.add_argument("--dry-run", action="store_true", help="Discover and report, but do not write chunks.")
    parser.add_argument(
        "--only-k2-intersection",
        action="store_true",
        help="Only chunk documents whose source_url is present in the configured K2 corpus.",
    )
    args = parser.parse_args()

    limit = max(1, int(args.limit))

    k2_urls: set[str] | None = None
    if args.only_k2_intersection:
        client = _k2_client_from_env()
        corpus_ref = _require_env("K2_CORPUS_ID")
        corpus_id = _resolve_k2_corpus_id(client, corpus_ref)
        k2_urls = _list_k2_urls(client, corpus_id)
        print(f"k2_urls={len(k2_urls)}")

    pool = await _get_pool(args.db_url)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT d.id, d.source_url, d.raw_text
                FROM documents d
                WHERE d.raw_text IS NOT NULL
                  AND length(d.raw_text) > 0
                  AND NOT EXISTS (SELECT 1 FROM document_chunks dc WHERE dc.document_id = d.id)
                ORDER BY d.id ASC
                LIMIT $1
                """,
                limit,
            )

        docs = []
        for r in rows:
            url = _normalize_url(r["source_url"] or "")
            if k2_urls is not None and url not in k2_urls:
                continue
            docs.append((int(r["id"]), url, str(r["raw_text"])))

        print(f"candidates={len(rows)} selected={len(docs)} dry_run={args.dry_run}")
        if args.dry_run:
            return 0

        inserted_docs = 0
        inserted_chunks = 0

        for doc_id, url, raw_text in docs:
            chunks = chunk_document(raw_text)
            if not chunks:
                print(f"skip doc_id={doc_id} url={url} reason=no_chunks")
                continue

            values: list[tuple[Any, ...]] = []
            for c in chunks:
                values.append(
                    (
                        doc_id,
                        int(c["chunk_index"]),
                        c["chunk_text"],
                        c.get("section_header"),
                        int(c.get("approx_token_count") or 0),
                    )
                )

            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.executemany(
                        """
                        INSERT INTO document_chunks (
                            document_id, chunk_index, chunk_text, section_header,
                            token_count, embedding, chunk_tsvector
                        )
                        VALUES (
                            $1, $2, $3, $4,
                            $5, NULL, to_tsvector('english', $3)
                        )
                        """,
                        values,
                    )

            inserted_docs += 1
            inserted_chunks += len(values)
            print(f"chunked doc_id={doc_id} chunks={len(values)} url={url}")

        print(f"done inserted_docs={inserted_docs} inserted_chunks={inserted_chunks}")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

