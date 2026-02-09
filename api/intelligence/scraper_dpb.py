"""
Web scraper for Vancouver Development Permit Board (DPB) minutes.

This module scrapes DPB minutes from:
vancouver.ca/home-property-development/development-permit-board-past-minutes-and-agendas.aspx

The DPB reviews applications for development permits and rezoning. This scraper
extracts PDF documents containing meeting minutes, extracts the text, and stores
them in the documents table for further analysis.

Key functions:
- discover_dpb_minutes(): Find all available DPB meeting minute PDFs
- download_and_store(): Download PDFs, extract text, and store in database
"""

import asyncio
import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
import asyncpg
from .parser import parse_pdf

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BASE_URL = "https://vancouver.ca"
DPB_MINUTES_URL = (
    "https://vancouver.ca/home-property-development/"
    "development-permit-board-past-minutes-and-agendas.aspx"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
REQUEST_DELAY = 1.0  # Rate limiting: 1 request per second


async def discover_dpb_minutes(session: aiohttp.ClientSession) -> List[Dict]:
    """
    Fetch the DPB minutes page and find all links to PDF documents.
    
    Searches for PDF links to meeting minutes and agendas from the DPB
    archive page.
    
    Args:
        session: aiohttp ClientSession for making HTTP requests
    
    Returns:
        List of dicts containing:
        {
            'url': str (full URL to PDF),
            'filename': str,
            'date': str (extracted from text if available),
            'type': str ('minutes' or 'agenda')
        }
    
    Raises:
        aiohttp.ClientError: If the HTTP request fails
    """
    logger.info(f"Discovering DPB minutes from {DPB_MINUTES_URL}")
    
    try:
        async with session.get(DPB_MINUTES_URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                logger.error(f"Failed to fetch DPB page: HTTP {resp.status}")
                raise ValueError(f"HTTP {resp.status}")
            
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            
            documents = []
            
            # Find all PDF links on the page
            for link in soup.find_all("a", href=True):
                href = link.get("href")
                if not href or not href.lower().endswith(".pdf"):
                    continue
                
                # Construct full URL
                pdf_url = urljoin(BASE_URL, href)
                
                # Extract filename and link text for metadata
                link_text = link.get_text(strip=True)
                filename = href.split("/")[-1]
                
                # Determine document type
                doc_type = "minutes" if "minute" in link_text.lower() else "agenda"
                if "agenda" in link_text.lower():
                    doc_type = "agenda"
                
                # Try to extract date from link text
                # Common patterns: "January 2024", "2024-01-15", etc.
                date_str = extract_date_from_text(link_text)
                
                documents.append({
                    'url': pdf_url,
                    'filename': filename,
                    'date': date_str,
                    'type': doc_type,
                    'link_text': link_text,
                })
                
                logger.debug(f"Found DPB document: {filename} ({doc_type})")
            
            logger.info(f"Discovered {len(documents)} DPB PDF documents")
            return documents
    
    except asyncio.TimeoutError:
        logger.error("Request timeout while discovering DPB minutes")
        raise
    except Exception as e:
        logger.error(f"Error discovering DPB minutes: {e}")
        raise


async def download_and_parse_pdf(session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
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
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                logger.error(f"Failed to download PDF {url}: HTTP {resp.status}")
                return None
            
            pdf_bytes = await resp.read()

            # Extract text using docling (falls back to pdfplumber)
            parsed = parse_pdf(pdf_bytes)
            if not parsed:
                logger.error(f"All parsers failed for PDF {url}")
                return {
                    'url': url,
                    'text': '',
                    'page_count': 0,
                    'error': 'All PDF parsers failed'
                }

            result = {
                'url': url,
                'text': parsed['text'],
                'page_count': parsed['page_count'],
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


async def store_document(
    db_pool: asyncpg.Pool,
    url: str,
    content: str,
    content_type: str,
    metadata: Optional[Dict] = None
) -> Optional[int]:
    """
    Store a document in the documents table, deduplicating by source_url.
    
    Args:
        db_pool: asyncpg connection pool
        url: Source URL
        content: Document content (plain text extracted from PDF)
        content_type: MIME type (typically 'application/pdf')
        metadata: Optional dictionary of additional metadata
    
    Returns:
        Document ID if stored successfully, None otherwise
    """
    try:
        async with db_pool.acquire() as conn:
            # Check if document already exists
            existing = await conn.fetchval(
                "SELECT id FROM documents WHERE source_url = $1",
                url
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
                url, 'dpb_minutes', content, content_type, metadata or {}
            )
            
            return doc_id
    
    except Exception as e:
        logger.error(f"Error storing document {url}: {e}")
        return None


async def download_and_store(
    db_pool: asyncpg.Pool,
    max_documents: Optional[int] = None
) -> Dict:
    """
    Main orchestrator that discovers, downloads, and stores DPB minutes.
    
    Process:
    1. Discovers DPB minute PDFs from the archive page
    2. Downloads each PDF
    3. Extracts text using pdfplumber
    4. Stores extracted text in documents table
    5. Deduplicates by source_url
    
    Args:
        db_pool: asyncpg connection pool
        max_documents: Optional limit on number of documents to process
    
    Returns:
        Dict with processing statistics:
        {
            'documents_discovered': int,
            'documents_downloaded': int,
            'documents_stored': int,
            'errors': [list of error messages]
        }
    """
    logger.info("Starting DPB minutes scraper")
    
    stats = {
        'documents_discovered': 0,
        'documents_downloaded': 0,
        'documents_stored': 0,
        'errors': []
    }
    
    connector = aiohttp.TCPConnector(limit=10)
    timeout = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        try:
            # Step 1: Discover DPB minutes
            documents = await discover_dpb_minutes(session)
            stats['documents_discovered'] = len(documents)
            
            # Apply max_documents limit if specified
            if max_documents:
                documents = documents[:max_documents]
            
            # Step 2: Download and store each document
            for idx, doc_info in enumerate(documents, 1):
                try:
                    logger.info(f"Processing document {idx}/{len(documents)}: {doc_info['filename']}")
                    
                    # Download and parse PDF
                    pdf_data = await download_and_parse_pdf(session, doc_info['url'])
                    
                    if not pdf_data:
                        logger.warning(f"Failed to download PDF: {doc_info['url']}")
                        stats['errors'].append(f"Failed to download: {doc_info['url']}")
                        continue
                    
                    stats['documents_downloaded'] += 1
                    
                    # Prepare metadata
                    metadata = {
                        'filename': doc_info['filename'],
                        'document_type': doc_info['type'],
                        'date': doc_info['date'],
                        'link_text': doc_info['link_text'],
                        'page_count': pdf_data['page_count'],
                    }
                    
                    # Store document
                    doc_id = await store_document(
                        db_pool,
                        url=doc_info['url'],
                        content=pdf_data['text'],
                        content_type='application/pdf',
                        metadata=metadata
                    )
                    
                    if doc_id:
                        stats['documents_stored'] += 1
                        logger.debug(f"Stored DPB document: {doc_id}")
                    
                    # Rate limit
                    await asyncio.sleep(REQUEST_DELAY)
                
                except Exception as e:
                    logger.error(f"Error processing document {doc_info['url']}: {e}")
                    stats['errors'].append(f"Processing error {doc_info['filename']}: {str(e)}")
                    continue
        
        except Exception as e:
            logger.error(f"Fatal error in DPB scraper: {e}")
            stats['errors'].append(f"Fatal error: {str(e)}")
    
    logger.info(f"DPB scraping completed. Stats: {stats}")
    return stats


def extract_date_from_text(text: str) -> str:
    """
    Extract date information from link text.
    
    Attempts to find common date patterns like "January 2024", "2024-01-15", etc.
    
    Args:
        text: Text to search for date patterns
    
    Returns:
        Date string if found, empty string otherwise
    """
    import re
    
    text_lower = text.lower()
    
    # Pattern: Month Year (e.g., "January 2024", "Feb 2023")
    month_year = re.search(
        r'(january|february|march|april|may|june|july|august|september|'
        r'october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{4})',
        text_lower
    )
    if month_year:
        return month_year.group(0)
    
    # Pattern: ISO format (e.g., "2024-01-15")
    iso_date = re.search(r'\d{4}-\d{2}-\d{2}', text)
    if iso_date:
        return iso_date.group(0)
    
    # Pattern: Year only (e.g., "2024")
    year = re.search(r'\b(20\d{2})\b', text)
    if year:
        return year.group(0)
    
    return ""
