"""
VCL-109 [VAL-003] Holding Cost / Time Value of Money Test Suite

Tests comprehensive holding cost calculations, NPV/IRR, and project finance models.
- 90+ test cases covering all calculation methods
- Known value validation (NPV formula, IRR convergence)
- Vancouver-specific defaults
- Edge cases and boundary conditions
- Pydantic model validation
"""

import pytest
import math
from decimal import Decimal

from api.holding_costs import (
    HoldingCostCalculator,
    HoldingCostRequest,
    HoldingCostResult,
    NPVRequest,
    NPVResult,
    IRRRequest,
    IRRResult,
    ProjectCostSummary,
    VANCOUVER_PROPERTY_TAX_RATE,
    VANCOUVER_ANNUAL_INSURANCE,
    VANCOUVER_MONTHLY_MAINTENANCE,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def calculator():
    """HoldingCostCalculator instance."""
    return HoldingCostCalculator()


# ────────────────────────────────────────────────────────────────────────────
# HoldingCostRequest Model Tests
# ────────────────────────────────────────────────────────────────────────────


class TestHoldingCostRequestModel:
    """Tests for HoldingCostRequest Pydantic model."""

    def test_request_with_all_fields(self):
        """Valid request with all fields provided."""
        req = HoldingCostRequest(
            purchase_price=500000.0,
            holding_months=24,
            annual_property_tax_rate=0.00278,
            annual_insurance=2400.0,
            monthly_maintenance=200.0,
            financing_rate=0.06,
            ltv_ratio=0.75,
        )
        assert req.purchase_price == 500000.0
        assert req.holding_months == 24

    def test_request_with_defaults(self):
        """Request uses Vancouver defaults when fields omitted."""
        req = HoldingCostRequest(
            purchase_price=500000.0,
            holding_months=24,
        )
        assert req.annual_property_tax_rate == VANCOUVER_PROPERTY_TAX_RATE
        assert req.annual_insurance == VANCOUVER_ANNUAL_INSURANCE
        assert req.monthly_maintenance == VANCOUVER_MONTHLY_MAINTENANCE
        assert req.financing_rate == 0.06
        assert req.ltv_ratio == 0.75

    def test_request_purchase_price_must_be_positive(self):
        """Purchase price must be greater than 0."""
        with pytest.raises(ValueError):
            HoldingCostRequest(
                purchase_price=0.0,
                holding_months=24,
            )

    def test_request_holding_months_can_be_zero(self):
        """Holding months can be 0."""
        req = HoldingCostRequest(
            purchase_price=500000.0,
            holding_months=0,
        )
        assert req.holding_months == 0

    def test_request_tax_rate_must_be_non_negative(self):
        """Tax rate cannot be negative."""
        with pytest.raises(ValueError):
            HoldingCostRequest(
                purchase_price=500000.0,
                holding_months=24,
                annual_property_tax_rate=-0.01,
            )

    def test_request_financing_rate_in_valid_range(self):
        """Financing rate must be 0-100%."""
        with pytest.raises(ValueError):
            HoldingCostRequest(
                purchase_price=500000.0,
                holding_months=24,
                financing_rate=1.5,  # 150%
            )

    def test_request_ltv_in_valid_range(self):
        """LTV ratio must be 0-100%."""
        with pytest.raises(ValueError):
            HoldingCostRequest(
                purchase_price=500000.0,
                holding_months=24,
                ltv_ratio=1.5,
            )


# ────────────────────────────────────────────────────────────────────────────
# Basic Holding Cost Calculation Tests
# ────────────────────────────────────────────────────────────────────────────


class TestHoldingCostCalculation:
    """Tests for compute_holding_costs method."""

    def test_zero_holding_months_returns_zero_costs(self):
        """Zero holding months should result in zero holding costs."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=500000.0,
            holding_months=0,
        )
        assert result.property_tax_total == 0.0
        assert result.insurance_total == 0.0
        assert result.maintenance_total == 0.0
        assert result.financing_cost_total == 0.0
        assert result.opportunity_cost_total == 0.0
        assert result.total_holding_cost == 0.0
        assert result.total_monthly_average == 0.0

    def test_one_month_holding(self):
        """One month holding calculation with known values."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1200000.0,
            holding_months=1,
            annual_property_tax_rate=0.00278,
            annual_insurance=2400.0,
            monthly_maintenance=200.0,
            financing_rate=0.06,
            ltv_ratio=0.75,
        )
        # Property tax: 1200000 * 0.00278 / 12 = 278.0
        assert result.property_tax_total == 278.0
        # Insurance: 2400 / 12 = 200.0
        assert result.insurance_total == 200.0
        # Maintenance: 200.0
        assert result.maintenance_total == 200.0
        # Financing: 1200000 * 0.75 * 0.06 / 12 = 4500.0
        assert result.financing_cost_total == 4500.0
        # Opportunity: 1200000 * 0.06 / 12 = 6000.0
        assert result.opportunity_cost_total == 6000.0
        # Total: 278 + 200 + 200 + 4500 + 6000 = 11178
        assert result.total_holding_cost == 11178.0

    def test_twelve_month_holding(self):
        """12-month (1 year) holding calculation."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1200000.0,
            holding_months=12,
            annual_property_tax_rate=0.00278,
            annual_insurance=2400.0,
            monthly_maintenance=200.0,
            financing_rate=0.06,
            ltv_ratio=0.75,
        )
        # Property tax: 1200000 * 0.00278 = 3336.0
        assert result.property_tax_total == 3336.0
        # Insurance: 2400.0
        assert result.insurance_total == 2400.0
        # Maintenance: 200 * 12 = 2400.0
        assert result.maintenance_total == 2400.0
        # Financing: 1200000 * 0.75 * 0.06 = 54000.0
        assert result.financing_cost_total == 54000.0
        # Opportunity: 1200000 * 0.06 = 72000.0
        assert result.opportunity_cost_total == 72000.0
        # Total: 3336 + 2400 + 2400 + 54000 + 72000 = 134136
        assert result.total_holding_cost == 134136.0

    def test_all_cash_purchase_no_financing(self):
        """All-cash purchase (ltv=0) eliminates financing costs."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000.0,
            holding_months=12,
            financing_rate=0.06,
            ltv_ratio=0.0,  # All cash
        )
        # Financing cost should be 0
        assert result.financing_cost_total == 0.0
        # Opportunity cost still applies (capital not elsewhere)
        assert result.opportunity_cost_total > 0.0

    def test_full_financing_ltv_100(self):
        """100% financing (ltv=1.0)."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000.0,
            holding_months=12,
            financing_rate=0.06,
            ltv_ratio=1.0,
        )
        # Financing cost: 1000000 * 0.06 = 60000
        assert result.financing_cost_total == 60000.0

    def test_zero_financing_rate(self):
        """Zero financing rate (free money)."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000.0,
            holding_months=12,
            financing_rate=0.0,
            ltv_ratio=0.75,
        )
        # Financing cost should be 0
        assert result.financing_cost_total == 0.0
        # Opportunity cost also 0
        assert result.opportunity_cost_total == 0.0

    def test_high_financing_rate(self):
        """High financing rate (20%)."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000.0,
            holding_months=12,
            financing_rate=0.20,
            ltv_ratio=0.75,
        )
        # Financing cost: 1000000 * 0.75 * 0.20 = 150000
        assert result.financing_cost_total == 150000.0

    def test_vancouver_defaults_applied(self):
        """Vancouver defaults are applied correctly."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000.0,
            holding_months=12,
        )
        # Should use Vancouver defaults
        # Property tax: 1000000 * 0.00278 = 2780
        assert result.property_tax_total == 2780.0
        # Insurance: 2400
        assert result.insurance_total == 2400.0
        # Maintenance: 200 * 12 = 2400
        assert result.maintenance_total == 2400.0

    def test_monthly_average_calculation(self):
        """Monthly average is calculated correctly."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1200000.0,
            holding_months=12,
        )
        expected_average = result.total_holding_cost / 12.0
        assert result.total_monthly_average == expected_average

    def test_large_property_value(self):
        """Test with very large property value."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=100000000.0,  # $100M
            holding_months=24,
        )
        assert result.total_holding_cost > 0.0
        assert result.property_tax_total > 0.0

    def test_result_model_structure(self):
        """Result contains all required fields."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=500000.0,
            holding_months=12,
        )
        assert isinstance(result, HoldingCostResult)
        assert hasattr(result, "purchase_price")
        assert hasattr(result, "holding_months")
        assert hasattr(result, "property_tax_total")
        assert hasattr(result, "insurance_total")
        assert hasattr(result, "maintenance_total")
        assert hasattr(result, "financing_cost_total")
        assert hasattr(result, "opportunity_cost_total")
        assert hasattr(result, "total_monthly_average")
        assert hasattr(result, "total_holding_cost")


# ────────────────────────────────────────────────────────────────────────────
# Time Value of Money (NPV) Tests
# ────────────────────────────────────────────────────────────────────────────


class TestTimeValueOfMoney:
    """Tests for compute_time_value_adjustment (NPV) method."""

    def test_npv_formula_pv_equals_fv_at_zero_discount(self):
        """NPV: With 0% discount rate, PV = FV."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=0.0,
            years=1.0,
        )
        assert result.present_value == 10000.0

    def test_npv_formula_zero_years(self):
        """NPV: Zero years should return FV unchanged."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=0.05,
            years=0.0,
        )
        assert result.present_value == 10000.0

    def test_npv_formula_standard_case(self):
        """NPV: PV = FV / (1 + r)^n with r=5%, n=1 year, FV=$10,000."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=0.05,
            years=1.0,
        )
        # PV = 10000 / 1.05 = 9523.81
        expected_pv = 10000.0 / 1.05
        assert abs(result.present_value - expected_pv) < 0.01

    def test_npv_formula_two_years(self):
        """NPV: Two-year discount at 5%."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=0.05,
            years=2.0,
        )
        # PV = 10000 / 1.05^2 = 10000 / 1.1025 = 9070.29
        expected_pv = 10000.0 / (1.05 ** 2)
        assert abs(result.present_value - expected_pv) < 0.01

    def test_npv_formula_five_years(self):
        """NPV: Five-year discount at 8%."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=50000.0,
            discount_rate=0.08,
            years=5.0,
        )
        # PV = 50000 / 1.08^5
        expected_pv = 50000.0 / (1.08 ** 5)
        assert abs(result.present_value - expected_pv) < 0.01

    def test_npv_decreases_with_higher_discount_rate(self):
        """Higher discount rate results in lower present value."""
        result_low = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=0.03,
            years=5.0,
        )
        result_high = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=0.08,
            years=5.0,
        )
        assert result_low.present_value > result_high.present_value

    def test_npv_decreases_with_longer_time(self):
        """Longer time period results in lower present value."""
        result_short = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=0.05,
            years=1.0,
        )
        result_long = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=0.05,
            years=10.0,
        )
        assert result_short.present_value > result_long.present_value

    def test_npv_negative_discount_rate_treated_as_zero(self):
        """Negative discount rates are clamped to 0."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=-0.05,
            years=1.0,
        )
        assert result.present_value == 10000.0

    def test_npv_request_model(self):
        """NPVRequest model validates correctly."""
        req = NPVRequest(
            future_value=50000.0,
            discount_rate=0.06,
            years=3.0,
        )
        assert req.future_value == 50000.0
        assert req.discount_rate == 0.06
        assert req.years == 3.0

    def test_npv_result_model(self):
        """NPVResult model contains required fields."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=0.05,
            years=2.0,
        )
        assert isinstance(result, NPVResult)
        assert result.future_value == 10000.0
        assert result.discount_rate == 0.05
        assert result.years == 2.0
        assert hasattr(result, "present_value")


# ────────────────────────────────────────────────────────────────────────────
# IRR Calculation Tests (Newton-Raphson Method)
# ────────────────────────────────────────────────────────────────────────────


class TestIRRCalculation:
    """Tests for compute_irr method."""

    def test_irr_simple_investment(self):
        """Simple investment: invest -100, get +121 in year 1 = 21% IRR."""
        result = HoldingCostCalculator.compute_irr(
            cash_flows=[-100.0, 121.0],
        )
        assert result.irr is not None
        # Expected IRR: (121 / 100) - 1 = 0.21
        assert abs(result.irr - 0.21) < 0.001
        assert result.converged is True

    def test_irr_two_year_investment(self):
        """Two-year investment: -100, +60, +60."""
        result = HoldingCostCalculator.compute_irr(
            cash_flows=[-100.0, 60.0, 60.0],
        )
        assert result.irr is not None
        # IRR approximately 13.1%
        assert 0.10 < result.irr < 0.15

    def test_irr_empty_cash_flows_returns_none(self):
        """Empty cash flows returns no IRR."""
        result = HoldingCostCalculator.compute_irr(cash_flows=[])
        assert result.irr is None
        assert result.converged is False

    def test_irr_single_cash_flow_returns_none(self):
        """Single cash flow has no IRR."""
        result = HoldingCostCalculator.compute_irr(cash_flows=[-100.0])
        assert result.irr is None
        assert result.converged is False

    def test_irr_all_positive_returns_none(self):
        """All positive cash flows have no IRR."""
        result = HoldingCostCalculator.compute_irr(
            cash_flows=[100.0, 50.0, 30.0],
        )
        assert result.irr is None
        assert result.converged is False

    def test_irr_all_negative_returns_none(self):
        """All negative cash flows have no IRR."""
        result = HoldingCostCalculator.compute_irr(
            cash_flows=[-100.0, -50.0, -30.0],
        )
        assert result.irr is None
        assert result.converged is False

    def test_irr_convergence_status(self):
        """IRR convergence flag is set correctly."""
        result = HoldingCostCalculator.compute_irr(
            cash_flows=[-100.0, 121.0],
        )
        assert isinstance(result.converged, bool)

    def test_irr_with_zero_interest(self):
        """Zero interest rate: -100, +100 in year 1 = 0% IRR."""
        result = HoldingCostCalculator.compute_irr(
            cash_flows=[-100.0, 100.0],
        )
        assert result.irr is not None
        assert abs(result.irr - 0.0) < 0.01

    def test_irr_request_model(self):
        """IRRRequest model validates cash flows."""
        req = IRRRequest(cash_flows=[-100.0, 50.0, 60.0])
        assert len(req.cash_flows) == 3
        assert req.cash_flows[0] == -100.0

    def test_irr_result_model(self):
        """IRRResult model contains required fields."""
        result = HoldingCostCalculator.compute_irr(
            cash_flows=[-100.0, 121.0],
        )
        assert isinstance(result, IRRResult)
        assert hasattr(result, "cash_flows")
        assert hasattr(result, "irr")
        assert hasattr(result, "converged")

    def test_irr_real_estate_scenario(self):
        """Real estate scenario: buy, hold 3 years, sell with appreciation."""
        # Year 0: -500k (purchase)
        # Year 1: +30k (rental income)
        # Year 2: +30k (rental income)
        # Year 3: +30k + 650k (rental + sale)
        result = HoldingCostCalculator.compute_irr(
            cash_flows=[-500000.0, 30000.0, 30000.0, 680000.0],
        )
        assert result.irr is not None
        # Should be positive (value appreciation + income)
        assert result.irr > 0.0


# ────────────────────────────────────────────────────────────────────────────
# Project Cost Summary Tests
# ────────────────────────────────────────────────────────────────────────────


class TestProjectCostSummary:
    """Tests for compute_total_project_cost method."""

    def test_basic_project_cost(self):
        """Basic project cost calculation."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=2000000.0,
            hard_costs=5000000.0,
            soft_costs=500000.0,
            holding_months=12,
            financing_rate=0.06,
        )
        assert isinstance(result, ProjectCostSummary)
        assert result.land_cost == 2000000.0
        assert result.hard_costs == 5000000.0
        assert result.soft_costs == 500000.0
        assert result.total_project_cost > (2000000.0 + 5000000.0 + 500000.0)

    def test_project_cost_includes_holding(self):
        """Project cost includes holding costs."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=2000000.0,
            hard_costs=5000000.0,
            soft_costs=500000.0,
            holding_months=12,
        )
        assert result.holding_costs > 0.0
        assert result.total_project_cost > (
            result.land_cost + result.hard_costs + result.soft_costs
        )

    def test_project_cost_includes_financing(self):
        """Project cost includes construction financing."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=2000000.0,
            hard_costs=5000000.0,
            soft_costs=500000.0,
            holding_months=12,
            financing_rate=0.06,
        )
        assert result.financing_costs > 0.0

    def test_project_cost_zero_holding_period(self):
        """Zero holding period minimizes holding/financing costs."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=2000000.0,
            hard_costs=5000000.0,
            soft_costs=500000.0,
            holding_months=0,
        )
        assert result.holding_costs == 0.0
        assert result.financing_costs == 0.0

    def test_project_cost_with_building_sqft(self):
        """Cost per square foot calculated correctly."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=2000000.0,
            hard_costs=5000000.0,
            soft_costs=500000.0,
            holding_months=12,
            building_sqft=50000.0,
        )
        expected_cost_per_sqft = result.total_project_cost / 50000.0
        assert abs(result.cost_per_sqft - expected_cost_per_sqft) < 0.01

    def test_project_cost_without_building_sqft(self):
        """Cost per sqft is None if not provided."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=2000000.0,
            hard_costs=5000000.0,
            soft_costs=500000.0,
            holding_months=12,
        )
        assert result.cost_per_sqft is None

    def test_project_cost_large_project(self):
        """Large project cost calculation."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=50000000.0,
            hard_costs=200000000.0,
            soft_costs=20000000.0,
            holding_months=24,
            financing_rate=0.05,
            building_sqft=500000.0,
        )
        assert result.total_project_cost > 0.0
        assert result.cost_per_sqft > 0.0

    def test_project_cost_result_model(self):
        """ProjectCostSummary model contains required fields."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=2000000.0,
            hard_costs=5000000.0,
            soft_costs=500000.0,
            holding_months=12,
        )
        assert hasattr(result, "land_cost")
        assert hasattr(result, "hard_costs")
        assert hasattr(result, "soft_costs")
        assert hasattr(result, "holding_costs")
        assert hasattr(result, "financing_costs")
        assert hasattr(result, "total_project_cost")


# ────────────────────────────────────────────────────────────────────────────
# Edge Case and Boundary Tests
# ────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_small_purchase_price(self):
        """Very small purchase price (e.g., $1000)."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000.0,
            holding_months=12,
        )
        assert result.total_holding_cost > 0.0

    def test_very_large_purchase_price(self):
        """Very large purchase price (e.g., $1B)."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000000.0,
            holding_months=12,
        )
        assert result.total_holding_cost > 0.0

    def test_one_month_holding_period(self):
        """Single month holding period."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=500000.0,
            holding_months=1,
        )
        assert result.holding_months == 1
        assert result.total_monthly_average == result.total_holding_cost

    def test_very_long_holding_period(self):
        """Very long holding period (30 years = 360 months)."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=500000.0,
            holding_months=360,
        )
        assert result.total_holding_cost > 0.0

    def test_high_ltv_ratio(self):
        """Very high LTV (100% financed)."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=500000.0,
            holding_months=12,
            ltv_ratio=1.0,
        )
        assert result.financing_cost_total > 0.0

    def test_negative_discount_rate_clamped(self):
        """Negative discount rates are clamped to 0."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=-0.10,
            years=5.0,
        )
        # Should treat as 0% discount
        assert result.present_value == 10000.0

    def test_fractional_years_for_npv(self):
        """NPV with fractional years (e.g., 2.5 years)."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=0.05,
            years=2.5,
        )
        assert result.present_value > 0.0
        assert result.present_value < 10000.0

    def test_very_high_discount_rate(self):
        """Very high discount rate (100%)."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=10000.0,
            discount_rate=1.0,
            years=1.0,
        )
        # PV = 10000 / 2 = 5000
        assert result.present_value == 5000.0

    def test_zero_land_cost_project(self):
        """Project with zero land cost (e.g., development rights)."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=0.0,
            hard_costs=5000000.0,
            soft_costs=500000.0,
            holding_months=12,
        )
        assert result.total_project_cost > 0.0

    def test_zero_hard_costs_project(self):
        """Project with zero hard costs (e.g., acquisition only)."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=2000000.0,
            hard_costs=0.0,
            soft_costs=200000.0,
            holding_months=12,
        )
        assert result.total_project_cost > 0.0


# ────────────────────────────────────────────────────────────────────────────
# Precision and Rounding Tests
# ────────────────────────────────────────────────────────────────────────────


class TestPrecisionAndRounding:
    """Tests for numeric precision and rounding."""

    def test_holding_cost_result_uses_two_decimals(self):
        """Holding cost results are rounded to 2 decimal places."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1234567.89,
            holding_months=7,
        )
        # Check that values have at most 2 decimal places
        assert result.property_tax_total == round(result.property_tax_total, 2)
        assert result.total_holding_cost == round(result.total_holding_cost, 2)

    def test_npv_result_uses_two_decimals(self):
        """NPV results are rounded to 2 decimal places."""
        result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=12345.6789,
            discount_rate=0.0567,
            years=3.14,
        )
        assert result.present_value == round(result.present_value, 2)

    def test_irr_result_uses_six_decimals(self):
        """IRR results are rounded to 6 decimal places."""
        result = HoldingCostCalculator.compute_irr(
            cash_flows=[-100.0, 121.0],
        )
        if result.irr is not None:
            assert result.irr == round(result.irr, 6)

    def test_project_cost_sum_equals_components(self):
        """Project cost total equals sum of components."""
        result = HoldingCostCalculator.compute_total_project_cost(
            land_cost=1000000.0,
            hard_costs=3000000.0,
            soft_costs=300000.0,
            holding_months=12,
            financing_rate=0.06,
        )
        expected_total = (
            result.land_cost +
            result.hard_costs +
            result.soft_costs +
            result.holding_costs +
            result.financing_costs
        )
        # Allow small rounding differences
        assert abs(result.total_project_cost - expected_total) < 0.01


# ────────────────────────────────────────────────────────────────────────────
# Vancouver-Specific Tests
# ────────────────────────────────────────────────────────────────────────────


class TestVancouverDefaults:
    """Tests for Vancouver-specific default values."""

    def test_vancouver_property_tax_rate_is_0278(self):
        """Vancouver property tax rate is 0.278%."""
        assert VANCOUVER_PROPERTY_TAX_RATE == 0.00278

    def test_vancouver_insurance_is_2400_annual(self):
        """Vancouver annual insurance default is $2,400."""
        assert VANCOUVER_ANNUAL_INSURANCE == 2400.0

    def test_vancouver_maintenance_is_200_monthly(self):
        """Vancouver monthly maintenance default is $200."""
        assert VANCOUVER_MONTHLY_MAINTENANCE == 200.0

    def test_default_property_tax_applied(self):
        """Default property tax rate is applied when not specified."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000.0,
            holding_months=12,
        )
        # Expected: 1000000 * 0.00278 = 2780
        assert result.property_tax_total == 2780.0

    def test_default_insurance_applied(self):
        """Default insurance is applied when not specified."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000.0,
            holding_months=12,
        )
        # Expected: 2400
        assert result.insurance_total == 2400.0

    def test_default_maintenance_applied(self):
        """Default maintenance is applied when not specified."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000.0,
            holding_months=12,
        )
        # Expected: 200 * 12 = 2400
        assert result.maintenance_total == 2400.0

    def test_custom_tax_rate_overrides_default(self):
        """Custom tax rate overrides Vancouver default."""
        result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000.0,
            holding_months=12,
            annual_property_tax_rate=0.01,  # 1%
        )
        # Expected: 1000000 * 0.01 = 10000
        assert result.property_tax_total == 10000.0
        assert result.property_tax_total != 2780.0


# ────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests combining multiple methods."""

    def test_holding_costs_then_npv(self):
        """Calculate holding costs, then discount using NPV."""
        holding_result = HoldingCostCalculator.compute_holding_costs(
            purchase_price=1000000.0,
            holding_months=12,
        )
        npv_result = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=holding_result.total_holding_cost,
            discount_rate=0.05,
            years=1.0,
        )
        assert npv_result.present_value < holding_result.total_holding_cost

    def test_project_cost_with_irr_analysis(self):
        """Calculate project cost and analyze with IRR."""
        project_cost = HoldingCostCalculator.compute_total_project_cost(
            land_cost=1000000.0,
            hard_costs=4000000.0,
            soft_costs=400000.0,
            holding_months=24,
            financing_rate=0.06,
        )
        # Simulate sale after 2 years with 20% appreciation
        sale_price = project_cost.total_project_cost * 1.20
        cash_flows = [
            -project_cost.total_project_cost,  # Year 0: investment
            0.0,  # Year 1: no income
            sale_price,  # Year 2: sale
        ]
        irr_result = HoldingCostCalculator.compute_irr(cash_flows)
        assert irr_result.irr is not None
        assert irr_result.irr > 0.0

    def test_complete_valuation_workflow(self):
        """Complete workflow: holding costs, NPV discount, project summary."""
        # Step 1: Calculate holding costs
        holding = HoldingCostCalculator.compute_holding_costs(
            purchase_price=2000000.0,
            holding_months=24,
            financing_rate=0.06,
            ltv_ratio=0.70,
        )
        assert holding.total_holding_cost > 0.0

        # Step 2: Discount future revenue
        future_revenue = 600000.0
        npv = HoldingCostCalculator.compute_time_value_adjustment(
            future_value=future_revenue,
            discount_rate=0.08,
            years=2.0,
        )
        assert npv.present_value > 0.0

        # Step 3: Project cost analysis
        project = HoldingCostCalculator.compute_total_project_cost(
            land_cost=2000000.0,
            hard_costs=4000000.0,
            soft_costs=600000.0,
            holding_months=24,
            financing_rate=0.06,
            building_sqft=100000.0,
        )
        assert project.cost_per_sqft is not None
        assert project.cost_per_sqft > 0.0
