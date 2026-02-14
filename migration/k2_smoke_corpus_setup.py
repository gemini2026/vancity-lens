#!/usr/bin/env python3
"""Create (or reuse) a tiny K2 corpus for end-to-end smoke validation.

This is intentionally small and safe: it uploads a couple of short raw-text
documents with metadata and builds indexes so searches can succeed.

Usage:
  K2_API_HOST=https://api-dev.knowledge2.ai \
  K2_API_KEY=... \
  python3 migration/k2_smoke_corpus_setup.py

Output:
  Prints `K2_CORPUS_ID=<id>` to stdout on success.
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from sdk import Knowledge2, Knowledge2Error  # noqa: E402


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def _first_by_name(items: list[dict], name: str) -> dict | None:
    for item in items:
        if item.get("name") == name:
            return item
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap a K2 smoke-test corpus.")
    parser.add_argument("--project-name", default="bill47-smoke", help="K2 project name to create/use")
    parser.add_argument("--corpus-name", default="bill47-smoke", help="K2 corpus name to create/use")
    parser.add_argument(
        "--query",
        default="transit-oriented development",
        help="Query to validate search after indexing",
    )
    args = parser.parse_args()

    api_host = (os.environ.get("K2_API_HOST") or "https://api-dev.knowledge2.ai").strip().rstrip("/")
    api_key = _require_env("K2_API_KEY")

    client = Knowledge2(api_host=api_host, api_key=api_key)

    projects = client.list_projects(limit=100, offset=0).get("projects", [])
    project = _first_by_name(projects, args.project_name)
    if project is None:
        project = client.create_project(args.project_name)

    corpora = client.list_corpora(limit=100, offset=0).get("corpora", [])
    corpus = None
    for c in corpora:
        if c.get("name") == args.corpus_name and c.get("project_id") == project["id"]:
            corpus = c
            break
    if corpus is None:
        corpus = client.create_corpus(
            project["id"],
            args.corpus_name,
            description="Bill47 smoke-test corpus (auto-created by migration harness).",
        )

    corpus_id = corpus["id"]

    docs = [
        {
            "raw_text": (
                "Bill 47 enables transit-oriented development (TOD) near qualifying stations. "
                "Due diligence includes zoning checks, OCP review, and community opposition risk."
            ),
            "source_uri": "bill47://smoke/doc1",
            "metadata": {
                "title": "Bill47 Smoke Doc 1",
                "source_url": "https://example.com/bill47-smoke/doc1",
                "source_type": "smoke",
                "published_date": "2024-01-02",
                "section_header": "Overview",
            },
        },
        {
            "raw_text": (
                "In Vancouver, station-area plans and zoning bylaws can change density allowances. "
                "Monitor council minutes and rezoning applications for pipeline signals."
            ),
            "source_uri": "bill47://smoke/doc2",
            "metadata": {
                "title": "Bill47 Smoke Doc 2",
                "source_url": "https://example.com/bill47-smoke/doc2",
                "source_type": "smoke",
                "published_date": "2024-02-10",
                "section_header": "Signals",
            },
        },
    ]

    # Upload (idempotency is best-effort via stable source_uri values).
    client.upload_documents_batch(corpus_id, docs, auto_index=False, wait=True, poll_s=2)

    # Build both sparse + dense indexes so hybrid search is available.
    client.build_indexes(corpus_id, dense=True, sparse=True, mode="full", wait=True, poll_s=2)

    # Verify search works (raises on HTTP errors).
    result = client.search(
        corpus_id=corpus_id,
        query=args.query,
        top_k=3,
        return_config={"include_text": True, "include_scores": True, "include_provenance": True},
    )
    if not (result.get("results") or []):
        raise SystemExit("Search returned 0 results; corpus may not be indexed yet.")

    print(f"K2_CORPUS_ID={corpus_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Knowledge2Error as exc:
        print(f"K2 API error: {exc}", file=sys.stderr)
        if "Org-wide API key" in str(exc):
            print(
                "Hint: this API key cannot create projects/corpora. "
                "Ask K2 to provision a corpus and share its corpus_id (or provide an org-wide API key).",
                file=sys.stderr,
            )
        raise SystemExit(2)
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
