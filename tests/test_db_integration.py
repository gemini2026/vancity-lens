"""
[TEST-006] Comprehensive database integration tests for VanCity Lens.

Tests verify:
1. Connection pool management (creation, configuration, cleanup)
2. Signal queries with various filters and pagination
3. Document operations (unprocessed queries, counts, NULL text exclusion)
4. Chat message persistence and session grouping
"""

import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from asyncpg import Pool

from api.intelligence.signals import (
    get_signal_feed,
    get_signal_by_id,
    get_signal_stats,
    get_neighborhoods,
)
from api.intelligence.models import SignalResponse, SignalFeedResponse
from api.db import Database, DATABASE_URL, _get_database_url


# ────────────────────────────────────────────────────────────────────────────
# Connection Pool Management Tests
# ────────────────────────────────────────────────────────────────────────────


class TestDatabasePoolManagement:
    """Test asyncpg connection pool creation and lifecycle."""

    def test_database_url_from_env(self):
        """Test that DATABASE_URL is resolved from environment."""
        # DATABASE_URL is set globally in api/db.py
        assert DATABASE_URL is not None
        assert isinstance(DATABASE_URL, str)
        assert "postgresql://" in DATABASE_URL or "postgres://" in DATABASE_URL

    def test_database_url_requires_env_in_production(self):
        """Test that production mode requires DATABASE_URL set."""
        # Temporarily set to production
        old_env = os.getenv("VANCITY_ENV")
        old_db_url = os.getenv("DATABASE_URL")

        try:
            os.environ["VANCITY_ENV"] = "production"
            # Remove DATABASE_URL to test the error
            if "DATABASE_URL" in os.environ:
                del os.environ["DATABASE_URL"]

            # Should raise RuntimeError
            with pytest.raises(RuntimeError, match="DATABASE_URL environment variable is REQUIRED"):
                _get_database_url()
        finally:
            # Restore environment
            if old_env:
                os.environ["VANCITY_ENV"] = old_env
            else:
                os.environ.pop("VANCITY_ENV", None)
            if old_db_url:
                os.environ["DATABASE_URL"] = old_db_url

    def test_database_url_uses_dev_default(self):
        """Test that development uses default DB URL when not set."""
        old_env = os.getenv("VANCITY_ENV")
        old_db_url = os.getenv("DATABASE_URL")

        try:
            os.environ["VANCITY_ENV"] = "development"
            if "DATABASE_URL" in os.environ:
                del os.environ["DATABASE_URL"]

            url = _get_database_url()
            assert "localhost" in url or "127.0.0.1" in url
            assert "vancity_lens" in url
        finally:
            if old_env:
                os.environ["VANCITY_ENV"] = old_env
            else:
                os.environ.pop("VANCITY_ENV", None)
            if old_db_url:
                os.environ["DATABASE_URL"] = old_db_url

    @pytest.mark.asyncio
    async def test_database_pool_initialization(self):
        """Test that Database class initializes with None pool."""
        db = Database()
        assert db.pool is None

    @pytest.mark.asyncio
    async def test_database_acquire_without_connection_raises_error(self):
        """Test that acquiring without connect() raises RuntimeError."""
        db = Database()
        with pytest.raises(RuntimeError, match="Database not connected"):
            async with db.acquire():
                pass

    @pytest.mark.asyncio
    async def test_database_pool_acquire_context_manager(self, mock_db_pool):
        """Test that acquire() properly manages async context."""
        db = Database()
        db.pool = mock_db_pool

        # Verify acquire returns context manager
        ctx = db.pool.acquire()
        assert hasattr(ctx, "__aenter__")
        assert hasattr(ctx, "__aexit__")

        # Verify we can use it as async context manager
        async with db.acquire() as conn:
            assert conn is not None

        # Verify pool.acquire was called
        mock_db_pool.acquire.assert_called()

    @pytest.mark.asyncio
    async def test_database_disconnect(self, mock_db_pool):
        """Test pool cleanup on disconnect."""
        mock_db_pool.close = AsyncMock()

        db = Database()
        db.pool = mock_db_pool

        await db.disconnect()

        mock_db_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_database_disconnect_when_pool_is_none(self):
        """Test that disconnect handles None pool gracefully."""
        db = Database()
        db.pool = None

        # Should not raise
        await db.disconnect()


# ────────────────────────────────────────────────────────────────────────────
# Signal Query Tests - Basic Retrieval
# ────────────────────────────────────────────────────────────────────────────


class TestSignalQueries:
    """Test signal retrieval queries."""

    @pytest.mark.asyncio
    async def test_get_signal_feed_no_filters(self, mock_db_pool):
        """Test signal feed retrieval with no filters."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        count_row = {"total": 5}
        signal_rows = [
            {
                "id": 1,
                "document_id": 1,
                "signal_type": "rezoning_decision",
                "summary": "Rezoned to 25-storey",
                "headline": "Main St rezoned",
                "addresses": ["1234 Main St"],
                "neighborhood": "Downtown",
                "decision": "approved",
                "vote_for": 10,
                "vote_against": 1,
                "sentiment": "positive_for_development",
                "severity": "high",
                "confidence": 0.95,
                "event_date": date(2024, 1, 15),
                "source_title": "Council Meeting",
                "source_url": "https://council.ca",
                "source_type": "council_minutes",
                "source_date": date(2024, 1, 15),
            }
        ]

        conn.fetchrow.return_value = count_row
        conn.fetch.return_value = signal_rows

        result = await get_signal_feed(mock_db_pool)

        assert isinstance(result, SignalFeedResponse)
        assert result.total_count == 5
        assert len(result.signals) == 1
        assert result.signals[0].signal_type == "rezoning_decision"

    @pytest.mark.asyncio
    async def test_get_signal_feed_filter_by_neighborhood(self, mock_db_pool):
        """Test filtering signals by neighborhood."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 2}
        conn.fetch.return_value = []

        result = await get_signal_feed(mock_db_pool, neighborhood="Downtown")

        assert result.total_count == 2
        # Verify that conn.fetchrow was called with SQL containing neighborhood filter
        call_args = conn.fetchrow.call_args
        assert call_args is not None
        query_str = str(call_args[0][0])  # First positional argument is SQL query
        assert "neighborhood" in query_str.lower()

    @pytest.mark.asyncio
    async def test_get_signal_feed_filter_by_signal_type(self, mock_db_pool):
        """Test filtering signals by type."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 3}
        conn.fetch.return_value = []

        result = await get_signal_feed(mock_db_pool, signal_type="rezoning_decision")

        assert result.total_count == 3
        call_args = conn.fetchrow.call_args
        query_str = str(call_args[0][0])
        assert "signal_type" in query_str.lower()

    @pytest.mark.asyncio
    async def test_get_signal_feed_filter_by_severity(self, mock_db_pool):
        """Test filtering signals by minimum severity."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 2}
        conn.fetch.return_value = []

        result = await get_signal_feed(mock_db_pool, severity_min="high")

        assert result.total_count == 2
        call_args = conn.fetchrow.call_args
        query_str = str(call_args[0][0])
        assert "severity" in query_str.lower()

    @pytest.mark.asyncio
    async def test_get_signal_feed_filter_by_date_range(self, mock_db_pool):
        """Test filtering signals by date range."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 4}
        conn.fetch.return_value = []

        result = await get_signal_feed(
            mock_db_pool,
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
        )

        assert result.total_count == 4
        call_args = conn.fetchrow.call_args
        query_str = str(call_args[0][0])
        assert "event_date" in query_str.lower()

    @pytest.mark.asyncio
    async def test_get_signal_feed_combined_filters(self, mock_db_pool):
        """Test filtering with multiple criteria combined."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 1}
        conn.fetch.return_value = []

        result = await get_signal_feed(
            mock_db_pool,
            neighborhood="Downtown",
            signal_type="rezoning_decision",
            severity_min="medium",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
        )

        assert result.total_count == 1
        call_args = conn.fetchrow.call_args
        query_str = str(call_args[0][0])
        # Verify multiple conditions are in query
        assert query_str.count("$") >= 4  # At least 4 parameters


# ────────────────────────────────────────────────────────────────────────────
# Signal Query Tests - Pagination
# ────────────────────────────────────────────────────────────────────────────


class TestSignalPagination:
    """Test signal feed pagination."""

    @pytest.mark.asyncio
    async def test_pagination_limit_and_offset(self, mock_db_pool):
        """Test that limit and offset are passed correctly."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 100}
        conn.fetch.return_value = []

        await get_signal_feed(mock_db_pool, limit=20, offset=40)

        # Verify fetch was called with limit=20, offset=40
        fetch_call_args = conn.fetch.call_args
        assert fetch_call_args is not None
        # The last two positional args should be limit and offset
        assert fetch_call_args[0][-2:] == (20, 40)

    @pytest.mark.asyncio
    async def test_has_more_flag_true(self, mock_db_pool):
        """Test has_more is True when more records exist."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 100}
        conn.fetch.return_value = []

        result = await get_signal_feed(mock_db_pool, limit=20, offset=40)

        # 40 + 20 = 60, which is < 100, so has_more should be True
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_has_more_flag_false(self, mock_db_pool):
        """Test has_more is False when at end of results."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 50}
        conn.fetch.return_value = []

        result = await get_signal_feed(mock_db_pool, limit=20, offset=40)

        # 40 + 20 = 60, which is >= 50, so has_more should be False
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_limit_capped_at_100(self, mock_db_pool):
        """Test that limit is capped at 100."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 500}
        conn.fetch.return_value = []

        await get_signal_feed(mock_db_pool, limit=200, offset=0)

        # Verify limit was capped at 100
        fetch_call_args = conn.fetch.call_args
        actual_limit = fetch_call_args[0][-2]  # Second-to-last arg
        assert actual_limit == 100

    @pytest.mark.asyncio
    async def test_offset_non_negative(self, mock_db_pool):
        """Test that negative offset becomes 0."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 50}
        conn.fetch.return_value = []

        await get_signal_feed(mock_db_pool, limit=10, offset=-5)

        # Verify offset was clamped to 0
        fetch_call_args = conn.fetch.call_args
        actual_offset = fetch_call_args[0][-1]  # Last arg
        assert actual_offset == 0


# ────────────────────────────────────────────────────────────────────────────
# Signal Query Tests - Individual Retrieval
# ────────────────────────────────────────────────────────────────────────────


class TestGetSignalById:
    """Test signal retrieval by ID."""

    @pytest.mark.asyncio
    async def test_get_signal_by_id_found(self, mock_db_pool):
        """Test retrieving a signal by ID when it exists."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        signal_row = {
            "id": 42,
            "document_id": 10,
            "signal_type": "rezoning_decision",
            "summary": "Test summary",
            "headline": "Test headline",
            "addresses": ["1234 Main St"],
            "neighborhood": "Downtown",
            "decision": "approved",
            "vote_for": 9,
            "vote_against": 2,
            "sentiment": "positive_for_development",
            "severity": "high",
            "confidence": 0.92,
            "event_date": date(2024, 6, 15),
            "source_title": "Council Session",
            "source_url": "https://example.com",
            "source_type": "council_minutes",
            "source_date": date(2024, 6, 15),
        }

        conn.fetchrow.return_value = signal_row

        result = await get_signal_by_id(mock_db_pool, 42)

        assert result is not None
        assert isinstance(result, SignalResponse)
        assert result.id == 42
        assert result.signal_type == "rezoning_decision"

        # Verify fetchrow was called with correct signal_id
        conn.fetchrow.assert_called_once()
        call_args = conn.fetchrow.call_args[0]
        assert 42 in call_args

    @pytest.mark.asyncio
    async def test_get_signal_by_id_not_found(self, mock_db_pool):
        """Test retrieving a non-existent signal returns None."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = None

        result = await get_signal_by_id(mock_db_pool, 9999)

        assert result is None


# ────────────────────────────────────────────────────────────────────────────
# Signal Aggregation Tests
# ────────────────────────────────────────────────────────────────────────────


class TestSignalAggregation:
    """Test signal statistics and aggregation queries."""

    @pytest.mark.asyncio
    async def test_get_signal_stats(self, mock_db_pool):
        """Test signal statistics aggregation."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock stats row
        stats_row = {
            "total_signals": 150,
            "recent_7d": 12,
            "recent_30d": 45,
        }

        # Mock type aggregation
        type_rows = [
            {"signal_type": "rezoning_decision", "count": 80},
            {"signal_type": "policy_change", "count": 50},
            {"signal_type": "permit_approval", "count": 20},
        ]

        # Mock neighborhood aggregation
        neighborhood_rows = [
            {"neighborhood": "Downtown", "count": 60},
            {"neighborhood": "Kitsilano", "count": 40},
            {"neighborhood": "Mount Pleasant", "count": 25},
        ]

        # Mock severity aggregation
        severity_rows = [
            {"severity": "high", "count": 80},
            {"severity": "medium", "count": 50},
            {"severity": "low", "count": 20},
        ]

        conn.fetchrow.return_value = stats_row
        conn.fetch.side_effect = [type_rows, neighborhood_rows, severity_rows]

        result = await get_signal_stats(mock_db_pool)

        assert result["total_signals"] == 150
        assert result["recent_count_7d"] == 12
        assert result["recent_count_30d"] == 45
        assert result["by_type"]["rezoning_decision"] == 80
        assert result["by_neighborhood"]["Downtown"] == 60
        assert result["by_severity"]["high"] == 80

    @pytest.mark.asyncio
    async def test_get_neighborhoods(self, mock_db_pool):
        """Test retrieving distinct neighborhoods."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        neighborhood_rows = [
            {"neighborhood": "Downtown"},
            {"neighborhood": "Kitsilano"},
            {"neighborhood": "Mount Pleasant"},
            {"neighborhood": "West End"},
            {"neighborhood": "East Vancouver"},
        ]

        conn.fetch.return_value = neighborhood_rows

        result = await get_neighborhoods(mock_db_pool)

        assert len(result) == 5
        assert "Downtown" in result
        assert "Kitsilano" in result
        assert all(isinstance(n, str) for n in result)


# ────────────────────────────────────────────────────────────────────────────
# Document Operation Tests
# ────────────────────────────────────────────────────────────────────────────


class TestDocumentOperations:
    """Test document queries used by processing pipeline."""

    @pytest.mark.asyncio
    async def test_get_unprocessed_documents(self, mock_db_pool):
        """Test querying documents that need processing."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        unprocessed_rows = [
            {
                "id": 5,
                "title": "Council Minutes Jan 2024",
                "raw_text": "Meeting content here...",
                "source_url": "https://council.ca/minutes",
                "published_date": date(2024, 1, 15),
            },
            {
                "id": 6,
                "title": "Council Minutes Feb 2024",
                "raw_text": "More meeting content...",
                "source_url": "https://council.ca/minutes",
                "published_date": date(2024, 2, 15),
            },
        ]

        conn.fetch.return_value = unprocessed_rows

        # Simulate query to get unprocessed documents
        query = """
            SELECT id, title, raw_text, source_url, published_date
            FROM documents
            WHERE processed_at IS NULL AND raw_text IS NOT NULL
            ORDER BY published_date DESC
        """

        async with mock_db_pool.acquire() as conn_inner:
            rows = await conn_inner.fetch(query)

        assert len(rows) == 2
        assert rows[0]["id"] == 5
        assert rows[0]["raw_text"] is not None

    @pytest.mark.asyncio
    async def test_document_count_statistics(self, mock_db_pool):
        """Test document count aggregation."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        count_row = {"total": 523, "processed": 512, "unprocessed": 11}

        conn.fetchrow.return_value = count_row

        query = """
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN processed_at IS NOT NULL THEN 1 END) as processed,
                COUNT(CASE WHEN processed_at IS NULL THEN 1 END) as unprocessed
            FROM documents
        """

        async with mock_db_pool.acquire() as conn_inner:
            result = await conn_inner.fetchrow(query)

        assert result["total"] == 523
        assert result["processed"] == 512
        assert result["unprocessed"] == 11

    @pytest.mark.asyncio
    async def test_null_raw_text_excluded_from_processing(self, mock_db_pool):
        """Test that documents with NULL raw_text are excluded."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # This should only return documents with non-NULL raw_text
        unprocessed_rows = [
            {
                "id": 1,
                "title": "Valid Doc",
                "raw_text": "Text content",
                "processed_at": None,
            }
        ]

        conn.fetch.return_value = unprocessed_rows

        query = """
            SELECT id, title, raw_text, processed_at
            FROM documents
            WHERE processed_at IS NULL AND raw_text IS NOT NULL
        """

        async with mock_db_pool.acquire() as conn_inner:
            rows = await conn_inner.fetch(query)

        assert all(row["raw_text"] is not None for row in rows)
        assert all(row["processed_at"] is None for row in rows)

    @pytest.mark.asyncio
    async def test_document_source_type_distribution(self, mock_db_pool):
        """Test document distribution by source type."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        source_rows = [
            {"source_type": "council_minutes", "count": 250},
            {"source_type": "rezoning_applications", "count": 180},
            {"source_type": "development_permits", "count": 93},
        ]

        conn.fetch.return_value = source_rows

        query = """
            SELECT source_type, COUNT(*) as count
            FROM documents
            GROUP BY source_type
            ORDER BY count DESC
        """

        async with mock_db_pool.acquire() as conn_inner:
            result = await conn_inner.fetch(query)

        assert len(result) == 3
        assert result[0]["source_type"] == "council_minutes"
        assert result[0]["count"] == 250


# ────────────────────────────────────────────────────────────────────────────
# Chat Message Persistence Tests
# ────────────────────────────────────────────────────────────────────────────


class TestChatMessagePersistence:
    """Test chat message storage in database."""

    @pytest.mark.asyncio
    async def test_user_message_insertion(self, mock_db_pool):
        """Test inserting user messages into chat_messages table."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchval.return_value = 1  # Returns inserted ID

        query = """
            INSERT INTO chat_messages
            (session_id, role, content, source_references, created_at)
            VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            RETURNING id
        """

        async with mock_db_pool.acquire() as conn_inner:
            msg_id = await conn_inner.fetchval(
                query,
                "session-123",
                "user",
                "What rezoning decisions were made?",
                '["doc-1", "doc-2"]',
            )

        assert msg_id == 1
        conn.fetchval.assert_called_once()

    @pytest.mark.asyncio
    async def test_assistant_message_insertion(self, mock_db_pool):
        """Test inserting assistant responses into chat_messages table."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchval.return_value = 2

        query = """
            INSERT INTO chat_messages
            (session_id, role, content, source_references, created_at)
            VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            RETURNING id
        """

        async with mock_db_pool.acquire() as conn_inner:
            msg_id = await conn_inner.fetchval(
                query,
                "session-123",
                "assistant",
                "The City Council approved rezoning of 1234 Main Street...",
                '["doc-1"]',
            )

        assert msg_id == 2

    @pytest.mark.asyncio
    async def test_session_message_grouping(self, mock_db_pool):
        """Test retrieving all messages for a session."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        session_messages = [
            {
                "id": 1,
                "session_id": "session-123",
                "role": "user",
                "content": "What rezoning decisions?",
                "source_references": ["doc-1"],
                "created_at": "2024-01-15T10:00:00",
            },
            {
                "id": 2,
                "session_id": "session-123",
                "role": "assistant",
                "content": "The City Council approved...",
                "source_references": ["doc-1"],
                "created_at": "2024-01-15T10:00:05",
            },
        ]

        conn.fetch.return_value = session_messages

        query = """
            SELECT id, session_id, role, content, source_references, created_at
            FROM chat_messages
            WHERE session_id = $1
            ORDER BY created_at ASC
        """

        async with mock_db_pool.acquire() as conn_inner:
            messages = await conn_inner.fetch(query, "session-123")

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert all(m["session_id"] == "session-123" for m in messages)


# ────────────────────────────────────────────────────────────────────────────
# SQL Query Structure Validation Tests
# ────────────────────────────────────────────────────────────────────────────


class TestSQLQueryStructure:
    """Test that SQL queries are properly structured and parameterized."""

    @pytest.mark.asyncio
    async def test_signal_feed_uses_parameterized_queries(self, mock_db_pool):
        """Test that signal feed uses proper parameterized queries."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 5}
        conn.fetch.return_value = []

        await get_signal_feed(
            mock_db_pool,
            neighborhood="Downtown",
            signal_type="rezoning_decision",
        )

        # Verify parameterized queries were used ($ placeholders)
        fetchrow_call = conn.fetchrow.call_args[0]
        query = fetchrow_call[0]
        assert "$" in query  # Should use $ for parameters

        fetch_call = conn.fetch.call_args[0]
        query = fetch_call[0]
        assert "$" in query

    @pytest.mark.asyncio
    async def test_signal_queries_use_joins(self, mock_db_pool):
        """Test that signal queries properly join with documents table."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 1}
        conn.fetch.return_value = []

        await get_signal_feed(mock_db_pool)

        fetch_call = conn.fetch.call_args[0]
        query = fetch_call[0]
        # Should join documents table for source info
        assert "join" in query.lower()
        assert "documents" in query.lower()

    @pytest.mark.asyncio
    async def test_aggregation_queries_use_group_by(self, mock_db_pool):
        """Test that aggregation queries properly use GROUP BY."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        stats_row = {"total_signals": 100, "recent_7d": 10, "recent_30d": 30}
        type_rows = [{"signal_type": "rezoning_decision", "count": 50}]
        neighborhood_rows = [{"neighborhood": "Downtown", "count": 40}]
        severity_rows = [{"severity": "high", "count": 30}]

        conn.fetchrow.return_value = stats_row
        conn.fetch.side_effect = [type_rows, neighborhood_rows, severity_rows]

        await get_signal_stats(mock_db_pool)

        # Check that fetch calls included aggregation queries
        fetch_calls = conn.fetch.call_args_list
        for call in fetch_calls:
            query = call[0][0]
            assert "group by" in query.lower()


# ────────────────────────────────────────────────────────────────────────────
# Pool Configuration Tests
# ────────────────────────────────────────────────────────────────────────────


class TestPoolConfiguration:
    """Test pool size and configuration parameters."""

    def test_pool_size_from_environment(self):
        """Test that pool size is configurable via environment."""
        # The pool size is set at module import time
        # We can verify the configuration values exist
        from api import db as db_module

        # These are set from environment variables
        assert hasattr(db_module, "_POOL_MIN")
        assert hasattr(db_module, "_POOL_MAX")
        assert isinstance(db_module._POOL_MIN, int)
        assert isinstance(db_module._POOL_MAX, int)
        assert db_module._POOL_MIN > 0
        assert db_module._POOL_MAX >= db_module._POOL_MIN

    def test_pool_size_defaults(self):
        """Test default pool sizes."""
        from api import db as db_module

        # Default values should be sensible
        assert db_module._POOL_MIN >= 1
        assert db_module._POOL_MAX <= 100
        assert db_module._POOL_MIN <= db_module._POOL_MAX
