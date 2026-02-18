"""Pagination: iter_documents vs list_documents manual pagination, iter with filters."""

from __future__ import annotations

import os

from sdk import Knowledge2, Knowledge2Error

try:
    api_key = os.environ.get("K2_API_KEY")
    if not api_key:
        raise SystemExit("K2_API_KEY is required")

    client = Knowledge2(api_key=api_key)
    corpus_id = os.environ.get("K2_CORPUS_ID", "corpus-123")

    # Manual pagination with list_documents
    offset = 0
    limit = 20
    while True:
        page = client.list_documents(corpus_id, limit=limit, offset=offset)
        docs = page.get("documents", [])
        if not docs:
            break
        for doc in docs:
            print(doc.get("id"), doc.get("source_uri", ""))
        offset += len(docs)
        if len(docs) < limit:
            break

    # iter_documents: lazy iteration over all documents
    for item in client.iter_documents(corpus_id, limit=50):
        print(item.get("id"), item.get("source_uri", ""))

    # iter_documents with filters
    for item in client.iter_documents(
        corpus_id,
        limit=50,
        status="indexed",
        source="doc://",
    ):
        print(item.get("id"))

    # Collect all items into a list
    all_docs = list(client.iter_documents(corpus_id, limit=100))
    print(f"Total documents: {len(all_docs)}")

except Knowledge2Error as e:
    print(f"API error: {e}")
    raise
