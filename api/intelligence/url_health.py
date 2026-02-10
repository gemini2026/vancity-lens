"""
URL health checker for VanCity Lens documents (RAG-002 + RAG-003).

Checks source_url liveness via async HEAD requests, updates url_status,
and auto-generates Internet Archive (Wayback Machine) fallback URLs
for dead links.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import asyncpg

logger = logging.getLogger(__name__)

# Statuses: alive, dead, redirect, timeout, unchecked
ALIVE = "alive"
DEAD = "dead"
REDIRECT = "redirect"
TIMEOUT = "timeout"
UNCHECKED = "unchecked"

HEAD_TIMEOUT = 15  # seconds per URL
MAX_CONCURRENCY = 10  # parallel HEAD requests
WAYBACK_PREFIX = "https://web.archive.org/web/"


def build_archive_url(source_url: str) -> str:
    """Build an Internet Archive Wayback Machine URL."""
    return f"{WAYBACK_PREFIX}{source_url}"


async def check_single_url(
    session: aiohttp.ClientSession,
    url: str,
) -> tuple[str, Optional[str]]:
    """
    HEAD-check a single URL.

    Returns:
        (status, final_url) where status is alive/dead/redirect/timeout
        and final_url is the redirect target if status is redirect.
    """
    try:
        async with session.head(
            url,
            allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=HEAD_TIMEOUT),
        ) as resp:
            if 200 <= resp.status < 400:
                if 300 <= resp.status < 400:
                    location = resp.headers.get("Location", "")
                    return REDIRECT, location
                return ALIVE, None
            elif resp.status in (404, 410, 451):
                return DEAD, None
            else:
                # Treat other errors (403, 500, etc.) as alive but inaccessible
                # — the resource exists, just can't be reached
                return ALIVE, None
    except asyncio.TimeoutError:
        return TIMEOUT, None
    except (aiohttp.ClientError, Exception) as e:
        logger.debug(f"URL check failed for {url}: {e}")
        return DEAD, None


async def check_document_urls(
    db_pool: asyncpg.Pool,
    limit: int = 100,
    recheck_hours: int = 24,
) -> dict:
    """
    Check source URLs for documents and update their status.

    Args:
        db_pool: Database connection pool
        limit: Max documents to check per run
        recheck_hours: Skip URLs checked within this window

    Returns:
        Stats dict with counts of alive, dead, redirect, timeout, errors
    """
    stats = {"checked": 0, "alive": 0, "dead": 0, "redirect": 0, "timeout": 0, "errors": 0}

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, source_url FROM documents
            WHERE url_status = 'unchecked'
               OR url_checked_at IS NULL
               OR url_checked_at < NOW() - ($1 || ' hours')::interval
            ORDER BY url_checked_at ASC NULLS FIRST
            LIMIT $2
            """,
            str(recheck_hours),
            limit,
        )

    if not rows:
        logger.info("No URLs to check")
        return stats

    logger.info(f"Checking {len(rows)} document URLs")

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    now = datetime.now(timezone.utc)

    async def _check_and_update(doc_id: int, url: str):
        async with semaphore:
            try:
                async with aiohttp.ClientSession() as session:
                    status, _ = await check_single_url(session, url)

                archive_url = None
                if status == DEAD:
                    archive_url = build_archive_url(url)

                async with db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE documents
                        SET url_status = $1,
                            url_checked_at = $2,
                            archive_url = COALESCE($3, archive_url)
                        WHERE id = $4
                        """,
                        status,
                        now,
                        archive_url,
                        doc_id,
                    )

                stats[status] = stats.get(status, 0) + 1
                stats["checked"] += 1

            except Exception as e:
                logger.error(f"Error checking URL for doc {doc_id}: {e}")
                stats["errors"] += 1

    tasks = [_check_and_update(row["id"], row["source_url"]) for row in rows]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(f"URL health check complete: {stats}")
    return stats


async def get_document_url_status(
    db_pool: asyncpg.Pool,
    document_id: int,
) -> dict:
    """Get URL health info for a single document."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT source_url, url_status, url_checked_at, archive_url
            FROM documents WHERE id = $1
            """,
            document_id,
        )

    if not row:
        return {}

    return {
        "source_url": row["source_url"],
        "url_status": row["url_status"] or UNCHECKED,
        "url_checked_at": row["url_checked_at"],
        "archive_url": row["archive_url"],
    }
