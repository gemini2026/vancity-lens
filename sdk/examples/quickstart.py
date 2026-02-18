"""Minimal example: create client, project, corpus, upload document, build indexes, search."""

from __future__ import annotations

import os

from sdk import Knowledge2, Knowledge2Error

try:
    api_key = os.environ.get("K2_API_KEY")
    if not api_key:
        raise SystemExit("K2_API_KEY is required")

    client = Knowledge2(
        api_host=os.environ.get("K2_BASE_URL", "https://api.knowledge2.ai"),
        api_key=api_key,
    )

    project = client.create_project("quickstart-demo")
    corpus = client.create_corpus(project["id"], "quickstart-corpus")

    client.upload_document(
        corpus["id"],
        raw_text="Knowledge2 enables semantic search over your documents.",
        source_uri="doc://intro",
    )

    client.build_indexes(corpus["id"], dense=True, sparse=True, wait=True)

    results = client.search(corpus["id"], "What does Knowledge2 do?", top_k=5)
    for r in results.get("results", []):
        print((r.get("text") or "")[:80])

except Knowledge2Error as e:
    print(f"API error: {e}")
    raise
