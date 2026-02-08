"""Tests for prepared statement query building in VanCity Lens.

This test suite covers:
- QueryBuilder class with single and multiple filters
- Date range filtering
- Severity filter mapping
- Pagination parameter handling
- SQL injection prevention via parameterization
- PreparedStatementCache LRU eviction
- Helper functions for common query patterns
- Integration with refactored signals.py and chat.py functions
"""

from datetime import date
import pytest
from unittest.mock import AsyncMock, MagicMock

from api.intelligence.prepared_queries import (
    QueryBuilder,
    PreparedStatementCache,
    build_signal_feed_query,
    build_signal_count_query,
)
from api.intelligence.signals import get_signal_feed
from api.intelligence.chat import get_relevant_signals


class TestQueryBuilder:
    """Test the QueryBuilder class for safe parameterized query construction."""

    def test_query_builder_initialization(self):
        """Test QueryBuilder initializes with empty conditions and params."""
        builder = QueryBuilder()
        assert builder.conditions == []
        assert builder.params == []

    def test_add_single_filter(self):
        """Test adding a single filter condition."""
        builder = QueryBuilder()
        builder.add_filter("isig.neighborhood", "=", "Downtown")

        where_clause, params = builder.build()

        assert where_clause == "isig.neighborhood = $1"
        assert params == ["Downtown"]

    def test_add_multiple_filters(self):
        """Test adding multiple filter conditions."""
        builder = QueryBuilder()
        builder.add_filter("isig.neighborhood", "=", "Downtown")
        builder.add_filter("isig.signal_type", "=", "rezoning_decision")

        where_clause, params = builder.build()

        assert where_clause == "isig.neighborhood = $1 AND isig.signal_type = $2"
        assert params == ["Downtown", "rezoning_decision"]

    def test_add_filter_method_chaining(self):
        """Test that add_filter returns self for method chaining."""
        builder = QueryBuilder()
        result = builder.add_filter("isig.neighborhood", "=", "Downtown")

        assert result is builder

    def test_add_filter_with_in_operator(self):
        """Test add_filter with IN operator and list value."""
        builder = QueryBuilder()
        builder.add_filter("isig.signal_type", "IN", ["rezoning_decision", "permit_approval"])

        where_clause, params = builder.build()

        assert where_clause == "isig.signal_type IN ($1, $2)"
        assert params == ["rezoning_decision", "permit_approval"]

    def test_add_filter_with_not_in_operator(self):
        """Test add_filter with NOT IN operator."""
        builder = QueryBuilder()
        builder.add_filter("isig.severity", "NOT IN", ["info", "low"])

        where_clause, params = builder.build()

        assert where_clause == "isig.severity NOT IN ($1, $2)"
        assert params == ["info", "low"]

    def test_add_filter_in_operator_requires_list(self):
        """Test that IN operator raises error if not given list/tuple."""
        builder = QueryBuilder()

        with pytest.raises(ValueError, match="IN operator requires list/tuple"):
            builder.add_filter("isig.signal_type", "IN", "single_value")

    def test_add_date_range_from_date(self):
        """Test adding a date range filter with from_date only."""
        builder = QueryBuilder()
        builder.add_date_range("isig.event_date", from_date=date(2024, 1, 1))

        where_clause, params = builder.build()

        assert where_clause == "isig.event_date >= $1"
        assert params == [date(2024, 1, 1)]

    def test_add_date_range_to_date(self):
        """Test adding a date range filter with to_date only."""
        builder = QueryBuilder()
        builder.add_date_range("isig.event_date", to_date=date(2024, 12, 31))

        where_clause, params = builder.build()

        assert where_clause == "isig.event_date <= $1"
        assert params == [date(2024, 12, 31)]

    def test_add_date_range_both_dates(self):
        """Test adding a date range filter with both from_date and to_date."""
        builder = QueryBuilder()
        builder.add_date_range(
            "isig.event_date",
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31)
        )

        where_clause, params = builder.build()

        assert where_clause == "isig.event_date >= $1 AND isig.event_date <= $2"
        assert params == [date(2024, 1, 1), date(2024, 12, 31)]

    def test_add_severity_filter(self):
        """Test severity filter creates proper CASE expression."""
        builder = QueryBuilder()
        builder.add_severity_filter("high")

        where_clause, params = builder.build()

        # Should contain CASE expression and >= 3 for high
        assert "CASE isig.severity" in where_clause
        assert ">= 3" in where_clause
        assert params == []  # No params for severity (hardcoded value)

    def test_add_severity_filter_critical(self):
        """Test severity filter for critical level."""
        builder = QueryBuilder()
        builder.add_severity_filter("critical")

        where_clause, params = builder.build()

        assert ">= 4" in where_clause

    def test_add_severity_filter_low(self):
        """Test severity filter for low level."""
        builder = QueryBuilder()
        builder.add_severity_filter("low")

        where_clause, params = builder.build()

        assert ">= 1" in where_clause

    def test_add_severity_filter_invalid_level(self):
        """Test severity filter with invalid level defaults to 0."""
        builder = QueryBuilder()
        builder.add_severity_filter("nonexistent")

        where_clause, params = builder.build()

        assert ">= 0" in where_clause

    def test_add_pagination(self):
        """Test adding pagination parameters."""
        builder = QueryBuilder()
        builder.add_pagination(20, 40)

        assert builder.params == [20, 40]

    def test_get_limit_offset_placeholders(self):
        """Test getting limit and offset placeholders after pagination."""
        builder = QueryBuilder()
        builder.add_pagination(20, 40)

        limit_ph, offset_ph = builder.get_limit_offset_placeholders()

        assert limit_ph == "$1"
        assert offset_ph == "$2"

    def test_get_limit_offset_placeholders_with_filters(self):
        """Test getting placeholders when filters are already added."""
        builder = QueryBuilder()
        builder.add_filter("isig.neighborhood", "=", "Downtown")
        builder.add_filter("isig.signal_type", "=", "rezoning_decision")
        builder.add_pagination(20, 40)

        limit_ph, offset_ph = builder.get_limit_offset_placeholders()

        assert limit_ph == "$3"
        assert offset_ph == "$4"

    def test_get_limit_offset_placeholders_without_pagination(self):
        """Test that getting placeholders without pagination raises error."""
        builder = QueryBuilder()
        builder.add_filter("isig.neighborhood", "=", "Downtown")

        with pytest.raises(ValueError, match="add_pagination"):
            builder.get_limit_offset_placeholders()

    def test_build_without_conditions(self):
        """Test build returns '1=1' when no conditions added."""
        builder = QueryBuilder()

        where_clause, params = builder.build()

        assert where_clause == "1=1"
        assert params == []

    def test_complex_filter_combination(self):
        """Test combining multiple filters of different types."""
        builder = QueryBuilder()
        builder.add_filter("isig.neighborhood", "=", "Downtown")
        builder.add_filter("isig.signal_type", "=", "rezoning_decision")
        builder.add_date_range(
            "isig.event_date",
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31)
        )
        builder.add_severity_filter("medium")

        where_clause, params = builder.build()

        # Verify structure without exact whitespace sensitivity
        assert "isig.neighborhood = $1" in where_clause
        assert "isig.signal_type = $2" in where_clause
        assert "isig.event_date >= $3" in where_clause
        assert "isig.event_date <= $4" in where_clause
        assert "CASE isig.severity" in where_clause
        assert params == ["Downtown", "rezoning_decision", date(2024, 1, 1), date(2024, 12, 31)]


class TestPreparedStatementCache:
    """Test the PreparedStatementCache for statement caching and eviction."""

    def test_cache_initialization(self):
        """Test cache initializes with correct max size."""
        cache = PreparedStatementCache(max_statements=50)

        assert cache.max_statements == 50
        assert len(cache.cache) == 0

    def test_cache_put_and_get(self):
        """Test putting and retrieving from cache."""
        cache = PreparedStatementCache()
        mock_stmt = MagicMock()

        cache.put("query1", mock_stmt)
        result = cache.get("query1")

        assert result is mock_stmt

    def test_cache_get_nonexistent_returns_none(self):
        """Test that getting nonexistent key returns None."""
        cache = PreparedStatementCache()

        result = cache.get("nonexistent")

        assert result is None

    def test_cache_lru_eviction(self):
        """Test that oldest item is evicted when cache exceeds max."""
        cache = PreparedStatementCache(max_statements=3)

        # Add 3 items
        cache.put("query1", MagicMock())
        cache.put("query2", MagicMock())
        cache.put("query3", MagicMock())

        assert len(cache.cache) == 3

        # Add 4th item - should evict query1 (oldest)
        cache.put("query4", MagicMock())

        assert len(cache.cache) == 3
        assert cache.get("query1") is None
        assert cache.get("query2") is not None
        assert cache.get("query3") is not None
        assert cache.get("query4") is not None

    def test_cache_lru_reorder_on_access(self):
        """Test that accessing item moves it to end (most recently used)."""
        cache = PreparedStatementCache(max_statements=2)

        stmt1 = MagicMock()
        stmt2 = MagicMock()
        cache.put("query1", stmt1)
        cache.put("query2", stmt2)

        # Access query1 - moves it to end
        cache.get("query1")

        # Add new item - should evict query2 (now oldest)
        cache.put("query3", MagicMock())

        assert len(cache.cache) == 2
        assert cache.get("query1") is not None
        assert cache.get("query2") is None
        assert cache.get("query3") is not None

    def test_cache_clear(self):
        """Test clearing all cached statements."""
        cache = PreparedStatementCache()
        cache.put("query1", MagicMock())
        cache.put("query2", MagicMock())

        cache.clear()

        assert len(cache.cache) == 0

    def test_cache_stats(self):
        """Test getting cache statistics."""
        cache = PreparedStatementCache(max_statements=50)
        cache.put("query1", MagicMock())
        cache.put("query2", MagicMock())

        stats = cache.stats()

        assert stats["cache_size"] == 2
        assert stats["max_statements"] == 50


class TestBuildSignalFeedQuery:
    """Test the build_signal_feed_query helper function."""

    def test_build_signal_feed_query_no_filters(self):
        """Test building feed query without filters."""
        query, params, limit_ph, offset_ph = build_signal_feed_query()

        assert "SELECT" in query
        assert "FROM intelligence_signals isig" in query
        assert "WHERE 1=1" in query
        assert "LIMIT" in query
        assert limit_ph == "$1"
        assert offset_ph == "$2"
        assert params == [20, 0]  # Default limit and offset

    def test_build_signal_feed_query_with_neighborhood(self):
        """Test building feed query with neighborhood filter."""
        query, params, _, _ = build_signal_feed_query(
            {"neighborhood": "Downtown"}
        )

        assert "isig.neighborhood = $1" in query
        assert params[0] == "Downtown"

    def test_build_signal_feed_query_with_signal_type(self):
        """Test building feed query with signal type filter."""
        query, params, _, _ = build_signal_feed_query(
            {"signal_type": "rezoning_decision"}
        )

        assert "isig.signal_type = $1" in query
        assert params[0] == "rezoning_decision"

    def test_build_signal_feed_query_with_date_range(self):
        """Test building feed query with date range."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 12, 31)

        query, params, _, _ = build_signal_feed_query(
            {
                "date_from": start_date,
                "date_to": end_date,
            }
        )

        assert "isig.event_date >= $1" in query
        assert "isig.event_date <= $2" in query
        assert params[0] == start_date
        assert params[1] == end_date

    def test_build_signal_feed_query_with_severity(self):
        """Test building feed query with severity filter."""
        query, params, _, _ = build_signal_feed_query(
            {"severity_min": "high"}
        )

        assert "CASE isig.severity" in query
        assert ">= 3" in query

    def test_build_signal_feed_query_with_pagination(self):
        """Test building feed query with custom pagination."""
        query, params, limit_ph, offset_ph = build_signal_feed_query(
            {"limit": 50, "offset": 100}
        )

        assert limit_ph == "$1"
        assert offset_ph == "$2"
        assert params[-2:] == [50, 100]

    def test_build_signal_feed_query_all_filters(self):
        """Test building feed query with all filters combined."""
        query, params, _, _ = build_signal_feed_query(
            {
                "neighborhood": "Downtown",
                "signal_type": "rezoning_decision",
                "severity_min": "high",
                "date_from": date(2024, 1, 1),
                "date_to": date(2024, 12, 31),
                "limit": 50,
                "offset": 100,
            }
        )

        # Verify all filters are in query
        assert "isig.neighborhood = $1" in query
        assert "isig.signal_type = $2" in query
        assert "isig.event_date >= $3" in query
        assert "isig.event_date <= $4" in query
        assert "CASE isig.severity" in query
        # Should have 4 data params (neighborhood, type, dates) + 2 pagination params
        # Severity doesn't add a param (uses hardcoded value)
        assert len(params) == 6


class TestBuildSignalCountQuery:
    """Test the build_signal_count_query helper function."""

    def test_build_signal_count_query_no_filters(self):
        """Test building count query without filters."""
        query, params = build_signal_count_query()

        assert "SELECT COUNT(*)" in query
        assert "WHERE 1=1" in query
        assert params == []

    def test_build_signal_count_query_with_neighborhood(self):
        """Test building count query with neighborhood filter."""
        query, params = build_signal_count_query(
            {"neighborhood": "Downtown"}
        )

        assert "isig.neighborhood = $1" in query
        assert params == ["Downtown"]

    def test_build_signal_count_query_with_multiple_filters(self):
        """Test building count query with multiple filters."""
        query, params = build_signal_count_query(
            {
                "neighborhood": "Downtown",
                "signal_type": "rezoning_decision",
                "date_from": date(2024, 1, 1),
            }
        )

        assert "isig.neighborhood = $1" in query
        assert "isig.signal_type = $2" in query
        assert "isig.event_date >= $3" in query
        assert len(params) == 3


class TestSQLInjectionPrevention:
    """Test that parameterized queries prevent SQL injection."""

    def test_sql_injection_in_string_parameter(self):
        """Test that SQL injection in string param doesn't affect query structure."""
        malicious_input = "Downtown'; DROP TABLE intelligence_signals; --"

        builder = QueryBuilder()
        builder.add_filter("isig.neighborhood", "=", malicious_input)

        where_clause, params = builder.build()

        # The malicious input should be in params, not in the query
        assert "DROP TABLE" not in where_clause
        assert params[0] == malicious_input
        assert where_clause == "isig.neighborhood = $1"

    def test_sql_injection_in_list_parameter(self):
        """Test that SQL injection in list params doesn't affect query structure."""
        malicious_items = ["rezoning_decision", "'; DROP TABLE--", "permit"]

        builder = QueryBuilder()
        builder.add_filter("isig.signal_type", "IN", malicious_items)

        where_clause, params = builder.build()

        # Malicious values in params, not in where clause
        assert "DROP TABLE" not in where_clause
        assert params == malicious_items
        assert where_clause == "isig.signal_type IN ($1, $2, $3)"


class TestSignalsFeedIntegration:
    """Test that refactored get_signal_feed uses QueryBuilder correctly."""

    @pytest.mark.asyncio
    async def test_get_signal_feed_uses_parameterized_query(self):
        """Test that get_signal_feed uses parameterized queries."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock responses
        conn.fetchrow.return_value = {"total": 5}
        conn.fetch.return_value = []

        await get_signal_feed(
            mock_pool,
            neighborhood="Downtown",
            signal_type="rezoning_decision",
            limit=20,
            offset=0
        )

        # Verify fetchrow was called (for count query)
        assert conn.fetchrow.called
        # Verify fetch was called (for feed query)
        assert conn.fetch.called

        # Get the queries that were called
        count_query_call = conn.fetchrow.call_args
        feed_query_call = conn.fetch.call_args

        # Verify parameterized queries (check for $ placeholders)
        assert "$1" in count_query_call[0][0]  # First arg is query
        assert "$" in feed_query_call[0][0]  # First arg is query

    @pytest.mark.asyncio
    async def test_get_signal_feed_with_all_filters(self):
        """Test get_signal_feed with all filter types."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 2}
        conn.fetch.return_value = []

        await get_signal_feed(
            mock_pool,
            neighborhood="Downtown",
            signal_type="rezoning_decision",
            severity_min="high",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
            limit=50,
            offset=100
        )

        # Verify both queries were called
        assert conn.fetchrow.called
        assert conn.fetch.called


class TestChatGetRelevantSignalsIntegration:
    """Test that refactored get_relevant_signals uses QueryBuilder correctly."""

    @pytest.mark.asyncio
    async def test_get_relevant_signals_uses_parameterized_query(self):
        """Test that get_relevant_signals uses parameterized queries."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch.return_value = []

        await get_relevant_signals(
            mock_pool,
            query="rezoning downtown",
            neighborhood="Downtown",
            limit=5
        )

        # Verify fetch was called
        assert conn.fetch.called

        query_call = conn.fetch.call_args
        query_string = query_call[0][0]

        # Verify parameterized query with $ placeholders
        assert "$1" in query_string  # For search query
        assert "$2" in query_string  # For neighborhood
        assert "$3" in query_string  # For limit

    @pytest.mark.asyncio
    async def test_get_relevant_signals_without_neighborhood(self):
        """Test get_relevant_signals without neighborhood filter."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch.return_value = []

        await get_relevant_signals(
            mock_pool,
            query="rezoning",
            limit=5
        )

        # Verify fetch was called
        assert conn.fetch.called

        query_call = conn.fetch.call_args
        query_string = query_call[0][0]

        # Should only have $1 for query and $2 for limit (no neighborhood)
        assert "$1" in query_string
        assert "$2" in query_string
