#!/usr/bin/env python3
"""
Seed document_chunks table by chunking all documents with raw_text.

Uses chunk_document() from the intelligence chunker (semchunk + tiktoken).
No API keys required — all processing is local.

Chunks are inserted with:
  - embedding = NULL  (backfilled later via embed_chunks.py when Cohere key available)
  - chunk_tsvector = to_tsvector('english', chunk_text)  (ready for BM25 search immediately)

Usage:
    python scripts/seed_chunks.py [--force] [--database-url URL]

Options:
    --force          Re-chunk documents that already have chunks (deletes existing first)
    --database-url   Override DATABASE_URL environment variable
"""

import argparse
import asyncio
import logging
import os
import sys

# Add project root to path so we can import api modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

from api.intelligence.chunker import chunk_document

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)


async def seed_chunks(database_url: str, force: bool = False):
    """Chunk all documents and insert into document_chunks."""
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)

    try:
        async with pool.acquire() as conn:
            # Get documents with raw_text
            if force:
                docs = await conn.fetch(
                    "SELECT id, title, raw_text FROM documents WHERE raw_text IS NOT NULL ORDER BY id"
                )
            else:
                # Skip docs that already have chunks
                docs = await conn.fetch(
                    """
                    SELECT d.id, d.title, d.raw_text
                    FROM documents d
                    WHERE d.raw_text IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM document_chunks dc WHERE dc.document_id = d.id
                      )
                    ORDER BY d.id
                    """
                )

        logger.info(f"Found {len(docs)} documents to chunk")

        if not docs:
            logger.info("No documents to process. Use --force to re-chunk existing.")
            return

        total_chunks = 0
        errors = 0

        for doc in docs:
            doc_id = doc["id"]
            title = doc["title"] or f"Document {doc_id}"
            raw_text = doc["raw_text"]

            try:
                # If force mode, delete existing chunks first
                if force:
                    async with pool.acquire() as conn:
                        deleted = await conn.fetchval(
                            "DELETE FROM document_chunks WHERE document_id = $1 RETURNING COUNT(*)",
                            doc_id,
                        )
                        # fetchval on DELETE ... RETURNING COUNT(*) may return None
                        # Use execute with a count instead
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "DELETE FROM document_chunks WHERE document_id = $1", doc_id
                        )

                # Chunk the document (local, no API)
                chunks = chunk_document(raw_text)

                if not chunks:
                    logger.warning(f"  Doc {doc_id} ({title[:50]}): no chunks produced")
                    continue

                # Insert chunks with NULL embedding and inline tsvector
                async with pool.acquire() as conn:
                    for chunk in chunks:
                        await conn.execute(
                            """
                            INSERT INTO document_chunks (
                                document_id, chunk_index, chunk_text,
                                section_header, token_count,
                                embedding, chunk_tsvector
                            ) VALUES (
                                $1, $2, $3, $4, $5,
                                NULL,
                                to_tsvector('english', $3)
                            )
                            """,
                            doc_id,
                            chunk["chunk_index"],
                            chunk["chunk_text"],
                            chunk.get("section_header"),
                            chunk.get("approx_token_count", 0),
                        )

                total_chunks += len(chunks)
                logger.info(
                    f"  Doc {doc_id} ({title[:50]}): {len(chunks)} chunks"
                )

            except Exception as e:
                errors += 1
                logger.error(f"  Doc {doc_id} ({title[:50]}): FAILED — {e}")

        logger.info(f"\nDone: {total_chunks} chunks from {len(docs)} documents ({errors} errors)")

        # Print summary stats
        async with pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM document_chunks")
            with_tsvec = await conn.fetchval(
                "SELECT COUNT(*) FROM document_chunks WHERE chunk_tsvector IS NOT NULL"
            )
            with_emb = await conn.fetchval(
                "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL"
            )

        logger.info(f"Total chunks in DB: {total}")
        logger.info(f"  With tsvector: {with_tsvec} (ready for BM25 search)")
        logger.info(f"  With embedding: {with_emb} (ready for dense search)")

    finally:
        await pool.close()


def main():
    parser = argparse.ArgumentParser(description="Seed document_chunks from raw_text")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-chunk documents that already have chunks",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "postgresql://localhost:5432/bill47"),
        help="PostgreSQL connection URL",
    )
    args = parser.parse_args()

    asyncio.run(seed_chunks(args.database_url, force=args.force))


if __name__ == "__main__":
    main()
