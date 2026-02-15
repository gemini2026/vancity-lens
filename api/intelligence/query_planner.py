"""
RAG-010: Multi-hop retrieval query planner for VanCity Lens.

Decomposes complex comparative queries into sub-queries, runs hybrid search
for each independently, then merges and deduplicates results before sending
to the LLM for synthesis.

Examples of multi-hop queries:
- "Compare the rezoning at 123 Main to the one at 456 Oak"
- "How do the density changes in Kitsilano compare to Mount Pleasant?"
- "What are the differences between the Broadway Plan and the Cambie Corridor Plan?"
"""

import logging
import re
from typing import List, Any, Dict

logger = logging.getLogger(__name__)

# Patterns that indicate a comparative / multi-hop query
COMPARE_PATTERNS = [
    r"\bcompare\b",
    r"\bcomparison\b",
    r"\bvs\.?\b",
    r"\bversus\b",
    r"\bdifference(?:s)?\s+between\b",
    r"\bhow\s+(?:does?|do)\s+.+\s+compare\b",
    r"\bcontrast\b",
    r"\bboth\b.+\band\b",
]

# Conjunctions that split sub-topics
SPLIT_PATTERNS = [
    r"\bcompare\s+(.+?)\s+(?:to|with|and|vs\.?)\s+(.+)",
    r"\bdifference(?:s)?\s+between\s+(.+?)\s+and\s+(.+)",
    r"(.+?)\s+vs\.?\s+(.+)",
]


def is_multi_hop(query: str) -> bool:
    """
    Detect whether a query requires multi-hop retrieval.

    Returns True if the query contains comparative language that would
    benefit from separate retrieval passes.
    """
    q_lower = query.lower()
    for pattern in COMPARE_PATTERNS:
        if re.search(pattern, q_lower):
            return True
    return False


def decompose_query(query: str) -> List[str]:
    """
    Decompose a complex query into sub-queries for independent retrieval.

    For comparative queries like "Compare X to Y", returns ["X", "Y"].
    For non-comparative queries, returns the original query as a single-element list.

    Args:
        query: The user's natural language query

    Returns:
        List of sub-query strings (1-4 items)
    """
    q_lower = query.lower().strip()

    for pattern in SPLIT_PATTERNS:
        m = re.search(pattern, q_lower)
        if m:
            parts = [p.strip() for p in m.groups() if p and p.strip()]
            if len(parts) >= 2:
                # Clean up each sub-query
                sub_queries = []
                for part in parts[:4]:  # cap at 4 sub-queries
                    # Remove trailing punctuation
                    cleaned = part.rstrip("?.!,;")
                    if cleaned:
                        sub_queries.append(cleaned)
                if sub_queries:
                    logger.info(f"Decomposed query into {len(sub_queries)} sub-queries: {sub_queries}")
                    return sub_queries

    # No decomposition possible — return original
    return [query]


async def multi_hop_search(
    db_pool: Any,
    query: str,
    api_key: str,
    search_fn: Any,
    limit_per_hop: int = 8,
    final_limit: int = 12,
    **search_kwargs,
) -> List[Dict[str, Any]]:
    """
    Run multi-hop retrieval: decompose → parallel search → merge → deduplicate.

    Args:
        db_pool: AsyncPG connection pool
        query: Original user query
        api_key: Cohere API key for embeddings
        search_fn: The hybrid_search function to call
        limit_per_hop: Results per sub-query
        final_limit: Max total results after dedup
        **search_kwargs: Extra kwargs passed to search_fn (e.g. neighborhood, date_from)

    Returns:
        Merged, deduplicated list of search result dicts
    """
    import asyncio

    sub_queries = decompose_query(query)

    if len(sub_queries) <= 1:
        # Single query — just run normal search
        return await search_fn(
            db_pool, query, api_key, limit=final_limit, **search_kwargs
        )

    # Run sub-queries in parallel
    logger.info(f"Multi-hop search: {len(sub_queries)} sub-queries")

    async def _run_sub(sq: str) -> List[Dict[str, Any]]:
        try:
            return await search_fn(
                db_pool, sq, api_key, limit=limit_per_hop, **search_kwargs
            )
        except Exception as e:
            logger.error(f"Sub-query search failed for '{sq[:50]}': {e}")
            return []

    tasks = [_run_sub(sq) for sq in sub_queries]
    results_per_hop = await asyncio.gather(*tasks)

    # Merge and deduplicate by chunk_id
    seen_ids: set = set()
    merged: List[Dict[str, Any]] = []

    for hop_results in results_per_hop:
        for result in hop_results:
            chunk_id = result.get("chunk_id")
            if chunk_id and chunk_id in seen_ids:
                continue
            if chunk_id:
                seen_ids.add(chunk_id)
            merged.append(result)

    # Sort by score descending
    merged.sort(key=lambda r: r.get("final_score", r.get("rrf_score", 0)), reverse=True)

    # Cap at final_limit
    final = merged[:final_limit]
    logger.info(
        f"Multi-hop search: {sum(len(r) for r in results_per_hop)} total results "
        f"→ {len(merged)} after dedup → {len(final)} final"
    )
    return final
