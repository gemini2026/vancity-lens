"""Search examples: basic search, hybrid config, filters, search_generate (RAG)."""

from __future__ import annotations

import os

from sdk import Knowledge2, Knowledge2Error
from sdk.types.search import SearchHybridConfig

try:
    api_key = os.environ.get("K2_API_KEY")
    if not api_key:
        raise SystemExit("K2_API_KEY is required")

    client = Knowledge2(api_key=api_key)
    corpus_id = os.environ.get("K2_CORPUS_ID", "corpus-123")

    # Basic search
    basic = client.search(corpus_id, "machine learning basics", top_k=5)
    for r in basic.get("results", []):
        print((r.get("text") or "")[:80])

    # Hybrid search with TypedDict config
    hybrid_config: SearchHybridConfig = {
        "enabled": True,
        "fusion_mode": "rrf",
        "rrf_k": 60,
        "dense_weight": 0.6,
        "sparse_weight": 0.4,
    }
    hybrid = client.search(
        corpus_id,
        "neural networks",
        top_k=5,
        hybrid=hybrid_config,
        return_config={"include_text": True, "include_scores": True},
    )
    for r in hybrid.get("results", []):
        print(r.get("score"), (r.get("text") or "")[:60])

    # Search with metadata filters
    filtered = client.search(
        corpus_id,
        "API documentation",
        top_k=5,
        filters={"topic": "docs", "org": "acme"},
    )
    for r in filtered.get("results", []):
        print(r.get("chunk_id"), (r.get("text") or "")[:60])

    # RAG: search_generate returns answer + retrieval results
    rag = client.search_generate(
        corpus_id,
        "Summarize best practices for hybrid search.",
        top_k=5,
        generation={"temperature": 0.3, "max_tokens": 500},
    )
    print("Answer:", (rag.get("answer") or "")[:200])
    for r in rag.get("results", []):
        print("Source:", (r.get("text") or "")[:80])

except Knowledge2Error as e:
    print(f"API error: {e}")
    raise
