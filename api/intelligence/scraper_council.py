"""
Vancouver City Council Meeting Minutes and Agendas Web Scraper

This module provides utilities to discover, scrape, and store Vancouver City Council
meeting agendas, minutes, and related PDF documents. It uses async/concurrent requests
with rate limiting to responsibly scrape the council.vancouver.ca domain.

Key functions:
- discover_meetings(): Find council meeting URLs within a date range
- scrape_meeting_page(): Extract agenda items and PDF links from meeting pages
- download_and_parse_pdf(): Extract text from PDF documents
- scrape_and_store(): Main orchestrator for full scraping workflow
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional, Dict, List, Tuple, Any
from urllib.parse import urljoin, urlparse

import aiohttp
import asyncpg
from bs4 import BeautifulSoup
from .parser import parse_pdf

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Constants
BASE_URL = "https://council.vancouver.ca"
RATE_LIMIT_DELAY = 1.0  # seconds between requests
COUNCIL_MEETING_PATTERNS = {
    'regular': 'regu{yyyymmdd}ag.htm',
    'special': 'spec{yyyymmdd}ag.htm',
    'public_hearing': 'phea{yyyymmdd}ag.htm',
}

# Meeting types typically occur on Tuesdays, roughly bi-weekly
MEETING_DAY_OF_WEEK = 1  # Tuesday (0=Monday, 1=Tuesday, etc.)


class RateLimiter:
    """Simple rate limiter for async operations."""

    def __init__(self, delay: float = 1.0):
        """
        Initialize rate limiter.

        Args:
            delay: Minimum seconds between requests
        """
        self.delay = delay
        self.last_request_time = 0.0

    async def acquire(self):
        """Wait if necessary to respect rate limit."""
        elapsed = asyncio.get_event_loop().time() - self.last_request_time
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
        self.last_request_time = asyncio.get_event_loop().time()


class VancouverCouncilScraper:
    """Scraper for Vancouver City Council meeting documents."""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        """
        Initialize the scraper.

        Args:
            session: Optional aiohttp ClientSession for reuse
            rate_limiter: Optional RateLimiter instance
        """
        self.session = session
        self.rate_limiter = rate_limiter or RateLimiter(RATE_LIMIT_DELAY)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; VancouverCouncilScraper/1.0)'
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _make_request(self, url: str, method: str = 'GET',
                           timeout: int = 10) -> Optional[str]:
        """
        Make HTTP request with rate limiting.

        Args:
            url: URL to request
            method: HTTP method (GET, HEAD)
            timeout: Request timeout in seconds

        Returns:
            Response text or None on error
        """
        await self.rate_limiter.acquire()

        session = await self._get_session()
        try:
            async with session.request(
                method, url, headers=self.headers, timeout=timeout,
                allow_redirects=True
            ) as response:
                if response.status == 200:
                    if method == 'GET':
                        return await response.text()
                    return ''  # For HEAD requests
                elif response.status == 404:
                    logger.debug(f"URL not found (404): {url}")
                    return None
                else:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {url}")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    async def _check_url_exists(self, url: str) -> bool:
        """
        Check if a URL exists using HEAD request.

        Args:
            url: URL to check

        Returns:
            True if URL returns 200 OK, False otherwise
        """
        await self.rate_limiter.acquire()

        session = await self._get_session()
        try:
            async with session.head(
                url, headers=self.headers, timeout=10, allow_redirects=True
            ) as response:
                exists = response.status == 200
                logger.debug(f"URL check {url}: {response.status}")
                return exists
        except Exception as e:
            logger.debug(f"Error checking {url}: {e}")
            return False

    def discover_meetings(self, start_date: datetime,
                         end_date: datetime) -> List[Dict[str, str]]:
        """
        Discover council meetings by iterating through dates and checking
        which meeting URL patterns exist.

        Council meetings typically occur on Tuesdays, roughly every 2 weeks.
        This checks all Tuesdays in the range across all three meeting types.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of dicts with keys: 'url', 'date', 'type', 'yyyymmdd'
        """
        meetings = []
        current = start_date

        # Align to next Tuesday if not already on Tuesday
        if current.weekday() != MEETING_DAY_OF_WEEK:
            days_ahead = MEETING_DAY_OF_WEEK - current.weekday()
            if days_ahead < 0:
                days_ahead += 7
            current += timedelta(days=days_ahead)

        logger.info(f"Discovering meetings between {start_date.date()} and {end_date.date()}")

        while current <= end_date:
            yyyymmdd = current.strftime('%Y%m%d')

            for meeting_type, pattern in COUNCIL_MEETING_PATTERNS.items():
                filename = pattern.replace('{yyyymmdd}', yyyymmdd)
                url = f"{BASE_URL}/{yyyymmdd}/{filename}"
                meetings.append({
                    'url': url,
                    'date': current.date(),
                    'type': meeting_type,
                    'yyyymmdd': yyyymmdd,
                })

            current += timedelta(weeks=2)

        logger.info(f"Generated {len(meetings)} potential meeting URLs to check")
        return meetings

    async def discover_meetings_async(self, start_date: datetime,
                                      end_date: datetime) -> List[Dict[str, str]]:
        """
        Async version: Discover meetings and verify they exist via HEAD requests.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of verified meeting URLs
        """
        potential_meetings = self.discover_meetings(start_date, end_date)

        # Check which URLs actually exist
        verified_meetings = []
        tasks = []

        async def check_and_collect(meeting: Dict[str, str]):
            exists = await self._check_url_exists(meeting['url'])
            if exists:
                verified_meetings.append(meeting)
                logger.info(f"Found meeting: {meeting['type']} on {meeting['date']}")

        for meeting in potential_meetings:
            tasks.append(check_and_collect(meeting))

        await asyncio.gather(*tasks)
        logger.info(f"Verified {len(verified_meetings)} existing meeting URLs")

        return verified_meetings

    async def scrape_meeting_page(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch and parse a council meeting agenda page.

        Extracts meeting metadata, agenda items, and PDF document links.

        Args:
            url: URL of the meeting agenda page

        Returns:
            Dict with keys:
            - html: Raw HTML content
            - title: Meeting title
            - date: Meeting date
            - type: Meeting type
            - agenda_items: List of agenda item texts
            - pdf_links: List of PDF URLs found on page
            Or None if fetch fails
        """
        html = await self._make_request(url, method='GET')
        if not html:
            logger.warning(f"Failed to fetch meeting page: {url}")
            return None

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract meeting title and date from page
            # Title typically in heading tags
            title_tag = soup.find(['h1', 'h2', 'title'])
            title = title_tag.get_text(strip=True) if title_tag else "Unknown"

            # Extract date from URL pattern (YYYYMMDD)
            match = re.search(r'/(\d{8})/', url)
            date_str = match.group(1) if match else ""
            try:
                meeting_date = datetime.strptime(date_str, '%Y%m%d').date()
            except ValueError:
                meeting_date = None

            # Determine meeting type from URL
            if 'regu' in url:
                meeting_type = 'regular'
            elif 'spec' in url:
                meeting_type = 'special'
            elif 'phea' in url:
                meeting_type = 'public_hearing'
            else:
                meeting_type = 'unknown'

            # Extract all agenda item text
            agenda_items = []
            for item in soup.find_all(['li', 'p']):
                text = item.get_text(strip=True)
                if text and len(text) > 10:  # Filter out very short lines
                    agenda_items.append(text)

            # Extract PDF links
            pdf_links = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if href.lower().endswith('.pdf'):
                    # Convert relative URLs to absolute
                    pdf_url = urljoin(url, href)
                    pdf_links.append(pdf_url)

            logger.info(f"Parsed meeting: {meeting_type} on {meeting_date}, "
                       f"found {len(agenda_items)} items, {len(pdf_links)} PDFs")

            return {
                'html': html,
                'title': title,
                'date': meeting_date,
                'type': meeting_type,
                'agenda_items': agenda_items,
                'pdf_links': list(set(pdf_links)),  # Remove duplicates
                'source_url': url,
            }

        except Exception as e:
            logger.error(f"Error parsing meeting page {url}: {e}")
            return None

    async def download_and_parse_pdf(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Download and extract text from a PDF document.

        Args:
            url: URL of the PDF file

        Returns:
            Dict with keys:
            - text: Extracted text
            - page_count: Number of pages
            - source_url: Original URL
            Or None if download/parse fails
        """
        await self.rate_limiter.acquire()

        session = await self._get_session()
        try:
            async with session.get(
                url, headers=self.headers, timeout=30
            ) as response:
                if response.status != 200:
                    logger.warning(f"Failed to download PDF (HTTP {response.status}): {url}")
                    return None

                content = await response.read()

                # Parse PDF with docling (falls back to pdfplumber)
                result = parse_pdf(content)
                if not result:
                    logger.warning(f"All parsers failed for PDF: {url}")
                    return None

                logger.info(
                    f"Extracted {result['page_count']} pages from PDF "
                    f"(parser={result['parser']}): {url}"
                )

                return {
                    'text': result['text'],
                    'page_count': result['page_count'],
                    'source_url': url,
                }

        except asyncio.TimeoutError:
            logger.warning(f"Timeout downloading PDF: {url}")
            return None
        except Exception as e:
            logger.error(f"Error downloading/parsing PDF {url}: {e}")
            return None

    async def scrape_and_store(self, db_pool: asyncpg.Pool,
                               start_date: datetime, end_date: datetime,
                               download_pdfs: bool = True) -> Dict[str, int]:
        """
        Main orchestrator: Discover meetings, scrape pages, download PDFs, and store in DB.

        Args:
            db_pool: asyncpg connection pool
            start_date: Start of date range
            end_date: End of date range
            download_pdfs: Whether to download and parse PDF documents

        Returns:
            Dict with counts: meetings_found, pages_stored, pdfs_stored, errors
        """
        stats = {
            'meetings_found': 0,
            'pages_stored': 0,
            'pdfs_stored': 0,
            'errors': 0,
        }

        logger.info(f"Starting scrape_and_store: {start_date.date()} to {end_date.date()}")

        # Discover meetings
        meetings = await self.discover_meetings_async(start_date, end_date)
        stats['meetings_found'] = len(meetings)

        if not meetings:
            logger.info("No meetings found in date range")
            return stats

        # Scrape each meeting page
        for meeting in meetings:
            try:
                meeting_data = await self.scrape_meeting_page(meeting['url'])
                if not meeting_data:
                    stats['errors'] += 1
                    continue

                # Store meeting page in database
                await self._store_document(
                    db_pool,
                    source_type='council_minutes',
                    source_url=meeting['url'],
                    title=meeting_data['title'],
                    published_date=meeting_data['date'],
                    meeting_date=meeting_data['date'],
                    raw_text=meeting_data['html'],
                    text_length=len(meeting_data['html']),
                    page_count=1,
                    file_format='html',
                    metadata={
                        'meeting_type': meeting_data['type'],
                        'agenda_items_count': len(meeting_data['agenda_items']),
                        'pdf_count': len(meeting_data['pdf_links']),
                    }
                )
                stats['pages_stored'] += 1

                # Download and store PDFs if requested
                if download_pdfs and meeting_data['pdf_links']:
                    for pdf_url in meeting_data['pdf_links']:
                        try:
                            pdf_data = await self.download_and_parse_pdf(pdf_url)
                            if pdf_data:
                                # Determine PDF type from URL or content
                                if 'staff' in pdf_url.lower():
                                    source_type = 'staff_report'
                                elif 'referral' in pdf_url.lower():
                                    source_type = 'public_hearing'
                                else:
                                    source_type = 'staff_report'

                                await self._store_document(
                                    db_pool,
                                    source_type=source_type,
                                    source_url=pdf_url,
                                    title=self._extract_pdf_title(pdf_url),
                                    published_date=meeting_data['date'],
                                    meeting_date=meeting_data['date'],
                                    raw_text=pdf_data['text'],
                                    text_length=len(pdf_data['text']),
                                    page_count=pdf_data['page_count'],
                                    file_format='pdf',
                                    metadata={
                                        'extracted_from_url': pdf_url,
                                    }
                                )
                                stats['pdfs_stored'] += 1
                        except Exception as e:
                            logger.error(f"Error processing PDF {pdf_url}: {e}")
                            stats['errors'] += 1

            except Exception as e:
                logger.error(f"Error processing meeting {meeting['url']}: {e}")
                stats['errors'] += 1

        logger.info(f"Scrape completed. Stats: {stats}")
        return stats

    async def _store_document(self, db_pool: asyncpg.Pool,
                             source_type: str, source_url: str, title: str,
                             published_date: Optional[datetime.date],
                             meeting_date: Optional[datetime.date],
                             raw_text: str, text_length: int, page_count: int,
                             file_format: str, metadata: Optional[Dict] = None) -> bool:
        """
        Store a document in the database.

        Handles duplicates by checking source_url UNIQUE constraint.

        Args:
            db_pool: asyncpg connection pool
            source_type: Type of document
            source_url: Source URL
            title: Document title
            published_date: Publication date
            meeting_date: Meeting date
            raw_text: Raw text content
            text_length: Length of raw text
            page_count: Number of pages
            file_format: File format (html or pdf)
            metadata: Additional metadata dict

        Returns:
            True if stored successfully, False if duplicate
        """
        metadata = metadata or {}

        try:
            async with db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    INSERT INTO documents (
                        source_type, source_url, title, published_date,
                        meeting_date, raw_text, text_length, page_count,
                        file_format, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (source_url) DO NOTHING
                    RETURNING id
                    """,
                    source_type, source_url, title, published_date,
                    meeting_date, raw_text, text_length, page_count,
                    file_format, metadata
                )

                if result == 'INSERT 0 1':
                    logger.debug(f"Stored document: {title}")
                    return True
                else:
                    logger.debug(f"Document already exists: {source_url}")
                    return False

        except asyncpg.UniqueViolationError:
            logger.debug(f"Duplicate document skipped: {source_url}")
            return False
        except Exception as e:
            logger.error(f"Error storing document {source_url}: {e}")
            return False

    @staticmethod
    def _extract_pdf_title(url: str) -> str:
        """
        Extract a reasonable title from a PDF URL.

        Args:
            url: PDF URL

        Returns:
            Extracted title or filename
        """
        # Get filename from URL
        parsed = urlparse(url)
        filename = parsed.path.split('/')[-1]

        # Clean up filename: remove .pdf and replace underscores/hyphens with spaces
        title = filename.replace('.pdf', '').replace('_', ' ').replace('-', ' ')

        return title

    async def close(self):
        """Close the aiohttp session if we created it."""
        if self.session:
            await self.session.close()


# Standalone convenience functions

async def discover_meetings(start_date: datetime,
                           end_date: datetime) -> List[Dict[str, str]]:
    """
    Discover Vancouver City Council meetings in date range.

    Args:
        start_date: Start of date range
        end_date: End of date range

    Returns:
        List of discovered meeting URLs with metadata
    """
    scraper = VancouverCouncilScraper()
    try:
        return await scraper.discover_meetings_async(start_date, end_date)
    finally:
        await scraper.close()


async def scrape_meeting_page(url: str) -> Optional[Dict[str, Any]]:
    """
    Scrape a council meeting page.

    Args:
        url: Meeting page URL

    Returns:
        Parsed meeting data or None
    """
    scraper = VancouverCouncilScraper()
    try:
        return await scraper.scrape_meeting_page(url)
    finally:
        await scraper.close()


async def download_and_parse_pdf(url: str) -> Optional[Dict[str, Any]]:
    """
    Download and parse a PDF document.

    Args:
        url: PDF URL

    Returns:
        Extracted PDF data or None
    """
    scraper = VancouverCouncilScraper()
    try:
        return await scraper.download_and_parse_pdf(url)
    finally:
        await scraper.close()


async def scrape_and_store(db_pool: asyncpg.Pool,
                          start_date: datetime, end_date: datetime,
                          download_pdfs: bool = True) -> Dict[str, int]:
    """
    Main orchestrator: scrape meetings and store in database.

    Args:
        db_pool: asyncpg connection pool
        start_date: Start of date range
        end_date: End of date range
        download_pdfs: Whether to download PDFs

    Returns:
        Statistics dict
    """
    scraper = VancouverCouncilScraper()
    try:
        return await scraper.scrape_and_store(
            db_pool, start_date, end_date, download_pdfs
        )
    finally:
        await scraper.close()


if __name__ == '__main__':
    # Example usage
    print("Vancouver City Council Scraper Module")
    print("Import this module to use its functions")
