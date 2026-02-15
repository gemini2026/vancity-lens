"""
BC Gazette scraper — monitors the BC Gazette for regulatory notices.

The BC Gazette publishes Orders in Council, regulatory amendments, and official
notices that can affect zoning, development, and housing policy. Part I contains
general notices; Part II contains regulations.

Architecture:
  - CIVIX XML API for Gazette content browsing
  - HTML content extraction
  - Deduplication by source_url
  - Stores to documents table for K2 ingestion
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional
from xml.etree import ElementTree

import aiohttp
import asyncpg

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────

# CIVIX base for Gazette content
CIVIX_BASE = "https://www.bclaws.gov.bc.ca/civix"

# Gazette document listings
GAZETTE_COLLECTIONS = [
    # Recent BC Gazette Part II (regulations)
    f"{CIVIX_BASE}/content/bcgaz2/bcgaz2",
    # Recent BC Gazette Part I (general notices)
    f"{CIVIX_BASE}/content/bcgaz1/bcgaz1",
]

# Keywords to filter relevant gazette entries
RELEVANCE_KEYWORDS = [
    "transit", "zoning", "land use", "housing", "density",
    "development", "strata", "building", "municipal",
    "vancouver", "local government", "community plan",
    "residential", "commercial", "industrial",
]

DOC_URL_TEMPLATE = "https://www.bclaws.gov.bc.ca/civix/document/id/{collection}/{doc_id}"

HEADERS = {
    "User-Agent": "VanCityLensBot/0.1 (real-estate-intelligence)",
    "Accept": "application/xml, text/html",
}

SOURCE_TYPE = "bc_gazette"
RATE_LIMIT_DELAY = 0.5


class BCGazetteScraper:
    """Scrapes BC Gazette for regulatory notices."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self._last_request = 0.0

    async def _rate_limit(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request
        if elapsed < RATE_LIMIT_DELAY:
            await asyncio.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request = asyncio.get_event_loop().time()

    async def _fetch(self, url: str) -> Optional[str]:
        await self._rate_limit()
        try:
            async with self.session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    return await resp.text()
                logger.warning("BC Gazette fetch %s returned %d", url, resp.status)
                return None
        except Exception as e:
            logger.error("BC Gazette fetch error %s: %s", url, e)
            return None

    async def list_gazette_entries(self, collection_url: str, max_entries: int = 50) -> List[dict]:
        """List recent Gazette entries from a CIVIX collection."""
        xml_text = await self._fetch(collection_url)
        if not xml_text:
            return []

        entries = []
        try:
            root = ElementTree.fromstring(xml_text)
            for item in root.findall(".//CIVIX_INDEX_ENTRY"):
                doc_id_el = item.find("CIVIX_DOCUMENT_ID")
                title_el = item.find("CIVIX_DOCUMENT_TITLE")
                if doc_id_el is not None and doc_id_el.text:
                    doc_id = doc_id_el.text.strip()
                    title = title_el.text.strip() if title_el is not None and title_el.text else doc_id

                    # Determine collection name from URL
                    collection = "bcgaz2" if "bcgaz2" in collection_url else "bcgaz1"
                    url = DOC_URL_TEMPLATE.format(collection=collection, doc_id=doc_id)

                    entries.append({
                        "doc_id": doc_id,
                        "title": title,
                        "url": url,
                        "collection": collection,
                    })
                    if len(entries) >= max_entries:
                        break
        except ElementTree.ParseError as e:
            logger.error("CIVIX XML parse error: %s", e)

        return entries

    def _is_relevant(self, title: str) -> bool:
        """Check if a gazette entry title contains relevant keywords."""
        title_lower = title.lower()
        return any(kw in title_lower for kw in RELEVANCE_KEYWORDS)

    async def fetch_document_text(self, url: str) -> Optional[str]:
        """Fetch and extract text from a Gazette document."""
        html = await self._fetch(url)
        if not html:
            return None

        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        if len(text) > 100_000:
            text = text[:100_000] + "\n\n[Truncated — full text available at source URL]"

        return text

    async def discover_documents(self) -> List[dict]:
        """Discover relevant Gazette entries from both Part I and Part II."""
        all_docs = {}
        for collection_url in GAZETTE_COLLECTIONS:
            entries = await self.list_gazette_entries(collection_url)
            for entry in entries:
                if self._is_relevant(entry["title"]) and entry["doc_id"] not in all_docs:
                    all_docs[entry["doc_id"]] = entry

        logger.info("BC Gazette discovery: %d relevant entries from %d collections",
                     len(all_docs), len(GAZETTE_COLLECTIONS))
        return list(all_docs.values())


SQL_CHECK_EXISTS = "SELECT id FROM documents WHERE source_url = $1"

SQL_INSERT_DOC = """
INSERT INTO documents (source_type, source_url, title, raw_text, text_length, file_format, metadata, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
ON CONFLICT (source_url) DO NOTHING
RETURNING id
"""


async def scrape_and_store(
    db_pool: asyncpg.Pool,
    start_date: datetime,
    end_date: datetime,
) -> Dict[str, int]:
    """
    Main entry point for the BC Gazette scraper.
    Called by the scheduler with standard signature.
    """
    stats: Dict[str, int] = {
        "documents_found": 0,
        "documents_new": 0,
        "documents_skipped": 0,
        "errors": 0,
    }

    async with aiohttp.ClientSession() as session:
        scraper = BCGazetteScraper(session)
        documents = await scraper.discover_documents()
        stats["documents_found"] = len(documents)

        async with db_pool.acquire() as conn:
            for doc in documents:
                try:
                    existing = await conn.fetchrow(SQL_CHECK_EXISTS, doc["url"])
                    if existing:
                        stats["documents_skipped"] += 1
                        continue

                    text = await scraper.fetch_document_text(doc["url"])
                    if not text:
                        stats["errors"] += 1
                        continue

                    metadata = {
                        "source_type": SOURCE_TYPE,
                        "doc_id": doc["doc_id"],
                        "collection": doc["collection"],
                        "scraper": "scraper_gazette",
                    }

                    result = await conn.fetchrow(
                        SQL_INSERT_DOC,
                        SOURCE_TYPE,
                        doc["url"],
                        doc["title"],
                        text,
                        len(text),
                        "html",
                        json.dumps(metadata),
                    )
                    if result:
                        stats["documents_new"] += 1
                        logger.info("Stored Gazette doc: %s", doc["title"][:80])
                    else:
                        stats["documents_skipped"] += 1

                except Exception as e:
                    logger.error("Error storing Gazette doc %s: %s", doc.get("url", "?"), e)
                    stats["errors"] += 1

    logger.info("BC Gazette scraper complete: %s", stats)
    return stats
