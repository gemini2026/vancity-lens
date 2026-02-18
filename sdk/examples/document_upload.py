"""Document upload: single file, batch raw_text, URL ingestion. Shows wait=True pattern."""

from __future__ import annotations

import os

from sdk import Knowledge2, Knowledge2Error

try:
    api_key = os.environ.get("K2_API_KEY")
    if not api_key:
        raise SystemExit("K2_API_KEY is required")

    client = Knowledge2(api_key=api_key)
    corpus_id = os.environ.get("K2_CORPUS_ID", "corpus-123")

    # Single upload via file_path
    resp = client.upload_document(
        corpus_id,
        file_path="/path/to/doc.pdf",
        source_uri="doc://my-file",
        idempotency_key="upload-1",
    )
    print("Uploaded:", resp.get("doc_id"))

    # Batch upload raw_text list (wait=True blocks until job completes)
    docs = [
        {"source_uri": "doc://a", "raw_text": "First document content."},
        {"source_uri": "doc://b", "raw_text": "Second document content."},
    ]
    batch_resp = client.upload_documents_batch(
        corpus_id,
        docs,
        idempotency_key="batch-1",
        wait=True,
        poll_s=5,
    )
    print("Batch job:", batch_resp.get("job_id"))

    # URL ingestion with wait=True
    urls = [
        {"url": "https://example.com/page1", "title": "Page 1"},
        {"url": "https://example.com/page2", "title": "Page 2"},
    ]
    url_resp = client.ingest_urls(
        corpus_id,
        urls,
        idempotency_key="urls-1",
        wait=True,
        poll_s=5,
    )
    print("URL ingest job:", url_resp.get("job_id"))

except Knowledge2Error as e:
    print(f"API error: {e}")
    raise
