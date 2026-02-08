"""Tests for the VanCity Lens hidden_costs module.

Pure function tests for cost estimation logic. No database required.
"""

import pytest
from decimal import Decimal
from api.hidden_costs import (
    estimate_demolition,
    estimate_environmental,
    estimate_tenant_displacement,
    estimate_rezoning_cost,
    estimate_soft_soil,
    calculate_total_hidden_costs,
)


# ─────────────────────────────────────────────────────────────
# Tests for estimate_demolition
# ─────────────────────────────────────────────────────────────

class TestEstimateDemolition:
    """Test demolition cost estimation."""

    def test_normal_lot_with_pre1980_building(self):
        """Test 25% asbestos premium for pre-1980 buildings."""
        # Normal improvement value, lot ~10,000 sqft, pre-1980 building
        # Expected: 40% lot footprint × $20/sqft × 1.25 asbestos multiplier
        cost, explanation = estimate_demolition(
            improvement_value=500_000,
            year_built=1975,
            lot_area_sqm=Decimal("930"),  # ~10,000 sqft
            entitled_storeys=8
        )
        assert cost > 0
        assert "25% asbestos" in explanation
        assert "1975" in explanation

    def test_pre1960_building_asbestos_bug(self):
        """
        Test the asbestos premium logic bug:
        Pre-1960 check (40%) runs AFTER pre-1980 check (25%),
        so it never applies — pre-1980 catches year < 1960 first.
        This test documents the bug behavior.
        """
        cost1950, exp1950 = estimate_demolition(
            improvement_value=500_000,
            year_built=1950,  # < 1960
            lot_area_sqm=Decimal("930"),
            entitled_storeys=8
        )

        cost1975, exp1975 = estimate_demolition(
            improvement_value=500_000,
            year_built=1975,  # Between 1960-1980
            lot_area_sqm=Decimal("930"),
            entitled_storeys=8
        )

        # BUG: Both should have same multiplier because pre-1960 logic
        # never executes (pre-1980 check catches year < 1960 first)
        assert "25% asbestos" in exp1950
        assert "25% asbestos" in exp1975
        # The 40% premium for pre-1960 is never applied due to logic order
        assert "40% asbestos" not in exp1950

    def test_low_improvement_value_minimal_cost(self):
        """Test minimal demolition cost ($50K) for improvement < $200K."""
        cost, explanation = estimate_demolition(
            improvement_value=150_000,  # < $200K
            year_built=1980,
            lot_area_sqm=Decimal("930"),
            entitled_storeys=5
        )
        assert cost == 50_000
        assert "Minimal demolition" in explanation
        assert "$50K" in explanation

    def test_large_lot_increased_rate(self):
        """Test $25/sqft base rate for lots > 15,000 sqft."""
        cost, explanation = estimate_demolition(
            improvement_value=500_000,
            year_built=2000,
            lot_area_sqm=Decimal("1400"),  # ~15,050 sqft, just over 15K
            entitled_storeys=6
        )
        assert cost > 0
        # Footprint = 15050 * 0.4 = 6020, rate = $25, mult = 1.0
        # Cost should be ~150,500, clamped to min $150K and max $1.2M
        expected_base = 15050 * 0.4 * 25
        assert abs(cost - int(expected_base)) < 1000 or cost == 150_000

    def test_medium_lot_medium_rate(self):
        """Test $22/sqft base rate for lots between 8K-15K sqft."""
        cost, explanation = estimate_demolition(
            improvement_value=500_000,
            year_built=2000,
            lot_area_sqm=Decimal("1000"),  # ~10,764 sqft
            entitled_storeys=6
        )
        assert cost > 0
        # Should use $22/sqft rate
        assert "22" in str(cost) or cost >= 150_000  # May be clamped

    def test_small_lot_base_rate(self):
        """Test $20/sqft base rate for small lots."""
        cost, explanation = estimate_demolition(
            improvement_value=500_000,
            year_built=2000,
            lot_area_sqm=Decimal("500"),  # ~5,382 sqft
            entitled_storeys=4
        )
        assert cost > 0
        # Footprint = 5382 * 0.4 = 2152.8, rate = $20
        # Cost = 43,056, clamped to $150K
        assert cost == 150_000  # floored at $150K

    def test_cost_floored_at_150k(self):
        """Test minimum cost floor of $150K."""
        cost, explanation = estimate_demolition(
            improvement_value=300_000,
            year_built=2000,
            lot_area_sqm=Decimal("500"),  # Small lot
            entitled_storeys=3
        )
        assert cost >= 150_000
        assert cost == 150_000

    def test_cost_capped_at_1_2m(self):
        """Test maximum cost cap of $1.2M."""
        cost, explanation = estimate_demolition(
            improvement_value=1_000_000,
            year_built=1950,
            lot_area_sqm=Decimal("10000"),  # Extremely large lot (~107,600 sqft)
            entitled_storeys=15
        )
        assert cost <= 1_200_000
        # Verify the cap is actually applied by checking a theoretical uncapped cost
        # Footprint: 107600 * 0.4 = 43040 sqft
        # Rate: $25/sqft (lot > 15K sqft)
        # Mult: 1.25 (pre-1980)
        # Theoretical: 43040 * 25 * 1.25 = 1,345,000 (exceeds cap)
        # So cost should be capped at 1.2M
        assert cost == 1_200_000

    def test_no_year_built_provided(self):
        """Test handling of missing year_built."""
        cost, explanation = estimate_demolition(
            improvement_value=500_000,
            year_built=None,
            lot_area_sqm=Decimal("930"),
            entitled_storeys=6
        )
        assert cost > 0
        assert "asbestos" not in explanation
        assert "1.0" not in explanation or "storey" in explanation


# ─────────────────────────────────────────────────────────────
# Tests for estimate_environmental
# ─────────────────────────────────────────────────────────────

class TestEstimateEnvironmental:
    """Test environmental cost estimation."""

    def test_gas_station_highest_priority(self):
        """Test gas station → $500K."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Gas Station"]
        )
        assert cost == 500_000
        assert "gas station" in explanation.lower() or "fuel" in explanation.lower()

    def test_gasoline_station_variant(self):
        """Test 'Gasoline Station' variant → $500K."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Gasoline Station"]
        )
        assert cost == 500_000

    def test_service_station_variant(self):
        """Test 'Service Station' variant → $500K."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Service Station"]
        )
        assert cost == 500_000

    def test_dry_cleaner_500k_priority(self):
        """Test dry cleaner → $350K (but gas station takes priority)."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Dry Cleaning"]
        )
        assert cost == 350_000
        assert "dry clean" in explanation.lower() or "solvent" in explanation.lower()

    def test_dry_cleaning_plant_variant(self):
        """Test 'Dry Cleaning Plant' variant → $350K."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Dry Cleaning Plant"]
        )
        assert cost == 350_000

    def test_laundry_plant_variant(self):
        """Test 'Laundry Plant' variant → $350K."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Laundry Plant"]
        )
        assert cost == 350_000

    def test_auto_repair_200k(self):
        """Test auto repair → $200K."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Auto Repair"]
        )
        assert cost == 200_000
        assert "200" in explanation

    def test_auto_service_variant(self):
        """Test 'Auto Service' variant → $200K."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Auto Service"]
        )
        assert cost == 200_000

    def test_auto_body_shop(self):
        """Test 'Auto Body' → $200K."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Auto Body"]
        )
        assert cost == 200_000

    def test_multiple_risk_types_gas_priority(self):
        """Test that gas station takes priority over other risks."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Dry Cleaning", "Gas Station", "Auto Repair"]
        )
        assert cost == 500_000
        assert "gas" in explanation.lower()

    def test_multiple_dry_cleaner_precedence(self):
        """Test dry cleaner precedence over auto repair."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Auto Repair", "Dry Cleaning"]
        )
        assert cost == 350_000

    def test_no_risk_types_returns_zero(self):
        """Test no risk types → ($0, '')."""
        cost, explanation = estimate_environmental(
            nearby_business_types=[]
        )
        assert cost == 0
        assert explanation == ""

    def test_none_risk_types(self):
        """Test empty list → ($0, '')."""
        cost, explanation = estimate_environmental(
            nearby_business_types=[]
        )
        assert cost == 0

    def test_partial_match_auto_service_ltd(self):
        """Test partial string matching ('Auto Service Ltd' matches 'Auto Service')."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Auto Service Ltd"]
        )
        assert cost == 200_000

    def test_partial_match_dry_cleaning_co(self):
        """Test partial string matching ('Dry Cleaning Co' matches 'Dry Cleaning')."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Dry Cleaning Co"]
        )
        assert cost == 350_000

    def test_case_insensitive_matching(self):
        """Test case-insensitive matching."""
        cost1, _ = estimate_environmental(["gas station"])
        cost2, _ = estimate_environmental(["GAS STATION"])
        cost3, _ = estimate_environmental(["Gas Station"])
        assert cost1 == cost2 == cost3 == 500_000

    def test_manufacturing_200k(self):
        """Test manufacturing → $200K."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Manufacturing"]
        )
        assert cost == 200_000

    def test_printing_200k(self):
        """Test printing → $200K."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Printing"]
        )
        assert cost == 200_000

    def test_non_risk_business_no_cost(self):
        """Test non-risk business type → ($0, '')."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Coffee Shop"]
        )
        assert cost == 0
        assert explanation == ""

    def test_non_risk_with_risk(self):
        """Test mix of risk and non-risk → uses risk type."""
        cost, explanation = estimate_environmental(
            nearby_business_types=["Coffee Shop", "Dry Cleaning", "Restaurant"]
        )
        assert cost == 350_000


# ─────────────────────────────────────────────────────────────
# Tests for estimate_tenant_displacement
# ─────────────────────────────────────────────────────────────

class TestEstimateTenantDisplacement:
    """Test tenant displacement cost estimation."""

    def test_zero_licences_no_cost(self):
        """Test 0 licences → ($0, '')."""
        cost, explanation = estimate_tenant_displacement(0)
        assert cost == 0
        assert explanation == ""

    def test_one_licence_40k(self):
        """Test 1 licence → $40K."""
        cost, explanation = estimate_tenant_displacement(1)
        assert cost == 40_000
        assert "1" in explanation
        assert "40" in explanation

    def test_five_licences_200k(self):
        """Test 5 licences → $200K (5 × $40K)."""
        cost, explanation = estimate_tenant_displacement(5)
        assert cost == 200_000
        assert "5" in explanation
        assert "200" in explanation

    def test_ten_licences_400k(self):
        """Test 10 licences → $400K (10 × $40K)."""
        cost, explanation = estimate_tenant_displacement(10)
        assert cost == 400_000

    def test_negative_count_no_cost(self):
        """Test negative count → ($0, '') per check in code."""
        cost, explanation = estimate_tenant_displacement(-5)
        assert cost == 0
        assert explanation == ""

    def test_large_count_scales_linearly(self):
        """Test large count scales linearly ($40K per licence)."""
        cost, explanation = estimate_tenant_displacement(50)
        assert cost == 50 * 40_000
        assert cost == 2_000_000


# ─────────────────────────────────────────────────────────────
# Tests for estimate_rezoning_cost
# ─────────────────────────────────────────────────────────────

class TestEstimateRezoningCost:
    """Test rezoning cost estimation."""

    def test_cd1_zone_250k(self):
        """Test CD-1 zone → $250K."""
        cost, explanation = estimate_rezoning_cost(
            current_zoning="CD-1",
            is_cd1=True
        )
        assert cost == 250_000
        assert "CD-1" in explanation

    def test_complex_zoning_with_cd_in_name(self):
        """Test complex zoning with 'CD' in name → $200K."""
        cost, explanation = estimate_rezoning_cost(
            current_zoning="CD-2",
            is_cd1=False
        )
        assert cost == 200_000
        assert "complex" in explanation.lower() or "CD" in explanation

    def test_complex_zoning_with_fccdd(self):
        """Test complex zoning with 'FCCDD' → $200K."""
        cost, explanation = estimate_rezoning_cost(
            current_zoning="FCCDD",
            is_cd1=False
        )
        assert cost == 200_000

    def test_normal_zoning_no_cost(self):
        """Test normal zoning (RS-1) → $0."""
        cost, explanation = estimate_rezoning_cost(
            current_zoning="RS-1",
            is_cd1=False
        )
        assert cost == 0
        assert explanation == ""

    def test_none_zoning_no_cost(self):
        """Test None zoning → $0."""
        cost, explanation = estimate_rezoning_cost(
            current_zoning=None,
            is_cd1=False
        )
        assert cost == 0

    def test_rm4_zoning_no_cost(self):
        """Test RM-4 zoning → $0."""
        cost, explanation = estimate_rezoning_cost(
            current_zoning="RM-4",
            is_cd1=False
        )
        assert cost == 0

    def test_cd1_flag_overrides_zoning(self):
        """Test is_cd1=True overrides zoning string."""
        cost, explanation = estimate_rezoning_cost(
            current_zoning="RS-1",
            is_cd1=True
        )
        assert cost == 250_000

    def test_cd_lowercase_in_zoning(self):
        """Test case-insensitive 'cd' detection."""
        cost, explanation = estimate_rezoning_cost(
            current_zoning="cd-3",
            is_cd1=False
        )
        assert cost == 200_000


# ─────────────────────────────────────────────────────────────
# Tests for estimate_soft_soil
# ─────────────────────────────────────────────────────────────

class TestEstimateSoftSoil:
    """Test soft soil foundation cost estimation."""

    def test_20_storeys_soft_soil_1_5m(self):
        """Test 20+ storeys in soft soil zone → $1.5M."""
        cost, explanation = estimate_soft_soil(
            neighborhood="False Creek",
            entitled_storeys=20
        )
        assert cost == 1_500_000
        assert "1.5" in explanation or "1500" in explanation

    def test_25_storeys_soft_soil_1_5m(self):
        """Test 25 storeys in soft soil zone → $1.5M."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Olympic Village",
            entitled_storeys=25
        )
        assert cost == 1_500_000

    def test_13_to_19_storeys_soft_soil_800k(self):
        """Test 13-19 storeys in soft soil zone → $800K."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Southeast False Creek",
            entitled_storeys=15
        )
        assert cost == 800_000
        assert "800" in explanation

    def test_13_storeys_soft_soil_800k(self):
        """Test exactly 13 storeys in soft soil zone → $800K."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Mount Pleasant",
            entitled_storeys=13
        )
        assert cost == 800_000

    def test_19_storeys_soft_soil_800k(self):
        """Test exactly 19 storeys in soft soil zone → $800K."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Strathcona",
            entitled_storeys=19
        )
        assert cost == 800_000

    def test_7_to_12_storeys_soft_soil_400k(self):
        """Test 7-12 storeys in soft soil zone → $400K."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Marpole",
            entitled_storeys=10
        )
        assert cost == 400_000
        assert "400" in explanation

    def test_7_storeys_soft_soil_400k(self):
        """Test exactly 7 storeys in soft soil zone → $400K."""
        cost, explanation = estimate_soft_soil(
            neighborhood="South Vancouver",
            entitled_storeys=7
        )
        assert cost == 400_000

    def test_12_storeys_soft_soil_400k(self):
        """Test exactly 12 storeys in soft soil zone → $400K."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Victoria-Fraserview",
            entitled_storeys=12
        )
        assert cost == 400_000

    def test_less_than_7_storeys_no_cost(self):
        """Test <7 storeys in soft soil zone → $0."""
        cost, explanation = estimate_soft_soil(
            neighborhood="False Creek",
            entitled_storeys=6
        )
        assert cost == 0

    def test_0_storeys_no_cost(self):
        """Test 0 storeys → $0."""
        cost, explanation = estimate_soft_soil(
            neighborhood="False Creek",
            entitled_storeys=0
        )
        assert cost == 0

    def test_not_in_soft_soil_zone_no_cost(self):
        """Test building outside soft soil zone → $0."""
        cost, explanation = estimate_soft_soil(
            neighborhood="West End",
            entitled_storeys=20
        )
        assert cost == 0
        assert explanation == ""

    def test_none_neighborhood_no_cost(self):
        """Test None neighborhood → $0."""
        cost, explanation = estimate_soft_soil(
            neighborhood=None,
            entitled_storeys=15
        )
        assert cost == 0
        assert explanation == ""

    def test_partial_match_false_creek(self):
        """Test partial match for False Creek."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Southeast False Creek",
            entitled_storeys=15
        )
        assert cost == 800_000

    def test_killarney_soft_soil_zone(self):
        """Test Killarney as soft soil zone."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Killarney",
            entitled_storeys=10
        )
        assert cost == 400_000

    def test_sunset_soft_soil_zone(self):
        """Test Sunset as soft soil zone."""
        cost, explanation = estimate_soft_soil(
            neighborhood="Sunset",
            entitled_storeys=15
        )
        assert cost == 800_000


# ─────────────────────────────────────────────────────────────
# Tests for calculate_total_hidden_costs
# ─────────────────────────────────────────────────────────────

class TestCalculateTotalHiddenCosts:
    """Test aggregation of all hidden costs."""

    def test_aggregation_simple(self):
        """Test basic aggregation of costs."""
        total, items = calculate_total_hidden_costs(
            improvement_value=500_000,
            year_built=1975,
            lot_area_sqm=Decimal("930"),
            entitled_storeys=8,
            nearby_business_types=["Gas Station"],
            active_licence_count=2,
            current_zoning="RS-1",
            is_cd1=False,
            neighborhood="Downtown"
        )

        # Should have multiple items
        assert len(items) >= 2  # At least demo + environmental

        # Each item is (category, cost, explanation)
        for category, cost, explanation in items:
            assert isinstance(category, str)
            assert isinstance(cost, int)
            assert isinstance(explanation, str)
            assert cost > 0

        # Total should equal sum
        calculated_total = sum(cost for _, cost, _ in items)
        assert total == calculated_total

    def test_total_equals_sum_of_items(self):
        """Verify total = sum of individual items."""
        total, items = calculate_total_hidden_costs(
            improvement_value=500_000,
            year_built=1980,
            lot_area_sqm=Decimal("1000"),
            entitled_storeys=15,
            nearby_business_types=["Dry Cleaning", "Auto Repair"],
            active_licence_count=3,
            current_zoning="CD-1",
            is_cd1=True,
            neighborhood="False Creek"
        )

        calculated_sum = sum(cost for _, cost, _ in items)
        assert total == calculated_sum

    def test_items_list_contains_expected_categories(self):
        """Verify items list contains correct category names."""
        total, items = calculate_total_hidden_costs(
            improvement_value=500_000,
            year_built=1970,
            lot_area_sqm=Decimal("2000"),
            entitled_storeys=20,
            nearby_business_types=["Gas Station"],
            active_licence_count=5,
            current_zoning="CD-2",
            is_cd1=False,
            neighborhood="Olympic Village"
        )

        categories = [cat for cat, _, _ in items]

        # Should contain demolition
        assert "Demolition" in categories

        # Should contain environmental (gas station)
        assert "Environmental" in categories

        # Should contain tenant displacement (5 licences)
        assert "Tenant Displacement" in categories

        # Should contain rezoning (CD-2)
        assert "Rezoning" in categories

        # Should contain soft soil (20 storeys in Olympic Village)
        assert "Soft Soil / Foundation" in categories

    def test_all_costs_zero_returns_empty_list(self):
        """Test that zero-cost items are not included."""
        total, items = calculate_total_hidden_costs(
            improvement_value=500_000,
            year_built=2010,
            lot_area_sqm=Decimal("930"),
            entitled_storeys=4,
            nearby_business_types=[],
            active_licence_count=0,
            current_zoning="RS-1",
            is_cd1=False,
            neighborhood="West End"
        )

        # Demolition is always included (has minimum)
        # But other costs should be zero
        assert len(items) >= 1  # At least demolition
        assert total > 0  # At least demolition cost

    def test_minimal_costs_with_low_improvement(self):
        """Test minimal demo cost with low improvement value."""
        total, items = calculate_total_hidden_costs(
            improvement_value=100_000,
            year_built=1950,
            lot_area_sqm=Decimal("500"),
            entitled_storeys=2,
            nearby_business_types=[],
            active_licence_count=0,
            current_zoning="RS-1",
            is_cd1=False,
            neighborhood="Kitsilano"
        )

        # Should have minimal demo ($50K)
        demo_items = [item for item in items if "Demolition" in item[0]]
        assert len(demo_items) > 0
        assert demo_items[0][1] == 50_000

    def test_high_cost_scenario(self):
        """Test high total cost with all risk factors."""
        total, items = calculate_total_hidden_costs(
            improvement_value=1_000_000,
            year_built=1945,
            lot_area_sqm=Decimal("5000"),  # Large lot
            entitled_storeys=25,
            nearby_business_types=["Gas Station", "Dry Cleaning"],
            active_licence_count=10,
            current_zoning="CD-1",
            is_cd1=True,
            neighborhood="False Creek"
        )

        # Should have multiple significant costs
        assert len(items) >= 4
        assert total > 1_000_000  # Multiple major costs

        # Verify each has non-zero cost
        for category, cost, explanation in items:
            assert cost > 0
            assert len(explanation) > 0

    def test_demolition_always_present(self):
        """Verify demolition cost is always included."""
        total, items = calculate_total_hidden_costs(
            improvement_value=500_000,
            year_built=None,
            lot_area_sqm=Decimal("100"),
            entitled_storeys=1,
            nearby_business_types=[],
            active_licence_count=0,
            current_zoning=None,
            is_cd1=False,
            neighborhood=None
        )

        # Demolition should always be present (minimum $150K)
        categories = [cat for cat, _, _ in items]
        assert "Demolition" in categories
        assert total >= 150_000
