#!/usr/bin/env python3
"""Print K2 corpus status (resolves name -> id).

Usage:
  K2_API_HOST=https://api-dev.knowledge2.ai \
  K2_API_KEY=... \
  K2_CORPUS_ID=vancity \
  python3 migration/k2_corpus_status.py
"""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from sdk import Knowledge2  # noqa: E402


def _require_env(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise SystemExit(f"Missing required env var: {name}")
    return v


def _resolve_corpus_id(client: Knowledge2, corpus_ref: str) -> str:
    corpus_ref = corpus_ref.strip()
    corpora = (client.list_corpora(limit=200, offset=0) or {}).get("corpora") or []
    for c in corpora:
        if c.get("id") == corpus_ref:
            return corpus_ref
    matches = [c for c in corpora if c.get("name") == corpus_ref and c.get("id")]
    if len(matches) == 1:
        return matches[0]["id"]
    if len(matches) > 1:
        raise SystemExit(f"Ambiguous corpus name '{corpus_ref}'. Set K2_CORPUS_ID to the corpus UUID.")
    raise SystemExit(f"Corpus not found: '{corpus_ref}'")


def main() -> int:
    api_host = (os.environ.get("K2_API_HOST") or "https://api-dev.knowledge2.ai").strip().rstrip("/")
    api_key = _require_env("K2_API_KEY")
    corpus_ref = _require_env("K2_CORPUS_ID")

    client = Knowledge2(api_host=api_host, api_key=api_key)
    corpus_id = _resolve_corpus_id(client, corpus_ref)

    status = client.get_corpus_status(corpus_id)
    print(f"corpus_ref={corpus_ref}")
    print(f"corpus_id={corpus_id}")
    for k in ["status", "ingesting", "indexing", "document_count", "documents_processing", "dense_status", "sparse_status"]:
        if k in status:
            print(f"{k}={status.get(k)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

