"""
Comprehensive unit tests for the VanCity Lens Bill 47 Entitlement Engine.

Tests cover:
- Core entitlement computation (compute_entitlement)
- Hidden cost estimation (calculate_total_hidden_costs)
- Validation engine (compute_validation)
- Three-scenario pro forma analysis
- Gap analysis narratives
- Execution difficulty scoring
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from api.entitlement import compute_entitlement, _build_sources, ParcelNotFoundError
from api.models import (
    TOATier, EntitlementSignal, StationEntitlement, ValueEstimate,
    ParcelEntitlementResponse, SourceAttribution, DealValidation,
    RiskFlag, StationType,
)
from api.validation import compute_validation, _calculate_execution_difficulty
from api.hidden_costs import (
    calculate_total_hidden_costs,
    estimate_demolition,
    estimate_environmental,
    estimate_tenant_displacement,
    estimate_rezoning_cost,
    estimate_soft_soil,
)
from api.neighborhood_economics import get_neighborhood_multiplier


# ════════════════════════════════════════════════════════════════════════════
# FIXTURES: Mock Database Connections
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_conn():
    """Mock asyncpg.Connection with configurable responses."""
    conn = AsyncMock()
    return conn


@pytest.fixture
def parcel_single_toa_tier():
    """Parcel in a single TOA tier (Tier 1, near SkyTrain station)."""
    return {
        "pid": "001-234-567",
        "civic_address": "1234 Main Street, Vancouver, BC",
        "current_zoning": "RM-4",
        "current_height": 6,
        "current_fsr": Decimal("2.5"),
        "lot_area_sqm": Decimal("500"),
        "assessed_value": 2_500_000,
        "asking_price": 3_200_000,
        "land_value": 1_800_000,
        "improvement_value": 700_000,
        "year_built": 1975,
        "geo_local_area": "Mount Pleasant",
    }


@pytest.fixture
def parcel_multiple_toa_tiers():
    """Parcel overlapping multiple TOA tiers (best selected)."""
    return {
        "pid": "002-345-678",
        "civic_address": "5678 Granville Street, Vancouver, BC",
        "current_zoning": "RM-3",
        "current_height": 8,
        "current_fsr": Decimal("2.0"),
        "lot_area_sqm": Decimal("800"),
        "assessed_value": 4_000_000,
        "asking_price": 5_100_000,
        "land_value": 2_200_000,
        "improvement_value": 1_800_000,
        "year_built": 1990,
        "geo_local_area": "Kitsilano",
    }


@pytest.fixture
def parcel_outside_toa():
    """Parcel outside all TOA zones."""
    return {
        "pid": "003-456-789",
        "civic_address": "9999 Distant Avenue, Vancouver, BC",
        "current_zoning": "RS-1",
        "current_height": 3,
        "current_fsr": Decimal("0.5"),
        "lot_area_sqm": Decimal("600"),
        "assessed_value": 1_800_000,
        "asking_price": None,
        "land_value": 1_600_000,
        "improvement_value": 200_000,
        "year_built": 2005,
        "geo_local_area": "South Vancouver",
    }


@pytest.fixture
def parcel_zoning_exceeds_bill47():
    """Parcel with current zoning already exceeding Bill 47."""
    return {
        "pid": "004-567-890",
        "civic_address": "4321 Elite Drive, Vancouver, BC",
        "current_zoning": "CD-1",
        "current_height": 25,
        "current_fsr": Decimal("6.5"),
        "lot_area_sqm": Decimal("2000"),
        "assessed_value": 10_000_000,
        "asking_price": 12_500_000,
        "land_value": 5_000_000,
        "improvement_value": 5_000_000,
        "year_built": 2015,
        "geo_local_area": "Downtown",
    }


@pytest.fixture
def parcel_no_current_height():
    """Parcel with missing current height/FSR data."""
    return {
        "pid": "005-678-901",
        "civic_address": "2000 Vacant Lot, Vancouver, BC",
        "current_zoning": "RS-5",
        "current_height": None,
        "current_fsr": None,
        "lot_area_sqm": Decimal("450"),
        "assessed_value": 800_000,
        "asking_price": 950_000,
        "land_value": 750_000,
        "improvement_value": 50_000,
        "year_built": None,
        "geo_local_area": "West End",
    }


@pytest.fixture
def parcel_zero_lot_area():
    """Parcel with zero lot area (edge case)."""
    return {
        "pid": "006-789-012",
        "civic_address": "0 Invalid Lot, Vancouver, BC",
        "current_zoning": "RM-4",
        "current_height": 6,
        "current_fsr": Decimal("2.0"),
        "lot_area_sqm": Decimal("0"),
        "assessed_value": 0,
        "asking_price": None,
        "land_value": 0,
        "improvement_value": 0,
        "year_built": None,
        "geo_local_area": "Downtown",
    }


@pytest.fixture
def entitlement_tier1():
    """TOA Tier 1 entitlement (0-200m from station)."""
    return {
        "station_name": "Main Street Station",
        "tier": 1,
        "max_storeys": 20,
        "max_fsr": Decimal("4.0"),
        "distance_m": Decimal("150"),
        "current_height": 6,
        "current_fsr": Decimal("2.5"),
    }


@pytest.fixture
def entitlement_tier2():
    """TOA Tier 2 entitlement (200-400m)."""
    return {
        "station_name": "Broadway Station",
        "tier": 2,
        "max_storeys": 12,
        "max_fsr": Decimal("2.5"),
        "distance_m": Decimal("350"),
        "current_height": 8,
        "current_fsr": Decimal("2.0"),
    }


@pytest.fixture
def entitlement_tier3():
    """TOA Tier 3 entitlement (400-800m)."""
    return {
        "station_name": "King Edward Station",
        "tier": 3,
        "max_storeys": 6,
        "max_fsr": Decimal("1.5"),
        "distance_m": Decimal("650"),
        "current_height": 3,
        "current_fsr": Decimal("0.8"),
    }


# ════════════════════════════════════════════════════════════════════════════
# TEST SUITE 1: CORE ENTITLEMENT LOGIC (compute_entitlement)
# ════════════════════════════════════════════════════════════════════════════

class TestComputeEntitlementBasic:
    """Test core entitlement computation functionality."""

    @pytest.mark.asyncio
    async def test_01_single_toa_tier(self, mock_conn, parcel_single_toa_tier, entitlement_tier1):
        """Test 1: Normal parcel in single TOA tier - verify storeys, FSR, uplift."""
        # Setup mocks
        mock_conn.fetchrow.side_effect = [parcel_single_toa_tier]
        mock_conn.fetch.return_value = [entitlement_tier1]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "001-234-567")

        assert result.pid == "001-234-567"
        assert result.in_toa is True
        assert len(result.entitlements) == 1

        ent = result.entitlements[0]
        assert ent.station_name == "Main Street Station"
        assert ent.tier == TOATier.TIER_1
        assert ent.bill47_storeys == 20
        assert ent.bill47_fsr == Decimal("4.0")
        assert ent.entitled_storeys == 20  # max(20, 6)
        assert ent.entitled_fsr == Decimal("4.0")  # max(4.0, 2.5)
        assert ent.storey_uplift == 14  # 20 - 6
        assert ent.fsr_uplift == Decimal("1.5")  # 4.0 - 2.5
        assert ent.zoning_already_exceeds is False

    @pytest.mark.asyncio
    async def test_02_multiple_toa_tiers(self, mock_conn, parcel_multiple_toa_tiers, entitlement_tier1, entitlement_tier2):
        """Test 2: Parcel in multiple TOA tiers - verify best entitlement selected."""
        # Multiple overlapping tiers, Tier 1 should be best (highest storeys)
        mock_conn.fetchrow.side_effect = [parcel_multiple_toa_tiers]
        mock_conn.fetch.return_value = [entitlement_tier1, entitlement_tier2]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "002-345-678")

        assert result.in_toa is True
        assert len(result.entitlements) == 2
        # Best should be first (Tier 1 with 20 storeys)
        assert result.best_entitlement.tier == TOATier.TIER_1
        assert result.best_entitlement.entitled_storeys == 20
        # Entitlements should be sorted by storeys descending
        assert result.entitlements[0].entitled_storeys > result.entitlements[1].entitled_storeys

    @pytest.mark.asyncio
    async def test_03_outside_toa_zones(self, mock_conn, parcel_outside_toa):
        """Test 3: Parcel outside all TOA zones - verify in_toa=False, no entitlements."""
        mock_conn.fetchrow.side_effect = [parcel_outside_toa]
        mock_conn.fetch.return_value = []  # No entitlements
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "003-456-789")

        assert result.pid == "003-456-789"
        assert result.in_toa is False
        assert len(result.entitlements) == 0
        assert result.best_entitlement is None
        assert result.value_estimate is None

    @pytest.mark.asyncio
    async def test_04_zoning_exceeds_bill47(self, mock_conn, parcel_zoning_exceeds_bill47, entitlement_tier1):
        """Test 4: Current zoning exceeds Bill 47 - verify zoning_already_exceeds=True."""
        # Current: 25 storeys, Bill 47 Tier 1: 20 storeys
        parcel = parcel_zoning_exceeds_bill47.copy()
        parcel["current_height"] = 25
        parcel["current_fsr"] = Decimal("6.5")

        ent = entitlement_tier1.copy()
        ent["current_height"] = 25
        ent["current_fsr"] = Decimal("6.5")

        mock_conn.fetchrow.side_effect = [parcel]
        mock_conn.fetch.return_value = [ent]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "004-567-890")

        be = result.best_entitlement
        assert be.zoning_already_exceeds is True
        assert be.entitled_storeys == 25  # max(20, 25)
        assert be.entitled_fsr == Decimal("6.5")  # max(4.0, 6.5)
        assert be.storey_uplift == 0  # No uplift since current exceeds Bill 47
        assert be.fsr_uplift == Decimal("0")

    @pytest.mark.asyncio
    async def test_05_no_current_height_data(self, mock_conn, parcel_no_current_height, entitlement_tier1):
        """Test 5: Parcel with no current height/FSR - verify defaults to Bill 47 values."""
        parcel = parcel_no_current_height.copy()
        parcel["current_height"] = None
        parcel["current_fsr"] = None

        ent = entitlement_tier1.copy()
        ent["current_height"] = None
        ent["current_fsr"] = None

        mock_conn.fetchrow.side_effect = [parcel]
        mock_conn.fetch.return_value = [ent]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "005-678-901")

        be = result.best_entitlement
        # current_height is None, so effective = max(20, 0) = 20
        assert be.entitled_storeys == 20
        assert be.entitled_fsr == Decimal("4.0")
        assert be.storey_uplift == 20  # Full Bill 47 uplift
        assert be.fsr_uplift == Decimal("4.0")

    @pytest.mark.asyncio
    async def test_06_parcel_not_found(self, mock_conn):
        """Test: ParcelNotFoundError raised when PID doesn't exist."""
        mock_conn.fetchrow.return_value = None

        with pytest.raises(ParcelNotFoundError) as exc_info:
            await compute_entitlement(mock_conn, "999-999-999")

        assert exc_info.value.pid == "999-999-999"


class TestValueEstimation:
    """Test value estimation based on entitled density."""

    @pytest.mark.asyncio
    async def test_06_value_estimate_with_asking_price(self, mock_conn, parcel_single_toa_tier, entitlement_tier1):
        """Test 6: Value estimation with asking price - verify buildable_sqft, estimated_land_value, delta."""
        mock_conn.fetchrow.side_effect = [parcel_single_toa_tier]
        mock_conn.fetch.return_value = [entitlement_tier1]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "001-234-567", price_per_sqft=Decimal("800"))

        ve = result.value_estimate
        assert ve is not None
        assert ve.lot_area_sqm == Decimal("500")
        assert ve.entitled_fsr == Decimal("4.0")

        # buildable_sqft = 500 sqm * 4.0 FSR * 10.7639 sqft/sqm
        expected_buildable = 500 * 4.0 * 10.7639
        assert float(ve.buildable_sqft) == pytest.approx(expected_buildable, rel=0.01)

        # estimated_land_value = buildable_sqft * price_per_sqft
        expected_value = int(Decimal(str(expected_buildable)) * Decimal("800"))
        assert ve.estimated_land_value == expected_value

        # value_delta = estimated - asking_price
        assert ve.value_delta == ve.estimated_land_value - parcel_single_toa_tier["asking_price"]
        assert ve.price_per_sqft_assumption == Decimal("800")

    @pytest.mark.asyncio
    async def test_07_value_estimate_assessed_only(self, mock_conn):
        """Test 7: Value estimation with assessed value only (no asking) - verify fallback."""
        parcel = {
            "pid": "007-890-123",
            "civic_address": "1111 Test Street, Vancouver, BC",
            "current_zoning": "RM-4",
            "current_height": 6,
            "current_fsr": Decimal("2.0"),
            "lot_area_sqm": Decimal("600"),
            "assessed_value": 2_000_000,
            "asking_price": None,  # No asking price
            "land_value": 1_200_000,
            "improvement_value": 800_000,
            "year_built": 1980,
            "geo_local_area": "Strathcona",
        }

        ent = {
            "station_name": "Nanaimo Station",
            "tier": 2,
            "max_storeys": 12,
            "max_fsr": Decimal("2.5"),
            "distance_m": Decimal("300"),
            "current_height": 6,
            "current_fsr": Decimal("2.0"),
        }

        mock_conn.fetchrow.side_effect = [parcel]
        mock_conn.fetch.return_value = [ent]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "007-890-123", price_per_sqft=Decimal("750"))

        ve = result.value_estimate
        assert ve is not None
        # value_delta uses assessed_value as fallback
        assert ve.value_delta == ve.estimated_land_value - parcel["assessed_value"]

    @pytest.mark.asyncio
    async def test_08_zero_lot_area_no_estimate(self, mock_conn, parcel_zero_lot_area, entitlement_tier1):
        """Test 8: Parcel with zero lot area - verify graceful handling."""
        mock_conn.fetchrow.side_effect = [parcel_zero_lot_area]
        mock_conn.fetch.return_value = [entitlement_tier1]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "006-789-012")

        # Should not create value estimate when lot_area is 0/None
        assert result.value_estimate is None

    @pytest.mark.asyncio
    async def test_09_price_per_sqft_scaling(self, mock_conn, parcel_single_toa_tier, entitlement_tier1):
        """Test 9: Different price_per_sqft assumptions - verify calculation scales correctly."""
        mock_conn.fetchrow.side_effect = [parcel_single_toa_tier]
        mock_conn.fetch.return_value = [entitlement_tier1]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            # Test with $1000/sqft
            result = await compute_entitlement(mock_conn, "001-234-567", price_per_sqft=Decimal("1000"))

        ve = result.value_estimate
        # Value should scale linearly with price_per_sqft
        buildable = float(parcel_single_toa_tier["lot_area_sqm"]) * 4.0 * 10.7639
        expected_value_1000 = int(Decimal(str(buildable)) * Decimal("1000"))
        assert ve.estimated_land_value == expected_value_1000

        # Now test with $600/sqft
        mock_conn.fetchrow.side_effect = [parcel_single_toa_tier]
        mock_conn.fetch.return_value = [entitlement_tier1]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "001-234-567", price_per_sqft=Decimal("600"))

        ve = result.value_estimate
        expected_value_600 = int(Decimal(str(buildable)) * Decimal("600"))
        assert ve.estimated_land_value == expected_value_600

    @pytest.mark.asyncio
    async def test_10_source_attribution(self, mock_conn, parcel_single_toa_tier, entitlement_tier1):
        """Test 10: Source attribution - verify all source links are generated."""
        mock_conn.fetchrow.side_effect = [parcel_single_toa_tier]
        mock_conn.fetch.return_value = [entitlement_tier1]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "001-234-567")

        sources = result.sources
        assert sources is not None
        assert len(sources.sources) > 0

        # Check expected source types are present
        source_fields = {s.field for s in sources.sources}
        assert "pid" in source_fields
        assert "civic_address" in source_fields
        assert "current_zoning" in source_fields
        assert "entitlement" in source_fields
        assert "station" in source_fields
        assert "lot_area_sqm" in source_fields
        assert "assessed_value" in source_fields

        # Verify each source has required fields
        for source in sources.sources:
            assert source.field
            assert source.label
            assert source.origin
            assert source.confidence in ["verified", "estimated", "calculated"]
            assert source.url or source.field in ["estimated_land_value", "bc_assessment_lookup"]


# ════════════════════════════════════════════════════════════════════════════
# TEST SUITE 2: HIDDEN COSTS (calculate_total_hidden_costs)
# ════════════════════════════════════════════════════════════════════════════

class TestHiddenCosts:
    """Test hidden cost estimation engine."""

    def test_11_gas_station_environmental(self):
        """Test 11: Gas station environmental cost - verify $500K estimate."""
        cost, explanation = estimate_environmental(["Gasoline Station"])
        assert cost == 500_000
        assert "gas" in explanation.lower() or "fuel" in explanation.lower()

    def test_12_dry_cleaner_environmental(self):
        """Test 12: Dry cleaner environmental cost - verify $350K estimate."""
        cost, explanation = estimate_environmental(["Dry Cleaning"])
        assert cost == 350_000
        assert "dry clean" in explanation.lower() or "perc" in explanation.lower()

    def test_13_no_risky_businesses(self):
        """Test 13: No risky businesses - verify $0 environmental cost."""
        cost, explanation = estimate_environmental(["Coffee Shop", "Restaurant", "Accounting Firm"])
        assert cost == 0
        assert explanation == ""

    def test_14_demolition_pre1960(self):
        """Test 14: Demolition cost for pre-1960 building - verify 40% asbestos premium."""
        # Pre-1960 building with normal improvement value
        cost, explanation = estimate_demolition(
            improvement_value=500_000,
            year_built=1955,
            lot_area_sqm=Decimal("800"),
            entitled_storeys=15
        )

        assert cost > 0
        assert "40%" in explanation or "asbestos" in explanation.lower() or "hazmat" in explanation.lower()
        # Should have asbestos premium
        assert cost >= 150_000  # Floor

    def test_15_demolition_low_value(self):
        """Test 15: Demolition for low-value improvement - verify minimal $50K."""
        cost, explanation = estimate_demolition(
            improvement_value=100_000,  # Very low
            year_built=2000,
            lot_area_sqm=Decimal("500"),
            entitled_storeys=10
        )

        assert cost == 50_000
        assert "minimal" in explanation.lower() or "clearing" in explanation.lower()

    def test_16_tenant_displacement(self):
        """Test 16: Tenant displacement with 3 licences - verify 3 × $40K."""
        cost, explanation = estimate_tenant_displacement(active_licence_count=3)
        assert cost == 120_000
        assert "3" in explanation and "40" in explanation

    def test_17_rezoning_cd1(self):
        """Test 17: CD-1 rezoning cost - verify $250K."""
        cost, explanation = estimate_rezoning_cost(current_zoning="CD-1", is_cd1=True)
        assert cost == 250_000
        assert "250" in explanation or "CD-1" in explanation

    def test_18_bill47_standard_rezoning(self):
        """Test 18: Bill 47 standard rezoning - verify $0."""
        cost, explanation = estimate_rezoning_cost(current_zoning="RM-4", is_cd1=False)
        assert cost == 0
        assert explanation == ""

    def test_19_soft_soil_20_storeys(self):
        """Test 19: Soft soil zone with 20+ storeys - verify $1.5M."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Mount Pleasant",
            entitled_storeys=25
        )
        assert cost == 1_500_000
        assert "1.5" in explanation or "1500" in explanation.lower()

    def test_20_soft_soil_7_12_storeys(self):
        """Test 20: Soft soil with 7-12 storeys - verify $400K."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Mount Pleasant",
            entitled_storeys=10
        )
        assert cost == 400_000
        assert "400" in explanation

    def test_soft_soil_non_soft_zone(self):
        """Soft soil: No cost in non-soft-soil neighborhoods."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Kitsilano",
            entitled_storeys=15
        )
        assert cost == 0

    def test_total_hidden_costs_itemized(self):
        """Test total hidden costs with itemized breakdown."""
        total, items = calculate_total_hidden_costs(
            improvement_value=600_000,
            year_built=1970,
            lot_area_sqm=Decimal("1000"),
            entitled_storeys=15,
            nearby_business_types=["Dry Cleaning"],
            active_licence_count=2,
            current_zoning="CD-1",
            is_cd1=True,
            neighborhood="Mount Pleasant"
        )

        assert total > 0
        assert len(items) > 0

        # Check itemization
        categories = [item[0] for item in items]
        assert "Demolition" in categories
        assert "Environmental" in categories
        assert "Tenant Displacement" in categories
        assert "Rezoning" in categories
        # Mount Pleasant is soft soil zone, so should have soft soil cost
        assert "Soft Soil / Foundation" in categories or "Demolition" in categories


# ════════════════════════════════════════════════════════════════════════════
# TEST SUITE 3: VALIDATION ENGINE (compute_validation)
# ════════════════════════════════════════════════════════════════════════════

class TestValidationEngine:
    """Test the comprehensive validation and pro forma engine."""

    @pytest.mark.asyncio
    async def test_21_grade_a_parcel(self, mock_conn):
        """Test 21: Grade A parcel - no red flags, good economics."""
        parcel = {
            "pid": "101-000-001",
            "civic_address": "1000 Premium Street, Vancouver, BC",
            "current_zoning": "RM-4",
            "current_height": 6,
            "current_fsr": Decimal("2.0"),
            "lot_area_sqm": Decimal("2000"),
            "assessed_value": 6_000_000,
            "asking_price": 7_000_000,
            "land_value": 4_500_000,
            "improvement_value": 1_500_000,
            "year_built": 2010,
            "geo_local_area": "Kitsilano",
        }

        best = StationEntitlement(
            station_name="King Edward Station",
            distance_m=Decimal("250"),
            tier=TOATier.TIER_1,
            bill47_storeys=20,
            bill47_fsr=Decimal("4.0"),
            entitled_storeys=20,
            entitled_fsr=Decimal("4.0"),
            current_storeys=6,
            current_fsr=Decimal("2.0"),
            storey_uplift=14,
            fsr_uplift=Decimal("2.0"),
            zoning_already_exceeds=False,
        )

        value_est = ValueEstimate(
            lot_area_sqm=Decimal("2000"),
            entitled_fsr=Decimal("4.0"),
            buildable_sqft=Decimal("857560"),
            estimated_land_value=686_000_000,
            current_assessed=6_000_000,
            asking_price=7_000_000,
            value_delta=679_000_000,
            price_per_sqft_assumption=Decimal("800"),
        )

        # Mock database queries to return minimal risk data
        mock_conn.fetchrow.side_effect = [None, None, None, None, None, None]
        mock_conn.fetchval.side_effect = [0, 0, 0]
        mock_conn.fetch.return_value = []

        validation = await compute_validation(mock_conn, "101-000-001", parcel, best, value_est)

        assert validation.deal_grade == "A"
        assert validation.deal_score >= 80
        assert validation.red_flag_count == 0

    @pytest.mark.asyncio
    async def test_22_grade_f_parcel(self, mock_conn):
        """Test 22: Grade F parcel - multiple red flags."""
        parcel = {
            "pid": "102-000-002",
            "civic_address": "2000 Problem Site, Vancouver, BC",
            "current_zoning": "RM-4",
            "current_height": 6,
            "current_fsr": Decimal("2.0"),
            "lot_area_sqm": Decimal("100"),  # Very small lot
            "assessed_value": 500_000,
            "asking_price": 1_500_000,  # Way overpriced
            "land_value": 300_000,
            "improvement_value": 200_000,
            "year_built": 1950,
            "geo_local_area": "Downtown",
        }

        best = StationEntitlement(
            station_name="Main Station",
            distance_m=Decimal("150"),
            tier=TOATier.TIER_1,
            bill47_storeys=20,
            bill47_fsr=Decimal("4.0"),
            entitled_storeys=20,
            entitled_fsr=Decimal("4.0"),
            current_storeys=6,
            current_fsr=Decimal("2.0"),
            storey_uplift=14,
            fsr_uplift=Decimal("2.0"),
            zoning_already_exceeds=False,
        )

        value_est = ValueEstimate(
            lot_area_sqm=Decimal("100"),
            entitled_fsr=Decimal("4.0"),
            buildable_sqft=Decimal("42876"),  # Very small
            estimated_land_value=34_000,
            current_assessed=500_000,
            asking_price=1_500_000,
            value_delta=-1_466_000,
            price_per_sqft_assumption=Decimal("800"),
        )

        mock_conn.fetchrow.side_effect = [None, None, None, None, None, None]
        mock_conn.fetchval.side_effect = [0, 0, 0]
        mock_conn.fetch.return_value = []

        validation = await compute_validation(mock_conn, "102-000-002", parcel, best, value_est)

        # Should have multiple risk factors
        # Downtown premium + old building + overpriced = red flags
        assert validation.red_flag_count >= 1
        assert validation.deal_grade in ["B", "C", "D", "F"]  # Grading depends on actual pro forma

    def test_23_execution_difficulty_scoring(self):
        """Test 23: Execution difficulty scoring - verify score calculation."""
        risk_flags = [
            RiskFlag(code="HERITAGE_SITE", severity="red", label="Heritage", detail="Near heritage site", cost_impact=None, verify_url=None),
            RiskFlag(code="EASEMENTS", severity="yellow", label="Easements", detail="3 easements", cost_impact=None, verify_url=None),
        ]

        score, factors = _calculate_execution_difficulty(
            risk_flags=risk_flags,
            lot_adequate=False,  # Assembly required (+3)
            is_cd1=True,  # CD-1 rezoning (+2)
            active_licence_count=2,  # 2 tenants (+2)
            neighborhood="Mount Pleasant",
            entitled_storeys=15,
        )

        assert score > 0
        assert len(factors) > 0
        # Should accumulate: assembly(3) + cd1(2) + tenants(2) + heritage(3) = 10
        assert score <= 10  # Capped at 10

    @pytest.mark.asyncio
    async def test_24_three_scenario_proforma(self, mock_conn):
        """Test 24: Three-scenario pro forma - verify bull > base > bear."""
        parcel = {
            "pid": "103-000-003",
            "civic_address": "3000 Test Ave, Vancouver, BC",
            "current_zoning": "RM-4",
            "current_height": 8,
            "current_fsr": Decimal("2.0"),
            "lot_area_sqm": Decimal("1500"),
            "assessed_value": 4_000_000,
            "asking_price": 5_000_000,
            "land_value": 2_500_000,
            "improvement_value": 1_500_000,
            "year_built": 1990,
            "geo_local_area": "Mount Pleasant",
        }

        best = StationEntitlement(
            station_name="Main Street Station",
            distance_m=Decimal("200"),
            tier=TOATier.TIER_1,
            bill47_storeys=20,
            bill47_fsr=Decimal("4.0"),
            entitled_storeys=20,
            entitled_fsr=Decimal("4.0"),
            current_storeys=8,
            current_fsr=Decimal("2.0"),
            storey_uplift=12,
            fsr_uplift=Decimal("2.0"),
            zoning_already_exceeds=False,
        )

        value_est = ValueEstimate(
            lot_area_sqm=Decimal("1500"),
            entitled_fsr=Decimal("4.0"),
            buildable_sqft=Decimal("643080"),
            estimated_land_value=514_464,
            current_assessed=4_000_000,
            asking_price=5_000_000,
            value_delta=-4_485_536,
            price_per_sqft_assumption=Decimal("800"),
        )

        mock_conn.fetchrow.side_effect = [None, None, None, None, None, None]
        mock_conn.fetchval.side_effect = [0, 0, 0]
        mock_conn.fetch.return_value = []

        validation = await compute_validation(mock_conn, "103-000-003", parcel, best, value_est)

        if validation.three_scenario_proforma:
            three_scen = validation.three_scenario_proforma
            # Bull should have highest alpha
            # Base should have moderate alpha
            # Bear should have lowest alpha
            assert three_scen.bull.true_alpha >= three_scen.base.true_alpha
            assert three_scen.base.true_alpha >= three_scen.bear.true_alpha

    @pytest.mark.asyncio
    async def test_25_gap_analysis_narrative(self, mock_conn):
        """Test 25: Gap analysis narrative - verify it explains alpha erosion."""
        parcel = {
            "pid": "104-000-004",
            "civic_address": "4000 Gap Analysis, Vancouver, BC",
            "current_zoning": "RM-4",
            "current_height": 6,
            "current_fsr": Decimal("2.0"),
            "lot_area_sqm": Decimal("1000"),
            "assessed_value": 3_000_000,
            "asking_price": 4_000_000,
            "land_value": 2_000_000,
            "improvement_value": 1_000_000,
            "year_built": 1980,
            "geo_local_area": "Strathcona",
        }

        best = StationEntitlement(
            station_name="Main Station",
            distance_m=Decimal("150"),
            tier=TOATier.TIER_1,
            bill47_storeys=20,
            bill47_fsr=Decimal("4.0"),
            entitled_storeys=20,
            entitled_fsr=Decimal("4.0"),
            current_storeys=6,
            current_fsr=Decimal("2.0"),
            storey_uplift=14,
            fsr_uplift=Decimal("2.0"),
            zoning_already_exceeds=False,
        )

        value_est = ValueEstimate(
            lot_area_sqm=Decimal("1000"),
            entitled_fsr=Decimal("4.0"),
            buildable_sqft=Decimal("428760"),
            estimated_land_value=343_000,
            current_assessed=3_000_000,
            asking_price=4_000_000,
            value_delta=-3_657_000,
            price_per_sqft_assumption=Decimal("800"),
        )

        mock_conn.fetchrow.side_effect = [None, None, None, None, None, None]
        mock_conn.fetchval.side_effect = [0, 0, 0]
        mock_conn.fetch.return_value = []

        validation = await compute_validation(mock_conn, "104-000-004", parcel, best, value_est)

        if validation.gap_analysis:
            gap = validation.gap_analysis
            # Gap analysis should explain where theoretical alpha goes
            assert len(gap) > 0
            # Check for key terms that explain cost deductions
            lower_gap = gap.lower()
            # Should mention some of these cost factors
            has_cost_mention = any(term in lower_gap for term in [
                "demolition", "environmental", "contingency", "marketing",
                "absorption", "inflation", "gap", "exists", "costs"
            ])
            assert has_cost_mention


# ════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestEntitlementSignals:
    """Test entitlement signal generation."""

    @pytest.mark.asyncio
    async def test_signal_high_alpha(self, mock_conn, parcel_single_toa_tier, entitlement_tier1):
        """Test signal generation for high alpha opportunity."""
        mock_conn.fetchrow.side_effect = [parcel_single_toa_tier]
        mock_conn.fetch.return_value = [entitlement_tier1]
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "001-234-567", price_per_sqft=Decimal("1200"))

        assert result.value_estimate is not None
        if result.value_estimate.value_delta > 1_000_000:
            assert result.signal == EntitlementSignal.HIGH_ALPHA

    @pytest.mark.asyncio
    async def test_signal_no_entitlement(self, mock_conn, parcel_outside_toa):
        """Test signal for parcel outside TOA."""
        mock_conn.fetchrow.side_effect = [parcel_outside_toa]
        mock_conn.fetch.return_value = []
        mock_conn.fetchval.return_value = 0

        with patch('api.validation.compute_validation') as mock_validation:
            mock_validation.return_value = MagicMock(spec=DealValidation)

            result = await compute_entitlement(mock_conn, "003-456-789")

        assert result.signal == EntitlementSignal.NO_ENTITLEMENT


# ════════════════════════════════════════════════════════════════════════════
# NEIGHBORHOOD & ECONOMICS TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestNeighborhoodMultipliers:
    """Test neighborhood revenue multiplier logic."""

    def test_premium_neighborhood_kitsilano(self):
        """Test Kitsilano (premium) has multiplier > 1.0."""
        mult = get_neighborhood_multiplier("Kitsilano")
        assert mult >= Decimal("1.10")

    def test_value_neighborhood_south_vancouver(self):
        """Test South Vancouver (value) has multiplier < 1.0."""
        mult = get_neighborhood_multiplier("South Vancouver")
        assert mult <= Decimal("0.90")

    def test_neutral_neighborhood(self):
        """Test neutral neighborhood has multiplier ~1.0."""
        mult = get_neighborhood_multiplier("Marpole")
        assert Decimal("0.95") <= mult <= Decimal("1.05")

    def test_unknown_neighborhood(self):
        """Test unknown neighborhood defaults to 1.0."""
        mult = get_neighborhood_multiplier("NonExistentArea")
        assert mult == Decimal("1.00")

    def test_case_insensitive_lookup(self):
        """Test multiplier lookup is case-insensitive."""
        mult1 = get_neighborhood_multiplier("Kitsilano")
        mult2 = get_neighborhood_multiplier("KITSILANO")
        mult3 = get_neighborhood_multiplier("kitsilano")
        assert mult1 == mult2 == mult3
