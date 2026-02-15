"""
BC Laws scraper — monitors bclaws.ca for legislative changes affecting zoning/density.

Fetches the BC Laws CIVIX API to discover new or amended statutes and regulations
relevant to land use, transit-oriented development, and housing policy.

Architecture:
  - CIVIX XML API for document discovery
  - HTML content extraction from bclaws.ca
  - Deduplication by source_url
  - Stores to documents table for K2 ingestion
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from xml.etree import ElementTree

import aiohttp
import asyncpg

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────

# CIVIX API for browsing BC Laws content
CIVIX_BASE = "https://www.bclaws.gov.bc.ca/civix"

# Search terms for relevant legislation
SEARCH_TERMS = [
    "transit-oriented",
    "zoning",
    "land use",
    "housing supply",
    "small scale multi-unit",
    "density bonus",
    "development permit",
    "strata",
    "local government act",
    "vancouver charter",
    "housing statutes amendment",
]

# Document URL template
DOC_URL_TEMPLATE = "https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/{doc_id}"

HEADERS = {
    "User-Agent": "VanCityLensBot/0.1 (real-estate-intelligence)",
    "Accept": "application/xml, text/html",
}

SOURCE_TYPE = "provincial_legislation"

# Rate limiting: 2 requests per second
RATE_LIMIT_DELAY = 0.5


class BCLawsScraper:
    """Scrapes BC Laws (bclaws.ca) for legislative changes."""

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
        """Fetch URL with rate limiting and error handling."""
        await self._rate_limit()
        try:
            async with self.session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    return await resp.text()
                logger.warning("BC Laws fetch %s returned %d", url, resp.status)
                return None
        except Exception as e:
            logger.error("BC Laws fetch error %s: %s", url, e)
            return None

    async def search_civix(self, query: str, max_results: int = 20) -> List[dict]:
        """Search CIVIX API for documents matching a query."""
        search_url = f"{CIVIX_BASE}/search/complete/statreg/{query}"
        xml_text = await self._fetch(search_url)
        if not xml_text:
            return []

        results = []
        try:
            root = ElementTree.fromstring(xml_text)
            for doc in root.findall(".//doc"):
                doc_id_el = doc.find("CIVIX_DOCUMENT_ID")
                title_el = doc.find("CIVIX_DOCUMENT_TITLE")
                if doc_id_el is not None and doc_id_el.text:
                    doc_id = doc_id_el.text.strip()
                    title = title_el.text.strip() if title_el is not None and title_el.text else doc_id
                    results.append({
                        "doc_id": doc_id,
                        "title": title,
                        "url": DOC_URL_TEMPLATE.format(doc_id=doc_id),
                    })
                    if len(results) >= max_results:
                        break
        except ElementTree.ParseError as e:
            logger.error("CIVIX XML parse error for query '%s': %s", query, e)

        return results

    async def fetch_document_text(self, url: str) -> Optional[str]:
        """Fetch the HTML text of a BC Laws document."""
        html = await self._fetch(url)
        if not html:
            return None

        # Extract meaningful text from the HTML
        # BC Laws pages have content in <div class="content"> or similar
        # Simple extraction — strip tags for raw text storage
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        # Trim to reasonable size (BC Laws docs can be huge)
        if len(text) > 100_000:
            text = text[:100_000] + "\n\n[Truncated — full text available at source URL]"

        return text

    async def discover_documents(self) -> List[dict]:
        """Discover relevant BC Laws documents via CIVIX search."""
        all_docs = {}  # Dedup by doc_id
        for term in SEARCH_TERMS:
            docs = await self.search_civix(term, max_results=10)
            for doc in docs:
                if doc["doc_id"] not in all_docs:
                    all_docs[doc["doc_id"]] = doc
            logger.debug("BC Laws search '%s': found %d docs", term, len(docs))

        logger.info("BC Laws discovery: %d unique documents from %d search terms",
                     len(all_docs), len(SEARCH_TERMS))
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
    Main entry point for the BC Laws scraper.

    Discovers and stores BC Laws documents relevant to land use / zoning / TOD.
    Called by the scheduler with standard signature.
    """
    stats: Dict[str, int] = {
        "documents_found": 0,
        "documents_new": 0,
        "documents_skipped": 0,
        "errors": 0,
    }

    async with aiohttp.ClientSession() as session:
        scraper = BCLawsScraper(session)

        # Discover documents
        documents = await scraper.discover_documents()
        stats["documents_found"] = len(documents)

        async with db_pool.acquire() as conn:
            for doc in documents:
                try:
                    # Check if already stored
                    existing = await conn.fetchrow(SQL_CHECK_EXISTS, doc["url"])
                    if existing:
                        stats["documents_skipped"] += 1
                        continue

                    # Fetch full text
                    text = await scraper.fetch_document_text(doc["url"])
                    if not text:
                        stats["errors"] += 1
                        continue

                    metadata = {
                        "source_type": SOURCE_TYPE,
                        "doc_id": doc["doc_id"],
                        "scraper": "scraper_bclaws",
                    }

                    import json
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
                        logger.info("Stored BC Laws doc: %s", doc["title"][:80])
                    else:
                        stats["documents_skipped"] += 1

                except Exception as e:
                    logger.error("Error storing BC Laws doc %s: %s", doc.get("url", "?"), e)
                    stats["errors"] += 1

    logger.info("BC Laws scraper complete: %s", stats)
    return stats
