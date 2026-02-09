"""
VanCity Lens — Validation Engine V2 Tests (VCL-115 through VCL-123)

Tests for VAL-006 through VAL-010 standalone validation checks:
- VAL-006: Non-Market Housing Proximity
- VAL-007: CD-1 Zoning Detection
- VAL-008: Building Age Assessment
- VAL-009: Community Opposition Score (Composite)
- VAL-010: Contamination Risk

Each check is tested independently with mock asyncpg connections.
RED, YELLOW, and GREEN scenarios are tested for each check,
along with missing data / empty table edge cases.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.validation import (
    check_non_market_housing_proximity,
    check_cd1_zoning,
    check_building_age,
    check_community_opposition_score,
    check_contamination_risk,
)


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS: Mock asyncpg Connection and Record
# ═════════════════════════════════════════════════════════════════════════════


def _make_mock_record(**kwargs):
    """Create a mock asyncpg.Record with dictionary-style access."""
    record = MagicMock()
    record.__getitem__ = lambda self, key: kwargs.get(key)
    record.get = lambda key, default=None: kwargs.get(key, default)
    record.keys = lambda: kwargs.keys()
    return record


def _make_parcel(**overrides):
    """Create a mock parcel record with default fields."""
    defaults = {
        "lot_area_sqm": 930,
        "asking_price": 2_000_000,
        "assessed_value": 1_800_000,
        "civic_address": "123 Main St",
        "year_built": None,
        "geo_local_area": None,
        "land_value": None,
        "improvement_value": None,
        "current_zoning": None,
    }
    defaults.update(overrides)
    return _make_mock_record(**defaults)


def _make_conn():
    """Create a mock asyncpg connection with fetchrow/fetchval/fetch."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    conn.fetch = AsyncMock(return_value=[])
    return conn


# ═════════════════════════════════════════════════════════════════════════════
# VAL-006: NON-MARKET HOUSING PROXIMITY
# ═════════════════════════════════════════════════════════════════════════════


class TestVal006NonMarketHousingProximity:
    """Tests for VAL-006: Non-Market Housing Proximity."""

    @pytest.mark.asyncio
    async def test_nmh_on_parcel_returns_red(self):
        """RED: NMH directly on the parcel."""
        conn = _make_conn()
        parcel = _make_parcel()

        # First fetchrow (ST_Intersects) finds NMH on parcel
        conn.fetchrow = AsyncMock(
            side_effect=[
                _make_mock_record(name="Cedar Cottage Housing"),  # on_parcel
            ]
        )

        flag = await check_non_market_housing_proximity(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "red"
        assert flag.code == "VAL006_NMH_ON_PARCEL"
        assert "social housing on-site" in flag.detail
        assert "$50K-150K" in flag.cost_impact

    @pytest.mark.asyncio
    async def test_nmh_nearby_returns_yellow(self):
        """YELLOW: NMH within 100m but not on parcel."""
        conn = _make_conn()
        parcel = _make_parcel()

        # First fetchrow (ST_Intersects) returns None (not on parcel)
        # Second fetchrow (ST_DWithin) finds NMH nearby
        conn.fetchrow = AsyncMock(
            side_effect=[
                None,  # on_parcel check
                _make_mock_record(name="Main Street Co-op", distance_m=75),  # nearby
            ]
        )

        flag = await check_non_market_housing_proximity(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL006_NMH_NEARBY"
        assert "75m" in flag.detail
        assert "community scrutiny" in flag.detail

    @pytest.mark.asyncio
    async def test_nmh_none_nearby_returns_green(self):
        """GREEN: No NMH within 100m."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Both queries return None
        conn.fetchrow = AsyncMock(return_value=None)

        flag = await check_non_market_housing_proximity(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL006_NMH_CLEAR"
        assert "No non-market housing conflict" in flag.detail

    @pytest.mark.asyncio
    async def test_nmh_table_missing_returns_none(self):
        """Missing table returns None (graceful handling)."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Simulate table-not-found exception
        conn.fetchrow = AsyncMock(side_effect=Exception("relation 'non_market_housing' does not exist"))

        flag = await check_non_market_housing_proximity(conn, "PID-001", parcel)

        assert flag is None

    @pytest.mark.asyncio
    async def test_nmh_distance_zero_on_parcel(self):
        """NMH with distance_m=None (on-parcel edge case)."""
        conn = _make_conn()
        parcel = _make_parcel()

        conn.fetchrow = AsyncMock(
            side_effect=[
                None,  # on_parcel
                _make_mock_record(name="Test Housing", distance_m=None),  # nearby with None distance
            ]
        )

        flag = await check_non_market_housing_proximity(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert "0m" in flag.detail


# ═════════════════════════════════════════════════════════════════════════════
# VAL-007: CD-1 ZONING DETECTION
# ═════════════════════════════════════════════════════════════════════════════


class TestVal007CD1Zoning:
    """Tests for VAL-007: CD-1 Zoning Detection."""

    @pytest.mark.asyncio
    async def test_cd1_zoning_classification_returns_red(self):
        """RED: zoning_classification starts with CD-1."""
        conn = _make_conn()
        parcel = _make_parcel()

        conn.fetchrow = AsyncMock(
            return_value=_make_mock_record(
                zoning_classification="CD-1 (236)",
                zoning_category="CD-1",
            )
        )

        flag = await check_cd1_zoning(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "red"
        assert flag.code == "VAL007_CD1_ZONING"
        assert "manual bylaw review" in flag.detail
        assert "$50K-200K" in flag.cost_impact

    @pytest.mark.asyncio
    async def test_cd1_category_only_returns_red(self):
        """RED: zoning_category is CD-1 even if classification doesn't start with CD-1."""
        conn = _make_conn()
        parcel = _make_parcel()

        conn.fetchrow = AsyncMock(
            return_value=_make_mock_record(
                zoning_classification="Comprehensive Development",
                zoning_category="CD-1",
            )
        )

        flag = await check_cd1_zoning(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "red"
        assert flag.code == "VAL007_CD1_ZONING"

    @pytest.mark.asyncio
    async def test_standard_zoning_returns_green(self):
        """GREEN: Standard zoning (not CD-1)."""
        conn = _make_conn()
        parcel = _make_parcel()

        conn.fetchrow = AsyncMock(
            return_value=_make_mock_record(
                zoning_classification="RS-1",
                zoning_category="RS",
            )
        )

        flag = await check_cd1_zoning(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL007_STANDARD_ZONING"
        assert "Standard zoning" in flag.detail

    @pytest.mark.asyncio
    async def test_no_zoning_record_returns_green(self):
        """GREEN: No zoning record found for parcel."""
        conn = _make_conn()
        parcel = _make_parcel()

        conn.fetchrow = AsyncMock(return_value=None)

        flag = await check_cd1_zoning(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL007_STANDARD_ZONING"

    @pytest.mark.asyncio
    async def test_cd1_zoning_table_missing_returns_none(self):
        """Missing table returns None."""
        conn = _make_conn()
        parcel = _make_parcel()

        conn.fetchrow = AsyncMock(side_effect=Exception("relation 'zoning_districts' does not exist"))

        flag = await check_cd1_zoning(conn, "PID-001", parcel)

        assert flag is None

    @pytest.mark.asyncio
    async def test_cd1_none_classification_not_cd1(self):
        """zoning_classification is None, zoning_category is not CD-1."""
        conn = _make_conn()
        parcel = _make_parcel()

        conn.fetchrow = AsyncMock(
            return_value=_make_mock_record(
                zoning_classification=None,
                zoning_category="RM",
            )
        )

        flag = await check_cd1_zoning(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"


# ═════════════════════════════════════════════════════════════════════════════
# VAL-008: BUILDING AGE ASSESSMENT
# ═════════════════════════════════════════════════════════════════════════════


class TestVal008BuildingAge:
    """Tests for VAL-008: Building Age Assessment."""

    @pytest.mark.asyncio
    async def test_pre_1940_returns_red(self):
        """RED: Heritage-era structure (pre-1940)."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=1935)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "red"
        assert flag.code == "VAL008_HERITAGE_ERA"
        assert "1935" in flag.detail
        assert "heritage review" in flag.detail
        assert "$100K-500K+" in flag.cost_impact

    @pytest.mark.asyncio
    async def test_exactly_1940_returns_yellow_pre1960(self):
        """YELLOW: 1940 is not pre-1940, falls into pre-1960 bracket."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=1940)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL008_ASBESTOS_LIKELY"
        assert "1940" in flag.detail
        assert "asbestos" in flag.detail

    @pytest.mark.asyncio
    async def test_pre_1960_returns_yellow_asbestos(self):
        """YELLOW: Pre-1960 structure — asbestos remediation likely."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=1955)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL008_ASBESTOS_LIKELY"
        assert "1955" in flag.detail
        assert "asbestos" in flag.detail
        assert "$50K-200K" in flag.cost_impact

    @pytest.mark.asyncio
    async def test_exactly_1960_returns_yellow_enviro(self):
        """YELLOW: 1960 is not pre-1960, falls into pre-1980 bracket."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=1960)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL008_ENVIRO_SCREENING"
        assert "1960" in flag.detail

    @pytest.mark.asyncio
    async def test_pre_1980_returns_yellow_enviro(self):
        """YELLOW: Pre-1980 structure — environmental screening recommended."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=1975)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL008_ENVIRO_SCREENING"
        assert "1975" in flag.detail
        assert "environmental screening" in flag.detail
        assert "$50K-200K" in flag.cost_impact

    @pytest.mark.asyncio
    async def test_exactly_1980_returns_green(self):
        """GREEN: 1980 is post-1980 boundary — modern structure."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=1980)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL008_MODERN"

    @pytest.mark.asyncio
    async def test_post_1980_returns_green(self):
        """GREEN: Post-1980 — modern structure."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=2005)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL008_MODERN"
        assert "Modern structure" in flag.detail

    @pytest.mark.asyncio
    async def test_no_year_built_returns_green(self):
        """GREEN: No year_built data available."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=None)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL008_BUILDING_AGE_UNKNOWN"
        assert "Modern structure or undeveloped" in flag.detail

    @pytest.mark.asyncio
    async def test_year_built_missing_key_returns_green(self):
        """GREEN: year_built key missing from parcel record."""
        conn = _make_conn()
        # Simulate a parcel that raises KeyError for year_built
        parcel = MagicMock()
        parcel.__getitem__ = MagicMock(side_effect=KeyError("year_built"))

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL008_BUILDING_AGE_UNKNOWN"

    @pytest.mark.asyncio
    async def test_very_old_building_1900(self):
        """RED: Very old building (1900) — heritage-era."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=1900)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "red"
        assert "1900" in flag.detail

    @pytest.mark.asyncio
    async def test_boundary_1939_is_red(self):
        """RED: 1939 is pre-1940."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=1939)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "red"
        assert flag.code == "VAL008_HERITAGE_ERA"

    @pytest.mark.asyncio
    async def test_boundary_1959_is_yellow_asbestos(self):
        """YELLOW: 1959 is pre-1960 — asbestos."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=1959)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL008_ASBESTOS_LIKELY"

    @pytest.mark.asyncio
    async def test_boundary_1979_is_yellow_enviro(self):
        """YELLOW: 1979 is pre-1980 — environmental screening."""
        conn = _make_conn()
        parcel = _make_parcel(year_built=1979)

        flag = await check_building_age(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL008_ENVIRO_SCREENING"


# ═════════════════════════════════════════════════════════════════════════════
# VAL-009: COMMUNITY OPPOSITION SCORE
# ═════════════════════════════════════════════════════════════════════════════


class TestVal009CommunityOppositionScore:
    """Tests for VAL-009: Community Opposition Score (Composite)."""

    @pytest.mark.asyncio
    async def test_no_community_assets_returns_green(self):
        """GREEN: Score 0 — no community assets nearby."""
        conn = _make_conn()
        parcel = _make_parcel()

        # All queries return 0
        conn.fetchval = AsyncMock(return_value=0)

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL009_LOW_OPPOSITION"
        assert "Low opposition" in flag.detail

    @pytest.mark.asyncio
    async def test_gardens_only_score_2_returns_green(self):
        """GREEN: Score 2 — only gardens (+2)."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens = 1 (adds +2), NMH = 0, Trees = 0
        conn.fetchval = AsyncMock(side_effect=[1, 0, 0])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL009_LOW_OPPOSITION"

    @pytest.mark.asyncio
    async def test_nmh_only_score_3_returns_yellow(self):
        """YELLOW: Score 3 — NMH nearby (+3)."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens = 0, NMH = 1 (adds +3), Trees = 0
        conn.fetchval = AsyncMock(side_effect=[0, 1, 0])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL009_MODERATE_OPPOSITION"
        assert "Moderate community sensitivity" in flag.detail

    @pytest.mark.asyncio
    async def test_gardens_plus_nmh_score_5_returns_yellow(self):
        """YELLOW: Score 5 — gardens (+2) + NMH (+3)."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens = 1 (+2), NMH = 2 (+3), Trees = 0
        conn.fetchval = AsyncMock(side_effect=[1, 2, 0])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL009_MODERATE_OPPOSITION"

    @pytest.mark.asyncio
    async def test_all_factors_high_score_returns_red(self):
        """RED: Score 6+ — all factors present."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens = 1 (+2), NMH = 1 (+3), Trees = 10 (+2, i.e. 10//5=2)
        conn.fetchval = AsyncMock(side_effect=[1, 1, 10])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "red"
        assert flag.code == "VAL009_HIGH_OPPOSITION"
        assert "High opposition risk" in flag.detail

    @pytest.mark.asyncio
    async def test_many_trees_score_capped_at_3(self):
        """Tree points capped at 3 (max)."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens = 0, NMH = 0, Trees = 100 (100//5 = 20, capped to 3)
        conn.fetchval = AsyncMock(side_effect=[0, 0, 100])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        # Score = 3 -> YELLOW
        assert flag.severity == "yellow"
        assert flag.code == "VAL009_MODERATE_OPPOSITION"

    @pytest.mark.asyncio
    async def test_trees_below_5_contributes_zero(self):
        """Trees count < 5 contributes 0 points (4//5 = 0)."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens = 0, NMH = 0, Trees = 4 (4//5 = 0)
        conn.fetchval = AsyncMock(side_effect=[0, 0, 4])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL009_LOW_OPPOSITION"

    @pytest.mark.asyncio
    async def test_exactly_5_trees_contributes_1_point(self):
        """Trees count 5 contributes 1 point (5//5 = 1)."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens = 0, NMH = 0, Trees = 5 (5//5 = 1)
        conn.fetchval = AsyncMock(side_effect=[0, 0, 5])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        # Score = 1, so still GREEN
        assert flag.severity == "green"
        assert flag.code == "VAL009_LOW_OPPOSITION"

    @pytest.mark.asyncio
    async def test_gardens_plus_trees_score_3_yellow(self):
        """YELLOW: Gardens (+2) + 5 trees (+1) = score 3."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens = 1 (+2), NMH = 0, Trees = 5 (+1)
        conn.fetchval = AsyncMock(side_effect=[1, 0, 5])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL009_MODERATE_OPPOSITION"

    @pytest.mark.asyncio
    async def test_all_tables_missing_returns_green(self):
        """When all tables are missing, exceptions are caught, score = 0 -> GREEN."""
        conn = _make_conn()
        parcel = _make_parcel()

        conn.fetchval = AsyncMock(side_effect=Exception("relation does not exist"))

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL009_LOW_OPPOSITION"

    @pytest.mark.asyncio
    async def test_score_6_exact_boundary_is_red(self):
        """RED: Score exactly 6 is the boundary for RED."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens = 1 (+2), NMH = 1 (+3), Trees = 5 (+1) = total 6
        conn.fetchval = AsyncMock(side_effect=[1, 1, 5])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "red"
        assert flag.code == "VAL009_HIGH_OPPOSITION"

    @pytest.mark.asyncio
    async def test_factors_included_in_detail(self):
        """Verify factor descriptions are included in detail text."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens = 2 (+2), NMH = 0, Trees = 0
        conn.fetchval = AsyncMock(side_effect=[2, 0, 0])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        assert "community garden" in flag.detail.lower()


# ═════════════════════════════════════════════════════════════════════════════
# VAL-010: CONTAMINATION RISK
# ═════════════════════════════════════════════════════════════════════════════


class TestVal010ContaminationRisk:
    """Tests for VAL-010: Contamination Risk."""

    @pytest.mark.asyncio
    async def test_industrial_zoning_returns_yellow(self):
        """YELLOW: Industrial zoning (contains 'I')."""
        conn = _make_conn()
        parcel = _make_parcel(current_zoning="I-2")

        # No contaminated_sites table
        conn.fetchrow = AsyncMock(side_effect=Exception("relation 'contaminated_sites' does not exist"))

        flag = await check_contamination_risk(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL010_INDUSTRIAL_ZONING"
        assert "Industrial zoning" in flag.detail
        assert "Phase 1 ESA" in flag.detail
        assert "$50K-500K+" in flag.cost_impact

    @pytest.mark.asyncio
    async def test_dtes_neighborhood_returns_yellow(self):
        """YELLOW: Parcel in Downtown Eastside."""
        conn = _make_conn()
        parcel = _make_parcel(
            current_zoning="C-2",
            geo_local_area="Downtown Eastside",
        )

        conn.fetchrow = AsyncMock(side_effect=Exception("relation 'contaminated_sites' does not exist"))

        flag = await check_contamination_risk(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL010_HIGH_RISK_AREA"
        assert "Downtown Eastside" in flag.detail

    @pytest.mark.asyncio
    async def test_strathcona_neighborhood_returns_yellow(self):
        """YELLOW: Parcel in Strathcona."""
        conn = _make_conn()
        parcel = _make_parcel(
            current_zoning="RS-1",
            geo_local_area="Strathcona",
        )

        conn.fetchrow = AsyncMock(side_effect=Exception("relation 'contaminated_sites' does not exist"))

        flag = await check_contamination_risk(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL010_HIGH_RISK_AREA"
        assert "Strathcona" in flag.detail

    @pytest.mark.asyncio
    async def test_clean_parcel_returns_green(self):
        """GREEN: No contamination indicators (residential zoning, normal neighborhood)."""
        conn = _make_conn()
        parcel = _make_parcel(
            current_zoning="RS-1",
            geo_local_area="Kitsilano",
        )

        # No contaminated_sites table, no industrial, no high-risk area
        conn.fetchrow = AsyncMock(side_effect=Exception("relation 'contaminated_sites' does not exist"))

        flag = await check_contamination_risk(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL010_CLEAN"
        assert "No contamination indicators" in flag.detail

    @pytest.mark.asyncio
    async def test_contaminated_site_table_exists_returns_yellow(self):
        """YELLOW: Contaminated site found in table."""
        conn = _make_conn()
        parcel = _make_parcel(current_zoning="RS-1", geo_local_area="Kitsilano")

        # Contaminated_sites table exists and has a match
        conn.fetchrow = AsyncMock(
            return_value=_make_mock_record(site_name="Former Gas Station 123")
        )

        flag = await check_contamination_risk(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL010_CONTAMINATED_SITE"
        assert "Former Gas Station 123" in flag.detail
        assert "$50K-500K+" in flag.cost_impact

    @pytest.mark.asyncio
    async def test_no_zoning_no_neighborhood_returns_green(self):
        """GREEN: No zoning or neighborhood data."""
        conn = _make_conn()
        parcel = _make_parcel(current_zoning=None, geo_local_area=None)

        conn.fetchrow = AsyncMock(side_effect=Exception("relation 'contaminated_sites' does not exist"))

        flag = await check_contamination_risk(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "green"
        assert flag.code == "VAL010_CLEAN"

    @pytest.mark.asyncio
    async def test_industrial_zoning_m_series_not_flagged(self):
        """M-series zoning (manufacturing) should not falsely trigger on 'I' in M."""
        conn = _make_conn()
        parcel = _make_parcel(current_zoning="M-2", geo_local_area="Kitsilano")

        conn.fetchrow = AsyncMock(side_effect=Exception("relation 'contaminated_sites' does not exist"))

        flag = await check_contamination_risk(conn, "PID-001", parcel)

        # M-2 does not have "I" as the first part before the dash
        assert flag is not None
        assert flag.severity == "green"

    @pytest.mark.asyncio
    async def test_industrial_zoning_ic_variant(self):
        """IC zoning variant is still industrial (starts with I)."""
        conn = _make_conn()
        parcel = _make_parcel(current_zoning="IC-2", geo_local_area="Kitsilano")

        conn.fetchrow = AsyncMock(side_effect=Exception("relation 'contaminated_sites' does not exist"))

        flag = await check_contamination_risk(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL010_INDUSTRIAL_ZONING"

    @pytest.mark.asyncio
    async def test_contaminated_site_none_name(self):
        """Contaminated site with None name handled gracefully."""
        conn = _make_conn()
        parcel = _make_parcel(current_zoning="RS-1", geo_local_area="Kitsilano")

        conn.fetchrow = AsyncMock(
            return_value=_make_mock_record(site_name=None)
        )

        flag = await check_contamination_risk(conn, "PID-001", parcel)

        assert flag is not None
        assert flag.severity == "yellow"
        assert flag.code == "VAL010_CONTAMINATED_SITE"
        assert "Unknown" in flag.detail

    @pytest.mark.asyncio
    async def test_missing_zoning_key_handled(self):
        """Parcel record missing current_zoning key handled gracefully."""
        conn = _make_conn()
        # Simulate KeyError for current_zoning
        parcel = MagicMock()
        parcel.__getitem__ = MagicMock(side_effect=KeyError("current_zoning"))

        conn.fetchrow = AsyncMock(side_effect=Exception("relation 'contaminated_sites' does not exist"))

        flag = await check_contamination_risk(conn, "PID-001", parcel)

        assert flag is not None
        # Both current_zoning and geo_local_area are None due to KeyError, so GREEN
        assert flag.severity == "green"
        assert flag.code == "VAL010_CLEAN"


# ═════════════════════════════════════════════════════════════════════════════
# COMPOSITE OPPOSITION SCORE CALCULATION
# ═════════════════════════════════════════════════════════════════════════════


class TestVal009ScoreCalculation:
    """Detailed tests of the composite opposition score arithmetic."""

    @pytest.mark.asyncio
    async def test_score_0_gardens_0_nmh_0_trees_0(self):
        """Score = 0: no factors."""
        conn = _make_conn()
        parcel = _make_parcel()
        conn.fetchval = AsyncMock(side_effect=[0, 0, 0])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)
        assert flag.severity == "green"

    @pytest.mark.asyncio
    async def test_score_2_only_gardens(self):
        """Score = 2: gardens only."""
        conn = _make_conn()
        parcel = _make_parcel()
        conn.fetchval = AsyncMock(side_effect=[3, 0, 0])  # 3 gardens -> +2

        flag = await check_community_opposition_score(conn, "PID-001", parcel)
        assert flag.severity == "green"

    @pytest.mark.asyncio
    async def test_score_3_only_nmh(self):
        """Score = 3: NMH only."""
        conn = _make_conn()
        parcel = _make_parcel()
        conn.fetchval = AsyncMock(side_effect=[0, 5, 0])  # 5 NMH -> +3

        flag = await check_community_opposition_score(conn, "PID-001", parcel)
        assert flag.severity == "yellow"

    @pytest.mark.asyncio
    async def test_score_5_gardens_plus_nmh(self):
        """Score = 5: gardens (+2) + NMH (+3)."""
        conn = _make_conn()
        parcel = _make_parcel()
        conn.fetchval = AsyncMock(side_effect=[1, 1, 0])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)
        assert flag.severity == "yellow"

    @pytest.mark.asyncio
    async def test_score_8_all_max(self):
        """Score = 8: gardens (+2) + NMH (+3) + trees capped at +3."""
        conn = _make_conn()
        parcel = _make_parcel()
        conn.fetchval = AsyncMock(side_effect=[1, 1, 50])  # trees: 50//5=10, capped to 3

        flag = await check_community_opposition_score(conn, "PID-001", parcel)
        assert flag.severity == "red"

    @pytest.mark.asyncio
    async def test_trees_15_contributes_3_points(self):
        """Trees = 15 -> 15//5 = 3 (exactly at max)."""
        conn = _make_conn()
        parcel = _make_parcel()
        conn.fetchval = AsyncMock(side_effect=[0, 0, 15])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)
        # Score = 3 -> YELLOW
        assert flag.severity == "yellow"

    @pytest.mark.asyncio
    async def test_trees_20_still_contributes_3_points(self):
        """Trees = 20 -> 20//5 = 4, capped to 3."""
        conn = _make_conn()
        parcel = _make_parcel()
        conn.fetchval = AsyncMock(side_effect=[0, 0, 20])

        flag = await check_community_opposition_score(conn, "PID-001", parcel)
        # Score = 3 -> YELLOW
        assert flag.severity == "yellow"

    @pytest.mark.asyncio
    async def test_partial_table_failures_still_compute(self):
        """If gardens table fails but NMH and trees succeed, score is still computed."""
        conn = _make_conn()
        parcel = _make_parcel()

        # Gardens raises exception, NMH = 1 (+3), Trees = 10 (+2)
        call_count = 0

        async def side_effect_fn(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("relation 'community_gardens' does not exist")
            elif call_count == 2:
                return 1  # NMH count
            else:
                return 10  # Trees count

        conn.fetchval = AsyncMock(side_effect=side_effect_fn)

        flag = await check_community_opposition_score(conn, "PID-001", parcel)

        assert flag is not None
        # Score: NMH +3, Trees 10//5=2 -> total 5 -> YELLOW
        assert flag.severity == "yellow"
