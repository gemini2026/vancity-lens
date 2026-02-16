"""
Tests for neighborhood investment metrics computation.

Covers:
- Supply pipeline count with active/completed projects
- Average approval timeline calculation
- Supply pressure (proposed units / parcel count)
- Development momentum (90-day signal ratio)
- Edge cases: zero pipeline, zero signals, zero parcels, missing tables
- Slug-to-name resolution
- Combined metrics endpoint
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from api.intelligence.neighborhood_investment import (
    slug_to_neighborhood_name,
    resolve_neighborhood_name,
    get_supply_pipeline_count,
    get_avg_approval_timeline,
    get_supply_pressure,
    get_development_momentum,
    get_neighborhood_investment_metrics,
)


# ════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_conn():
    """Mock asyncpg connection."""
    conn = AsyncMock()
    return conn


# ════════════════════════════════════════════════════════════════════════════
# SLUG-TO-NAME CONVERSION
# ════════════════════════════════════════════════════════════════════════════

class TestSlugToName:
    def test_simple_slug(self):
        assert slug_to_neighborhood_name("downtown") == "Downtown"

    def test_multi_word_slug(self):
        assert slug_to_neighborhood_name("mount-pleasant") == "Mount Pleasant"

    def test_hyphenated_name(self):
        assert slug_to_neighborhood_name("dunbar-southlands") == "Dunbar Southlands"

    def test_three_word_slug(self):
        assert slug_to_neighborhood_name("west-point-grey") == "West Point Grey"


class TestResolveNeighborhoodName:
    @pytest.mark.asyncio
    async def test_resolves_from_db(self, mock_conn):
        mock_conn.fetchrow.return_value = {"name": "Mount Pleasant"}
        result = await resolve_neighborhood_name(mock_conn, "mount-pleasant")
        assert result == "Mount Pleasant"
        mock_conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_no_row(self, mock_conn):
        mock_conn.fetchrow.return_value = None
        result = await resolve_neighborhood_name(mock_conn, "mount-pleasant")
        assert result == "Mount Pleasant"

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self, mock_conn):
        mock_conn.fetchrow.side_effect = Exception("Table does not exist")
        result = await resolve_neighborhood_name(mock_conn, "downtown")
        assert result == "Downtown"


# ════════════════════════════════════════════════════════════════════════════
# SUPPLY PIPELINE COUNT
# ════════════════════════════════════════════════════════════════════════════

class TestSupplyPipelineCount:
    @pytest.mark.asyncio
    async def test_with_active_projects(self, mock_conn):
        mock_conn.fetchrow.return_value = {
            "active_projects": 5,
            "proposed_units": 1200,
        }
        result = await get_supply_pipeline_count(mock_conn, "Downtown")
        assert result["active_projects"] == 5
        assert result["proposed_units"] == 1200

    @pytest.mark.asyncio
    async def test_zero_pipeline(self, mock_conn):
        mock_conn.fetchrow.return_value = {
            "active_projects": 0,
            "proposed_units": 0,
        }
        result = await get_supply_pipeline_count(mock_conn, "Arbutus Ridge")
        assert result["active_projects"] == 0
        assert result["proposed_units"] == 0

    @pytest.mark.asyncio
    async def test_null_proposed_units(self, mock_conn):
        """When all projects have NULL proposed_units, COALESCE returns 0."""
        mock_conn.fetchrow.return_value = {
            "active_projects": 3,
            "proposed_units": 0,
        }
        result = await get_supply_pipeline_count(mock_conn, "Downtown")
        assert result["active_projects"] == 3
        assert result["proposed_units"] == 0

    @pytest.mark.asyncio
    async def test_db_error_returns_zeros(self, mock_conn):
        mock_conn.fetchrow.side_effect = Exception("Table missing")
        result = await get_supply_pipeline_count(mock_conn, "Downtown")
        assert result["active_projects"] == 0
        assert result["proposed_units"] == 0


# ════════════════════════════════════════════════════════════════════════════
# AVERAGE APPROVAL TIMELINE
# ════════════════════════════════════════════════════════════════════════════

class TestAvgApprovalTimeline:
    @pytest.mark.asyncio
    async def test_with_data(self, mock_conn):
        mock_conn.fetchrow.return_value = {"avg_months": 8.5}
        result = await get_avg_approval_timeline(mock_conn, "Downtown")
        assert result == 8.5

    @pytest.mark.asyncio
    async def test_no_approved_projects(self, mock_conn):
        mock_conn.fetchrow.return_value = {"avg_months": None}
        result = await get_avg_approval_timeline(mock_conn, "Downtown")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_rows(self, mock_conn):
        mock_conn.fetchrow.return_value = None
        result = await get_avg_approval_timeline(mock_conn, "Downtown")
        assert result is None

    @pytest.mark.asyncio
    async def test_db_error(self, mock_conn):
        mock_conn.fetchrow.side_effect = Exception("Query error")
        result = await get_avg_approval_timeline(mock_conn, "Downtown")
        assert result is None

    @pytest.mark.asyncio
    async def test_fractional_months(self, mock_conn):
        mock_conn.fetchrow.return_value = {"avg_months": 3.14159}
        result = await get_avg_approval_timeline(mock_conn, "Downtown")
        assert result == 3.1


# ════════════════════════════════════════════════════════════════════════════
# SUPPLY PRESSURE
# ════════════════════════════════════════════════════════════════════════════

class TestSupplyPressure:
    @pytest.mark.asyncio
    async def test_normal_calculation(self, mock_conn):
        mock_conn.fetchrow.return_value = {
            "proposed_units": 500,
            "parcel_count": 1000,
        }
        result = await get_supply_pressure(mock_conn, "Downtown")
        assert result == 0.5

    @pytest.mark.asyncio
    async def test_zero_parcels(self, mock_conn):
        """Division by zero avoided."""
        mock_conn.fetchrow.return_value = {
            "proposed_units": 100,
            "parcel_count": 0,
        }
        result = await get_supply_pressure(mock_conn, "Downtown")
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_proposed_units(self, mock_conn):
        mock_conn.fetchrow.return_value = {
            "proposed_units": 0,
            "parcel_count": 500,
        }
        result = await get_supply_pressure(mock_conn, "Downtown")
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_no_row(self, mock_conn):
        mock_conn.fetchrow.return_value = None
        result = await get_supply_pressure(mock_conn, "Downtown")
        assert result is None

    @pytest.mark.asyncio
    async def test_db_error(self, mock_conn):
        mock_conn.fetchrow.side_effect = Exception("Table missing")
        result = await get_supply_pressure(mock_conn, "Downtown")
        assert result is None


# ════════════════════════════════════════════════════════════════════════════
# DEVELOPMENT MOMENTUM
# ════════════════════════════════════════════════════════════════════════════

class TestDevelopmentMomentum:
    @pytest.mark.asyncio
    async def test_growing_momentum(self, mock_conn):
        mock_conn.fetchrow.return_value = {
            "signals_last_90d": 20,
            "signals_prior_90d": 10,
        }
        result = await get_development_momentum(mock_conn, "Downtown")
        assert result == 2.0

    @pytest.mark.asyncio
    async def test_declining_momentum(self, mock_conn):
        mock_conn.fetchrow.return_value = {
            "signals_last_90d": 5,
            "signals_prior_90d": 20,
        }
        result = await get_development_momentum(mock_conn, "Downtown")
        assert result == 0.25

    @pytest.mark.asyncio
    async def test_zero_prior_with_recent(self, mock_conn):
        """When prior period has zero signals but current has some."""
        mock_conn.fetchrow.return_value = {
            "signals_last_90d": 10,
            "signals_prior_90d": 0,
        }
        result = await get_development_momentum(mock_conn, "Downtown")
        assert result == 10.0  # Returns count as ratio

    @pytest.mark.asyncio
    async def test_zero_both_periods(self, mock_conn):
        """No signals at all returns None."""
        mock_conn.fetchrow.return_value = {
            "signals_last_90d": 0,
            "signals_prior_90d": 0,
        }
        result = await get_development_momentum(mock_conn, "Downtown")
        assert result is None

    @pytest.mark.asyncio
    async def test_equal_periods(self, mock_conn):
        mock_conn.fetchrow.return_value = {
            "signals_last_90d": 15,
            "signals_prior_90d": 15,
        }
        result = await get_development_momentum(mock_conn, "Downtown")
        assert result == 1.0

    @pytest.mark.asyncio
    async def test_no_row(self, mock_conn):
        mock_conn.fetchrow.return_value = None
        result = await get_development_momentum(mock_conn, "Downtown")
        assert result is None

    @pytest.mark.asyncio
    async def test_db_error(self, mock_conn):
        mock_conn.fetchrow.side_effect = Exception("Connection lost")
        result = await get_development_momentum(mock_conn, "Downtown")
        assert result is None


# ════════════════════════════════════════════════════════════════════════════
# COMBINED INVESTMENT METRICS
# ════════════════════════════════════════════════════════════════════════════

class TestCombinedInvestmentMetrics:
    @pytest.mark.asyncio
    async def test_full_metrics(self, mock_conn):
        """All metrics populated."""
        # resolve_neighborhood_name call
        mock_conn.fetchrow.side_effect = [
            {"name": "Mount Pleasant"},  # resolve name
            {"active_projects": 8, "proposed_units": 2000},  # pipeline count
            {"avg_months": 6.3},  # approval timeline
            {"proposed_units": 2000, "parcel_count": 800},  # supply pressure
            {"signals_last_90d": 30, "signals_prior_90d": 20},  # momentum
        ]

        result = await get_neighborhood_investment_metrics(mock_conn, "mount-pleasant")

        assert result is not None
        assert result["neighborhood"] == "Mount Pleasant"
        assert result["slug"] == "mount-pleasant"
        assert result["active_projects"] == 8
        assert result["proposed_units"] == 2000
        assert result["avg_approval_months"] == 6.3
        assert result["supply_pressure"] == 2.5
        assert result["development_momentum"] == 1.5

    @pytest.mark.asyncio
    async def test_empty_neighborhood(self, mock_conn):
        """Neighborhood with no data at all."""
        mock_conn.fetchrow.side_effect = [
            None,  # resolve name (falls back)
            {"active_projects": 0, "proposed_units": 0},  # pipeline count
            {"avg_months": None},  # no approvals
            {"proposed_units": 0, "parcel_count": 0},  # zero parcels
            {"signals_last_90d": 0, "signals_prior_90d": 0},  # no signals
        ]

        result = await get_neighborhood_investment_metrics(mock_conn, "some-place")

        assert result is not None
        assert result["neighborhood"] == "Some Place"
        assert result["active_projects"] == 0
        assert result["proposed_units"] == 0
        assert result["avg_approval_months"] is None
        assert result["supply_pressure"] is None
        assert result["development_momentum"] is None

    @pytest.mark.asyncio
    async def test_partial_data(self, mock_conn):
        """Some metrics available, others not."""
        mock_conn.fetchrow.side_effect = [
            {"name": "Fairview"},  # resolve name
            {"active_projects": 3, "proposed_units": 500},  # pipeline count
            {"avg_months": None},  # no approval history
            {"proposed_units": 500, "parcel_count": 200},  # supply pressure
            {"signals_last_90d": 0, "signals_prior_90d": 0},  # no signals
        ]

        result = await get_neighborhood_investment_metrics(mock_conn, "fairview")

        assert result["active_projects"] == 3
        assert result["proposed_units"] == 500
        assert result["avg_approval_months"] is None
        assert result["supply_pressure"] == 2.5
        assert result["development_momentum"] is None

    @pytest.mark.asyncio
    async def test_resilient_to_table_errors(self, mock_conn):
        """If individual queries fail, other metrics still return."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"name": "Downtown"}
            if call_count == 2:
                raise Exception("supply_pipeline missing")
            if call_count == 3:
                raise Exception("pipeline_stage_history missing")
            if call_count == 4:
                raise Exception("parcels missing")
            if call_count == 5:
                return {"signals_last_90d": 10, "signals_prior_90d": 5}

        mock_conn.fetchrow = AsyncMock(side_effect=side_effect)

        result = await get_neighborhood_investment_metrics(mock_conn, "downtown")

        assert result is not None
        assert result["neighborhood"] == "Downtown"
        assert result["active_projects"] == 0  # failed gracefully
        assert result["proposed_units"] == 0  # failed gracefully
        assert result["avg_approval_months"] is None  # failed gracefully
        assert result["supply_pressure"] is None  # failed gracefully
        assert result["development_momentum"] == 2.0  # succeeded
