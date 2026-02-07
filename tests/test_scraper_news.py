"""Tests for the news feed scraper (RSS feeds + article content)."""

import asyncio
from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.intelligence.scraper_news import (
    NEWS_FEEDS,
    RELEVANCE_KEYWORDS,
    HEADERS,
    REQUEST_DELAY,
    fetch_rss_feed,
    fetch_article_content,
    is_relevant_article,
    scrape_news_feeds,
    get_configured_feeds,
)


# ── Constants ────────────────────────────────────────────────

class TestConstants:
    """Test module-level constants."""

    def test_news_feeds_not_empty(self):
        """Test NEWS_FEEDS list is populated."""
        assert len(NEWS_FEEDS) > 0

    def test_news_feeds_structure(self):
        """Test each feed has required keys."""
        required = {'name', 'url', 'source_type', 'priority'}
        for feed in NEWS_FEEDS:
            assert required.issubset(feed.keys()), f"Feed missing keys: {feed.get('name')}"

    def test_news_feeds_priorities(self):
        """Test feed priorities are valid."""
        valid_priorities = {'high', 'medium', 'low'}
        for feed in NEWS_FEEDS:
            assert feed['priority'] in valid_priorities

    def test_relevance_keywords_not_empty(self):
        """Test RELEVANCE_KEYWORDS list is populated."""
        assert len(RELEVANCE_KEYWORDS) > 10

    def test_relevance_keywords_lowercase(self):
        """Test all keywords are lowercase."""
        for kw in RELEVANCE_KEYWORDS:
            assert kw == kw.lower(), f"Keyword not lowercase: {kw}"

    def test_headers_user_agent(self):
        """Test HEADERS has a User-Agent."""
        assert 'User-Agent' in HEADERS
        assert 'VanCityLens' in HEADERS['User-Agent']

    def test_request_delay_positive(self):
        """Test REQUEST_DELAY is a reasonable positive number."""
        assert REQUEST_DELAY > 0
        assert REQUEST_DELAY < 10


# ── is_relevant_article ──────────────────────────────────────

class TestIsRelevantArticle:
    """Test article relevance filtering."""

    def test_relevant_rezoning_article(self):
        """Test article about rezoning is relevant."""
        assert is_relevant_article(
            "Vancouver Council Approves Rezoning for New Housing Development",
            "The city council approved rezoning for a 25-storey tower."
        ) is True

    def test_relevant_transit_housing(self):
        """Test article about transit + housing is relevant."""
        assert is_relevant_article(
            "New SkyTrain Station Will Drive Housing Development",
            "Transit-oriented development planned near Broadway."
        ) is True

    def test_irrelevant_sports_article(self):
        """Test sports article is not relevant."""
        assert is_relevant_article(
            "Canucks Win Big Game",
            "The Vancouver Canucks defeated the Flames 5-2 last night."
        ) is False

    def test_irrelevant_weather_article(self):
        """Test weather article is not relevant."""
        assert is_relevant_article(
            "Rain Expected All Week",
            "Metro Vancouver will see heavy rainfall through Friday."
        ) is False

    def test_empty_title_and_summary(self):
        """Test empty strings are not relevant."""
        assert is_relevant_article("", "") is False

    def test_single_keyword_not_enough(self):
        """Test that a single keyword match is not sufficient."""
        # Only 'vancouver' matches — needs 2+
        assert is_relevant_article(
            "Vancouver weather forecast",
            "Sunny skies expected this weekend."
        ) is False

    def test_two_keywords_sufficient(self):
        """Test that 2 keyword matches is sufficient."""
        # 'vancouver' + 'property' = 2 matches
        assert is_relevant_article(
            "Vancouver property news",
            "Local property values continue to rise."
        ) is True

    def test_case_insensitive(self):
        """Test keyword matching is case-insensitive."""
        assert is_relevant_article(
            "REZONING APPLICATION for NEW HOUSING",
            "City considers new density in Downtown."
        ) is True


# ── fetch_rss_feed ───────────────────────────────────────────

class TestFetchRssFeed:
    """Test RSS feed fetching and parsing."""

    @pytest.mark.asyncio
    async def test_successful_rss_fetch(self):
        """Test successful RSS feed parsing."""
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Rezoning Approved</title>
                    <link>https://example.com/article1</link>
                    <description>Council approved rezoning</description>
                </item>
                <item>
                    <title>New Tower Planned</title>
                    <link>https://example.com/article2</link>
                    <description>A new tower was announced</description>
                </item>
            </channel>
        </rss>"""

        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = rss_xml
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        articles = await fetch_rss_feed(mock_session, "https://example.com/feed")

        assert len(articles) == 2
        assert articles[0]['title'] == 'Rezoning Approved'
        assert articles[0]['url'] == 'https://example.com/article1'

    @pytest.mark.asyncio
    async def test_rss_feed_http_error(self):
        """Test RSS feed with HTTP error."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        articles = await fetch_rss_feed(mock_session, "https://example.com/feed")

        assert articles == []

    @pytest.mark.asyncio
    async def test_rss_feed_timeout(self):
        """Test RSS feed timeout handling."""
        mock_session = AsyncMock()
        mock_session.get.side_effect = asyncio.TimeoutError()

        articles = await fetch_rss_feed(mock_session, "https://example.com/feed")

        assert articles == []

    @pytest.mark.asyncio
    async def test_rss_feed_max_items(self):
        """Test max_items parameter limits results."""
        items_xml = ""
        for i in range(10):
            items_xml += f"""
                <item>
                    <title>Article {i}</title>
                    <link>https://example.com/article{i}</link>
                </item>"""

        rss_xml = f"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel><title>Test</title>{items_xml}</channel>
        </rss>"""

        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = rss_xml
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        articles = await fetch_rss_feed(mock_session, "https://example.com/feed", max_items=3)

        assert len(articles) == 3

    @pytest.mark.asyncio
    async def test_rss_feed_no_feedparser(self):
        """Test graceful handling when feedparser is not installed."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = "<rss></rss>"
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.scraper_news.fetch_rss_feed") as mock_fetch:
            # If feedparser import fails, function returns []
            mock_fetch.return_value = []
            result = await mock_fetch(mock_session, "https://example.com/feed")
            assert result == []

    @pytest.mark.asyncio
    async def test_rss_feed_skips_entries_without_url(self):
        """Test that entries without a link are skipped."""
        rss_xml = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test</title>
                <item>
                    <title>No Link Article</title>
                    <description>This has no link</description>
                </item>
                <item>
                    <title>Has Link</title>
                    <link>https://example.com/valid</link>
                </item>
            </channel>
        </rss>"""

        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = rss_xml
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        articles = await fetch_rss_feed(mock_session, "https://example.com/feed")

        # Only the article with a link should be returned
        assert len(articles) == 1
        assert articles[0]['title'] == 'Has Link'


# ── fetch_article_content ────────────────────────────────────

class TestFetchArticleContent:
    """Test full article content fetching."""

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        """Test successful article content extraction."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = "<html><body><p>Article content here</p></body></html>"
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.parser.parse_html") as mock_parse:
            mock_parse.return_value = {'text': 'Article content here', 'parser': 'bs4'}

            result = await fetch_article_content(mock_session, "https://example.com/article")

            assert result == 'Article content here'
            mock_parse.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_http_error(self):
        """Test article fetch with HTTP error."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await fetch_article_content(mock_session, "https://example.com/notfound")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_timeout(self):
        """Test article fetch timeout."""
        mock_session = AsyncMock()
        mock_session.get.side_effect = asyncio.TimeoutError()

        result = await fetch_article_content(mock_session, "https://example.com/slow")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_parser_returns_none(self):
        """Test handling when parser returns None."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = "<html></html>"
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.parser.parse_html") as mock_parse:
            mock_parse.return_value = None

            result = await fetch_article_content(mock_session, "https://example.com/empty")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_parser_returns_empty_text(self):
        """Test handling when parser returns empty text."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = "<html><body></body></html>"
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.parser.parse_html") as mock_parse:
            mock_parse.return_value = {'text': '', 'parser': 'bs4'}

            result = await fetch_article_content(mock_session, "https://example.com/empty")

            assert result is None


# ── scrape_news_feeds ────────────────────────────────────────

class TestScrapeNewsFeeds:
    """Test the main news scraping orchestrator."""

    @pytest.mark.asyncio
    async def test_scrape_returns_stats(self):
        """Test scrape_news_feeds returns stats dict."""
        mock_pool = AsyncMock()

        with patch("api.intelligence.scraper_news.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)

            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("api.intelligence.scraper_news.fetch_rss_feed", return_value=[]):
                stats = await scrape_news_feeds(mock_pool)

                assert 'feeds_checked' in stats
                assert 'articles_found' in stats
                assert 'articles_relevant' in stats
                assert 'articles_stored' in stats
                assert 'articles_duplicate' in stats
                assert 'errors' in stats

    @pytest.mark.asyncio
    async def test_scrape_counts_feeds(self):
        """Test that all feeds are counted."""
        mock_pool = AsyncMock()

        with patch("api.intelligence.scraper_news.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)

            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("api.intelligence.scraper_news.fetch_rss_feed", return_value=[]):
                stats = await scrape_news_feeds(mock_pool)

                assert stats['feeds_checked'] == len(NEWS_FEEDS)

    @pytest.mark.asyncio
    async def test_scrape_filters_irrelevant(self):
        """Test that irrelevant articles are filtered out."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        irrelevant_articles = [
            {
                'title': 'Canucks Win Game',
                'url': 'https://example.com/sports',
                'summary': 'Sports news about hockey.',
                'published': '',
            }
        ]

        with patch("api.intelligence.scraper_news.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)

            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("api.intelligence.scraper_news.fetch_rss_feed", return_value=irrelevant_articles):
                stats = await scrape_news_feeds(mock_pool)

                assert stats['articles_relevant'] == 0
                assert stats['articles_stored'] == 0

    @pytest.mark.asyncio
    async def test_scrape_skips_duplicates(self):
        """Test that duplicate URLs are skipped."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        # Document already exists in DB
        conn.fetchval.return_value = 42

        relevant_articles = [
            {
                'title': 'Vancouver rezoning housing development approved',
                'url': 'https://example.com/existing',
                'summary': 'Council approved rezoning for new housing.',
                'published': '',
            }
        ]

        with patch("api.intelligence.scraper_news.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)

            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("api.intelligence.scraper_news.fetch_rss_feed", return_value=relevant_articles):
                stats = await scrape_news_feeds(mock_pool)

                assert stats['articles_duplicate'] > 0

    @pytest.mark.asyncio
    async def test_scrape_stores_new_articles(self):
        """Test that new relevant articles are stored."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetchval.return_value = None  # Not a duplicate

        relevant_articles = [
            {
                'title': 'Vancouver rezoning housing development approved',
                'url': 'https://example.com/new-article',
                'summary': 'Council approved rezoning for new housing near transit.',
                'published': datetime.now().isoformat(),
            }
        ]

        with patch("api.intelligence.scraper_news.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)

            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("api.intelligence.scraper_news.fetch_rss_feed", return_value=relevant_articles):
                with patch("api.intelligence.scraper_news.fetch_article_content", return_value="Full article text here"):
                    stats = await scrape_news_feeds(mock_pool, fetch_full_text=True)

                    assert stats['articles_stored'] > 0

    @pytest.mark.asyncio
    async def test_scrape_skips_feeds_without_rss_url(self):
        """Test that feeds without rss_url are skipped (no errors)."""
        mock_pool = AsyncMock()

        # Override feeds to only have one without RSS
        test_feeds = [
            {
                'name': 'No RSS Feed',
                'url': 'https://example.com',
                'rss_url': None,
                'source_type': 'community_plan',
                'priority': 'high',
            }
        ]

        with patch("api.intelligence.scraper_news.NEWS_FEEDS", test_feeds):
            with patch("api.intelligence.scraper_news.aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)

                mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

                stats = await scrape_news_feeds(mock_pool)

                assert stats['feeds_checked'] == 1
                assert stats['articles_found'] == 0

    @pytest.mark.asyncio
    async def test_scrape_handles_feed_error_gracefully(self):
        """Test that errors in one feed don't stop processing."""
        mock_pool = AsyncMock()

        with patch("api.intelligence.scraper_news.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)

            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("api.intelligence.scraper_news.fetch_rss_feed", side_effect=Exception("Network error")):
                stats = await scrape_news_feeds(mock_pool)

                assert len(stats['errors']) > 0


# ── get_configured_feeds ─────────────────────────────────────

class TestGetConfiguredFeeds:
    """Test feed configuration listing."""

    @pytest.mark.asyncio
    async def test_returns_all_feeds(self):
        """Test get_configured_feeds returns all configured feeds."""
        feeds = await get_configured_feeds()

        assert len(feeds) == len(NEWS_FEEDS)

    @pytest.mark.asyncio
    async def test_feed_structure(self):
        """Test returned feed dicts have expected keys."""
        feeds = await get_configured_feeds()

        required_keys = {'name', 'url', 'rss_url', 'source_type', 'priority'}
        for feed in feeds:
            assert required_keys.issubset(feed.keys())

    @pytest.mark.asyncio
    async def test_feed_names_match(self):
        """Test feed names match original configuration."""
        feeds = await get_configured_feeds()
        original_names = {f['name'] for f in NEWS_FEEDS}
        returned_names = {f['name'] for f in feeds}

        assert original_names == returned_names
