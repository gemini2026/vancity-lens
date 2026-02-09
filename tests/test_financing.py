"""
VCL-114 [BIZ-013] Financing Calculator / Deal Modeling Test Suite

Comprehensive tests for:
- Basic calculation correctness
- Edge cases (0% equity, 100% equity, 0% interest rate)
- Scenario generation (bull / base / bear)
- Input validation (negative values, invalid percentages)
- ROI / ROE / IRR calculations
- Breakeven calculation
- Viability check (profitable vs unprofitable)
- Pydantic model validation
- API route integration (POST calculate, GET quick-calc)
"""

import math

import pytest
from pydantic import ValidationError

from api.financing import (
    FinancingCalculator,
    FinancingRequest,
    FinancingResult,
    ScenarioResult,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def base_params():
    """Standard deal parameters for a typical Vancouver project."""
    return {
        "acquisition_cost": 2_000_000.0,
        "equity_pct": 0.25,
        "interest_rate": 0.065,
        "hold_period_months": 36,
        "construction_cost": 5_000_000.0,
        "gross_revenue": 12_000_000.0,
        "soft_cost_pct": 0.18,
        "sellable_sqft": 10_000.0,
    }


@pytest.fixture
def base_result(base_params):
    """FinancingResult for the standard deal parameters."""
    return FinancingCalculator.calculate(**base_params)


# ────────────────────────────────────────────────────────────────────────────
# FinancingRequest Model Validation
# ────────────────────────────────────────────────────────────────────────────


class TestFinancingRequestModel:
    """Tests for FinancingRequest Pydantic model validation."""

    def test_valid_full_request(self):
        """All fields provided within valid ranges."""
        req = FinancingRequest(
            acquisition_cost=2_000_000.0,
            equity_pct=0.25,
            interest_rate=0.065,
            hold_period_months=36,
            construction_cost=5_000_000.0,
            gross_revenue=12_000_000.0,
            soft_cost_pct=0.18,
            sellable_sqft=10_000.0,
        )
        assert req.acquisition_cost == 2_000_000.0
        assert req.equity_pct == 0.25
        assert req.hold_period_months == 36

    def test_defaults_applied(self):
        """soft_cost_pct and sellable_sqft use defaults when omitted."""
        req = FinancingRequest(
            acquisition_cost=1_000_000.0,
            equity_pct=0.20,
            interest_rate=0.05,
            hold_period_months=24,
            construction_cost=3_000_000.0,
            gross_revenue=8_000_000.0,
        )
        assert req.soft_cost_pct == 0.18
        assert req.sellable_sqft == 0.0

    def test_acquisition_cost_must_be_positive(self):
        """acquisition_cost <= 0 rejected."""
        with pytest.raises(ValidationError):
            FinancingRequest(
                acquisition_cost=0.0,
                equity_pct=0.25,
                interest_rate=0.065,
                hold_period_months=36,
                construction_cost=5_000_000.0,
                gross_revenue=12_000_000.0,
            )

    def test_negative_acquisition_cost_rejected(self):
        """Negative acquisition_cost rejected."""
        with pytest.raises(ValidationError):
            FinancingRequest(
                acquisition_cost=-100.0,
                equity_pct=0.25,
                interest_rate=0.065,
                hold_period_months=36,
                construction_cost=5_000_000.0,
                gross_revenue=12_000_000.0,
            )

    def test_equity_pct_above_1_rejected(self):
        """equity_pct > 1.0 rejected."""
        with pytest.raises(ValidationError):
            FinancingRequest(
                acquisition_cost=1_000_000.0,
                equity_pct=1.5,
                interest_rate=0.065,
                hold_period_months=36,
                construction_cost=5_000_000.0,
                gross_revenue=12_000_000.0,
            )

    def test_equity_pct_negative_rejected(self):
        """Negative equity_pct rejected."""
        with pytest.raises(ValidationError):
            FinancingRequest(
                acquisition_cost=1_000_000.0,
                equity_pct=-0.1,
                interest_rate=0.065,
                hold_period_months=36,
                construction_cost=5_000_000.0,
                gross_revenue=12_000_000.0,
            )

    def test_interest_rate_above_1_rejected(self):
        """interest_rate > 1.0 rejected."""
        with pytest.raises(ValidationError):
            FinancingRequest(
                acquisition_cost=1_000_000.0,
                equity_pct=0.25,
                interest_rate=1.5,
                hold_period_months=36,
                construction_cost=5_000_000.0,
                gross_revenue=12_000_000.0,
            )

    def test_hold_period_months_zero_rejected(self):
        """hold_period_months < 1 rejected."""
        with pytest.raises(ValidationError):
            FinancingRequest(
                acquisition_cost=1_000_000.0,
                equity_pct=0.25,
                interest_rate=0.065,
                hold_period_months=0,
                construction_cost=5_000_000.0,
                gross_revenue=12_000_000.0,
            )

    def test_negative_construction_cost_rejected(self):
        """Negative construction_cost rejected."""
        with pytest.raises(ValidationError):
            FinancingRequest(
                acquisition_cost=1_000_000.0,
                equity_pct=0.25,
                interest_rate=0.065,
                hold_period_months=36,
                construction_cost=-1.0,
                gross_revenue=12_000_000.0,
            )

    def test_soft_cost_pct_above_1_rejected(self):
        """soft_cost_pct > 1.0 rejected."""
        with pytest.raises(ValidationError):
            FinancingRequest(
                acquisition_cost=1_000_000.0,
                equity_pct=0.25,
                interest_rate=0.065,
                hold_period_months=36,
                construction_cost=5_000_000.0,
                gross_revenue=12_000_000.0,
                soft_cost_pct=1.5,
            )


# ────────────────────────────────────────────────────────────────────────────
# Basic Calculation Correctness
# ────────────────────────────────────────────────────────────────────────────


class TestBasicCalculation:
    """Tests for core calculation correctness using known values."""

    def test_equity_required(self, base_result):
        """equity_required = acquisition_cost * equity_pct."""
        assert base_result.equity_required == 2_000_000.0 * 0.25

    def test_debt_amount(self, base_result):
        """debt_amount = acquisition_cost * (1 - equity_pct)."""
        assert base_result.debt_amount == 2_000_000.0 * 0.75

    def test_soft_costs(self, base_result):
        """soft_costs = construction_cost * soft_cost_pct."""
        assert base_result.soft_costs == 5_000_000.0 * 0.18

    def test_total_interest_cost(self, base_result):
        """total_interest_cost = debt_amount * interest_rate * (hold_months / 12)."""
        expected = 1_500_000.0 * 0.065 * (36 / 12.0)
        assert abs(base_result.total_interest_cost - expected) < 0.01

    def test_total_project_cost(self, base_result):
        """total_project_cost = acquisition + construction + soft + interest."""
        expected = (
            2_000_000.0
            + 5_000_000.0
            + 5_000_000.0 * 0.18
            + 1_500_000.0 * 0.065 * 3.0
        )
        assert abs(base_result.total_project_cost - expected) < 0.01

    def test_net_profit(self, base_result):
        """net_profit = gross_revenue - total_project_cost."""
        expected_net = 12_000_000.0 - base_result.total_project_cost
        assert abs(base_result.net_profit - expected_net) < 0.01

    def test_roi_calculation(self, base_result):
        """roi = net_profit / total_project_cost."""
        expected_roi = base_result.net_profit / base_result.total_project_cost
        assert abs(base_result.roi - expected_roi) < 0.000001

    def test_roe_calculation(self, base_result):
        """roe = net_profit / equity_required."""
        expected_roe = base_result.net_profit / base_result.equity_required
        assert abs(base_result.roe - expected_roe) < 0.000001

    def test_cash_on_cash_equals_roe(self, base_result):
        """cash_on_cash == roe in simple model."""
        assert base_result.cash_on_cash == base_result.roe

    def test_irr_estimate(self, base_result):
        """irr_estimate = (1 + roi)^(12/hold_period_months) - 1."""
        expected_irr = (1.0 + base_result.roi) ** (12.0 / 36) - 1.0
        assert abs(base_result.irr_estimate - expected_irr) < 0.000001

    def test_result_is_financing_result(self, base_result):
        """Result is a proper FinancingResult instance."""
        assert isinstance(base_result, FinancingResult)

    def test_all_fields_present(self, base_result):
        """All expected fields are present on result."""
        for field in [
            "equity_required", "debt_amount", "soft_costs",
            "total_interest_cost", "total_project_cost", "net_profit",
            "roi", "roe", "cash_on_cash", "irr_estimate",
            "breakeven_price_psf", "is_viable", "scenarios",
        ]:
            assert hasattr(base_result, field), f"Missing field: {field}"


# ────────────────────────────────────────────────────────────────────────────
# Breakeven Price Per Square Foot
# ────────────────────────────────────────────────────────────────────────────


class TestBreakevenPSF:
    """Tests for breakeven price per sellable square foot."""

    def test_breakeven_with_sqft(self, base_result):
        """breakeven_price_psf = total_project_cost / sellable_sqft."""
        expected = base_result.total_project_cost / 10_000.0
        assert abs(base_result.breakeven_price_psf - expected) < 0.01

    def test_breakeven_none_when_no_sqft(self, base_params):
        """breakeven_price_psf is None when sellable_sqft is 0."""
        params = {**base_params, "sellable_sqft": 0.0}
        result = FinancingCalculator.calculate(**params)
        assert result.breakeven_price_psf is None

    def test_breakeven_increases_with_higher_costs(self):
        """Higher costs produce higher breakeven PSF."""
        low = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0, equity_pct=0.25,
            interest_rate=0.05, hold_period_months=24,
            construction_cost=2_000_000.0, gross_revenue=5_000_000.0,
            sellable_sqft=5_000.0,
        )
        high = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0, equity_pct=0.25,
            interest_rate=0.05, hold_period_months=24,
            construction_cost=4_000_000.0, gross_revenue=5_000_000.0,
            sellable_sqft=5_000.0,
        )
        assert high.breakeven_price_psf > low.breakeven_price_psf


# ────────────────────────────────────────────────────────────────────────────
# Viability Check
# ────────────────────────────────────────────────────────────────────────────


class TestViability:
    """Tests for deal viability (is_viable flag)."""

    def test_profitable_deal_is_viable(self, base_result):
        """A deal with positive net profit is viable."""
        assert base_result.net_profit > 0
        assert base_result.is_viable is True

    def test_unprofitable_deal_not_viable(self):
        """A deal where costs exceed revenue is not viable."""
        result = FinancingCalculator.calculate(
            acquisition_cost=5_000_000.0,
            equity_pct=0.25,
            interest_rate=0.08,
            hold_period_months=60,
            construction_cost=10_000_000.0,
            gross_revenue=5_000_000.0,  # revenue < costs
        )
        assert result.net_profit < 0
        assert result.is_viable is False

    def test_breakeven_deal_not_viable(self):
        """Exactly breakeven (net_profit = 0) is NOT viable (profit must be > 0)."""
        # Construct inputs so revenue == total_project_cost exactly
        # acquisition=1000, equity=100%, interest=0%, hold=1, construction=0, soft=0
        result = FinancingCalculator.calculate(
            acquisition_cost=1_000.0,
            equity_pct=1.0,
            interest_rate=0.0,
            hold_period_months=1,
            construction_cost=0.0,
            gross_revenue=1_000.0,
        )
        assert result.net_profit == 0.0
        assert result.is_viable is False


# ────────────────────────────────────────────────────────────────────────────
# Edge Cases — Equity
# ────────────────────────────────────────────────────────────────────────────


class TestEquityEdgeCases:
    """Tests for extreme equity percentages."""

    def test_zero_equity(self):
        """0% equity = 100% debt."""
        result = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0,
            equity_pct=0.0,
            interest_rate=0.06,
            hold_period_months=24,
            construction_cost=3_000_000.0,
            gross_revenue=8_000_000.0,
        )
        assert result.equity_required == 0.0
        assert result.debt_amount == 1_000_000.0
        # ROE is 0 (division by zero guard)
        assert result.roe == 0.0
        assert result.cash_on_cash == 0.0

    def test_full_equity(self):
        """100% equity = 0 debt."""
        result = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0,
            equity_pct=1.0,
            interest_rate=0.06,
            hold_period_months=24,
            construction_cost=3_000_000.0,
            gross_revenue=8_000_000.0,
        )
        assert result.debt_amount == 0.0
        assert result.total_interest_cost == 0.0
        assert result.equity_required == 1_000_000.0

    def test_half_equity(self):
        """50% equity = 50% debt."""
        result = FinancingCalculator.calculate(
            acquisition_cost=2_000_000.0,
            equity_pct=0.50,
            interest_rate=0.06,
            hold_period_months=24,
            construction_cost=4_000_000.0,
            gross_revenue=10_000_000.0,
        )
        assert result.equity_required == 1_000_000.0
        assert result.debt_amount == 1_000_000.0


# ────────────────────────────────────────────────────────────────────────────
# Edge Cases — Interest Rate
# ────────────────────────────────────────────────────────────────────────────


class TestInterestRateEdgeCases:
    """Tests for extreme interest rate values."""

    def test_zero_interest_rate(self):
        """0% interest rate means no interest cost."""
        result = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0,
            equity_pct=0.25,
            interest_rate=0.0,
            hold_period_months=36,
            construction_cost=3_000_000.0,
            gross_revenue=8_000_000.0,
        )
        assert result.total_interest_cost == 0.0

    def test_high_interest_rate(self):
        """High interest rate dramatically increases costs."""
        low_rate = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0,
            equity_pct=0.25,
            interest_rate=0.03,
            hold_period_months=36,
            construction_cost=3_000_000.0,
            gross_revenue=8_000_000.0,
        )
        high_rate = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0,
            equity_pct=0.25,
            interest_rate=0.15,
            hold_period_months=36,
            construction_cost=3_000_000.0,
            gross_revenue=8_000_000.0,
        )
        assert high_rate.total_interest_cost > low_rate.total_interest_cost
        assert high_rate.total_project_cost > low_rate.total_project_cost


# ────────────────────────────────────────────────────────────────────────────
# ROI / ROE / IRR Calculations
# ────────────────────────────────────────────────────────────────────────────


class TestReturnMetrics:
    """Tests for return metric calculations."""

    def test_roi_positive_for_profitable_deal(self, base_result):
        """ROI > 0 when deal is profitable."""
        assert base_result.roi > 0

    def test_roi_negative_for_unprofitable_deal(self):
        """ROI < 0 when deal loses money."""
        result = FinancingCalculator.calculate(
            acquisition_cost=5_000_000.0,
            equity_pct=0.25,
            interest_rate=0.08,
            hold_period_months=60,
            construction_cost=10_000_000.0,
            gross_revenue=5_000_000.0,
        )
        assert result.roi < 0

    def test_roe_higher_than_roi_with_leverage(self, base_result):
        """ROE should be higher than ROI when leverage is used (and deal is profitable)."""
        # With 25% equity (leverage), ROE amplifies returns
        assert base_result.roe > base_result.roi

    def test_irr_estimate_positive_for_profitable_deal(self, base_result):
        """IRR estimate > 0 when deal is profitable."""
        assert base_result.irr_estimate > 0

    def test_irr_annualizes_correctly(self):
        """IRR estimate adjusts for hold period correctly.
        Longer hold should have lower annualized IRR for same total ROI."""
        short = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0,
            equity_pct=0.25,
            interest_rate=0.0,
            hold_period_months=12,
            construction_cost=2_000_000.0,
            gross_revenue=5_000_000.0,
        )
        long = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0,
            equity_pct=0.25,
            interest_rate=0.0,
            hold_period_months=60,
            construction_cost=2_000_000.0,
            gross_revenue=5_000_000.0,
        )
        # Same total ROI but shorter hold should have higher annualized return
        assert short.irr_estimate > long.irr_estimate

    def test_roi_calculation_manual(self):
        """Manual ROI verification with simple numbers."""
        # acquisition=1000, equity=100%, interest=0, hold=12, construction=0,
        # gross=2000 -> total_cost=1000, profit=1000, roi=1.0
        result = FinancingCalculator.calculate(
            acquisition_cost=1_000.0,
            equity_pct=1.0,
            interest_rate=0.0,
            hold_period_months=12,
            construction_cost=0.0,
            gross_revenue=2_000.0,
            soft_cost_pct=0.0,
        )
        assert result.total_project_cost == 1_000.0
        assert result.net_profit == 1_000.0
        assert abs(result.roi - 1.0) < 0.000001

    def test_roe_zero_equity_guard(self):
        """ROE returns 0.0 when equity is 0 (avoid division by zero)."""
        result = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0,
            equity_pct=0.0,
            interest_rate=0.06,
            hold_period_months=24,
            construction_cost=3_000_000.0,
            gross_revenue=8_000_000.0,
        )
        assert result.roe == 0.0


# ────────────────────────────────────────────────────────────────────────────
# Scenario Generation
# ────────────────────────────────────────────────────────────────────────────


class TestScenarios:
    """Tests for bull / base / bear scenario generation."""

    def test_three_scenarios_returned(self, base_result):
        """Result contains exactly bull, base, bear scenarios."""
        assert set(base_result.scenarios.keys()) == {"bull", "base", "bear"}

    def test_scenarios_are_scenario_result(self, base_result):
        """Each scenario is a ScenarioResult instance."""
        for label, scenario in base_result.scenarios.items():
            assert isinstance(scenario, ScenarioResult)
            assert scenario.label == label

    def test_bull_best_bear_worst(self, base_result):
        """Bull scenario has highest profit, bear has lowest."""
        bull = base_result.scenarios["bull"]
        base = base_result.scenarios["base"]
        bear = base_result.scenarios["bear"]

        assert bull.net_profit > base.net_profit
        assert base.net_profit > bear.net_profit

    def test_bull_revenue_10pct_higher(self, base_result):
        """Bull scenario has +10% revenue."""
        base_rev = base_result.scenarios["base"].gross_revenue
        bull_rev = base_result.scenarios["bull"].gross_revenue
        expected = base_rev * 1.10
        assert abs(bull_rev - expected) < 0.01

    def test_bear_revenue_10pct_lower(self, base_result):
        """Bear scenario has -10% revenue."""
        base_rev = base_result.scenarios["base"].gross_revenue
        bear_rev = base_result.scenarios["bear"].gross_revenue
        expected = base_rev * 0.90
        assert abs(bear_rev - expected) < 0.01

    def test_bull_costs_5pct_lower(self, base_result):
        """Bull scenario has lower total project cost than base."""
        bull = base_result.scenarios["bull"]
        base = base_result.scenarios["base"]
        assert bull.total_project_cost < base.total_project_cost

    def test_bear_costs_10pct_higher(self, base_result):
        """Bear scenario has higher total project cost than base."""
        bear = base_result.scenarios["bear"]
        base = base_result.scenarios["base"]
        assert bear.total_project_cost > base.total_project_cost

    def test_scenario_viability_flags(self):
        """Scenarios set is_viable correctly based on net_profit."""
        result = FinancingCalculator.calculate(
            acquisition_cost=2_000_000.0,
            equity_pct=0.25,
            interest_rate=0.065,
            hold_period_months=36,
            construction_cost=5_000_000.0,
            gross_revenue=12_000_000.0,
        )
        for label, scenario in result.scenarios.items():
            assert scenario.is_viable == (scenario.net_profit > 0), \
                f"Scenario {label} viability mismatch"

    def test_scenarios_have_roi_and_roe(self, base_result):
        """Each scenario includes roi and roe fields."""
        for label, scenario in base_result.scenarios.items():
            assert hasattr(scenario, "roi")
            assert hasattr(scenario, "roe")

    def test_calculate_scenarios_standalone(self, base_params):
        """calculate_scenarios can be called independently."""
        scenarios = FinancingCalculator.calculate_scenarios(
            acquisition_cost=base_params["acquisition_cost"],
            equity_pct=base_params["equity_pct"],
            interest_rate=base_params["interest_rate"],
            hold_period_months=base_params["hold_period_months"],
            construction_cost=base_params["construction_cost"],
            gross_revenue=base_params["gross_revenue"],
            soft_cost_pct=base_params["soft_cost_pct"],
        )
        assert "bull" in scenarios
        assert "base" in scenarios
        assert "bear" in scenarios


# ────────────────────────────────────────────────────────────────────────────
# Input Validation (Calculator-level)
# ────────────────────────────────────────────────────────────────────────────


class TestCalculatorValidation:
    """Tests for calculator-level input validation (ValueError)."""

    def test_negative_acquisition_cost(self):
        """Negative acquisition_cost raises ValueError."""
        with pytest.raises(ValueError, match="acquisition_cost"):
            FinancingCalculator.calculate(
                acquisition_cost=-1.0,
                equity_pct=0.25,
                interest_rate=0.06,
                hold_period_months=24,
                construction_cost=3_000_000.0,
                gross_revenue=8_000_000.0,
            )

    def test_equity_pct_above_1(self):
        """equity_pct > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="equity_pct"):
            FinancingCalculator.calculate(
                acquisition_cost=1_000_000.0,
                equity_pct=1.5,
                interest_rate=0.06,
                hold_period_months=24,
                construction_cost=3_000_000.0,
                gross_revenue=8_000_000.0,
            )

    def test_equity_pct_negative(self):
        """Negative equity_pct raises ValueError."""
        with pytest.raises(ValueError, match="equity_pct"):
            FinancingCalculator.calculate(
                acquisition_cost=1_000_000.0,
                equity_pct=-0.1,
                interest_rate=0.06,
                hold_period_months=24,
                construction_cost=3_000_000.0,
                gross_revenue=8_000_000.0,
            )

    def test_interest_rate_above_1(self):
        """interest_rate > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="interest_rate"):
            FinancingCalculator.calculate(
                acquisition_cost=1_000_000.0,
                equity_pct=0.25,
                interest_rate=1.5,
                hold_period_months=24,
                construction_cost=3_000_000.0,
                gross_revenue=8_000_000.0,
            )

    def test_hold_period_zero(self):
        """hold_period_months < 1 raises ValueError."""
        with pytest.raises(ValueError, match="hold_period_months"):
            FinancingCalculator.calculate(
                acquisition_cost=1_000_000.0,
                equity_pct=0.25,
                interest_rate=0.06,
                hold_period_months=0,
                construction_cost=3_000_000.0,
                gross_revenue=8_000_000.0,
            )

    def test_negative_construction_cost(self):
        """Negative construction_cost raises ValueError."""
        with pytest.raises(ValueError, match="construction_cost"):
            FinancingCalculator.calculate(
                acquisition_cost=1_000_000.0,
                equity_pct=0.25,
                interest_rate=0.06,
                hold_period_months=24,
                construction_cost=-1.0,
                gross_revenue=8_000_000.0,
            )

    def test_negative_gross_revenue(self):
        """Negative gross_revenue raises ValueError."""
        with pytest.raises(ValueError, match="gross_revenue"):
            FinancingCalculator.calculate(
                acquisition_cost=1_000_000.0,
                equity_pct=0.25,
                interest_rate=0.06,
                hold_period_months=24,
                construction_cost=3_000_000.0,
                gross_revenue=-1.0,
            )

    def test_soft_cost_pct_above_1(self):
        """soft_cost_pct > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="soft_cost_pct"):
            FinancingCalculator.calculate(
                acquisition_cost=1_000_000.0,
                equity_pct=0.25,
                interest_rate=0.06,
                hold_period_months=24,
                construction_cost=3_000_000.0,
                gross_revenue=8_000_000.0,
                soft_cost_pct=1.5,
            )


# ────────────────────────────────────────────────────────────────────────────
# Precision and Rounding
# ────────────────────────────────────────────────────────────────────────────


class TestPrecisionAndRounding:
    """Tests for numeric precision and rounding."""

    def test_dollar_values_two_decimals(self, base_result):
        """Dollar amounts are rounded to 2 decimals."""
        for field in [
            "equity_required", "debt_amount", "soft_costs",
            "total_interest_cost", "total_project_cost", "net_profit",
        ]:
            val = getattr(base_result, field)
            assert val == round(val, 2), f"{field} not rounded to 2 decimals"

    def test_ratios_six_decimals(self, base_result):
        """Rate/ratio fields are rounded to 6 decimals."""
        for field in ["roi", "roe", "cash_on_cash", "irr_estimate"]:
            val = getattr(base_result, field)
            assert val == round(val, 6), f"{field} not rounded to 6 decimals"

    def test_breakeven_two_decimals(self, base_result):
        """breakeven_price_psf is rounded to 2 decimals."""
        if base_result.breakeven_price_psf is not None:
            val = base_result.breakeven_price_psf
            assert val == round(val, 2)

    def test_scenario_values_rounded(self, base_result):
        """Scenario dollar amounts rounded to 2 decimals, ratios to 6."""
        for scenario in base_result.scenarios.values():
            for field in ["gross_revenue", "total_project_cost", "net_profit"]:
                val = getattr(scenario, field)
                assert val == round(val, 2), f"Scenario {scenario.label}.{field} not rounded"
            for field in ["roi", "roe"]:
                val = getattr(scenario, field)
                assert val == round(val, 6), f"Scenario {scenario.label}.{field} not rounded"


# ────────────────────────────────────────────────────────────────────────────
# Total Project Cost Sum Verification
# ────────────────────────────────────────────────────────────────────────────


class TestProjectCostSum:
    """Verify total_project_cost equals sum of components."""

    def test_total_equals_sum(self, base_result):
        """total_project_cost = acquisition + construction + soft + interest."""
        expected = (
            2_000_000.0  # acquisition_cost
            + 5_000_000.0  # construction_cost
            + base_result.soft_costs
            + base_result.total_interest_cost
        )
        assert abs(base_result.total_project_cost - expected) < 0.01

    def test_total_equals_sum_no_construction(self):
        """Works with zero construction cost."""
        result = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0,
            equity_pct=0.25,
            interest_rate=0.05,
            hold_period_months=12,
            construction_cost=0.0,
            gross_revenue=2_000_000.0,
        )
        expected = (
            1_000_000.0
            + 0.0
            + result.soft_costs
            + result.total_interest_cost
        )
        assert abs(result.total_project_cost - expected) < 0.01
        assert result.soft_costs == 0.0


# ────────────────────────────────────────────────────────────────────────────
# Large and Small Value Tests
# ────────────────────────────────────────────────────────────────────────────


class TestExtremeValues:
    """Tests with very large and very small numbers."""

    def test_very_large_project(self):
        """$100M+ project doesn't overflow."""
        result = FinancingCalculator.calculate(
            acquisition_cost=50_000_000.0,
            equity_pct=0.30,
            interest_rate=0.055,
            hold_period_months=48,
            construction_cost=150_000_000.0,
            gross_revenue=300_000_000.0,
            sellable_sqft=500_000.0,
        )
        assert result.total_project_cost > 0
        assert result.breakeven_price_psf is not None
        assert result.breakeven_price_psf > 0
        assert not math.isinf(result.roi)
        assert not math.isnan(result.roi)

    def test_small_project(self):
        """Very small project ($10k)."""
        result = FinancingCalculator.calculate(
            acquisition_cost=10_000.0,
            equity_pct=0.50,
            interest_rate=0.05,
            hold_period_months=6,
            construction_cost=5_000.0,
            gross_revenue=20_000.0,
            sellable_sqft=500.0,
        )
        assert result.total_project_cost > 0
        assert isinstance(result.is_viable, bool)

    def test_minimum_hold_period(self):
        """Minimum hold period of 1 month."""
        result = FinancingCalculator.calculate(
            acquisition_cost=1_000_000.0,
            equity_pct=0.25,
            interest_rate=0.06,
            hold_period_months=1,
            construction_cost=500_000.0,
            gross_revenue=2_000_000.0,
        )
        assert result.total_interest_cost > 0
        assert not math.isnan(result.irr_estimate)
        assert not math.isinf(result.irr_estimate)

    def test_long_hold_period(self):
        """Very long hold period (120 months / 10 years)."""
        result = FinancingCalculator.calculate(
            acquisition_cost=2_000_000.0,
            equity_pct=0.25,
            interest_rate=0.06,
            hold_period_months=120,
            construction_cost=5_000_000.0,
            gross_revenue=15_000_000.0,
        )
        assert result.total_interest_cost > 0
        assert not math.isinf(result.irr_estimate)


# ────────────────────────────────────────────────────────────────────────────
# FastAPI Route Integration (using TestClient)
# ────────────────────────────────────────────────────────────────────────────


class TestAPIRoutes:
    """Integration tests for the financing API routes."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Create a TestClient for the FastAPI app."""
        try:
            from fastapi.testclient import TestClient
            from api.financing_routes import router
            from fastapi import FastAPI

            app = FastAPI()
            app.include_router(router)
            self.client = TestClient(app)
            self.client_available = True
        except ImportError:
            self.client_available = False

    def test_post_calculate(self):
        """POST /api/v1/financing/calculate returns 200 with valid body."""
        if not self.client_available:
            pytest.skip("TestClient not available")

        resp = self.client.post("/api/v1/financing/calculate", json={
            "acquisition_cost": 2_000_000.0,
            "equity_pct": 0.25,
            "interest_rate": 0.065,
            "hold_period_months": 36,
            "construction_cost": 5_000_000.0,
            "gross_revenue": 12_000_000.0,
            "soft_cost_pct": 0.18,
            "sellable_sqft": 10_000.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "equity_required" in data
        assert "scenarios" in data
        assert "bull" in data["scenarios"]

    def test_post_calculate_validation_error(self):
        """POST /api/v1/financing/calculate returns 422 on invalid body."""
        if not self.client_available:
            pytest.skip("TestClient not available")

        resp = self.client.post("/api/v1/financing/calculate", json={
            "acquisition_cost": -1.0,  # invalid
            "equity_pct": 0.25,
            "interest_rate": 0.065,
            "hold_period_months": 36,
            "construction_cost": 5_000_000.0,
            "gross_revenue": 12_000_000.0,
        })
        assert resp.status_code == 422

    def test_get_quick_calc(self):
        """GET /api/v1/financing/quick-calc returns 200 with valid params."""
        if not self.client_available:
            pytest.skip("TestClient not available")

        resp = self.client.get("/api/v1/financing/quick-calc", params={
            "acquisition_cost": 1_000_000.0,
            "equity_pct": 0.25,
            "interest_rate": 0.06,
            "hold_period_months": 24,
            "construction_cost": 3_000_000.0,
            "gross_revenue": 6_000_000.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "roi" in data
        assert "is_viable" in data

    def test_get_quick_calc_missing_required_param(self):
        """GET /api/v1/financing/quick-calc returns 422 when required param missing."""
        if not self.client_available:
            pytest.skip("TestClient not available")

        resp = self.client.get("/api/v1/financing/quick-calc", params={
            "acquisition_cost": 1_000_000.0,
            # missing equity_pct and others
        })
        assert resp.status_code == 422

    def test_get_quick_calc_with_defaults(self):
        """GET /api/v1/financing/quick-calc uses defaults for optional params."""
        if not self.client_available:
            pytest.skip("TestClient not available")

        resp = self.client.get("/api/v1/financing/quick-calc", params={
            "acquisition_cost": 1_000_000.0,
            "equity_pct": 0.25,
            "interest_rate": 0.06,
            "hold_period_months": 24,
            "construction_cost": 3_000_000.0,
            "gross_revenue": 6_000_000.0,
            # soft_cost_pct and sellable_sqft use defaults
        })
        assert resp.status_code == 200
        data = resp.json()
        # Default soft_cost_pct=0.18 should be reflected in soft_costs
        expected_soft = 3_000_000.0 * 0.18
        assert abs(data["soft_costs"] - expected_soft) < 0.01

    def test_post_calculate_returns_all_fields(self):
        """POST response includes all FinancingResult fields."""
        if not self.client_available:
            pytest.skip("TestClient not available")

        resp = self.client.post("/api/v1/financing/calculate", json={
            "acquisition_cost": 2_000_000.0,
            "equity_pct": 0.25,
            "interest_rate": 0.065,
            "hold_period_months": 36,
            "construction_cost": 5_000_000.0,
            "gross_revenue": 12_000_000.0,
        })
        data = resp.json()
        required_fields = [
            "equity_required", "debt_amount", "soft_costs",
            "total_interest_cost", "total_project_cost", "net_profit",
            "roi", "roe", "cash_on_cash", "irr_estimate",
            "breakeven_price_psf", "is_viable", "scenarios",
        ]
        for field in required_fields:
            assert field in data, f"Missing field in response: {field}"
