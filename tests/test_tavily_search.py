"""
Tests for Tavily-powered search enhancement.

All Tavily API calls are mocked — no real API key or network access needed.
Tests cover:
- search_web() with mocked TavilyClient.search
- extract_content() with mocked TavilyClient.extract
- store_document() dedup via ON CONFLICT DO NOTHING
- search_and_store() full pipeline (search + extract + store)
- Graceful handling: missing API key, API errors, DB errors
"""

import asyncio
import json
import os
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Module Import ─────────────────────────────────────────────
# tavily_search uses lazy-loaded env vars, so import is safe without TAVILY_API_KEY

from api.intelligence.tavily_search import (
    DEFAULT_QUERIES,
    MAX_RESULTS_PER_QUERY,
    MAX_EXTRACT_URLS,
    SEARCH_DAYS,
    _get_api_key,
    _get_client,
    search_web,
    extract_content,
    store_document,
    search_and_store,
)


# ── Fixtures ──────────────────────────────────────────────────

MOCK_SEARCH_RESULTS = {
    "results": [
        {
            "title": "Vancouver Rezoning Application 2026: Major Changes Coming",
            "url": "https://example.com/rezoning-2026",
            "content": "Vancouver city council approved a major rezoning application...",
            "published_date": "2026-02-10",
        },
        {
            "title": "Bill 47 TOD Development in Vancouver",
            "url": "https://example.com/bill47-tod",
            "content": "Transit-oriented development under Bill 47 is accelerating...",
            "published_date": "2026-02-12",
        },
        {
            "title": "New Density Policies for Vancouver Neighborhoods",
            "url": "https://example.com/density-news",
            "content": "New density bonuses announced for several Vancouver neighborhoods.",
            "published_date": None,
        },
    ]
}

MOCK_EXTRACT_RESULTS = {
    "results": [
        {
            "url": "https://example.com/rezoning-2026",
            "raw_content": "# Vancouver Rezoning 2026\n\nFull article content here with detailed analysis of the rezoning proposal...",
        },
        {
            "url": "https://example.com/bill47-tod",
            "raw_content": "# Bill 47 TOD\n\nTransit-oriented development is transforming Vancouver neighborhoods...",
        },
    ]
}


def _make_mock_client(search_return=None, extract_return=None):
    """Create a mock TavilyClient with configurable returns."""
    client = MagicMock()
    client.search.return_value = search_return or MOCK_SEARCH_RESULTS
    client.extract.return_value = extract_return or MOCK_EXTRACT_RESULTS
    return client


def _make_mock_pool(mock_conn):
    """Create a properly-structured mock asyncpg pool.

    asyncpg pool.acquire() returns an async context manager, not a coroutine.
    We need to set up the mock so that:
        async with pool.acquire() as conn:
            ...
    works correctly.
    """
    mock_pool = MagicMock()
    # pool.acquire() must return an object with __aenter__ and __aexit__
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire.return_value = ctx
    return mock_pool


# ── Test _get_api_key ─────────────────────────────────────────

class TestGetApiKey:
    """Test lazy API key loading."""

    def test_missing_api_key_raises(self):
        """Test ValueError raised when TAVILY_API_KEY is not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TAVILY_API_KEY", None)
            with pytest.raises(ValueError, match="TAVILY_API_KEY not set"):
                _get_api_key()

    def test_api_key_returned_when_set(self):
        """Test API key is returned correctly."""
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key-123"}):
            assert _get_api_key() == "test-key-123"

    def test_empty_api_key_raises(self):
        """Test empty string API key raises ValueError."""
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
            with pytest.raises(ValueError, match="TAVILY_API_KEY not set"):
                _get_api_key()


# ── Test _get_client ──────────────────────────────────────────

class TestGetClient:
    """Test TavilyClient creation."""

    def test_creates_client_with_key(self):
        """Test client is created with the API key."""
        mock_tavily_cls = MagicMock()
        with patch("api.intelligence.tavily_search._get_api_key", return_value="test-key"), \
             patch.dict("sys.modules", {"tavily": MagicMock(TavilyClient=mock_tavily_cls)}):
            _get_client()
            mock_tavily_cls.assert_called_once_with(api_key="test-key")


# ── Test Constants ────────────────────────────────────────────

class TestConstants:
    """Test module-level constants."""

    def test_default_queries_not_empty(self):
        """Test DEFAULT_QUERIES is populated."""
        assert len(DEFAULT_QUERIES) >= 3

    def test_default_queries_contain_vancouver(self):
        """Test all default queries mention Vancouver."""
        for q in DEFAULT_QUERIES:
            assert "vancouver" in q.lower() or "bill 47" in q.lower()

    def test_max_results_reasonable(self):
        """Test MAX_RESULTS_PER_QUERY is a reasonable number."""
        assert 1 <= MAX_RESULTS_PER_QUERY <= 50

    def test_search_days_reasonable(self):
        """Test SEARCH_DAYS is a reasonable number."""
        assert 1 <= SEARCH_DAYS <= 30

    def test_max_extract_urls_reasonable(self):
        """Test MAX_EXTRACT_URLS is reasonable."""
        assert 1 <= MAX_EXTRACT_URLS <= 20


# ── Test search_web ───────────────────────────────────────────

class TestSearchWeb:
    """Test Tavily search functionality."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Test search_web returns structured results."""
        mock_client = _make_mock_client()
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            results = await search_web(queries=["test query"])

        assert len(results) == 3
        assert results[0]["title"] == "Vancouver Rezoning Application 2026: Major Changes Coming"
        assert results[0]["url"] == "https://example.com/rezoning-2026"
        assert results[0]["query"] == "test query"

    @pytest.mark.asyncio
    async def test_search_deduplicates_urls(self):
        """Test URLs are deduplicated across queries."""
        mock_client = _make_mock_client()
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            # Two queries returning the same results should still have unique URLs
            results = await search_web(queries=["query1", "query2"])

        urls = [r["url"] for r in results]
        assert len(urls) == len(set(urls)), "Duplicate URLs found"

    @pytest.mark.asyncio
    async def test_search_handles_api_error(self):
        """Test graceful handling of Tavily API errors."""
        mock_client = _make_mock_client()
        mock_client.search.side_effect = Exception("API rate limit exceeded")
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            results = await search_web(queries=["test"])

        assert results == []

    @pytest.mark.asyncio
    async def test_search_uses_default_queries(self):
        """Test default queries are used when none provided."""
        mock_client = _make_mock_client()
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            await search_web()

        # Should have been called once per default query
        assert mock_client.search.call_count == len(DEFAULT_QUERIES)

    @pytest.mark.asyncio
    async def test_search_passes_correct_params(self):
        """Test search passes correct parameters to Tavily."""
        mock_client = _make_mock_client()
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            await search_web(queries=["test query"], max_results=5, days=3)

        mock_client.search.assert_called_once_with(
            query="test query",
            search_depth="basic",
            max_results=5,
            days=3,
        )

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        """Test handling of empty search results."""
        mock_client = _make_mock_client(search_return={"results": []})
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            results = await search_web(queries=["test"])

        assert results == []

    @pytest.mark.asyncio
    async def test_search_skips_empty_urls(self):
        """Test results with empty URLs are skipped."""
        mock_client = _make_mock_client(search_return={
            "results": [
                {"title": "Good", "url": "https://example.com/good", "content": "ok"},
                {"title": "Bad", "url": "", "content": "empty url"},
                {"title": "None", "content": "no url at all"},
            ]
        })
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            results = await search_web(queries=["test"])

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/good"


# ── Test extract_content ──────────────────────────────────────

class TestExtractContent:
    """Test Tavily content extraction."""

    @pytest.mark.asyncio
    async def test_extract_returns_content(self):
        """Test extract_content returns url->content mapping."""
        mock_client = _make_mock_client()
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            result = await extract_content(["https://example.com/rezoning-2026"])

        assert "https://example.com/rezoning-2026" in result
        assert "Vancouver Rezoning 2026" in result["https://example.com/rezoning-2026"]

    @pytest.mark.asyncio
    async def test_extract_empty_urls(self):
        """Test extract with empty URL list returns empty dict."""
        result = await extract_content([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_handles_api_error(self):
        """Test graceful handling of Tavily extract errors."""
        mock_client = _make_mock_client()
        mock_client.extract.side_effect = Exception("Extract failed")
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            result = await extract_content(["https://example.com/test"])

        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_passes_urls(self):
        """Test extract passes correct URLs to Tavily."""
        mock_client = _make_mock_client()
        urls = ["https://example.com/a", "https://example.com/b"]
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            await extract_content(urls)

        mock_client.extract.assert_called_once_with(urls=urls)

    @pytest.mark.asyncio
    async def test_extract_skips_empty_content(self):
        """Test results with empty raw_content are skipped."""
        mock_client = _make_mock_client(extract_return={
            "results": [
                {"url": "https://example.com/full", "raw_content": "Full content here"},
                {"url": "https://example.com/empty", "raw_content": ""},
            ]
        })
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client):
            result = await extract_content(["https://example.com/full", "https://example.com/empty"])

        assert len(result) == 1
        assert "https://example.com/full" in result


# ── Test store_document ───────────────────────────────────────

class TestStoreDocument:
    """Test document storage with dedup."""

    @pytest.mark.asyncio
    async def test_new_document_inserted(self):
        """Test new document returns True."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "INSERT 0 1"

        result = await store_document(
            conn=mock_conn,
            url="https://example.com/new-article",
            title="New Article",
            content="Article content here.",
            published_date=date(2026, 2, 10),
            source_query="test query",
        )

        assert result is True
        mock_conn.execute.assert_called_once()

        # Verify ON CONFLICT DO NOTHING is in the SQL
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        assert "ON CONFLICT (source_url) DO NOTHING" in sql

    @pytest.mark.asyncio
    async def test_duplicate_document_skipped(self):
        """Test duplicate document returns False."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "INSERT 0 0"

        result = await store_document(
            conn=mock_conn,
            url="https://example.com/existing",
            title="Existing Article",
            content="Already in DB.",
            published_date=date(2026, 2, 10),
            source_query="test query",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_store_document_correct_params(self):
        """Test store_document passes correct parameters."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "INSERT 0 1"

        pub_date = date(2026, 2, 10)
        await store_document(
            conn=mock_conn,
            url="https://example.com/test",
            title="Test Title",
            content="Test content",
            published_date=pub_date,
            source_query="my query",
        )

        call_args = mock_conn.execute.call_args[0]
        # Positional args after the SQL:
        # $1=source_type, $2=url, $3=title, $4=published_date, $5=content,
        # $6=text_length, $7=file_format, $8=metadata_json, $9=scraped_at
        assert call_args[1] == "tavily_search"  # source_type
        assert call_args[2] == "https://example.com/test"  # source_url
        assert call_args[3] == "Test Title"  # title
        assert call_args[4] == pub_date  # published_date
        assert call_args[5] == "Test content"  # raw_text
        assert call_args[6] == len("Test content")  # text_length
        assert call_args[7] == "html"  # file_format

        # Metadata should be a JSON string with source info
        metadata = json.loads(call_args[8])
        assert metadata["source"] == "tavily"
        assert metadata["search_query"] == "my query"

    @pytest.mark.asyncio
    async def test_store_document_none_content(self):
        """Test store with empty content uses 0 for text_length."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "INSERT 0 1"

        result = await store_document(
            conn=mock_conn,
            url="https://example.com/no-content",
            title="No Content",
            content="",
            published_date=None,
            source_query="test",
        )

        assert result is True
        call_args = mock_conn.execute.call_args[0]
        assert call_args[6] == 0  # text_length for empty content


# ── Test search_and_store (full pipeline) ─────────────────────

class TestSearchAndStore:
    """Test the main search_and_store pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_success(self):
        """Test successful search -> extract -> store pipeline."""
        mock_client = _make_mock_client()

        mock_conn = AsyncMock()
        # First two: new documents; third: duplicate
        mock_conn.execute.side_effect = ["INSERT 0 1", "INSERT 0 1", "INSERT 0 0"]

        mock_pool = _make_mock_pool(mock_conn)

        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client), \
             patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            result = await search_and_store(mock_pool)

        assert result["searched"] == len(DEFAULT_QUERIES)
        assert result["urls_found"] == 3
        assert result["new_documents"] == 2
        assert result["duplicates_skipped"] == 1

        # Scheduler compatibility aliases
        assert result["documents_found"] == 3
        assert result["documents_new"] == 2
        assert result["documents_skipped"] == 1

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_empty(self):
        """Test graceful handling of missing API key."""
        mock_pool = MagicMock()

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TAVILY_API_KEY", None)
            result = await search_and_store(mock_pool)

        assert result["searched"] == 0
        assert result["urls_found"] == 0
        assert result["new_documents"] == 0
        assert result["documents_found"] == 0

    @pytest.mark.asyncio
    async def test_search_failure_returns_empty(self):
        """Test graceful handling of search API failure."""
        mock_pool = MagicMock()

        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}), \
             patch("api.intelligence.tavily_search.search_web", side_effect=Exception("API down")):
            result = await search_and_store(mock_pool)

        assert result["new_documents"] == 0
        assert result["documents_new"] == 0

    @pytest.mark.asyncio
    async def test_extract_failure_still_stores_snippets(self):
        """Test that when extract fails, search snippets are still stored."""
        mock_client = _make_mock_client()
        mock_client.extract.side_effect = Exception("Extract API down")

        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "INSERT 0 1"

        mock_pool = _make_mock_pool(mock_conn)

        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client), \
             patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            result = await search_and_store(mock_pool)

        # Should still store documents using search snippets
        assert result["new_documents"] == 3
        assert mock_conn.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_db_error_counted_as_skipped(self):
        """Test DB errors are counted as duplicates_skipped."""
        mock_client = _make_mock_client()

        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("DB connection lost")

        mock_pool = _make_mock_pool(mock_conn)

        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client), \
             patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            result = await search_and_store(mock_pool)

        assert result["new_documents"] == 0
        assert result["duplicates_skipped"] == 3

    @pytest.mark.asyncio
    async def test_custom_queries(self):
        """Test custom queries are passed through."""
        mock_client = _make_mock_client(search_return={"results": []})

        mock_pool = MagicMock()

        custom = ["custom query 1", "custom query 2"]
        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client), \
             patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            result = await search_and_store(mock_pool, queries=custom)

        assert result["searched"] == 2
        assert mock_client.search.call_count == 2

    @pytest.mark.asyncio
    async def test_scheduler_interface_compatible(self):
        """Test function signature matches scheduler: func(pool, start_date, end_date)."""
        mock_pool = MagicMock()

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TAVILY_API_KEY", None)
            # Call with the scheduler's signature
            result = await search_and_store(
                mock_pool,
                datetime(2026, 2, 1),
                datetime(2026, 2, 16),
            )

        # Should run without error and return a valid dict
        assert isinstance(result, dict)
        assert "documents_found" in result
        assert "documents_new" in result
        assert "documents_skipped" in result

    @pytest.mark.asyncio
    async def test_published_date_parsing(self):
        """Test published_date is parsed correctly from ISO string."""
        search_return = {
            "results": [
                {
                    "title": "Test",
                    "url": "https://example.com/dated",
                    "content": "Content",
                    "published_date": "2026-02-10T14:30:00Z",
                },
            ]
        }
        mock_client = _make_mock_client(
            search_return=search_return,
            extract_return={"results": []},
        )

        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "INSERT 0 1"

        mock_pool = _make_mock_pool(mock_conn)

        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client), \
             patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            await search_and_store(mock_pool)

        # Verify the published_date parameter ($4) is a date object
        call_args = mock_conn.execute.call_args[0]
        assert call_args[4] == date(2026, 2, 10)

    @pytest.mark.asyncio
    async def test_null_published_date(self):
        """Test None published_date is handled correctly."""
        search_return = {
            "results": [
                {
                    "title": "No Date",
                    "url": "https://example.com/no-date",
                    "content": "Content",
                    "published_date": None,
                },
            ]
        }
        mock_client = _make_mock_client(
            search_return=search_return,
            extract_return={"results": []},
        )

        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "INSERT 0 1"

        mock_pool = _make_mock_pool(mock_conn)

        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client), \
             patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            await search_and_store(mock_pool)

        call_args = mock_conn.execute.call_args[0]
        assert call_args[4] is None  # published_date should be None

    @pytest.mark.asyncio
    async def test_extract_content_used_over_snippet(self):
        """Test extracted full content is preferred over search snippet."""
        search_return = {
            "results": [
                {
                    "title": "Test Article",
                    "url": "https://example.com/rezoning-2026",
                    "content": "Short snippet from search.",
                    "published_date": "2026-02-10",
                },
            ]
        }
        extract_return = {
            "results": [
                {
                    "url": "https://example.com/rezoning-2026",
                    "raw_content": "This is the full extracted article content with much more detail.",
                },
            ]
        }
        mock_client = _make_mock_client(
            search_return=search_return,
            extract_return=extract_return,
        )

        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "INSERT 0 1"

        mock_pool = _make_mock_pool(mock_conn)

        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client), \
             patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            await search_and_store(mock_pool)

        call_args = mock_conn.execute.call_args[0]
        stored_content = call_args[5]  # raw_text ($5)
        assert "full extracted article content" in stored_content
        assert stored_content != "Short snippet from search."

    @pytest.mark.asyncio
    async def test_no_results_returns_zeros(self):
        """Test empty search results return all-zero counts."""
        mock_client = _make_mock_client(search_return={"results": []})

        mock_pool = MagicMock()

        with patch("api.intelligence.tavily_search._get_client", return_value=mock_client), \
             patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            result = await search_and_store(mock_pool)

        assert result["urls_found"] == 0
        assert result["new_documents"] == 0
        assert result["duplicates_skipped"] == 0
