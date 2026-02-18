"""
Web scraper for Vancouver rezoning applications.

This module scrapes rezoning applications from rezoning.vancouver.ca/applications/,
extracting application details, zoning information, and linked PDF documents
(staff reports, plans, etc.). Results are stored in the documents table.

Key functions:
- discover_applications(): Find all active/recent rezoning applications
- scrape_application_page(): Extract details from individual application pages
- download_and_parse_pdf(): Extract text from PDF documents
- scrape_and_store(): Main orchestrator that discovers, scrapes, and stores data
"""

import asyncio
import logging
from typing import List, Tuple, Dict, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
import asyncpg
from .parser import parse_pdf

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BASE_URL = "https://rezoning.vancouver.ca"
APPLICATIONS_URL = f"{BASE_URL}/applications/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
REQUEST_DELAY = 1.0  # Rate limiting: 1 request per second


async def discover_applications(
    session: aiohttp.ClientSession,
) -> List[Tuple[str, str, str]]:
    """
    Fetch the main applications listing page and extract all application links.

    Args:
        session: aiohttp ClientSession for making HTTP requests

    Returns:
        List of (url, address, status) tuples for each application found

    Raises:
        aiohttp.ClientError: If the HTTP request fails
        ValueError: If the page structure is unexpected
    """
    logger.info(f"Discovering applications from {APPLICATIONS_URL}")

    try:
        async with session.get(
            APPLICATIONS_URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status != 200:
                logger.error(f"Failed to fetch applications page: HTTP {resp.status}")
                raise ValueError(f"HTTP {resp.status}")

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            applications = []

            # Find all application rows (adjust selector based on actual page structure)
            # Common structures: table rows, div containers, list items
            app_rows = soup.select("[data-application], .application-item, tr[data-id]")

            if not app_rows:
                logger.warning(
                    "No application rows found - checking alternative selectors"
                )
                app_rows = soup.select("article, .result, .item")

            for row in app_rows:
                try:
                    # Extract URL
                    link_elem = row.find("a", href=True)
                    if not link_elem:
                        continue

                    app_url = link_elem.get("href")
                    if not app_url.startswith("http"):
                        app_url = urljoin(BASE_URL, app_url)

                    # Extract address (try multiple selectors)
                    address_elem = row.select_one(
                        ".address, [data-address], .location, .title"
                    )
                    address = (
                        address_elem.get_text(strip=True) if address_elem else "Unknown"
                    )

                    # Extract status (try multiple selectors)
                    status_elem = row.select_one(".status, [data-status], .state")
                    status = (
                        status_elem.get_text(strip=True) if status_elem else "Active"
                    )

                    applications.append((app_url, address, status))
                    logger.debug(f"Found application: {address} - {status}")

                except Exception as e:
                    logger.debug(f"Error parsing application row: {e}")
                    continue

            logger.info(f"Discovered {len(applications)} applications")
            return applications

    except asyncio.TimeoutError:
        logger.error("Request timeout while discovering applications")
        raise
    except Exception as e:
        logger.error(f"Error discovering applications: {e}")
        raise


async def scrape_application_page(session: aiohttp.ClientSession, url: str) -> Dict:
    """
    Fetch an individual application page and extract structured data.

    Extracts:
    - Address
    - Application status (active, approved, denied, etc.)
    - Current zoning
    - Proposed zoning (if listed)
    - Description/summary
    - Links to any PDF documents (staff reports, plans, etc.)

    Args:
        session: aiohttp ClientSession
        url: URL of the application detail page

    Returns:
        Dict containing:
        {
            'url': str,
            'address': str,
            'status': str,
            'current_zoning': str,
            'proposed_zoning': str,
            'description': str,
            'pdf_links': [list of PDF URLs],
            'html': str (raw HTML)
        }

    Raises:
        aiohttp.ClientError: If the HTTP request fails
    """
    logger.info(f"Scraping application page: {url}")

    try:
        async with session.get(
            url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status != 200:
                logger.error(
                    f"Failed to fetch application page {url}: HTTP {resp.status}"
                )
                return {"url": url, "error": f"HTTP {resp.status}"}

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            result = {
                "url": url,
                "html": html,
                "address": extract_text_by_label(soup, "address", "location"),
                "status": extract_text_by_label(soup, "status", "state"),
                "current_zoning": extract_text_by_label(
                    soup, "current zoning", "existing zoning"
                ),
                "proposed_zoning": extract_text_by_label(
                    soup, "proposed zoning", "new zoning"
                ),
                "description": extract_text_by_label(
                    soup, "description", "summary", "project description"
                ),
                "pdf_links": extract_pdf_links(soup, BASE_URL),
            }

            logger.debug(f"Extracted {len(result['pdf_links'])} PDF links from {url}")
            return result

    except asyncio.TimeoutError:
        logger.error(f"Request timeout for {url}")
        return {"url": url, "error": "Request timeout"}
    except Exception as e:
        logger.error(f"Error scraping application page {url}: {e}")
        return {"url": url, "error": str(e)}


async def download_and_parse_pdf(
    session: aiohttp.ClientSession, url: str
) -> Optional[Dict]:
    """
    Download a PDF and extract text using pdfplumber.

    Args:
        session: aiohttp ClientSession
        url: URL of the PDF file

    Returns:
        Dict containing:
        {
            'url': str,
            'text': str (extracted text),
            'page_count': int,
            'error': str (if extraction failed)
        }
        Returns None if download fails

    Raises:
        aiohttp.ClientError: If the HTTP request fails
    """
    logger.info(f"Downloading PDF: {url}")

    try:
        async with session.get(
            url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status != 200:
                logger.error(f"Failed to download PDF {url}: HTTP {resp.status}")
                return None

            pdf_bytes = await resp.read()

            # Extract text using docling (falls back to pdfplumber)
            parsed = parse_pdf(pdf_bytes)
            if not parsed:
                logger.error(f"All parsers failed for PDF {url}")
                return {
                    "url": url,
                    "text": "",
                    "page_count": 0,
                    "error": "All PDF parsers failed",
                }

            result = {
                "url": url,
                "text": parsed["text"],
                "page_count": parsed["page_count"],
            }

            logger.info(
                f"Extracted text from {parsed['page_count']} pages "
                f"(parser={parsed['parser']}): {url}"
            )
            return result

    except asyncio.TimeoutError:
        logger.error(f"Request timeout downloading PDF {url}")
        return None
    except Exception as e:
        logger.error(f"Error downloading PDF {url}: {e}")
        return None


async def scrape_and_store(db_pool: asyncpg.Pool, max_applications: int = 50) -> Dict:
    """
    Main orchestrator that discovers, scrapes, and stores rezoning applications.

    Process:
    1. Discovers applications from the listing page
    2. Scrapes each application page (respecting rate limit)
    3. Downloads linked PDF documents
    4. Stores HTML and PDFs in documents table
    5. Deduplicates by source_url

    Args:
        db_pool: asyncpg connection pool
        max_applications: Maximum number of applications to process (default: 50)

    Returns:
        Dict with processing statistics:
        {
            'applications_discovered': int,
            'applications_scraped': int,
            'pdfs_downloaded': int,
            'documents_stored': int,
            'errors': [list of error messages]
        }
    """
    logger.info(f"Starting rezoning scraper (max {max_applications} applications)")

    stats = {
        "applications_discovered": 0,
        "applications_scraped": 0,
        "pdfs_downloaded": 0,
        "documents_stored": 0,
        "errors": [],
    }

    connector = aiohttp.TCPConnector(limit=10)
    timeout = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        try:
            # Step 1: Discover applications
            applications = await discover_applications(session)
            stats["applications_discovered"] = len(applications)
            applications = applications[:max_applications]

            # Step 2: Scrape each application
            for idx, (app_url, address, status) in enumerate(applications, 1):
                try:
                    logger.info(
                        f"Processing application {idx}/{len(applications)}: {address}"
                    )

                    # Scrape application page
                    app_data = await scrape_application_page(session, app_url)

                    if "error" in app_data:
                        stats["errors"].append(
                            f"Failed to scrape {app_url}: {app_data['error']}"
                        )
                        continue

                    stats["applications_scraped"] += 1

                    # Store HTML page
                    html_doc_id = await store_document(
                        db_pool,
                        url=app_url,
                        source_type="rezoning_report",
                        content=app_data["html"],
                        content_type="text/html",
                        metadata={
                            "address": app_data.get("address"),
                            "status": app_data.get("status"),
                            "current_zoning": app_data.get("current_zoning"),
                            "proposed_zoning": app_data.get("proposed_zoning"),
                        },
                    )

                    if html_doc_id:
                        stats["documents_stored"] += 1
                        logger.debug(f"Stored HTML document: {html_doc_id}")

                    # Step 3: Download and store PDFs
                    pdf_links = app_data.get("pdf_links", [])
                    for pdf_url in pdf_links:
                        try:
                            pdf_data = await download_and_parse_pdf(session, pdf_url)

                            if not pdf_data:
                                continue

                            # Store PDF text
                            pdf_doc_id = await store_document(
                                db_pool,
                                url=pdf_url,
                                source_type="rezoning_report",
                                content=pdf_data["text"],
                                content_type="application/pdf",
                                metadata={
                                    "page_count": pdf_data["page_count"],
                                    "application_url": app_url,
                                    "application_address": app_data.get("address"),
                                },
                            )

                            if pdf_doc_id:
                                stats["pdfs_downloaded"] += 1
                                stats["documents_stored"] += 1
                                logger.debug(f"Stored PDF document: {pdf_doc_id}")

                            # Rate limit
                            await asyncio.sleep(REQUEST_DELAY)

                        except Exception as e:
                            logger.error(f"Error processing PDF {pdf_url}: {e}")
                            stats["errors"].append(
                                f"PDF processing error {pdf_url}: {str(e)}"
                            )
                            continue

                    # Rate limit between applications
                    await asyncio.sleep(REQUEST_DELAY)

                except Exception as e:
                    logger.error(f"Error processing application {app_url}: {e}")
                    stats["errors"].append(
                        f"Application processing error {app_url}: {str(e)}"
                    )
                    continue

        except Exception as e:
            logger.error(f"Fatal error in scraper: {e}")
            stats["errors"].append(f"Fatal error: {str(e)}")

    logger.info(f"Scraping completed. Stats: {stats}")
    return stats


async def store_document(
    db_pool: asyncpg.Pool,
    url: str,
    source_type: str,
    content: str,
    content_type: str,
    metadata: Optional[Dict] = None,
) -> Optional[int]:
    """
    Store a document in the documents table, deduplicating by source_url.

    Args:
        db_pool: asyncpg connection pool
        url: Source URL
        source_type: Type of document (e.g., 'rezoning_report')
        content: Document content (HTML, plain text, etc.)
        content_type: MIME type (e.g., 'text/html', 'application/pdf')
        metadata: Optional dictionary of additional metadata

    Returns:
        Document ID if stored successfully, None otherwise
    """
    try:
        async with db_pool.acquire() as conn:
            # Check if document already exists
            existing = await conn.fetchval(
                "SELECT id FROM documents WHERE source_url = $1", url
            )

            if existing:
                logger.debug(f"Document already exists: {url}")
                return existing

            # Insert new document
            doc_id = await conn.fetchval(
                """
                INSERT INTO documents 
                (source_url, source_type, content, content_type, metadata)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                url,
                source_type,
                content,
                content_type,
                metadata or {},
            )

            return doc_id

    except Exception as e:
        logger.error(f"Error storing document {url}: {e}")
        return None


def extract_text_by_label(soup: BeautifulSoup, *labels: str) -> str:
    """
    Extract text from an element labeled with any of the given labels.

    Searches for elements containing label text (case-insensitive) and
    returns the associated value/text content.

    Args:
        soup: BeautifulSoup object
        *labels: Label text to search for (e.g., 'Address', 'Status')

    Returns:
        Extracted text or empty string if not found
    """
    labels_lower = [label.lower() for label in labels]

    # Try various common patterns
    for label in labels_lower:
        # Pattern: dt/dd pairs (common in definitions)
        for dt in soup.find_all("dt"):
            if label in dt.get_text().lower():
                dd = dt.find_next("dd")
                if dd:
                    return dd.get_text(strip=True)

        # Pattern: label/input pairs
        for lbl in soup.find_all("label"):
            if label in lbl.get_text().lower():
                # Try to find adjacent input or parent container
                parent = lbl.find_parent()
                if parent:
                    text = parent.get_text(strip=True)
                    if text:
                        return text.replace(lbl.get_text(strip=True), "").strip()

        # Pattern: divs with class/data attributes containing label
        for div in soup.find_all("div"):
            div_class = div.get("class", [])
            div_data = div.get("data-label", "")
            if label in (
                div_class + [div_data]
                if isinstance(div_class, list)
                else [str(div_class), div_data]
            ):
                return div.get_text(strip=True)

    return ""


def extract_pdf_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract all PDF links from a page.

    Searches for links ending in .pdf and constructs full URLs.

    Args:
        soup: BeautifulSoup object
        base_url: Base URL for resolving relative links

    Returns:
        List of absolute PDF URLs
    """
    pdf_links = []

    for link in soup.find_all("a", href=True):
        href = link.get("href")
        if href and href.lower().endswith(".pdf"):
            full_url = urljoin(base_url, href)
            if full_url not in pdf_links:
                pdf_links.append(full_url)

    return pdf_links
