"""
URL document scraper for VanCity Lens.

Downloads documents from external URLs (PDFs, HTML pages), parses them,
and stores them in the documents table. Supports automatic dedup via
source_url UNIQUE constraint.
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import urlparse

import aiohttp

from .parser import parse_pdf, parse_html

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
DOWNLOAD_TIMEOUT = 120  # seconds


async def scrape_url(
    db_pool,
    url: str,
    source_type: str = "external",
    title: Optional[str] = None,
) -> dict:
    """
    Download a document from a URL, parse it, and store in the documents table.

    Args:
        db_pool: asyncpg connection pool
        url: The URL to download
        source_type: Document source type for the documents table
        title: Optional title override; if not provided, derived from URL

    Returns:
        dict with document_id, title, text_length, page_count, status ("new" or "exists")

    Raises:
        ValueError: For invalid URLs, download failures, or parse failures
    """
    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid URL scheme: {parsed.scheme}. Only http/https supported."
        )
    if not parsed.netloc:
        raise ValueError("Invalid URL: missing hostname")

    # Download
    timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    raise ValueError(f"Download failed: HTTP {resp.status}")

                content_type = resp.headers.get("Content-Type", "").lower()
                content_length = resp.content_length or 0
                if content_length > MAX_DOWNLOAD_SIZE:
                    raise ValueError(
                        f"File too large: {content_length / 1024 / 1024:.1f} MB "
                        f"(max {MAX_DOWNLOAD_SIZE / 1024 / 1024:.0f} MB)"
                    )

                data = await resp.read()
                if len(data) > MAX_DOWNLOAD_SIZE:
                    raise ValueError(
                        f"File too large: {len(data) / 1024 / 1024:.1f} MB "
                        f"(max {MAX_DOWNLOAD_SIZE / 1024 / 1024:.0f} MB)"
                    )
    except aiohttp.ClientError as e:
        raise ValueError(f"Download failed: {e}")

    # Detect content type and parse
    is_pdf = "application/pdf" in content_type or url.lower().endswith(".pdf")

    if is_pdf:
        result = parse_pdf(data)
        file_format = "pdf"
    else:
        text_content = data.decode("utf-8", errors="replace")
        result = parse_html(text_content, source_url=url)
        file_format = "html"

    if not result or not result.get("text"):
        raise ValueError("Failed to parse document: no text extracted")

    raw_text = result["text"]
    page_count = result.get("page_count", 1)

    # RAG-006: Extract metadata from parsed content
    doc_metadata: dict = {}
    if not is_pdf:
        # Extract og: meta tags from HTML
        doc_metadata = _extract_html_metadata(data.decode("utf-8", errors="replace"))
    else:
        # Extract PDF metadata if available from parser result
        if result.get("metadata"):
            doc_metadata = result["metadata"]

    # Derive title if not provided
    if not title:
        # Try og:title first
        if doc_metadata.get("og_title"):
            title = doc_metadata["og_title"]
        # Use last path segment as fallback title
        path = parsed.path.rstrip("/")
        title = path.split("/")[-1] if path else parsed.netloc
        # Clean up file extensions
        for ext in (".pdf", ".html", ".htm"):
            if title.lower().endswith(ext):
                title = title[: -len(ext)]
        title = title.replace("-", " ").replace("_", " ").strip() or parsed.netloc

    # Insert into documents table with ON CONFLICT for dedup
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO documents (source_type, source_url, title, raw_text,
                                   text_length, page_count, file_format, metadata, scraped_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW())
            ON CONFLICT (source_url) DO NOTHING
            RETURNING id
            """,
            source_type,
            url,
            title,
            raw_text,
            len(raw_text),
            page_count,
            file_format,
            json.dumps(doc_metadata) if doc_metadata else "{}",
        )

        if row:
            doc_id = row["id"]
            logger.info(
                f"Stored new document {doc_id}: {title} "
                f"({len(raw_text)} chars, {page_count} pages)"
            )
            return {
                "document_id": doc_id,
                "title": title,
                "text_length": len(raw_text),
                "page_count": page_count,
                "status": "new",
            }
        else:
            # Document already exists
            existing = await conn.fetchrow(
                "SELECT id, title, text_length, page_count FROM documents WHERE source_url = $1",
                url,
            )
            logger.info(f"Document already exists for URL: {url} (id={existing['id']})")
            return {
                "document_id": existing["id"],
                "title": existing["title"],
                "text_length": existing["text_length"],
                "page_count": existing["page_count"],
                "status": "exists",
            }


def _extract_html_metadata(html: str) -> dict:
    """
    RAG-006: Extract Open Graph and meta tags from HTML for richer document metadata.

    Extracts: og:title, og:description, og:site_name, article:published_time,
    meta description, meta author.
    """
    metadata: dict = {}

    # og:title
    m = re.search(
        r'<meta\s+(?:property|name)=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if m:
        metadata["og_title"] = m.group(1).strip()

    # og:description
    m = re.search(
        r'<meta\s+(?:property|name)=["\']og:description["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if m:
        metadata["og_description"] = m.group(1).strip()

    # og:site_name
    m = re.search(
        r'<meta\s+(?:property|name)=["\']og:site_name["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if m:
        metadata["og_site_name"] = m.group(1).strip()

    # article:published_time
    m = re.search(
        r'<meta\s+(?:property|name)=["\']article:published_time["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if m:
        metadata["article_published_time"] = m.group(1).strip()

    # meta description
    m = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if m:
        metadata["meta_description"] = m.group(1).strip()

    # meta author
    m = re.search(
        r'<meta\s+name=["\']author["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if m:
        metadata["meta_author"] = m.group(1).strip()

    return metadata
