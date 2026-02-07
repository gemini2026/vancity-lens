"""
Document parsing module using docling for VanCity Lens.

Provides unified PDF and HTML parsing with docling as primary parser
and pdfplumber as fallback. Docling provides superior table extraction,
layout understanding, and markdown output compared to pdfplumber.

Architecture:
  - Primary: docling DocumentConverter (PDF, HTML, DOCX, etc.)
  - Fallback: pdfplumber for simple text extraction
  - Output: Clean markdown text suitable for chunking
"""

import logging
import tempfile
import os
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── Lazy-load docling to avoid import overhead ────────────────

_docling_available = None


def _check_docling():
    """Check if docling is available."""
    global _docling_available
    if _docling_available is not None:
        return _docling_available
    try:
        from docling.document_converter import DocumentConverter
        _docling_available = True
        logger.info("docling available for document parsing")
    except ImportError:
        _docling_available = False
        logger.warning("docling not installed — falling back to pdfplumber")
    return _docling_available


# ── Primary: docling-based parsing ────────────────────────────

def parse_pdf_with_docling(pdf_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Parse a PDF using docling for high-quality text + table extraction.

    Docling provides:
    - Layout-aware text extraction
    - Table detection and markdown rendering
    - Header/section detection
    - Clean markdown output

    Args:
        pdf_bytes: Raw PDF file content

    Returns:
        Dict with 'text' (markdown), 'page_count', 'tables_found'
        or None on failure
    """
    try:
        from docling.document_converter import DocumentConverter

        # Write bytes to a temp file (docling needs a file path)
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            doc = result.document

            # Export as markdown for clean text
            markdown_text = doc.export_to_markdown()

            # Count tables
            tables_found = 0
            try:
                tables_found = len(doc.tables) if hasattr(doc, 'tables') else 0
            except Exception:
                pass

            # Estimate page count from the document
            page_count = 0
            try:
                page_count = len(doc.pages) if hasattr(doc, 'pages') else 0
            except Exception:
                pass

            logger.info(
                f"docling parsed PDF: {len(markdown_text)} chars, "
                f"{page_count} pages, {tables_found} tables"
            )

            return {
                'text': markdown_text,
                'page_count': page_count,
                'tables_found': tables_found,
                'parser': 'docling',
            }

        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except ImportError:
        logger.warning("docling not available for PDF parsing")
        return None
    except Exception as e:
        logger.error(f"docling PDF parsing failed: {e}")
        return None


def parse_html_with_docling(html_content: str, source_url: str = "") -> Optional[Dict[str, Any]]:
    """
    Parse HTML content using docling for clean text extraction.

    Args:
        html_content: Raw HTML string
        source_url: Source URL for reference

    Returns:
        Dict with 'text' (markdown), or None on failure
    """
    try:
        from docling.document_converter import DocumentConverter

        # Write HTML to temp file
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w') as tmp:
            tmp.write(html_content)
            tmp_path = tmp.name

        try:
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            doc = result.document

            markdown_text = doc.export_to_markdown()

            logger.info(f"docling parsed HTML: {len(markdown_text)} chars")

            return {
                'text': markdown_text,
                'page_count': 1,
                'tables_found': 0,
                'parser': 'docling',
            }

        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except ImportError:
        logger.warning("docling not available for HTML parsing")
        return None
    except Exception as e:
        logger.error(f"docling HTML parsing failed: {e}")
        return None


# ── Fallback: pdfplumber-based parsing ────────────────────────

def parse_pdf_with_pdfplumber(pdf_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Fallback PDF parsing using pdfplumber.

    Simpler extraction, no table detection, but reliable and fast.

    Args:
        pdf_bytes: Raw PDF file content

    Returns:
        Dict with 'text', 'page_count' or None on failure
    """
    try:
        import pdfplumber

        pdf_buffer = BytesIO(pdf_bytes)

        with pdfplumber.open(pdf_buffer) as pdf:
            text_parts = []
            page_count = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                except Exception as e:
                    logger.warning(f"pdfplumber error on page {page_num}: {e}")

            full_text = '\n\n'.join(text_parts)

        logger.info(f"pdfplumber parsed PDF: {len(full_text)} chars, {page_count} pages")

        return {
            'text': full_text,
            'page_count': page_count,
            'tables_found': 0,
            'parser': 'pdfplumber',
        }

    except ImportError:
        logger.error("pdfplumber not installed")
        return None
    except Exception as e:
        logger.error(f"pdfplumber parsing failed: {e}")
        return None


# ── Unified parser interface ──────────────────────────────────

def parse_pdf(pdf_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Parse a PDF using the best available parser.

    Tries docling first (superior quality), falls back to pdfplumber.

    Args:
        pdf_bytes: Raw PDF file content

    Returns:
        Dict with 'text', 'page_count', 'tables_found', 'parser'
        or None if all parsers fail
    """
    if _check_docling():
        result = parse_pdf_with_docling(pdf_bytes)
        if result and result.get('text'):
            return result
        logger.warning("docling returned empty result, trying pdfplumber")

    return parse_pdf_with_pdfplumber(pdf_bytes)


def parse_html(html_content: str, source_url: str = "") -> Optional[Dict[str, Any]]:
    """
    Parse HTML content to clean text.

    Tries docling first, falls back to BeautifulSoup.

    Args:
        html_content: Raw HTML string
        source_url: Source URL

    Returns:
        Dict with 'text', 'page_count', 'parser' or None
    """
    if _check_docling():
        result = parse_html_with_docling(html_content, source_url)
        if result and result.get('text'):
            return result

    # Fallback: BeautifulSoup
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove script and style elements
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()

        text = soup.get_text(separator='\n', strip=True)

        # Clean up multiple blank lines
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)

        logger.info(f"BeautifulSoup parsed HTML: {len(text)} chars")

        return {
            'text': text,
            'page_count': 1,
            'tables_found': 0,
            'parser': 'beautifulsoup',
        }

    except Exception as e:
        logger.error(f"HTML parsing failed: {e}")
        return None
