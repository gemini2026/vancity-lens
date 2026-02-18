"""
K2 Document Sync - Upload PostgreSQL documents to Knowledge2 corpus.

This module syncs documents from the local PostgreSQL database to the K2 corpus
used for RAG retrieval. It handles:
- Batch uploads (up to 100 docs per batch for efficiency)
- Idempotency via source_url tracking (K2 deduplicates by source_uri)
- Progress tracking via metadata column
- Chunking strategy configuration

Usage:
    # Sync all unsynced documents
    python -m api.intelligence.k2_sync

    # Force re-sync all documents
    python -m api.intelligence.k2_sync --force

    # Dry run (show what would be synced)
    python -m api.intelligence.k2_sync --dry-run

Design decisions:
- Uses document.source_url as K2 source_uri for deduplication
- Batch size: 100 (K2 batch upload limit)
- Tracks sync status in document.metadata['k2_synced']
- Auto-indexes after batch upload for immediate RAG availability
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg
from sdk import Knowledge2

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Batch size for K2 uploads (K2 supports up to 100 docs per batch)
BATCH_SIZE = 100

# Chunking strategy for K2
DEFAULT_CHUNKING = {
    "strategy": "semantic",  # semantic, fixed_size, or sentence
    "chunk_size": 512,  # tokens per chunk
    "overlap": 50,  # token overlap between chunks
}


def _get_env_required(name: str) -> str:
    """Get required environment variable or raise."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is required")
    return value


def get_k2_client() -> Knowledge2:
    """Build K2 client from environment variables."""
    api_host = (
        os.environ.get("K2_API_HOST", "https://api-dev.knowledge2.ai")
        .strip()
        .rstrip("/")
    )
    api_key = _get_env_required("K2_API_KEY")

    return Knowledge2(
        api_host=api_host,
        api_key=api_key,
        timeout=60.0,  # Longer timeout for batch uploads
    )


async def get_documents_to_sync(
    pool: asyncpg.Pool, *, force: bool = False, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Fetch documents from PostgreSQL that need to be synced to K2.

    Args:
        pool: asyncpg connection pool
        force: If True, return all documents (ignore sync status)
        limit: Optional limit on number of documents to fetch

    Returns:
        List of document dicts with fields needed for K2 upload
    """
    # Build query based on force flag
    if force:
        where_clause = "TRUE"
    else:
        # Only sync docs that haven't been synced yet
        where_clause = (
            "(metadata->>'k2_synced' IS NULL OR metadata->>'k2_synced' = 'false')"
        )

    limit_clause = f"LIMIT {limit}" if limit else ""

    query = f"""
        SELECT
            id,
            source_type,
            source_url,
            title,
            published_date,
            raw_text,
            metadata,
            scraped_at
        FROM documents
        WHERE {where_clause}
        ORDER BY scraped_at DESC
        {limit_clause}
    """

    rows = await pool.fetch(query)

    documents = []
    for row in rows:
        # Parse metadata JSON if it's a string (asyncpg returns JSONB as string)
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        elif metadata is None:
            metadata = {}

        documents.append(
            {
                "id": row["id"],
                "source_type": row["source_type"],
                "source_url": row["source_url"],
                "title": row["title"],
                "published_date": row["published_date"],
                "raw_text": row["raw_text"],
                "metadata": metadata,
                "scraped_at": row["scraped_at"],
            }
        )

    return documents


def format_for_k2(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a PostgreSQL document for K2 batch upload.

    Args:
        doc: Document dict from PostgreSQL

    Returns:
        K2-formatted document dict
    """
    # Build metadata for K2 (preserve original metadata + add tracking fields)
    k2_metadata = {
        "source_type": doc["source_type"],
        "title": doc["title"],
        "published_date": doc["published_date"].isoformat()
        if doc["published_date"]
        else None,
        "scraped_at": doc["scraped_at"].isoformat() if doc["scraped_at"] else None,
        "postgres_id": doc["id"],
    }

    # Merge with original metadata (but don't override postgres_id)
    if doc["metadata"]:
        k2_metadata.update(
            {k: v for k, v in doc["metadata"].items() if k != "postgres_id"}
        )

    # Sanitize source_url - remove newlines and whitespace that break K2 API
    source_url = doc["source_url"] or ""
    source_url = source_url.replace("\n", "").replace("\r", "").strip()

    # Sanitize raw_text - K2 API requires single-line text (newlines cause "Invalid non-printable ASCII character" error)
    raw_text = doc["raw_text"] or ""
    raw_text = raw_text.replace("\n", " ").replace("\r", " ").strip()

    return {
        "raw_text": raw_text,
        "source_uri": source_url,  # K2 uses this for deduplication
        "metadata": k2_metadata,
    }


async def mark_as_synced(pool: asyncpg.Pool, document_ids: List[int]) -> None:
    """
    Mark documents as synced to K2 in PostgreSQL.

    Updates metadata->>'k2_synced' = 'true' and adds k2_synced_at timestamp.

    Args:
        pool: asyncpg connection pool
        document_ids: List of document IDs to mark as synced
    """
    if not document_ids:
        return

    synced_at = datetime.now(timezone.utc).isoformat()

    await pool.execute(
        """
        UPDATE documents
        SET metadata = COALESCE(metadata, '{}'::jsonb) ||
            jsonb_build_object('k2_synced', 'true', 'k2_synced_at', $1)
        WHERE id = ANY($2)
        """,
        synced_at,
        document_ids,
    )


async def sync_to_k2(
    pool: asyncpg.Pool,
    *,
    force: bool = False,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Main sync orchestrator - fetch documents from PostgreSQL and upload to K2.

    Args:
        pool: asyncpg connection pool
        force: If True, re-sync all documents (ignore sync status)
        dry_run: If True, show what would be synced but don't actually upload
        limit: Optional limit on number of documents to process

    Returns:
        Stats dict with counts of documents processed
    """
    corpus_id = _get_env_required("K2_CORPUS_ID")

    logger.info(
        "Starting K2 sync (force=%s, dry_run=%s, limit=%s)", force, dry_run, limit
    )

    # Fetch documents to sync
    documents = await get_documents_to_sync(pool, force=force, limit=limit)

    if not documents:
        logger.info("No documents to sync")
        return {
            "documents_fetched": 0,
            "documents_uploaded": 0,
            "batches": 0,
        }

    logger.info("Fetched %d documents to sync", len(documents))

    if dry_run:
        logger.info("DRY RUN - would sync %d documents:", len(documents))
        for doc in documents[:10]:
            logger.info(
                "  [%d] %s (%s)", doc["id"], doc["title"][:60], doc["source_type"]
            )
        if len(documents) > 10:
            logger.info("  ... and %d more", len(documents) - 10)
        return {
            "documents_fetched": len(documents),
            "documents_uploaded": 0,
            "batches": 0,
            "dry_run": True,
        }

    # Build K2 client
    k2_client = get_k2_client()

    # Upload in batches
    total_uploaded = 0
    batch_count = 0

    for i in range(0, len(documents), BATCH_SIZE):
        batch = documents[i : i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1

        logger.info(
            "Uploading batch %d/%d (%d documents)...",
            batch_num,
            (len(documents) + BATCH_SIZE - 1) // BATCH_SIZE,
            len(batch),
        )

        # Format for K2
        k2_batch = []
        for doc in batch:
            try:
                formatted = format_for_k2(doc)

                # Check for newlines in all string fields
                issues = []
                if "\n" in formatted.get("source_uri", "") or "\r" in formatted.get(
                    "source_uri", ""
                ):
                    issues.append(
                        f"source_uri has newlines: {formatted['source_uri'][:100]!r}"
                    )
                if "\n" in formatted.get("raw_text", "") or "\r" in formatted.get(
                    "raw_text", ""
                ):
                    issues.append(
                        f"raw_text has newlines (len={len(formatted.get('raw_text', ''))})"
                    )

                # Check metadata fields
                metadata = formatted.get("metadata", {})
                for key, value in metadata.items():
                    if isinstance(value, str) and ("\n" in value or "\r" in value):
                        issues.append(f"metadata.{key} has newlines: {value[:100]!r}")

                if issues:
                    logger.warning(
                        "Document %d has newline issues: %s",
                        doc["id"],
                        "; ".join(issues),
                    )

                k2_batch.append(formatted)
            except Exception as e:
                logger.error(
                    "Failed to format document %d (%s): %s",
                    doc["id"],
                    doc.get("title", "")[:50],
                    e,
                )
                continue

        if not k2_batch:
            logger.warning(
                "Batch %d: No documents to upload after formatting", batch_num
            )
            continue

        # Upload batch to K2
        try:
            # Log first document in batch for debugging
            if k2_batch:
                import json as json_lib

                logger.info(
                    "First document in batch:\n%s",
                    json_lib.dumps(k2_batch[0], indent=2, default=str)[:1000],
                )

                # Check for invisible characters in source_uri around position 48
                source_uri = k2_batch[0].get("source_uri", "")
                if len(source_uri) > 40:
                    snippet = source_uri[40:60]
                    hex_dump = " ".join(f"{ord(c):02x}" for c in snippet)
                    logger.info("source_uri[40:60] = %r (hex: %s)", snippet, hex_dump)

            # Try uploading just the first document to isolate the issue
            logger.info("Attempting single-document upload for debugging...")
            try:
                single_doc_response = k2_client.upload_documents_batch(
                    corpus_id=corpus_id,
                    documents=[k2_batch[0]] if k2_batch else [],
                    chunking=DEFAULT_CHUNKING,
                    auto_index=True,
                    wait=True,
                    poll_s=5,
                )
                logger.info(
                    "Single-document upload succeeded! Response: %s",
                    single_doc_response,
                )
            except Exception as single_err:
                logger.error("Single-document upload also failed: %s", single_err)

            response = k2_client.upload_documents_batch(
                corpus_id=corpus_id,
                documents=k2_batch,
                chunking=DEFAULT_CHUNKING,
                auto_index=True,  # Auto-index for immediate RAG availability
                wait=True,  # Wait for indexing to complete
                poll_s=5,  # Poll every 5 seconds
            )

            logger.info(
                "Batch %d uploaded successfully (document_id=%s, status=%s)",
                batch_num,
                response.get("document_id"),
                response.get("status"),
            )

            # Mark as synced in PostgreSQL
            doc_ids = [doc["id"] for doc in batch]
            await mark_as_synced(pool, doc_ids)

            total_uploaded += len(batch)
            batch_count += 1

        except Exception as e:
            logger.error("Failed to upload batch %d: %s", batch_num, e)
            logger.error(
                "Sample document from batch: source_uri=%r",
                k2_batch[0].get("source_uri", "")[:100] if k2_batch else "N/A",
            )
            # Continue with next batch rather than failing entirely
            continue

    logger.info(
        "Sync complete: %d documents uploaded in %d batches",
        total_uploaded,
        batch_count,
    )

    return {
        "documents_fetched": len(documents),
        "documents_uploaded": total_uploaded,
        "batches": batch_count,
    }


# ── CLI entrypoint ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync PostgreSQL documents to K2 corpus"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-sync all documents (ignore sync status)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without actually uploading",
    )
    parser.add_argument(
        "--limit", type=int, help="Limit number of documents to process"
    )

    args = parser.parse_args()

    async def main():
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL environment variable is required")
            sys.exit(1)

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
        try:
            stats = await sync_to_k2(
                pool, force=args.force, dry_run=args.dry_run, limit=args.limit
            )

            # Print results as JSON for easy parsing
            print(json.dumps(stats, indent=2, default=str))

            # Exit with success only if we uploaded everything we fetched
            if stats.get("dry_run"):
                sys.exit(0)

            if stats["documents_uploaded"] < stats["documents_fetched"]:
                logger.warning("Some documents failed to upload")
                sys.exit(1)

            sys.exit(0)

        finally:
            await pool.close()

    asyncio.run(main())
