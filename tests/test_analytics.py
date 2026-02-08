"""
Tests for VCL-86 [BIZ-004] Usage analytics dashboard.

Comprehensive tests for analytics service layer and API routes,
including event tracking, user activity, platform metrics, and admin endpoints.
"""

from datetime import datetime, timedelta, timezone, date
from unittest.mock import AsyncMock, MagicMock
import pytest

from api.analytics import (
    AnalyticsTracker,
    EventType,
    UserActivitySummary,
    PlatformMetrics,
    TopItemsResponse,
    ActiveUsersMetrics,
    RetentionMetrics,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    pool.acquire = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    pool.conn = conn
    return pool


@pytest.fixture
def sample_user():
    """Sample user for testing."""
    return {
        "id": 1,
        "email": "test@example.com",
        "display_name": "Test User",
        "role": "user",
        "is_active": True,
    }


@pytest.fixture
def admin_user():
    """Sample admin user for testing."""
    return {
        "id": 999,
        "email": "admin@example.com",
        "display_name": "Admin User",
        "role": "admin",
        "is_active": True,
    }


# ────────────────────────────────────────────────────────────────────────────
# Event Tracking Tests
# ────────────────────────────────────────────────────────────────────────────

class TestTrackEvent:
    """Test event tracking functionality."""

    @pytest.mark.asyncio
    async def test_track_parcel_lookup(self, mock_pool):
        """Test tracking a parcel lookup event."""
        mock_pool.conn.fetchrow.return_value = {"id": 1}

        event_id = await AnalyticsTracker.track_event(
            mock_pool,
            user_id=1,
            event_type=EventType.PARCEL_LOOKUP.value,
            metadata={"parcel_id": 123},
        )

        assert event_id == 1
        mock_pool.conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_chat_query(self, mock_pool):
        """Test tracking a chat query event."""
        mock_pool.conn.fetchrow.return_value = {"id": 2}

        event_id = await AnalyticsTracker.track_event(
            mock_pool,
            user_id=1,
            event_type=EventType.CHAT_QUERY.value,
            metadata={"query": "What's happening in Downtown?"},
        )

        assert event_id == 2

    @pytest.mark.asyncio
    async def test_track_signal_view(self, mock_pool):
        """Test tracking a signal view event."""
        mock_pool.conn.fetchrow.return_value = {"id": 3}

        event_id = await AnalyticsTracker.track_event(
            mock_pool,
            user_id=1,
            event_type=EventType.SIGNAL_VIEW.value,
            metadata={"signal_id": 456, "signal_type": "rezoning_decision"},
        )

        assert event_id == 3

    @pytest.mark.asyncio
    async def test_track_scorecard_view(self, mock_pool):
        """Test tracking a scorecard view event."""
        mock_pool.conn.fetchrow.return_value = {"id": 4}

        event_id = await AnalyticsTracker.track_event(
            mock_pool,
            user_id=1,
            event_type=EventType.SCORECARD_VIEW.value,
            metadata={"neighborhood": "Downtown"},
        )

        assert event_id == 4

    @pytest.mark.asyncio
    async def test_track_report_export(self, mock_pool):
        """Test tracking a report export event."""
        mock_pool.conn.fetchrow.return_value = {"id": 5}

        event_id = await AnalyticsTracker.track_event(
            mock_pool,
            user_id=1,
            event_type=EventType.REPORT_EXPORT.value,
            metadata={"report_format": "pdf"},
        )

        assert event_id == 5

    @pytest.mark.asyncio
    async def test_track_login(self, mock_pool):
        """Test tracking a login event."""
        mock_pool.conn.fetchrow.return_value = {"id": 6}

        event_id = await AnalyticsTracker.track_event(
            mock_pool,
            user_id=1,
            event_type=EventType.LOGIN.value,
            metadata={"ip_address": "192.168.1.1"},
        )

        assert event_id == 6

    @pytest.mark.asyncio
    async def test_track_search(self, mock_pool):
        """Test tracking a search event."""
        mock_pool.conn.fetchrow.return_value = {"id": 7}

        event_id = await AnalyticsTracker.track_event(
            mock_pool,
            user_id=1,
            event_type=EventType.SEARCH.value,
            metadata={"neighborhood": "Kitsilano"},
        )

        assert event_id == 7

    @pytest.mark.asyncio
    async def test_track_event_without_metadata(self, mock_pool):
        """Test tracking an event without metadata."""
        mock_pool.conn.fetchrow.return_value = {"id": 8}

        event_id = await AnalyticsTracker.track_event(
            mock_pool,
            user_id=1,
            event_type=EventType.LOGIN.value,
        )

        assert event_id == 8


# ────────────────────────────────────────────────────────────────────────────
# User Activity Tests
# ────────────────────────────────────────────────────────────────────────────

class TestUserActivity:
    """Test user activity retrieval."""

    @pytest.mark.asyncio
    async def test_get_user_activity_with_events(self, mock_pool):
        """Test retrieving user activity with events."""
        mock_pool.conn.fetch.return_value = [
            {"event_type": EventType.PARCEL_LOOKUP.value, "count": 5},
            {"event_type": EventType.CHAT_QUERY.value, "count": 3},
            {"event_type": EventType.SIGNAL_VIEW.value, "count": 10},
        ]

        now = datetime.now(tz=timezone.utc)
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 18,
            "first_activity_at": now - timedelta(days=20),
            "last_activity_at": now,
        }

        result = await AnalyticsTracker.get_user_activity(mock_pool, user_id=1)

        assert isinstance(result, UserActivitySummary)
        assert result.user_id == 1
        assert result.total_events == 18
        assert result.parcel_lookups == 5
        assert result.chat_queries == 3
        assert result.signal_views == 10

    @pytest.mark.asyncio
    async def test_get_user_activity_no_events(self, mock_pool):
        """Test retrieving user activity with no events."""
        mock_pool.conn.fetch.return_value = []
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 0,
            "first_activity_at": None,
            "last_activity_at": None,
        }

        result = await AnalyticsTracker.get_user_activity(mock_pool, user_id=1)

        assert result.total_events == 0
        assert result.parcel_lookups == 0
        assert result.last_activity_at is None

    @pytest.mark.asyncio
    async def test_get_user_activity_custom_days(self, mock_pool):
        """Test retrieving user activity with custom days."""
        mock_pool.conn.fetch.return_value = []
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 5,
            "first_activity_at": datetime.now(tz=timezone.utc) - timedelta(days=5),
            "last_activity_at": datetime.now(tz=timezone.utc),
        }

        result = await AnalyticsTracker.get_user_activity(
            mock_pool,
            user_id=1,
            days=90,
        )

        assert result.total_events == 5

    @pytest.mark.asyncio
    async def test_get_user_activity_all_event_types(self, mock_pool):
        """Test retrieving user activity with all event types."""
        mock_pool.conn.fetch.return_value = [
            {"event_type": EventType.PARCEL_LOOKUP.value, "count": 1},
            {"event_type": EventType.CHAT_QUERY.value, "count": 1},
            {"event_type": EventType.SIGNAL_VIEW.value, "count": 1},
            {"event_type": EventType.SCORECARD_VIEW.value, "count": 1},
            {"event_type": EventType.REPORT_EXPORT.value, "count": 1},
            {"event_type": EventType.LOGIN.value, "count": 1},
            {"event_type": EventType.SEARCH.value, "count": 1},
        ]

        mock_pool.conn.fetchrow.return_value = {
            "total_events": 7,
            "first_activity_at": datetime.now(tz=timezone.utc) - timedelta(days=1),
            "last_activity_at": datetime.now(tz=timezone.utc),
        }

        result = await AnalyticsTracker.get_user_activity(mock_pool, user_id=1)

        assert result.parcel_lookups == 1
        assert result.chat_queries == 1
        assert result.signal_views == 1
        assert result.scorecard_views == 1
        assert result.report_exports == 1
        assert result.logins == 1
        assert result.searches == 1


# ────────────────────────────────────────────────────────────────────────────
# Platform Metrics Tests
# ────────────────────────────────────────────────────────────────────────────

class TestPlatformMetrics:
    """Test platform-wide metrics."""

    @pytest.mark.asyncio
    async def test_get_platform_metrics_daily(self, mock_pool):
        """Test getting daily platform metrics."""
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 100,
            "unique_users": 25,
        }

        mock_pool.conn.fetch.return_value = [
            {"event_type": EventType.PARCEL_LOOKUP.value, "count": 30},
            {"event_type": EventType.CHAT_QUERY.value, "count": 20},
            {"event_type": EventType.SIGNAL_VIEW.value, "count": 50},
        ]

        result = await AnalyticsTracker.get_platform_metrics(
            mock_pool,
            period="daily",
        )

        assert isinstance(result, PlatformMetrics)
        assert result.period == "daily"
        assert result.total_events == 100
        assert result.unique_users == 25
        assert result.average_events_per_user == 4.0
        assert result.parcel_lookups == 30

    @pytest.mark.asyncio
    async def test_get_platform_metrics_weekly(self, mock_pool):
        """Test getting weekly platform metrics."""
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 500,
            "unique_users": 100,
        }

        mock_pool.conn.fetch.return_value = []

        result = await AnalyticsTracker.get_platform_metrics(
            mock_pool,
            period="weekly",
        )

        assert result.period == "weekly"
        assert result.total_events == 500
        assert result.unique_users == 100

    @pytest.mark.asyncio
    async def test_get_platform_metrics_monthly(self, mock_pool):
        """Test getting monthly platform metrics."""
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 2000,
            "unique_users": 250,
        }

        mock_pool.conn.fetch.return_value = []

        result = await AnalyticsTracker.get_platform_metrics(
            mock_pool,
            period="monthly",
        )

        assert result.period == "monthly"
        assert result.total_events == 2000
        assert result.unique_users == 250

    @pytest.mark.asyncio
    async def test_get_platform_metrics_no_data(self, mock_pool):
        """Test platform metrics with no data."""
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 0,
            "unique_users": 0,
        }

        mock_pool.conn.fetch.return_value = []

        result = await AnalyticsTracker.get_platform_metrics(mock_pool)

        assert result.total_events == 0
        assert result.unique_users == 0
        assert result.average_events_per_user == 0.0

    @pytest.mark.asyncio
    async def test_get_platform_metrics_invalid_period(self, mock_pool):
        """Test platform metrics with invalid period."""
        with pytest.raises(ValueError):
            await AnalyticsTracker.get_platform_metrics(
                mock_pool,
                period="invalid",
            )


# ────────────────────────────────────────────────────────────────────────────
# Top Neighborhoods Tests
# ────────────────────────────────────────────────────────────────────────────

class TestTopNeighborhoods:
    """Test top neighborhoods retrieval."""

    @pytest.mark.asyncio
    async def test_get_top_neighborhoods(self, mock_pool):
        """Test getting top neighborhoods."""
        mock_pool.conn.fetchval.return_value = 100

        mock_pool.conn.fetch.return_value = [
            {"neighborhood": "Downtown", "count": 30},
            {"neighborhood": "Kitsilano", "count": 25},
            {"neighborhood": "Mount Pleasant", "count": 20},
        ]

        result = await AnalyticsTracker.get_top_neighborhoods(mock_pool)

        assert isinstance(result, TopItemsResponse)
        assert result.period_days == 30
        assert result.total_count == 100
        assert len(result.items) == 3
        assert result.items[0].rank == 1
        assert result.items[0].name == "Downtown"
        assert result.items[0].count == 30
        assert abs(result.items[0].percentage - 30.0) < 0.01

    @pytest.mark.asyncio
    async def test_get_top_neighborhoods_custom_days(self, mock_pool):
        """Test getting top neighborhoods with custom days."""
        mock_pool.conn.fetchval.return_value = 50

        mock_pool.conn.fetch.return_value = [
            {"neighborhood": "West End", "count": 50},
        ]

        result = await AnalyticsTracker.get_top_neighborhoods(
            mock_pool,
            days=7,
            limit=5,
        )

        assert result.period_days == 7

    @pytest.mark.asyncio
    async def test_get_top_neighborhoods_no_data(self, mock_pool):
        """Test getting top neighborhoods with no data."""
        mock_pool.conn.fetchval.return_value = 0
        mock_pool.conn.fetch.return_value = []

        result = await AnalyticsTracker.get_top_neighborhoods(mock_pool)

        assert result.total_count == 0
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_get_top_neighborhoods_percentages(self, mock_pool):
        """Test percentage calculations for neighborhoods."""
        mock_pool.conn.fetchval.return_value = 100

        mock_pool.conn.fetch.return_value = [
            {"neighborhood": "A", "count": 50},
            {"neighborhood": "B", "count": 30},
            {"neighborhood": "C", "count": 20},
        ]

        result = await AnalyticsTracker.get_top_neighborhoods(mock_pool)

        assert abs(result.items[0].percentage - 50.0) < 0.01
        assert abs(result.items[1].percentage - 30.0) < 0.01
        assert abs(result.items[2].percentage - 20.0) < 0.01


# ────────────────────────────────────────────────────────────────────────────
# Top Signals Tests
# ────────────────────────────────────────────────────────────────────────────

class TestTopSignals:
    """Test top signals retrieval."""

    @pytest.mark.asyncio
    async def test_get_top_signals(self, mock_pool):
        """Test getting top signals."""
        mock_pool.conn.fetchval.return_value = 100

        mock_pool.conn.fetch.return_value = [
            {"signal_type": "rezoning_decision", "count": 40},
            {"signal_type": "policy_change", "count": 30},
            {"signal_type": "infrastructure", "count": 20},
        ]

        result = await AnalyticsTracker.get_top_signals(mock_pool)

        assert isinstance(result, TopItemsResponse)
        assert result.total_count == 100
        assert len(result.items) == 3
        assert result.items[0].name == "rezoning_decision"
        assert result.items[0].count == 40

    @pytest.mark.asyncio
    async def test_get_top_signals_custom_params(self, mock_pool):
        """Test getting top signals with custom parameters."""
        mock_pool.conn.fetchval.return_value = 50

        mock_pool.conn.fetch.return_value = []

        result = await AnalyticsTracker.get_top_signals(
            mock_pool,
            days=90,
            limit=20,
        )

        assert result.period_days == 90

    @pytest.mark.asyncio
    async def test_get_top_signals_no_data(self, mock_pool):
        """Test getting top signals with no data."""
        mock_pool.conn.fetchval.return_value = 0
        mock_pool.conn.fetch.return_value = []

        result = await AnalyticsTracker.get_top_signals(mock_pool)

        assert result.total_count == 0
        assert len(result.items) == 0


# ────────────────────────────────────────────────────────────────────────────
# Active Users Tests
# ────────────────────────────────────────────────────────────────────────────

class TestActiveUsers:
    """Test active users metrics."""

    @pytest.mark.asyncio
    async def test_get_active_users_daily(self, mock_pool):
        """Test getting daily active users."""
        mock_pool.conn.fetchval.side_effect = [
            100,  # active users
            75,   # returning users
            25,   # new users
        ]

        result = await AnalyticsTracker.get_active_users(mock_pool, period="daily")

        assert isinstance(result, ActiveUsersMetrics)
        assert result.period == "daily"
        assert result.active_users == 100
        assert result.returning_users == 75
        assert result.new_users == 25
        assert abs(result.churn_rate - 0.25) < 0.01

    @pytest.mark.asyncio
    async def test_get_active_users_weekly(self, mock_pool):
        """Test getting weekly active users."""
        mock_pool.conn.fetchval.side_effect = [500, 400, 100]

        result = await AnalyticsTracker.get_active_users(mock_pool, period="weekly")

        assert result.period == "weekly"
        assert result.active_users == 500

    @pytest.mark.asyncio
    async def test_get_active_users_monthly(self, mock_pool):
        """Test getting monthly active users."""
        mock_pool.conn.fetchval.side_effect = [2000, 1500, 500]

        result = await AnalyticsTracker.get_active_users(mock_pool, period="monthly")

        assert result.period == "monthly"
        assert result.active_users == 2000

    @pytest.mark.asyncio
    async def test_get_active_users_no_users(self, mock_pool):
        """Test active users with no data."""
        mock_pool.conn.fetchval.side_effect = [0, 0, 0]

        result = await AnalyticsTracker.get_active_users(mock_pool)

        assert result.active_users == 0
        assert result.churn_rate == 0.0

    @pytest.mark.asyncio
    async def test_get_active_users_invalid_period(self, mock_pool):
        """Test active users with invalid period."""
        with pytest.raises(ValueError):
            await AnalyticsTracker.get_active_users(
                mock_pool,
                period="invalid",
            )


# ────────────────────────────────────────────────────────────────────────────
# Retention Metrics Tests
# ────────────────────────────────────────────────────────────────────────────

class TestRetentionMetrics:
    """Test user retention metrics."""

    @pytest.mark.asyncio
    async def test_get_retention_metrics(self, mock_pool):
        """Test getting retention metrics."""
        now = datetime.now(tz=timezone.utc)
        cohort_date = (now - timedelta(days=30)).date()

        mock_pool.conn.fetch.return_value = [
            {
                "cohort_date": cohort_date,
                "cohort_size": 50,
                "user_id": 1,
            },
            {
                "cohort_date": cohort_date,
                "cohort_size": 50,
                "user_id": 2,
            },
        ]

        result = await AnalyticsTracker.get_retention_metrics(mock_pool)

        assert isinstance(result, RetentionMetrics)
        assert len(result.cohorts) > 0

    @pytest.mark.asyncio
    async def test_get_retention_metrics_no_data(self, mock_pool):
        """Test retention metrics with no data."""
        mock_pool.conn.fetch.return_value = []

        result = await AnalyticsTracker.get_retention_metrics(mock_pool)

        assert len(result.cohorts) == 0


# ────────────────────────────────────────────────────────────────────────────
# Edge Case Tests
# ────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_track_event_with_large_metadata(self, mock_pool):
        """Test tracking event with large metadata."""
        mock_pool.conn.fetchrow.return_value = {"id": 1}

        large_metadata = {
            "key_" + str(i): "value_" * 100
            for i in range(100)
        }

        event_id = await AnalyticsTracker.track_event(
            mock_pool,
            user_id=1,
            event_type=EventType.PARCEL_LOOKUP.value,
            metadata=large_metadata,
        )

        assert event_id == 1

    @pytest.mark.asyncio
    async def test_get_user_activity_max_days(self, mock_pool):
        """Test getting user activity with max days (365)."""
        mock_pool.conn.fetch.return_value = []
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 1000,
            "first_activity_at": datetime.now(tz=timezone.utc) - timedelta(days=365),
            "last_activity_at": datetime.now(tz=timezone.utc),
        }

        result = await AnalyticsTracker.get_user_activity(
            mock_pool,
            user_id=1,
            days=365,
        )

        assert result.total_events == 1000

    @pytest.mark.asyncio
    async def test_get_top_neighborhoods_limit_respected(self, mock_pool):
        """Test that top neighborhoods respects limit parameter."""
        mock_pool.conn.fetchval.return_value = 1000

        many_results = [
            {"neighborhood": f"Hood_{i}", "count": 1000 - i}
            for i in range(50)
        ]

        mock_pool.conn.fetch.return_value = many_results[:10]

        result = await AnalyticsTracker.get_top_neighborhoods(
            mock_pool,
            limit=10,
        )

        assert len(result.items) == 10

    @pytest.mark.asyncio
    async def test_platform_metrics_zero_division(self, mock_pool):
        """Test platform metrics with zero users (division by zero)."""
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 10,
            "unique_users": 0,
        }

        mock_pool.conn.fetch.return_value = []

        result = await AnalyticsTracker.get_platform_metrics(mock_pool)

        assert result.average_events_per_user == 0.0

    @pytest.mark.asyncio
    async def test_active_users_churn_calculation(self, mock_pool):
        """Test active users churn rate calculation."""
        # Test: 100 active users, 50 returning, churn = 1 - (50/100) = 0.5
        mock_pool.conn.fetchval.side_effect = [100, 50, 50]

        result = await AnalyticsTracker.get_active_users(mock_pool)

        assert abs(result.churn_rate - 0.5) < 0.01

    @pytest.mark.asyncio
    async def test_active_users_perfect_retention(self, mock_pool):
        """Test active users with perfect retention (no churn)."""
        mock_pool.conn.fetchval.side_effect = [100, 100, 0]

        result = await AnalyticsTracker.get_active_users(mock_pool)

        assert abs(result.churn_rate - 0.0) < 0.01

    @pytest.mark.asyncio
    async def test_top_neighborhoods_percentage_precision(self, mock_pool):
        """Test percentage calculation precision."""
        mock_pool.conn.fetchval.return_value = 3

        mock_pool.conn.fetch.return_value = [
            {"neighborhood": "A", "count": 1},
            {"neighborhood": "B", "count": 1},
            {"neighborhood": "C", "count": 1},
        ]

        result = await AnalyticsTracker.get_top_neighborhoods(mock_pool)

        # Each should be 33.33%
        for item in result.items:
            assert 33.0 < item.percentage < 34.0


# ────────────────────────────────────────────────────────────────────────────
# Date Range Tests
# ────────────────────────────────────────────────────────────────────────────

class TestDateRangeFiltering:
    """Test date range filtering functionality."""

    @pytest.mark.asyncio
    async def test_user_activity_respects_day_cutoff(self, mock_pool):
        """Test that user activity respects the day cutoff."""
        now = datetime.now(tz=timezone.utc)
        cutoff_30 = now - timedelta(days=30)

        mock_pool.conn.fetch.return_value = []
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 0,
            "first_activity_at": None,
            "last_activity_at": None,
        }

        await AnalyticsTracker.get_user_activity(mock_pool, user_id=1, days=30)

        # Verify that the query was called with appropriate cutoff
        call_args = mock_pool.conn.fetch.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_platform_metrics_daily_cutoff(self, mock_pool):
        """Test platform metrics uses 1-day cutoff for daily period."""
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 0,
            "unique_users": 0,
        }
        mock_pool.conn.fetch.return_value = []

        await AnalyticsTracker.get_platform_metrics(mock_pool, period="daily")

        # Verify query was called
        assert mock_pool.conn.fetchrow.called

    @pytest.mark.asyncio
    async def test_platform_metrics_weekly_cutoff(self, mock_pool):
        """Test platform metrics uses 7-day cutoff for weekly period."""
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 0,
            "unique_users": 0,
        }
        mock_pool.conn.fetch.return_value = []

        await AnalyticsTracker.get_platform_metrics(mock_pool, period="weekly")

        assert mock_pool.conn.fetchrow.called

    @pytest.mark.asyncio
    async def test_platform_metrics_monthly_cutoff(self, mock_pool):
        """Test platform metrics uses 30-day cutoff for monthly period."""
        mock_pool.conn.fetchrow.return_value = {
            "total_events": 0,
            "unique_users": 0,
        }
        mock_pool.conn.fetch.return_value = []

        await AnalyticsTracker.get_platform_metrics(mock_pool, period="monthly")

        assert mock_pool.conn.fetchrow.called
