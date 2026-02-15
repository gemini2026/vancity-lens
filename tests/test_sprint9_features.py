"""
Sprint 9 tests — Undervalued Parcel Alerts

Tests cover:
- Implied value computation (9.1)
- Comparable averages (9.2)
- Undervaluation scoring (9.3, FR-DEAL-003)
- Repeat signal tracking (9.5)
- Active application exclusion (9.6)
- Min 3 comps validation (9.7)
- Contaminated/heritage caveats (9.8)
- Opportunity routes
- Frontend component
- Migration file
"""

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.intelligence.undervalued_scoring import (
    UNDERVALUED_THRESHOLD_PCT,
    MIN_COMPARABLES,
    MAX_BCA_AGE_MONTHS,
    COMP_LOOKBACK_MONTHS,
    compute_implied_value,
    compute_discount_pct,
    is_undervalued,
    build_caveats,
    get_top_opportunities,
    get_parcel_undervaluation,
)
from api.intelligence.undervalued_routes import router as undervalued_router


# ── Helpers ─────────────────────────────────────────────────────────


def _make_async_pool_mock():
    pool = MagicMock()
    conn = AsyncMock()
    acm = AsyncMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = acm
    return pool, conn


# ── Implied Value Tests ─────────────────────────────────────────────


class TestImpliedValue:
    """Sprint 9.1: Implied value computation."""

    def test_basic_computation(self):
        # 10000 sqft * $300/sqft = $3M
        value = compute_implied_value(10000, 300)
        assert value == 3000000

    def test_zero_buildable(self):
        assert compute_implied_value(0, 300) == 0

    def test_zero_comp_price(self):
        assert compute_implied_value(10000, 0) == 0

    def test_negative_values(self):
        assert compute_implied_value(-100, 300) == 0

    def test_realistic_values(self):
        # 26910 sqft buildable * $150/sqft = ~$4M
        value = compute_implied_value(26910, 150)
        assert 4000000 <= value <= 4100000


# ── Discount Percentage Tests ───────────────────────────────────────


class TestDiscountPct:
    """Sprint 9.3: Undervaluation scoring."""

    def test_undervalued(self):
        # Assessed $2M, implied $3M = 33% discount
        pct = compute_discount_pct(2000000, 3000000)
        assert 33.0 <= pct <= 34.0

    def test_overvalued(self):
        # Assessed $4M, implied $3M = -33% (overvalued)
        pct = compute_discount_pct(4000000, 3000000)
        assert pct < 0

    def test_equal_values(self):
        pct = compute_discount_pct(3000000, 3000000)
        assert pct == 0.0

    def test_zero_implied(self):
        assert compute_discount_pct(2000000, 0) is None

    def test_none_assessed(self):
        assert compute_discount_pct(None, 3000000) is None

    def test_large_discount(self):
        # Assessed $500K, implied $3M = 83% discount
        pct = compute_discount_pct(500000, 3000000)
        assert pct > 80


# ── Threshold Tests ─────────────────────────────────────────────────


class TestIsUndervalued:
    """FR-DEAL-003: Flag undervalued (>25% below)."""

    def test_threshold_value(self):
        assert UNDERVALUED_THRESHOLD_PCT == 25.0

    def test_above_threshold(self):
        assert is_undervalued(30.0) is True

    def test_below_threshold(self):
        assert is_undervalued(20.0) is False

    def test_at_threshold(self):
        assert is_undervalued(25.0) is False  # Must be > 25, not >=

    def test_just_above_threshold(self):
        assert is_undervalued(25.01) is True

    def test_none_value(self):
        assert is_undervalued(None) is False

    def test_negative_value(self):
        assert is_undervalued(-10.0) is False


# ── Caveat Tests ────────────────────────────────────────────────────


class TestBuildCaveats:
    """Sprint 9.8: Caveats for contaminated/heritage parcels."""

    def test_no_caveats(self):
        caveats = build_caveats(False, False, 10, 12)
        assert caveats == []

    def test_contamination_caveat(self):
        caveats = build_caveats(True, False, 10, 12)
        assert len(caveats) == 1
        assert "contamination" in caveats[0].lower()

    def test_heritage_caveat(self):
        caveats = build_caveats(False, True, 10, 12)
        assert len(caveats) == 1
        assert "heritage" in caveats[0].lower()

    def test_low_comp_caveat(self):
        caveats = build_caveats(False, False, 3, 12)
        assert len(caveats) == 1
        assert "limited" in caveats[0].lower()

    def test_old_bca_caveat(self):
        caveats = build_caveats(False, False, 10, 24)
        assert len(caveats) == 1
        assert "24 months" in caveats[0]

    def test_multiple_caveats(self):
        caveats = build_caveats(True, True, 3, 24)
        assert len(caveats) == 4

    def test_min_comps_validation(self):
        assert MIN_COMPARABLES == 3

    def test_max_bca_age(self):
        assert MAX_BCA_AGE_MONTHS == 18


# ── DB Query Tests ──────────────────────────────────────────────────


class TestGetTopOpportunities:
    """Sprint 9.4: Weekly top-20 ranking."""

    @pytest.mark.asyncio
    async def test_with_opportunities(self):
        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = [
            {
                "pid": "001-234-567",
                "neighborhood": "Kitsilano",
                "assessed_value": 2000000,
                "implied_value": 3500000,
                "buildable_sqft": Decimal("26000"),
                "discount_pct": Decimal("42.86"),
                "repeat_signal": True,
                "has_contamination": False,
                "has_heritage": False,
                "caveats": [],
                "comp_count": 8,
                "computed_at": datetime.now(timezone.utc),
                "civic_address": "123 Main St",
                "current_zoning": "RS-1",
            },
        ]

        result = await get_top_opportunities(pool, top_n=20)
        assert len(result) == 1
        assert result[0]["pid"] == "001-234-567"

    @pytest.mark.asyncio
    async def test_empty_opportunities(self):
        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = []

        result = await get_top_opportunities(pool)
        assert result == []

    @pytest.mark.asyncio
    async def test_db_failure(self):
        pool, conn = _make_async_pool_mock()
        conn.fetch.side_effect = Exception("table not found")

        result = await get_top_opportunities(pool)
        assert result == []


class TestGetParcelUndervaluation:
    """Test parcel-level undervaluation query."""

    @pytest.mark.asyncio
    async def test_parcel_found(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = {
            "pid": "001-234-567",
            "discount_pct": Decimal("35.5"),
            "is_undervalued": True,
            "implied_value": 3000000,
        }

        result = await get_parcel_undervaluation(pool, "001-234-567")
        assert result is not None
        assert result["is_undervalued"] is True

    @pytest.mark.asyncio
    async def test_parcel_not_found(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = None

        result = await get_parcel_undervaluation(pool, "000-000-000")
        assert result is None

    @pytest.mark.asyncio
    async def test_db_failure(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.side_effect = Exception("error")

        result = await get_parcel_undervaluation(pool, "001-234-567")
        assert result is None


# ── Route Tests ─────────────────────────────────────────────────────


class TestUndervaluedRoutes:
    """Test opportunity alert API routes."""

    def test_router_prefix(self):
        assert undervalued_router.prefix == "/api/v1/opportunities"

    def test_has_list_route(self):
        paths = [r.path for r in undervalued_router.routes]
        assert any(p == "" or p == "/" or "opportunities" in p for p in paths)

    def test_has_parcel_route(self):
        paths = [r.path for r in undervalued_router.routes]
        assert any("parcels" in p or "pid" in p for p in paths)


# ── Frontend Tests ──────────────────────────────────────────────────


class TestOpportunityFrontend:
    """Sprint 9.9: OpportunityAlertDashboard component."""

    def test_component_exists(self):
        assert os.path.exists("frontend/src/components/OpportunityAlertDashboard.tsx")

    def test_component_is_client(self):
        with open("frontend/src/components/OpportunityAlertDashboard.tsx") as f:
            content = f.read()
        assert '"use client"' in content

    def test_component_fetches_api(self):
        with open("frontend/src/components/OpportunityAlertDashboard.tsx") as f:
            content = f.read()
        assert "/api/v1/opportunities" in content

    def test_component_shows_discount(self):
        with open("frontend/src/components/OpportunityAlertDashboard.tsx") as f:
            content = f.read()
        assert "discount_pct" in content

    def test_component_shows_repeat_signal(self):
        with open("frontend/src/components/OpportunityAlertDashboard.tsx") as f:
            content = f.read()
        assert "repeat_signal" in content


# ── Migration Tests ─────────────────────────────────────────────────


class TestSprint9Migration:
    """Test Sprint 9 migration file."""

    def test_migration_exists(self):
        assert os.path.exists("db/041_undervalued_alerts_sprint9.sql")

    def test_migration_creates_table(self):
        with open("db/041_undervalued_alerts_sprint9.sql") as f:
            sql = f.read()
        assert "undervalued_scores" in sql
        assert "discount_pct" in sql
        assert "is_undervalued" in sql
        assert "implied_value" in sql

    def test_migration_has_exclusion_columns(self):
        with open("db/041_undervalued_alerts_sprint9.sql") as f:
            sql = f.read()
        assert "has_active_application" in sql
        assert "has_contamination" in sql
        assert "has_heritage" in sql
        assert "repeat_signal" in sql

    def test_migration_has_indexes(self):
        with open("db/041_undervalued_alerts_sprint9.sql") as f:
            sql = f.read()
        assert "idx_undervalued_pid" in sql
        assert "idx_undervalued_discount" in sql
        assert "idx_undervalued_flagged" in sql

    def test_comp_lookback_months(self):
        assert COMP_LOOKBACK_MONTHS == 12
