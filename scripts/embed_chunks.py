#!/usr/bin/env python3
"""
Backfill Cohere embeddings for document chunks that have NULL embeddings.

Requires a Cohere API key. Run after seed_chunks.py to enable full hybrid
search (dense + sparse).

Usage:
    python scripts/embed_chunks.py --cohere-key KEY [--database-url URL] [--batch-size 96]
"""

import argparse
import asyncio
import logging
import os
import sys

# Add project root to path so we can import api modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

from api.intelligence.local_rag.embeddings import batch_embed, EMBEDDING_DIMENSION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)


async def embed_null_chunks(
    database_url: str,
    cohere_api_key: str,
    batch_size: int = 96,
):
    """Backfill embeddings for chunks where embedding IS NULL."""
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)

    try:
        # Count total work
        async with pool.acquire() as conn:
            total_null = await conn.fetchval(
                "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NULL"
            )
            total_all = await conn.fetchval("SELECT COUNT(*) FROM document_chunks")

        logger.info(f"Chunks total: {total_all}, without embeddings: {total_null}")

        if total_null == 0:
            logger.info("All chunks already have embeddings. Nothing to do.")
            return

        # Process in batches
        embedded_count = 0
        offset = 0

        while True:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, chunk_text
                    FROM document_chunks
                    WHERE embedding IS NULL
                    ORDER BY id
                    LIMIT $1
                    """,
                    batch_size,
                )

            if not rows:
                break

            chunk_ids = [r["id"] for r in rows]
            chunk_texts = [r["chunk_text"] for r in rows]

            logger.info(
                f"Embedding batch {offset // batch_size + 1}: "
                f"{len(rows)} chunks (IDs {chunk_ids[0]}-{chunk_ids[-1]})"
            )

            try:
                embeddings = await batch_embed(
                    chunk_texts,
                    cohere_api_key,
                    input_type="search_document",
                    batch_size=batch_size,
                )
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                logger.info("Stopping. Re-run to continue from where we left off.")
                break

            if len(embeddings) != len(rows):
                logger.error(
                    f"Embedding count mismatch: {len(embeddings)} vs {len(rows)} chunks"
                )
                break

            # Update each chunk with its embedding
            async with pool.acquire() as conn:
                for chunk_id, embedding in zip(chunk_ids, embeddings):
                    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                    await conn.execute(
                        "UPDATE document_chunks SET embedding = $1::vector WHERE id = $2",
                        embedding_str,
                        chunk_id,
                    )

            embedded_count += len(rows)
            offset += batch_size
            logger.info(f"  Progress: {embedded_count}/{total_null} chunks embedded")

        # Final stats
        async with pool.acquire() as conn:
            remaining = await conn.fetchval(
                "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NULL"
            )
            with_emb = await conn.fetchval(
                "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL"
            )

        logger.info(f"\nDone: {embedded_count} chunks embedded this run")
        logger.info(f"Total with embeddings: {with_emb}")
        logger.info(f"Remaining without embeddings: {remaining}")

    finally:
        await pool.close()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill Cohere embeddings for document chunks"
    )
    parser.add_argument(
        "--cohere-key",
        default=os.environ.get("COHERE_API_KEY"),
        help="Cohere API key (or set COHERE_API_KEY env var)",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "postgresql://localhost:5432/bill47"),
        help="PostgreSQL connection URL",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=96,
        help="Texts per Cohere API call (max 96)",
    )
    args = parser.parse_args()

    if not args.cohere_key:
        print("ERROR: Cohere API key required. Use --cohere-key or set COHERE_API_KEY.")
        sys.exit(1)

    asyncio.run(
        embed_null_chunks(args.database_url, args.cohere_key, args.batch_size)
    )


if __name__ == "__main__":
    main()
