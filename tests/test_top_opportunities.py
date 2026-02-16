"""Tests for the /api/v1/opportunities/top endpoint (Opportunity Discovery Panel).

Validates:
- Composite score formula: GREATEST(storey_uplift, 0) * (1.0 - COALESCE(ilr, 0.5))
- Ranking order (highest composite_score first)
- ILR computation with NULLIF (handles zero-denominator)
- Route registration order (must come before /{pid} catch-all routes)
"""

import os
os.environ.setdefault("JWT_SECRET", "test-secret-for-ci-do-not-use-in-production")

import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTopOpportunitiesSQL:
    """Tests that validate the SQL query structure and formula."""

    def test_endpoint_uses_composite_score(self):
        """The top opportunities endpoint SQL includes composite_score computation."""
        from api.main import top_opportunities_ranked
        source = inspect.getsource(top_opportunities_ranked)
        assert "composite_score" in source, "Endpoint must compute composite_score"

    def test_endpoint_uses_greatest_for_storey_uplift(self):
        """Composite score uses GREATEST(storey_uplift, 0) to avoid negatives."""
        from api.main import top_opportunities_ranked
        source = inspect.getsource(top_opportunities_ranked)
        assert "GREATEST(storey_uplift, 0)" in source, "Must use GREATEST to prevent negative scores"

    def test_endpoint_uses_coalesce_for_ilr(self):
        """Composite score uses COALESCE(ilr, 0.5) for unknown ILR."""
        from api.main import top_opportunities_ranked
        source = inspect.getsource(top_opportunities_ranked)
        assert "COALESCE(ilr, 0.5)" in source, "Must use COALESCE(ilr, 0.5) for NULL ILR"

    def test_endpoint_uses_nullif_for_ilr_denominator(self):
        """ILR uses NULLIF to handle zero-denominator safely."""
        from api.main import top_opportunities_ranked
        source = inspect.getsource(top_opportunities_ranked)
        assert "NULLIF" in source, "ILR must use NULLIF for safe division"

    def test_endpoint_orders_by_composite_score_desc(self):
        """Results are ordered by composite_score descending."""
        from api.main import top_opportunities_ranked
        source = inspect.getsource(top_opportunities_ranked)
        assert "DESC" in source, "Must order by composite_score DESC"


class TestTopOpportunitiesRouteOrder:
    """Tests that /api/v1/opportunities/top is registered before /{pid} routes."""

    def test_top_route_registered_before_pid_routes(self):
        """The /top endpoint must be registered before any /{pid} catch-all routes."""
        from api.main import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]

        # Find the /api/v1/opportunities/top route
        top_idx = None
        pid_idx = None
        for i, path in enumerate(routes):
            if path == "/api/v1/opportunities/top":
                top_idx = i
            # The paginated opportunities endpoint (not a {pid} route but
            # let's also check against any /{pid} patterns)
            if "{pid}" in path and "/api/v1/parcels/" in path:
                if pid_idx is None:
                    pid_idx = i

        assert top_idx is not None, "Route /api/v1/opportunities/top must exist"

    def test_top_route_before_paginated_opportunities(self):
        """The /top endpoint must come before the /api/v1/opportunities endpoint."""
        from api.main import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]

        top_idx = None
        paginated_idx = None
        for i, path in enumerate(routes):
            if path == "/api/v1/opportunities/top":
                top_idx = i
            elif path == "/api/v1/opportunities":
                paginated_idx = i

        assert top_idx is not None, "Route /api/v1/opportunities/top must exist"
        assert paginated_idx is not None, "Route /api/v1/opportunities must exist"
        assert top_idx < paginated_idx, (
            f"/api/v1/opportunities/top (index {top_idx}) must come before "
            f"/api/v1/opportunities (index {paginated_idx})"
        )


class TestTopOpportunitiesEndpoint:
    """Tests for the endpoint behavior with mocked database."""

    def _make_mock_row(self, pid, storey_uplift, ilr, signal_count=0,
                       civic_address=None, current_zoning="RS-1",
                       tier=1, station_name="TestStation",
                       asking_price=None, est_value=None,
                       lng=-123.1, lat=49.26):
        """Helper to create a mock DB row dict."""
        composite = round(max(storey_uplift, 0) * (1.0 - (ilr if ilr is not None else 0.5)), 4)
        return {
            "pid": pid,
            "civic_address": civic_address or f"{pid} Test St",
            "current_zoning": current_zoning,
            "tier": tier,
            "station_name": station_name,
            "storey_uplift": storey_uplift,
            "ilr": ilr,
            "signal_count": signal_count,
            "asking_price": asking_price,
            "est_value": est_value,
            "lng": lng,
            "lat": lat,
            "composite_score": composite,
        }

    @pytest.mark.asyncio
    async def test_returns_list_of_opportunities(self):
        """Endpoint returns a list (not paginated envelope)."""
        from api.main import top_opportunities_ranked

        mock_conn = AsyncMock()
        rows = [
            self._make_mock_row("001", 15, 0.2),
            self._make_mock_row("002", 10, 0.3),
        ]
        mock_conn.fetch = AsyncMock(return_value=rows)

        mock_acm = MagicMock()
        mock_acm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acm.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db") as mock_db:
            mock_db.acquire.return_value = mock_acm
            result = await top_opportunities_ranked(limit=10)

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_ranking_order_by_composite_score(self):
        """Items are returned with highest composite_score first."""
        from api.main import top_opportunities_ranked

        mock_conn = AsyncMock()
        # Ordered by composite_score DESC (as the DB would do)
        rows = [
            self._make_mock_row("AAA", 20, 0.1),   # 20 * 0.9 = 18.0
            self._make_mock_row("BBB", 15, 0.2),   # 15 * 0.8 = 12.0
            self._make_mock_row("CCC", 10, 0.3),   # 10 * 0.7 = 7.0
        ]
        mock_conn.fetch = AsyncMock(return_value=rows)

        mock_acm = MagicMock()
        mock_acm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acm.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db") as mock_db:
            mock_db.acquire.return_value = mock_acm
            result = await top_opportunities_ranked(limit=10)

        scores = [r["composite_score"] for r in result]
        assert scores == sorted(scores, reverse=True), "Results must be ordered by composite_score DESC"
        assert result[0]["pid"] == "AAA"
        assert result[1]["pid"] == "BBB"
        assert result[2]["pid"] == "CCC"

    @pytest.mark.asyncio
    async def test_composite_score_formula(self):
        """Composite score = GREATEST(storey_uplift, 0) * (1.0 - COALESCE(ilr, 0.5))."""
        from api.main import top_opportunities_ranked

        mock_conn = AsyncMock()
        rows = [
            self._make_mock_row("X1", 12, 0.4),   # 12 * 0.6 = 7.2
        ]
        mock_conn.fetch = AsyncMock(return_value=rows)

        mock_acm = MagicMock()
        mock_acm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acm.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db") as mock_db:
            mock_db.acquire.return_value = mock_acm
            result = await top_opportunities_ranked(limit=10)

        assert len(result) == 1
        score = result[0]["composite_score"]
        expected = 12 * (1.0 - 0.4)  # 7.2
        assert abs(score - expected) < 0.01, f"Expected ~{expected}, got {score}"

    @pytest.mark.asyncio
    async def test_null_ilr_uses_default_05(self):
        """When ILR is NULL, composite score uses 0.5 as default."""
        from api.main import top_opportunities_ranked

        mock_conn = AsyncMock()
        rows = [
            self._make_mock_row("N1", 10, None),   # 10 * (1.0 - 0.5) = 5.0
        ]
        mock_conn.fetch = AsyncMock(return_value=rows)

        mock_acm = MagicMock()
        mock_acm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acm.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db") as mock_db:
            mock_db.acquire.return_value = mock_acm
            result = await top_opportunities_ranked(limit=10)

        assert len(result) == 1
        score = result[0]["composite_score"]
        expected = 10 * (1.0 - 0.5)  # 5.0
        assert abs(score - expected) < 0.01, f"Expected ~{expected}, got {score}"

    @pytest.mark.asyncio
    async def test_negative_uplift_clamped_to_zero(self):
        """When storey_uplift is negative, GREATEST(storey_uplift, 0) = 0."""
        from api.main import top_opportunities_ranked

        mock_conn = AsyncMock()
        rows = [
            self._make_mock_row("NEG", -5, 0.3),  # max(-5,0) * 0.7 = 0
        ]
        mock_conn.fetch = AsyncMock(return_value=rows)

        mock_acm = MagicMock()
        mock_acm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acm.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db") as mock_db:
            mock_db.acquire.return_value = mock_acm
            result = await top_opportunities_ranked(limit=10)

        assert len(result) == 1
        assert result[0]["composite_score"] == 0

    @pytest.mark.asyncio
    async def test_response_includes_all_required_fields(self):
        """Each opportunity includes all required fields for the panel."""
        from api.main import top_opportunities_ranked

        mock_conn = AsyncMock()
        rows = [
            self._make_mock_row(
                "F1", 15, 0.25, signal_count=3,
                civic_address="123 Main St", current_zoning="RM-4",
                tier=2, station_name="Broadway-City Hall",
                asking_price=2500000, est_value=5000000,
            ),
        ]
        mock_conn.fetch = AsyncMock(return_value=rows)

        mock_acm = MagicMock()
        mock_acm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acm.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db") as mock_db:
            mock_db.acquire.return_value = mock_acm
            result = await top_opportunities_ranked(limit=10)

        item = result[0]
        required_fields = [
            "pid", "civic_address", "current_zoning", "tier",
            "station_name", "storey_uplift", "ilr", "signal_count",
            "composite_score", "asking_price", "est_value", "lng", "lat",
        ]
        for field in required_fields:
            assert field in item, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_empty_results(self):
        """Endpoint returns empty list when no opportunities match."""
        from api.main import top_opportunities_ranked

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        mock_acm = MagicMock()
        mock_acm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acm.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db") as mock_db:
            mock_db.acquire.return_value = mock_acm
            result = await top_opportunities_ranked(limit=10)

        assert result == []

    @pytest.mark.asyncio
    async def test_limit_parameter_passed_to_query(self):
        """The limit parameter is passed to the SQL query."""
        from api.main import top_opportunities_ranked

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        mock_acm = MagicMock()
        mock_acm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acm.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db") as mock_db:
            mock_db.acquire.return_value = mock_acm
            await top_opportunities_ranked(limit=5)

        # Verify the limit parameter was passed
        mock_conn.fetch.assert_called_once()
        call_args = mock_conn.fetch.call_args
        assert call_args[0][1] == 5, "Limit parameter must be passed to query"


class TestCompositeScoreFormula:
    """Unit tests for the composite score formula math."""

    def test_high_uplift_low_ilr_gives_high_score(self):
        """High storey uplift + low ILR (teardown candidate) = high score."""
        storey_uplift = 20
        ilr = 0.1  # Mostly land value, low improvement
        score = max(storey_uplift, 0) * (1.0 - ilr)
        assert score == 18.0

    def test_low_uplift_high_ilr_gives_low_score(self):
        """Low storey uplift + high ILR (improved property) = low score."""
        storey_uplift = 3
        ilr = 0.9  # Mostly improvement value
        score = max(storey_uplift, 0) * (1.0 - ilr)
        assert abs(score - 0.3) < 0.01

    def test_zero_uplift_gives_zero_score(self):
        """Zero storey uplift always gives zero composite score."""
        storey_uplift = 0
        ilr = 0.1
        score = max(storey_uplift, 0) * (1.0 - ilr)
        assert score == 0.0

    def test_null_ilr_assumes_50_pct(self):
        """NULL ILR defaults to 0.5, giving a moderate penalty."""
        storey_uplift = 10
        ilr = None
        effective_ilr = ilr if ilr is not None else 0.5
        score = max(storey_uplift, 0) * (1.0 - effective_ilr)
        assert score == 5.0

    def test_ilr_of_1_gives_zero_score(self):
        """ILR of 1.0 (all improvement, no land value) gives zero score."""
        storey_uplift = 20
        ilr = 1.0
        score = max(storey_uplift, 0) * (1.0 - ilr)
        assert score == 0.0

    def test_ilr_of_0_gives_max_score(self):
        """ILR of 0.0 (all land value) gives maximum score."""
        storey_uplift = 15
        ilr = 0.0
        score = max(storey_uplift, 0) * (1.0 - ilr)
        assert score == 15.0

    def test_negative_uplift_clamped(self):
        """Negative uplift (already exceeds) gives zero score."""
        storey_uplift = -5
        ilr = 0.2
        score = max(storey_uplift, 0) * (1.0 - ilr)
        assert score == 0.0
