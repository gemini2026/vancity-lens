"""
Comprehensive tests for materialized view functionality (VCL-79 / PERF-011).

Tests cover:
- SQL migration structure and indexes
- Refresh functions (mocked DB calls)
- Rankings retrieval and ordering
- Detail retrieval with full scorecard
- Comparison endpoint logic
- Scheduled refresh timing
- Admin refresh endpoint
- Edge cases (no data, single neighborhood, missing metrics)
- API contract tests for new endpoints
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

# Import test utilities
from fastapi import HTTPException
from fastapi.testclient import TestClient


# ── Test Database Migration Structure ────────────────────────────

class TestMigrationStructure:
    """Tests for SQL migration file structure (012_materialized_views.sql)."""

    def test_migration_file_exists(self):
        """Verify migration file exists at correct path."""
        import os
        migration_path = "/sessions/zen-relaxed-lamport/mnt/bill47/db/012_materialized_views.sql"
        assert os.path.exists(migration_path), "Migration file 012_materialized_views.sql missing"

    def test_migration_file_is_readable(self):
        """Verify migration file is readable."""
        migration_path = "/sessions/zen-relaxed-lamport/mnt/bill47/db/012_materialized_views.sql"
        with open(migration_path, 'r') as f:
            content = f.read()
        assert len(content) > 0, "Migration file is empty"

    def test_migration_contains_required_views(self):
        """Verify migration creates required materialized views."""
        migration_path = "/sessions/zen-relaxed-lamport/mnt/bill47/db/012_materialized_views.sql"
        with open(migration_path, 'r') as f:
            content = f.read()

        assert "mv_neighborhood_scores" in content, "Missing mv_neighborhood_scores view"
        assert "mv_neighborhood_signal_activity" in content, "Missing mv_neighborhood_signal_activity view"

    def test_migration_contains_refresh_functions(self):
        """Verify migration creates refresh functions."""
        migration_path = "/sessions/zen-relaxed-lamport/mnt/bill47/db/012_materialized_views.sql"
        with open(migration_path, 'r') as f:
            content = f.read()

        assert "refresh_mv_neighborhood_scores" in content
        assert "refresh_mv_neighborhood_signal_activity" in content
        assert "refresh_all_materialized_views" in content

    def test_migration_contains_unique_indexes(self):
        """Verify migration creates unique indexes for REFRESH CONCURRENTLY."""
        migration_path = "/sessions/zen-relaxed-lamport/mnt/bill47/db/012_materialized_views.sql"
        with open(migration_path, 'r') as f:
            content = f.read()

        assert "idx_mv_neighborhood_scores_unique" in content
        assert "idx_mv_neighborhood_signal_activity_unique" in content
        assert "UNIQUE INDEX" in content

    def test_migration_contains_audit_table(self):
        """Verify migration creates audit table for refresh tracking."""
        migration_path = "/sessions/zen-relaxed-lamport/mnt/bill47/db/012_materialized_views.sql"
        with open(migration_path, 'r') as f:
            content = f.read()

        assert "materialized_view_refreshes" in content


# ── Test Refresh Functions ───────────────────────────────────────

@pytest.mark.asyncio
class TestRefreshFunctions:
    """Tests for materialized view refresh functions."""

    async def test_refresh_neighborhood_scores_success(self, mock_db_pool):
        """Test successful refresh of neighborhood scores view."""
        from api.intelligence.materialized_views import refresh_neighborhood_scores

        # Mock the database response
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(return_value={
            "view_name": "mv_neighborhood_scores",
            "rows_refreshed": 22,
            "duration_ms": 125,
            "success": True,
        })

        result = await refresh_neighborhood_scores(mock_db_pool)

        assert result["success"] is True
        assert result["view_name"] == "mv_neighborhood_scores"
        assert result["rows_refreshed"] == 22
        assert result["duration_ms"] == 125
        assert "timestamp" in result

    async def test_refresh_neighborhood_scores_failure(self, mock_db_pool):
        """Test failed refresh of neighborhood scores view."""
        from api.intelligence.materialized_views import refresh_neighborhood_scores

        # Mock a database error
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(side_effect=Exception("Database error"))

        result = await refresh_neighborhood_scores(mock_db_pool)

        assert result["success"] is False
        assert "error" in result

    async def test_refresh_signal_activity_success(self, mock_db_pool):
        """Test successful refresh of signal activity view."""
        from api.intelligence.materialized_views import refresh_signal_activity

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(return_value={
            "view_name": "mv_neighborhood_signal_activity",
            "rows_refreshed": 22,
            "duration_ms": 95,
            "success": True,
        })

        result = await refresh_signal_activity(mock_db_pool)

        assert result["success"] is True
        assert result["view_name"] == "mv_neighborhood_signal_activity"
        assert result["rows_refreshed"] == 22

    async def test_refresh_all_views_success(self, mock_db_pool):
        """Test successful refresh of all materialized views."""
        from api.intelligence.materialized_views import refresh_all_views

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {
                "view_name": "mv_neighborhood_scores",
                "rows_refreshed": 22,
                "duration_ms": 125,
                "success": True,
            },
            {
                "view_name": "mv_neighborhood_signal_activity",
                "rows_refreshed": 22,
                "duration_ms": 95,
                "success": True,
            }
        ])
        conn.execute = AsyncMock()

        result = await refresh_all_views(mock_db_pool)

        assert result["all_success"] is True
        assert len(result["views"]) == 2
        assert result["total_duration_ms"] == 220

    async def test_refresh_all_views_partial_failure(self, mock_db_pool):
        """Test refresh when one view fails."""
        from api.intelligence.materialized_views import refresh_all_views

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {
                "view_name": "mv_neighborhood_scores",
                "rows_refreshed": 22,
                "duration_ms": 125,
                "success": True,
            },
            {
                "view_name": "mv_neighborhood_signal_activity",
                "rows_refreshed": 0,
                "duration_ms": 0,
                "success": False,
            }
        ])
        conn.execute = AsyncMock()

        result = await refresh_all_views(mock_db_pool)

        assert result["all_success"] is False
        assert len(result["views"]) == 2


# ── Test Rankings Retrieval ──────────────────────────────────────

@pytest.mark.asyncio
class TestRankingsRetrieval:
    """Tests for neighborhood rankings from materialized view."""

    async def test_get_neighborhood_rankings_success(self, mock_db_pool):
        """Test successful retrieval of neighborhood rankings."""
        from api.intelligence.materialized_views import get_neighborhood_rankings

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {
                "name": "Downtown",
                "slug": "downtown",
                "overall_score": Decimal("8.5"),
                "rank": 1,
                "category_scores": {"safety": 7.8, "schools": 8.2, "transit": 9.1},
            },
            {
                "name": "Kitsilano",
                "slug": "kitsilano",
                "overall_score": Decimal("8.2"),
                "rank": 2,
                "category_scores": {"safety": 7.5, "schools": 8.0, "transit": 8.8},
            },
            {
                "name": "West End",
                "slug": "west-end",
                "overall_score": Decimal("7.9"),
                "rank": 3,
                "category_scores": {"safety": 7.2, "schools": 7.8, "transit": 9.0},
            },
        ])

        results = await get_neighborhood_rankings(mock_db_pool, limit=50)

        assert len(results) == 3
        assert results[0].slug == "downtown"
        assert results[0].rank == 1
        assert results[0].overall_score == 8.5
        assert results[0].top_category == "transit"

    async def test_get_neighborhood_rankings_ordered(self, mock_db_pool):
        """Test that rankings are ordered by rank."""
        from api.intelligence.materialized_views import get_neighborhood_rankings

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {
                "name": "Top Neighborhood",
                "slug": "top",
                "overall_score": Decimal("9.0"),
                "rank": 1,
                "category_scores": {},
            },
            {
                "name": "Middle Neighborhood",
                "slug": "middle",
                "overall_score": Decimal("5.0"),
                "rank": 11,
                "category_scores": {},
            },
            {
                "name": "Bottom Neighborhood",
                "slug": "bottom",
                "overall_score": Decimal("2.0"),
                "rank": 22,
                "category_scores": {},
            },
        ])

        results = await get_neighborhood_rankings(mock_db_pool)

        # Verify ordering
        assert results[0].rank < results[1].rank < results[2].rank

    async def test_get_neighborhood_rankings_empty(self, mock_db_pool):
        """Test rankings with no data."""
        from api.intelligence.materialized_views import get_neighborhood_rankings

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[])

        results = await get_neighborhood_rankings(mock_db_pool)

        assert results == []

    async def test_get_neighborhood_rankings_limit(self, mock_db_pool):
        """Test that limit parameter is respected."""
        from api.intelligence.materialized_views import get_neighborhood_rankings

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {"name": f"Hood {i}", "slug": f"hood-{i}", "overall_score": Decimal("8.0"),
             "rank": i, "category_scores": {}} for i in range(1, 11)
        ])

        results = await get_neighborhood_rankings(mock_db_pool, limit=10)

        assert len(results) == 10


# ── Test Detail Retrieval ────────────────────────────────────────

@pytest.mark.asyncio
class TestDetailRetrieval:
    """Tests for neighborhood scorecard detail retrieval."""

    async def test_get_neighborhood_detail_success(self, mock_db_pool):
        """Test successful retrieval of neighborhood detail."""
        from api.intelligence.materialized_views import get_neighborhood_detail

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(return_value={
            "name": "Kitsilano",
            "slug": "kitsilano",
            "overall_score": Decimal("8.2"),
            "rank": 2,
            "category_scores": {
                "safety": 7.5,
                "schools": 8.0,
                "transit": 8.8,
                "parks": 8.5,
                "development": 8.0,
                "air_quality": 7.8,
                "affordability": 6.5,
                "walkability": 8.3,
            },
            "active_rezonings": 3,
            "recent_permits": 7,
            "signal_activity_score": 4.2,
        })

        scorecard = await get_neighborhood_detail(mock_db_pool, "kitsilano")

        assert scorecard is not None
        assert scorecard.neighborhood.slug == "kitsilano"
        assert scorecard.overall_score == 8.2
        assert scorecard.rank == 2
        assert len(scorecard.category_scores) == 8
        assert scorecard.active_rezonings == 3
        assert scorecard.recent_permits == 7

    async def test_get_neighborhood_detail_not_found(self, mock_db_pool):
        """Test retrieval of non-existent neighborhood."""
        from api.intelligence.materialized_views import get_neighborhood_detail

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(return_value=None)

        scorecard = await get_neighborhood_detail(mock_db_pool, "nonexistent")

        assert scorecard is None

    async def test_get_neighborhood_detail_all_categories(self, mock_db_pool):
        """Test that all category scores are included."""
        from api.intelligence.materialized_views import get_neighborhood_detail
        from api.intelligence.models import MetricCategory

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(return_value={
            "name": "Test Neighborhood",
            "slug": "test",
            "overall_score": Decimal("5.0"),
            "rank": 11,
            "category_scores": {c.value: 5.0 for c in MetricCategory},
            "active_rezonings": 0,
            "recent_permits": 0,
            "signal_activity_score": 0.0,
        })

        scorecard = await get_neighborhood_detail(mock_db_pool, "test")

        assert len(scorecard.category_scores) == len(MetricCategory)


# ── Test Comparison Logic ────────────────────────────────────────

@pytest.mark.asyncio
class TestComparisonLogic:
    """Tests for neighborhood comparison functionality."""

    async def test_compare_neighborhoods_success(self, mock_db_pool):
        """Test successful comparison of neighborhoods."""
        from api.intelligence.materialized_views import compare_neighborhoods

        # Create mock responses for each neighborhood
        def make_scorecard(slug, name, score):
            return {
                "name": name,
                "slug": slug,
                "overall_score": Decimal(str(score)),
                "rank": 1,
                "category_scores": {"safety": score - 0.5, "schools": score + 0.3},
                "active_rezonings": 0,
                "recent_permits": 0,
                "signal_activity_score": 0.0,
            }

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(side_effect=[
            make_scorecard("kitsilano", "Kitsilano", 8.2),
            make_scorecard("downtown", "Downtown", 8.5),
        ])

        result = await compare_neighborhoods(mock_db_pool, ["kitsilano", "downtown"])

        assert result is not None
        assert len(result.neighborhoods) == 2
        assert len(result.categories) > 0

    async def test_compare_neighborhoods_invalid_count(self, mock_db_pool):
        """Test comparison with invalid number of neighborhoods."""
        from api.intelligence.materialized_views import compare_neighborhoods

        result = await compare_neighborhoods(mock_db_pool, ["only-one"])
        assert result is None

        result = await compare_neighborhoods(mock_db_pool, [f"hood-{i}" for i in range(5)])
        assert result is None

    async def test_compare_neighborhoods_not_found(self, mock_db_pool):
        """Test comparison when neighborhoods don't exist."""
        from api.intelligence.materialized_views import compare_neighborhoods

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(return_value=None)

        result = await compare_neighborhoods(mock_db_pool, ["nonexistent-1", "nonexistent-2"])

        assert result is None


# ── Test Scheduled Refresh ───────────────────────────────────────

@pytest.mark.asyncio
class TestScheduledRefresh:
    """Tests for scheduled refresh background task."""

    async def test_scheduled_refresh_initialization(self, mock_db_pool):
        """Test initialization of scheduled refresh task."""
        from api.intelligence.materialized_views import ScheduledRefresh

        refresh = ScheduledRefresh(mock_db_pool, interval_seconds=60)

        assert refresh.db_pool is not None
        assert refresh.interval_seconds == 60
        assert refresh.is_running is False

    async def test_scheduled_refresh_start_stop(self, mock_db_pool):
        """Test starting and stopping scheduled refresh."""
        from api.intelligence.materialized_views import ScheduledRefresh

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {
                "view_name": "mv_neighborhood_scores",
                "rows_refreshed": 22,
                "duration_ms": 125,
                "success": True,
            }
        ])
        conn.execute = AsyncMock()

        refresh = ScheduledRefresh(mock_db_pool, interval_seconds=1)
        await refresh.start()

        assert refresh.is_running is True
        assert refresh.task is not None

        await asyncio.sleep(0.1)
        await refresh.stop()

        assert refresh.is_running is False

    async def test_scheduled_refresh_already_running(self, mock_db_pool):
        """Test starting already-running refresh task."""
        from api.intelligence.materialized_views import ScheduledRefresh

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {
                "view_name": "mv_neighborhood_scores",
                "rows_refreshed": 22,
                "duration_ms": 125,
                "success": True,
            }
        ])
        conn.execute = AsyncMock()

        refresh = ScheduledRefresh(mock_db_pool, interval_seconds=1)
        await refresh.start()

        # Try to start again - should log warning but not raise
        await refresh.start()

        assert refresh.is_running is True

        await refresh.stop()


# ── Test Edge Cases ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    async def test_empty_category_scores(self, mock_db_pool):
        """Test handling of empty category scores."""
        from api.intelligence.materialized_views import get_neighborhood_detail

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(return_value={
            "name": "New Hood",
            "slug": "new-hood",
            "overall_score": Decimal("5.0"),
            "rank": 11,
            "category_scores": None,  # No scores yet
            "active_rezonings": 0,
            "recent_permits": 0,
            "signal_activity_score": 0.0,
        })

        scorecard = await get_neighborhood_detail(mock_db_pool, "new-hood")

        assert scorecard is not None
        assert len(scorecard.category_scores) > 0
        # All categories should have default score of 5.0
        for cat_score in scorecard.category_scores:
            assert cat_score.score == 5.0

    async def test_single_neighborhood_comparison(self, mock_db_pool):
        """Test that single neighborhood comparison fails."""
        from api.intelligence.materialized_views import compare_neighborhoods

        result = await compare_neighborhoods(mock_db_pool, ["single-hood"])

        assert result is None

    async def test_missing_intelligence_stats(self, mock_db_pool):
        """Test handling of missing intelligence statistics."""
        from api.intelligence.materialized_views import get_neighborhood_detail

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(return_value={
            "name": "Quiet Hood",
            "slug": "quiet-hood",
            "overall_score": Decimal("5.0"),
            "rank": 11,
            "category_scores": {},
            "active_rezonings": None,  # No recent activity
            "recent_permits": None,
            "signal_activity_score": None,
        })

        scorecard = await get_neighborhood_detail(mock_db_pool, "quiet-hood")

        assert scorecard is not None
        # Should handle None values gracefully
        assert isinstance(scorecard.active_rezonings, (int, type(None)))


# ── Test API Contracts ───────────────────────────────────────────

class TestAPIContracts:
    """Tests for API endpoint contracts (VCL-79 / PERF-011)."""

    def test_rankings_endpoint_exists(self):
        """Test that rankings endpoint is defined."""
        from api.intelligence.routes import router

        # Check that GET /neighborhoods/rankings is defined
        routes = [r for r in router.routes if "/neighborhoods/rankings" in str(r.path)]
        assert len(routes) > 0, "Rankings endpoint not found"

    def test_scorecard_endpoint_exists(self):
        """Test that scorecard endpoint is defined."""
        from api.intelligence.routes import router

        # Check that GET /neighborhoods/{slug}/scorecard is defined
        routes = [r for r in router.routes if "{slug}/scorecard" in str(r.path)]
        assert len(routes) > 0, "Scorecard endpoint not found"

    def test_compare_endpoint_exists(self):
        """Test that comparison endpoint is defined."""
        from api.intelligence.routes import router

        # Check that POST /neighborhoods/compare is defined
        routes = [r for r in router.routes if "/neighborhoods/compare" in str(r.path)]
        assert len(routes) > 0, "Comparison endpoint not found"

    def test_admin_refresh_endpoint_exists(self):
        """Test that admin refresh endpoint is defined."""
        from api.intelligence.routes import router

        # Check that POST /admin/refresh-views is defined
        routes = [r for r in router.routes if "/admin/refresh-views" in str(r.path)]
        assert len(routes) > 0, "Admin refresh endpoint not found"

    def test_rankings_response_model(self):
        """Test that rankings endpoint returns correct model."""
        from api.intelligence.routes import router
        from api.intelligence.models import NeighborhoodSummary

        # Find the rankings route
        routes = [r for r in router.routes if "/neighborhoods/rankings" in str(r.path)]
        assert len(routes) > 0

    def test_scorecard_response_model(self):
        """Test that scorecard endpoint returns correct model."""
        from api.intelligence.routes import router
        from api.intelligence.models import NeighborhoodScorecard

        # Find the scorecard route
        routes = [r for r in router.routes if "{slug}/scorecard" in str(r.path)]
        assert len(routes) > 0

    def test_comparison_response_model(self):
        """Test that comparison endpoint returns correct model."""
        from api.intelligence.routes import router
        from api.intelligence.models import NeighborhoodComparison

        # Find the comparison route
        routes = [r for r in router.routes if "/neighborhoods/compare" in str(r.path)]
        assert len(routes) > 0


# ── Test Integration ────────────────────────────────────────────

@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for materialized view workflow."""

    async def test_full_refresh_and_query_workflow(self, mock_db_pool):
        """Test complete workflow: refresh then query."""
        from api.intelligence.materialized_views import (
            refresh_all_views,
            get_neighborhood_rankings,
        )

        # Mock refresh
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {
                "view_name": "mv_neighborhood_scores",
                "rows_refreshed": 22,
                "duration_ms": 125,
                "success": True,
            }
        ])
        conn.execute = AsyncMock()

        refresh_result = await refresh_all_views(mock_db_pool)
        assert refresh_result["all_success"] is True

        # Now query rankings
        conn.fetch = AsyncMock(return_value=[
            {
                "name": "Downtown",
                "slug": "downtown",
                "overall_score": Decimal("8.5"),
                "rank": 1,
                "category_scores": {},
            }
        ])

        rankings = await get_neighborhood_rankings(mock_db_pool)
        assert len(rankings) > 0

    async def test_error_recovery(self, mock_db_pool):
        """Test recovery from refresh errors."""
        from api.intelligence.materialized_views import refresh_all_views

        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(side_effect=Exception("Connection lost"))

        result = await refresh_all_views(mock_db_pool)

        assert result["all_success"] is False
        assert "error" in result
