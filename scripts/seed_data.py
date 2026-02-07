#!/usr/bin/env python3
"""
VanCity Lens — Data Seeding Pipeline

Runs the full ingestion pipeline:
1. Scrape documents from Vancouver government sources
2. Process documents (chunk + embed + extract signals)

Usage:
    python scripts/seed_data.py                    # scrape all + process
    python scripts/seed_data.py --scrape-only      # just scrape
    python scripts/seed_data.py --process-only     # just process existing docs
    python scripts/seed_data.py --source council    # scrape only council minutes
"""

import argparse
import asyncio
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("seed")


async def get_pool() -> asyncpg.Pool:
    """Create database connection pool."""
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens",
    )
    logger.info(f"Connecting to database...")
    pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
    logger.info("Database pool created")
    return pool


async def scrape(pool: asyncpg.Pool, source: str, days_back: int):
    """Run scrapers to fetch documents."""
    from datetime import datetime, timedelta

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    if source in ("council", "all"):
        logger.info("=== Scraping council minutes ===")
        try:
            from api.intelligence.scraper_council import scrape_and_store
            count = await scrape_and_store(pool, start_date, end_date)
            logger.info(f"Council scraper done: {count} documents stored")
        except Exception as e:
            logger.error(f"Council scraper failed: {e}", exc_info=True)

    if source in ("rezoning", "all"):
        logger.info("=== Scraping rezoning applications ===")
        try:
            from api.intelligence.scraper_rezoning import scrape_and_store
            count = await scrape_and_store(pool)
            logger.info(f"Rezoning scraper done: {count} documents stored")
        except Exception as e:
            logger.error(f"Rezoning scraper failed: {e}", exc_info=True)

    if source in ("dpb", "all"):
        logger.info("=== Scraping DPB minutes ===")
        try:
            from api.intelligence.scraper_dpb import download_and_store
            count = await download_and_store(pool)
            logger.info(f"DPB scraper done: {count} documents stored")
        except Exception as e:
            logger.error(f"DPB scraper failed: {e}", exc_info=True)

    if source in ("news", "all"):
        logger.info("=== Scraping news feeds ===")
        try:
            from api.intelligence.scraper_news import scrape_news_feeds
            count = await scrape_news_feeds(pool, days_back=days_back)
            logger.info(f"News scraper done: {count} articles stored")
        except Exception as e:
            logger.error(f"News scraper failed: {e}", exc_info=True)


async def process(pool: asyncpg.Pool, batch_size: int):
    """Process unprocessed documents: chunk → embed → extract signals."""
    cohere_key = os.environ.get("COHERE_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not cohere_key:
        logger.error("COHERE_API_KEY not set — cannot embed documents")
        return
    if not anthropic_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot extract signals")
        return

    # Count unprocessed
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM documents WHERE processed_at IS NULL AND raw_text IS NOT NULL"
        )
    logger.info(f"Found {count} unprocessed documents")

    if count == 0:
        logger.info("Nothing to process")
        return

    # Import and run processing
    from api.intelligence.embeddings import process_document_chunks
    from api.intelligence.extractor import process_all_unprocessed

    # Get unprocessed doc IDs
    async with pool.acquire() as conn:
        doc_ids = await conn.fetch(
            """
            SELECT id, title, source_type FROM documents
            WHERE processed_at IS NULL AND raw_text IS NOT NULL
            ORDER BY scraped_at DESC
            LIMIT $1
            """,
            batch_size,
        )

    logger.info(f"Processing {len(doc_ids)} documents...")

    for i, row in enumerate(doc_ids, 1):
        doc_id = row["id"]
        title = row["title"] or "(untitled)"
        logger.info(f"[{i}/{len(doc_ids)}] Processing: {title}")
        try:
            chunks = await process_document_chunks(pool, doc_id, cohere_key)
            logger.info(f"  → {chunks} chunks embedded")
        except Exception as e:
            logger.error(f"  → Embedding failed: {e}")
            continue

    # Extract signals from all unprocessed
    logger.info("=== Extracting intelligence signals ===")
    try:
        stats = await process_all_unprocessed(pool, anthropic_key, batch_size=batch_size)
        logger.info(f"Extraction complete: {stats}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


async def show_status(pool: asyncpg.Pool):
    """Print current database status."""
    async with pool.acquire() as conn:
        docs = await conn.fetchval("SELECT COUNT(*) FROM documents")
        processed = await conn.fetchval(
            "SELECT COUNT(*) FROM documents WHERE processed_at IS NOT NULL"
        )
        chunks = await conn.fetchval("SELECT COUNT(*) FROM document_chunks")
        signals = await conn.fetchval("SELECT COUNT(*) FROM intelligence_signals")
        geocoded = await conn.fetchval(
            "SELECT COUNT(*) FROM intelligence_signals WHERE geom IS NOT NULL"
        )

    logger.info("=" * 50)
    logger.info("VanCity Lens — Database Status")
    logger.info("=" * 50)
    logger.info(f"  Documents:         {docs} ({processed} processed)")
    logger.info(f"  Document chunks:   {chunks}")
    logger.info(f"  Intelligence signals: {signals} ({geocoded} geocoded)")
    logger.info("=" * 50)


async def main():
    parser = argparse.ArgumentParser(description="VanCity Lens data seeding pipeline")
    parser.add_argument("--scrape-only", action="store_true", help="Only scrape, don't process")
    parser.add_argument("--process-only", action="store_true", help="Only process existing docs")
    parser.add_argument("--status", action="store_true", help="Show database status")
    parser.add_argument("--source", default="all", choices=["all", "council", "rezoning", "dpb", "news"])
    parser.add_argument("--days-back", type=int, default=180, help="How many days back to scrape")
    parser.add_argument("--batch-size", type=int, default=20, help="Documents to process per batch")
    args = parser.parse_args()

    pool = await get_pool()

    try:
        if args.status:
            await show_status(pool)
            return

        if not args.process_only:
            await scrape(pool, args.source, args.days_back)

        if not args.scrape_only:
            await process(pool, args.batch_size)

        await show_status(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
