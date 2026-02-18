"""
Tavily-powered search enhancement for Vancouver development news discovery.

Uses the Tavily Search API (purpose-built for AI/RAG pipelines) to discover
new Vancouver rezoning, density, and Bill 47 TOD content across the web,
and Tavily Extract to pull structured content from discovered URLs.

Key design decisions:
- TAVILY_API_KEY is lazy-loaded (never at module level) to avoid breaking tests
- tavily-python is synchronous; calls are wrapped with asyncio.to_thread()
- Dedup uses INSERT ... ON CONFLICT (source_url) DO NOTHING
- search_depth="basic" for credit budget efficiency
"""

import asyncio
import json
import logging
import os
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

# ── Default Search Queries ────────────────────────────────────

DEFAULT_QUERIES = [
    "Vancouver rezoning application 2026",
    "Bill 47 TOD development Vancouver",
    "Vancouver density development news",
]

# Maximum results per search query
MAX_RESULTS_PER_QUERY = 10

# Number of top URLs to extract full content from per search run
MAX_EXTRACT_URLS = 5

# Search window (days)
SEARCH_DAYS = 7


# ── Lazy API Key Loading ─────────────────────────────────────


def _get_api_key() -> str:
    """
    Lazy-load Tavily API key from environment.

    Raises:
        ValueError: If TAVILY_API_KEY is not set.
    """
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise ValueError("TAVILY_API_KEY not set")
    return key


def _get_client():
    """
    Create a TavilyClient with the lazy-loaded API key.

    Returns:
        TavilyClient instance.
    """
    from tavily import TavilyClient

    return TavilyClient(api_key=_get_api_key())


# ── Search Functions ─────────────────────────────────────────


async def search_web(
    queries: Optional[List[str]] = None,
    max_results: int = MAX_RESULTS_PER_QUERY,
    days: int = SEARCH_DAYS,
) -> List[Dict[str, Any]]:
    """
    Run Tavily search queries and return aggregated results.

    Args:
        queries: Search query strings. Defaults to DEFAULT_QUERIES.
        max_results: Max results per query.
        days: Only return results from the last N days.

    Returns:
        List of result dicts with keys: title, url, content, published_date.
    """
    if queries is None:
        queries = DEFAULT_QUERIES

    client = _get_client()
    all_results: List[Dict[str, Any]] = []
    seen_urls: set = set()

    for query in queries:
        try:
            logger.info("Tavily search: %s", query)
            # tavily-python is synchronous -- run in thread pool
            response = await asyncio.to_thread(
                client.search,
                query=query,
                search_depth="basic",
                max_results=max_results,
                days=days,
            )

            results = response.get("results", [])
            logger.info(
                "Tavily search returned %d results for: %s", len(results), query
            )

            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(
                        {
                            "title": r.get("title", ""),
                            "url": url,
                            "content": r.get("content", ""),
                            "published_date": r.get("published_date"),
                            "query": query,
                        }
                    )

        except Exception as e:
            logger.error("Tavily search error for query '%s': %s", query, e)

    return all_results


async def extract_content(urls: List[str]) -> Dict[str, str]:
    """
    Use Tavily Extract to get full markdown content from URLs.

    Args:
        urls: List of URLs to extract content from.

    Returns:
        Dict mapping url -> raw_content (markdown text).
    """
    if not urls:
        return {}

    client = _get_client()
    extracted: Dict[str, str] = {}

    try:
        logger.info("Tavily extract: %d URLs", len(urls))
        response = await asyncio.to_thread(
            client.extract,
            urls=urls,
        )

        for r in response.get("results", []):
            url = r.get("url", "")
            raw = r.get("raw_content", "")
            if url and raw:
                extracted[url] = raw

        logger.info(
            "Tavily extract returned content for %d/%d URLs", len(extracted), len(urls)
        )

    except Exception as e:
        logger.error("Tavily extract error: %s", e)

    return extracted


# ── Database Storage ─────────────────────────────────────────


async def store_document(
    conn: asyncpg.Connection,
    url: str,
    title: str,
    content: str,
    published_date: Optional[date],
    source_query: str,
) -> bool:
    """
    Store a discovered document, skipping duplicates via ON CONFLICT.

    Args:
        conn: asyncpg connection.
        url: Source URL (unique key).
        title: Document title.
        content: Full text content.
        published_date: Published date (may be None).
        source_query: The search query that found this document.

    Returns:
        True if document was inserted (new), False if duplicate.
    """
    result = await conn.execute(
        """
        INSERT INTO documents (
            source_type, source_url, title, published_date,
            raw_text, text_length, file_format, metadata,
            scraped_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (source_url) DO NOTHING
        """,
        "tavily_search",
        url,
        title,
        published_date,
        content,
        len(content) if content else 0,
        "html",
        json.dumps(
            {
                "source": "tavily",
                "search_query": source_query,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        datetime.now(timezone.utc),
    )
    # asyncpg execute returns command tag like "INSERT 0 1" or "INSERT 0 0"
    return result == "INSERT 0 1"


# ── Main Orchestrator ────────────────────────────────────────


async def search_and_store(
    pool: asyncpg.Pool,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    queries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Main entry point: search for Vancouver development content, extract full
    text from top URLs, and store new documents.

    Compatible with the ScraperScheduler interface:
        async func(pool, start_date, end_date) -> dict

    Args:
        pool: asyncpg connection pool.
        start_date: Not used directly (Tavily uses days param). Accepted for
                    scheduler interface compatibility.
        end_date: Not used directly. Accepted for scheduler compatibility.
        queries: Optional custom search queries. Defaults to DEFAULT_QUERIES.

    Returns:
        Dict with counts:
            searched: number of queries executed
            urls_found: total unique URLs discovered
            new_documents: documents successfully inserted
            duplicates_skipped: documents skipped due to existing source_url
            documents_found: alias for urls_found (scheduler compat)
            documents_new: alias for new_documents (scheduler compat)
            documents_skipped: alias for duplicates_skipped (scheduler compat)
    """
    if queries is None:
        queries = DEFAULT_QUERIES

    stats = {
        "searched": 0,
        "urls_found": 0,
        "new_documents": 0,
        "duplicates_skipped": 0,
    }

    # ── Step 1: Check API key availability ────────────────────
    try:
        _get_api_key()
    except ValueError:
        logger.warning(
            "TAVILY_API_KEY not set — skipping Tavily search. "
            "Set the environment variable to enable web search."
        )
        return {
            **stats,
            "documents_found": 0,
            "documents_new": 0,
            "documents_skipped": 0,
        }

    # ── Step 2: Run search queries ────────────────────────────
    try:
        search_results = await search_web(queries=queries)
    except Exception as e:
        logger.error("Tavily search_web failed: %s", e)
        return {
            **stats,
            "documents_found": 0,
            "documents_new": 0,
            "documents_skipped": 0,
        }

    stats["searched"] = len(queries)
    stats["urls_found"] = len(search_results)

    if not search_results:
        logger.info("Tavily search returned no results")
        return {
            **stats,
            "documents_found": 0,
            "documents_new": 0,
            "documents_skipped": 0,
        }

    # ── Step 3: Extract full content from top URLs ────────────
    top_urls = [r["url"] for r in search_results[:MAX_EXTRACT_URLS]]

    try:
        extracted = await extract_content(top_urls)
    except Exception as e:
        logger.error("Tavily extract_content failed: %s", e)
        extracted = {}

    # ── Step 4: Store to database ─────────────────────────────
    async with pool.acquire() as conn:
        for result in search_results:
            url = result["url"]
            title = result.get("title", "")
            # Use extracted full content if available, otherwise use search snippet
            content = extracted.get(url, result.get("content", ""))

            # Parse published date
            pub_date = None
            raw_date = result.get("published_date")
            if raw_date:
                try:
                    # Tavily returns ISO format dates
                    pub_date = date.fromisoformat(raw_date[:10])
                except (ValueError, TypeError):
                    pass

            try:
                is_new = await store_document(
                    conn=conn,
                    url=url,
                    title=title,
                    content=content,
                    published_date=pub_date,
                    source_query=result.get("query", ""),
                )
                if is_new:
                    stats["new_documents"] += 1
                else:
                    stats["duplicates_skipped"] += 1
            except Exception as e:
                logger.error("Error storing document %s: %s", url, e)
                stats["duplicates_skipped"] += 1

    logger.info(
        "Tavily search_and_store complete: %d searched, %d found, %d new, %d skipped",
        stats["searched"],
        stats["urls_found"],
        stats["new_documents"],
        stats["duplicates_skipped"],
    )

    # Return with scheduler-compatible aliases
    return {
        **stats,
        "documents_found": stats["urls_found"],
        "documents_new": stats["new_documents"],
        "documents_skipped": stats["duplicates_skipped"],
    }


# ── CLI entrypoint for K8s CronJob ─────────────────────────────────
if __name__ == "__main__":
    import asyncio
    import asyncpg
    import json
    import sys

    async def main():
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set")
            sys.exit(1)

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
        try:
            result = await search_and_store(pool)
            print(json.dumps(result, indent=2, default=str))
            if result.get("new_documents", 0) > 0:
                logger.info(
                    "Tavily CronJob success: %d new documents", result["new_documents"]
                )
        finally:
            await pool.close()

    asyncio.run(main())
