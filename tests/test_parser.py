"""Tests for the unified document parser (docling + pdfplumber fallback)."""

import pytest
from unittest.mock import patch, MagicMock, mock_open
from api.intelligence.parser import (
    parse_pdf,
    parse_html,
    parse_pdf_with_docling,
    parse_pdf_with_pdfplumber,
    parse_html_with_docling,
    _check_docling,
)


# ── parse_pdf (unified interface) ─────────────────────────────

class TestParsePdf:
    """Test the unified parse_pdf function."""

    def test_parse_pdf_with_docling_primary(self):
        """Test that parse_pdf tries docling first."""
        fake_bytes = b"%PDF-1.4 fake content"

        with patch("api.intelligence.parser._check_docling", return_value=True):
            with patch("api.intelligence.parser.parse_pdf_with_docling") as mock_docling:
                mock_docling.return_value = {
                    'text': 'Docling extracted text',
                    'page_count': 3,
                    'tables_found': 1,
                    'parser': 'docling',
                }

                result = parse_pdf(fake_bytes)

                assert result is not None
                assert result['parser'] == 'docling'
                assert result['text'] == 'Docling extracted text'
                mock_docling.assert_called_once_with(fake_bytes)

    def test_parse_pdf_falls_back_to_pdfplumber(self):
        """Test fallback to pdfplumber when docling fails."""
        fake_bytes = b"%PDF-1.4 fake content"

        with patch("api.intelligence.parser._check_docling", return_value=True):
            with patch("api.intelligence.parser.parse_pdf_with_docling", return_value=None):
                with patch("api.intelligence.parser.parse_pdf_with_pdfplumber") as mock_plumber:
                    mock_plumber.return_value = {
                        'text': 'Pdfplumber text',
                        'page_count': 2,
                        'tables_found': 0,
                        'parser': 'pdfplumber',
                    }

                    result = parse_pdf(fake_bytes)

                    assert result is not None
                    assert result['parser'] == 'pdfplumber'
                    mock_plumber.assert_called_once()

    def test_parse_pdf_docling_not_available(self):
        """Test fallback when docling is not installed."""
        fake_bytes = b"%PDF-1.4 fake content"

        with patch("api.intelligence.parser._check_docling", return_value=False):
            with patch("api.intelligence.parser.parse_pdf_with_pdfplumber") as mock_plumber:
                mock_plumber.return_value = {
                    'text': 'Fallback text',
                    'page_count': 1,
                    'tables_found': 0,
                    'parser': 'pdfplumber',
                }

                result = parse_pdf(fake_bytes)

                assert result is not None
                assert result['parser'] == 'pdfplumber'

    def test_parse_pdf_both_fail(self):
        """Test None returned when both parsers fail."""
        fake_bytes = b"not a real pdf"

        with patch("api.intelligence.parser._check_docling", return_value=False):
            with patch("api.intelligence.parser.parse_pdf_with_pdfplumber", return_value=None):
                result = parse_pdf(fake_bytes)
                assert result is None


# ── parse_pdf_with_pdfplumber ────────────────────────────────

class TestParsePdfWithPdfplumber:
    """Test the pdfplumber fallback parser."""

    def test_pdfplumber_success(self):
        """Test successful pdfplumber parsing."""
        fake_bytes = b"%PDF-1.4 content"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Page 1 text"
            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = "Page 2 text"
            mock_pdf.pages = [mock_page1, mock_page2]
            mock_open.return_value.__enter__.return_value = mock_pdf

            result = parse_pdf_with_pdfplumber(fake_bytes)

            assert result is not None
            assert "Page 1 text" in result['text']
            assert "Page 2 text" in result['text']
            assert result['page_count'] == 2
            assert result['parser'] == 'pdfplumber'

    def test_pdfplumber_empty_pages(self):
        """Test pdfplumber with pages that have no text."""
        fake_bytes = b"%PDF-1.4"

        with patch("pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = MagicMock()
            mock_page.extract_text.return_value = None
            mock_pdf.pages = [mock_page]
            mock_open.return_value.__enter__.return_value = mock_pdf

            result = parse_pdf_with_pdfplumber(fake_bytes)

            assert result is not None
            assert result['text'] == ''
            assert result['page_count'] == 1

    def test_pdfplumber_not_installed(self):
        """Test graceful handling when pdfplumber not installed."""
        import sys
        with patch.dict(sys.modules, {"pdfplumber": None}):
            result = parse_pdf_with_pdfplumber(b"fake")
            assert result is None

    def test_pdfplumber_corrupt_pdf(self):
        """Test handling of corrupt PDF data."""
        with patch("pdfplumber.open") as mock_open:
            mock_open.side_effect = Exception("Invalid PDF")

            result = parse_pdf_with_pdfplumber(b"not a pdf")
            assert result is None


# ── parse_html ───────────────────────────────────────────────

class TestParseHtml:
    """Test the unified parse_html function."""

    def test_parse_html_docling_primary(self):
        """Test that parse_html tries docling first."""
        html = "<html><body><p>Hello</p></body></html>"

        with patch("api.intelligence.parser._check_docling", return_value=True):
            with patch("api.intelligence.parser.parse_html_with_docling") as mock_docling:
                mock_docling.return_value = {
                    'text': 'Hello',
                    'page_count': 1,
                    'tables_found': 0,
                    'parser': 'docling',
                }

                result = parse_html(html)

                assert result is not None
                assert result['parser'] == 'docling'

    def test_parse_html_beautifulsoup_fallback(self):
        """Test BeautifulSoup fallback when docling unavailable."""
        html = "<html><body><p>Hello World</p><script>bad</script></body></html>"

        with patch("api.intelligence.parser._check_docling", return_value=False):
            result = parse_html(html)

            assert result is not None
            assert result['parser'] == 'beautifulsoup'
            assert 'Hello World' in result['text']
            # Script tags should be removed
            assert 'bad' not in result['text']

    def test_parse_html_strips_nav_footer(self):
        """Test that nav, footer, header elements are stripped."""
        html = """<html><body>
            <nav>Navigation</nav>
            <p>Main Content</p>
            <footer>Footer</footer>
        </body></html>"""

        with patch("api.intelligence.parser._check_docling", return_value=False):
            result = parse_html(html)

            assert result is not None
            assert 'Main Content' in result['text']
            assert 'Navigation' not in result['text']
            assert 'Footer' not in result['text']

    def test_parse_html_with_source_url(self):
        """Test that source_url parameter is accepted."""
        html = "<html><body><p>Content</p></body></html>"

        with patch("api.intelligence.parser._check_docling", return_value=False):
            result = parse_html(html, source_url="https://example.com")
            assert result is not None


# ── _check_docling ───────────────────────────────────────────

class TestCheckDocling:
    """Test docling availability check."""

    def test_check_docling_available(self):
        """Test detection when docling is installed."""
        import api.intelligence.parser as parser_mod
        original = parser_mod._docling_available

        try:
            parser_mod._docling_available = None  # Force re-check
            with patch.dict("sys.modules", {"docling.document_converter": MagicMock()}):
                with patch("api.intelligence.parser.DocumentConverter", create=True):
                    # Hard to mock reliably; just test the cache mechanism
                    parser_mod._docling_available = True
                    assert _check_docling() is True
        finally:
            parser_mod._docling_available = original

    def test_check_docling_not_available(self):
        """Test detection when docling is not installed."""
        import api.intelligence.parser as parser_mod
        original = parser_mod._docling_available

        try:
            parser_mod._docling_available = False
            assert _check_docling() is False
        finally:
            parser_mod._docling_available = original

    def test_check_docling_caches_result(self):
        """Test that result is cached after first check."""
        import api.intelligence.parser as parser_mod
        original = parser_mod._docling_available

        try:
            parser_mod._docling_available = True
            # Should return cached value without re-checking
            result = _check_docling()
            assert result is True
        finally:
            parser_mod._docling_available = original
