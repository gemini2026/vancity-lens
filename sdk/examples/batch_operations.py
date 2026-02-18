"""Batch workflow: upload multiple docs, build indexes with wait, batch search, iterate results."""

from __future__ import annotations

import os

from sdk import Knowledge2, Knowledge2Error

try:
    api_key = os.environ.get("K2_API_KEY")
    if not api_key:
        raise SystemExit("K2_API_KEY is required")

    client = Knowledge2(api_key=api_key)
    corpus_id = os.environ.get("K2_CORPUS_ID", "corpus-123")

    # Upload multiple documents with idempotency key
    docs = [
        {"source_uri": "doc://a", "raw_text": "Content A."},
        {"source_uri": "doc://b", "raw_text": "Content B."},
        {"source_uri": "doc://c", "raw_text": "Content C."},
    ]
    upload = client.upload_documents_batch(
        corpus_id,
        docs,
        idempotency_key="batch-demo-abc123",
        wait=True,
    )
    print("Upload job:", upload.get("job_id"))

    # Build indexes with wait and idempotency
    index_job = client.build_indexes(
        corpus_id,
        dense=True,
        sparse=True,
        mode="full",
        idempotency_key="index-demo-abc123",
        wait=True,
    )
    print("Index job:", index_job.get("job_id"))

    # Batch search multiple queries
    queries = ["What is A?", "What is B?", "What is C?"]
    batch = client.search_batch(
        corpus_id,
        queries,
        top_k=3,
        return_config={"include_text": True},
    )
    for i, resp in enumerate(batch.get("responses", [])):
        print(f"Query {i + 1}: {queries[i]}")
        for r in resp.get("results", []):
            print("  ", (r.get("text") or "")[:60])

except Knowledge2Error as e:
    print(f"API error: {e}")
    raise
