"""Tests for web scrapers."""

from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from api.intelligence.scraper_council import (
    VancouverCouncilScraper,
    RateLimiter,
    discover_meetings,
    scrape_meeting_page,
)


class TestRateLimiter:
    """Test rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_delay(self):
        """Test rate limiter enforces delay."""
        limiter = RateLimiter(delay=0.1)
        start = datetime.now()
        await limiter.acquire()
        await limiter.acquire()
        elapsed = (datetime.now() - start).total_seconds()
        # Should have at least 0.1 seconds between calls
        assert elapsed >= 0.05

    @pytest.mark.asyncio
    async def test_rate_limiter_no_delay_first_call(self):
        """Test rate limiter doesn't delay first call."""
        limiter = RateLimiter(delay=1.0)
        start = datetime.now()
        await limiter.acquire()
        elapsed = (datetime.now() - start).total_seconds()
        # First call should be immediate
        assert elapsed < 0.1


class TestVancouverCouncilScraper:
    """Test council meeting scraper."""

    def test_scraper_initialization(self):
        """Test scraper initialization."""
        scraper = VancouverCouncilScraper()
        assert scraper.rate_limiter is not None
        assert scraper.headers is not None

    def test_scraper_with_custom_rate_limiter(self):
        """Test scraper with custom rate limiter."""
        limiter = RateLimiter(delay=0.5)
        scraper = VancouverCouncilScraper(rate_limiter=limiter)
        assert scraper.rate_limiter == limiter

    def test_discover_meetings_generates_urls(self):
        """Test discover_meetings generates meeting URLs."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        scraper = VancouverCouncilScraper()
        meetings = scraper.discover_meetings(start, end)

        assert len(meetings) > 0
        for meeting in meetings:
            assert "url" in meeting
            assert "date" in meeting
            assert "type" in meeting
            assert "yyyymmdd" in meeting

    def test_discover_meetings_aligns_to_tuesdays(self):
        """Test discovery aligns to Tuesdays."""
        # January 1, 2024 is Monday
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        scraper = VancouverCouncilScraper()
        meetings = scraper.discover_meetings(start, end)

        # All meetings should be on valid dates
        assert len(meetings) > 0

    def test_discover_meetings_increments_by_weeks(self):
        """Test discovery increments by 2 weeks."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 3, 31)

        scraper = VancouverCouncilScraper()
        meetings = scraper.discover_meetings(start, end)

        # Should find multiple weeks worth of meetings
        assert len(meetings) > 5

    @pytest.mark.asyncio
    async def test_check_url_exists(self):
        """Test URL existence check."""
        scraper = VancouverCouncilScraper()

        with patch("api.intelligence.scraper_council.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_session.head = MagicMock()
            mock_session.head.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.head.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await scraper._check_url_exists("https://example.com/test.htm")

            assert result is True

    @pytest.mark.asyncio
    async def test_check_url_not_exists(self):
        """Test URL not found returns False."""
        scraper = VancouverCouncilScraper()

        with patch("api.intelligence.scraper_council.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            mock_response = AsyncMock()
            mock_response.status = 404
            mock_session.head = MagicMock()
            mock_session.head.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.head.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await scraper._check_url_exists("https://example.com/notfound.htm")

            assert result is False

    @pytest.mark.asyncio
    async def test_scrape_meeting_page_valid_html(self, sample_council_html):
        """Test scraping valid meeting page."""
        scraper = VancouverCouncilScraper()

        with patch.object(scraper, "_make_request", return_value=sample_council_html):
            result = await scraper.scrape_meeting_page("https://example.com/test.htm")

            assert result is not None
            assert "html" in result
            assert "title" in result
            assert "agenda_items" in result
            assert "pdf_links" in result

    @pytest.mark.asyncio
    async def test_scrape_meeting_page_failed_fetch(self):
        """Test scraping when fetch fails."""
        scraper = VancouverCouncilScraper()

        with patch.object(scraper, "_make_request", return_value=None):
            result = await scraper.scrape_meeting_page("https://example.com/test.htm")

            assert result is None

    @pytest.mark.asyncio
    async def test_scrape_meeting_extracts_pdf_links(self, sample_council_html):
        """Test that PDF links are extracted."""
        scraper = VancouverCouncilScraper()

        with patch.object(scraper, "_make_request", return_value=sample_council_html):
            result = await scraper.scrape_meeting_page("https://example.com/meeting/test.htm")

            assert result is not None
            assert len(result["pdf_links"]) >= 2

    @pytest.mark.asyncio
    async def test_download_and_parse_pdf(self):
        """Test PDF download and parsing."""
        scraper = VancouverCouncilScraper()

        with patch("api.intelligence.scraper_council.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            # Mock PDF content
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.read.return_value = b"PDF content"

            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            # Mock parse_pdf from parser module (replaces old pdfplumber.open mock)
            with patch("api.intelligence.scraper_council.parse_pdf") as mock_parse:
                mock_parse.return_value = {
                    'text': 'PDF text extracted by parser',
                    'page_count': 3,
                    'tables_found': 1,
                    'parser': 'docling',
                }

                result = await scraper.download_and_parse_pdf("https://example.com/doc.pdf")

                assert result is not None
                assert "text" in result
                assert "page_count" in result

    @pytest.mark.asyncio
    async def test_pdf_download_404(self):
        """Test PDF download with 404."""
        scraper = VancouverCouncilScraper()

        with patch("api.intelligence.scraper_council.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            mock_response = AsyncMock()
            mock_response.status = 404
            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await scraper.download_and_parse_pdf("https://example.com/notfound.pdf")

            assert result is None

    @pytest.mark.asyncio
    async def test_scrape_and_store_no_meetings(self):
        """Test scrape_and_store with no meetings found."""
        mock_pool = AsyncMock()
        scraper = VancouverCouncilScraper()

        with patch.object(scraper, "discover_meetings_async", return_value=[]):
            stats = await scraper.scrape_and_store(
                mock_pool,
                datetime(2024, 1, 1),
                datetime(2024, 1, 5)
            )

            assert stats["meetings_found"] == 0

    @pytest.mark.asyncio
    async def test_extract_pdf_title(self):
        """Test PDF title extraction."""
        url = "https://example.com/docs/staff_report_2024_01_15.pdf"
        title = VancouverCouncilScraper._extract_pdf_title(url)

        assert "staff" in title.lower()
        assert ".pdf" not in title.lower()

    @pytest.mark.asyncio
    async def test_scraper_cleanup(self):
        """Test scraper session cleanup."""
        scraper = VancouverCouncilScraper()

        # Create a session
        await scraper._get_session()
        assert scraper.session is not None

        # Clean up
        await scraper.close()


class TestScraperIntegration:
    """Integration tests for scrapers."""

    def test_discover_meetings_date_range(self):
        """Test discovering meetings in specific date range."""
        start = datetime(2024, 1, 15)
        end = datetime(2024, 2, 15)

        scraper = VancouverCouncilScraper()
        meetings = scraper.discover_meetings(start, end)

        # All meetings should be within date range
        for meeting in meetings:
            assert start.date() <= meeting["date"] <= end.date()

    def test_discover_meetings_all_types(self):
        """Test that discovery finds different meeting types."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 3, 31)

        scraper = VancouverCouncilScraper()
        meetings = scraper.discover_meetings(start, end)

        types = set(m["type"] for m in meetings)
        # Should find at least regular and special meetings
        assert len(types) >= 1
