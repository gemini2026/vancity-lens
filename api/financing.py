"""
VCL-114 [BIZ-013] Financing Calculator / Deal Modeling Engine
VanCity Lens real estate financing and deal viability analysis.

Provides comprehensive deal modeling for:
- Equity/debt split analysis
- Total project cost modeling (acquisition + construction + soft costs + interest)
- Return metrics: ROI, ROE, Cash-on-Cash, IRR estimate
- Breakeven price per sellable square foot
- Bull / Base / Bear scenario generation
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Models (Request / Response)
# ────────────────────────────────────────────────────────────────────────────


class FinancingRequest(BaseModel):
    """Request payload for financing / deal model calculation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    acquisition_cost: float = Field(
        ..., gt=0, description="Property purchase price in CAD"
    )
    equity_pct: float = Field(
        ..., ge=0.0, le=1.0, description="Equity percentage as decimal (0.25 = 25%)"
    )
    interest_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Annual interest rate as decimal (0.065 = 6.5%)",
    )
    hold_period_months: int = Field(
        ..., ge=1, description="Hold period in months (typically 24-60)"
    )
    construction_cost: float = Field(
        ..., ge=0, description="Total construction (hard) cost estimate in CAD"
    )
    gross_revenue: float = Field(
        ..., ge=0, description="Expected total revenue from sales in CAD"
    )
    soft_cost_pct: float = Field(
        default=0.18,
        ge=0.0,
        le=1.0,
        description="Soft costs as percentage of hard costs (0.18 = 18%)",
    )
    sellable_sqft: float = Field(
        default=0.0,
        ge=0.0,
        description="Total sellable square footage (for breakeven PSF calc)",
    )


class ScenarioResult(BaseModel):
    """Single scenario output (bull / base / bear)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    label: str = Field(description="Scenario label (bull / base / bear)")
    gross_revenue: float
    total_project_cost: float
    net_profit: float
    roi: float
    roe: float
    is_viable: bool


class FinancingResult(BaseModel):
    """Full result of a financing / deal model calculation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    # Capital structure
    equity_required: float = Field(
        description="Equity contribution (acquisition_cost * equity_pct)"
    )
    debt_amount: float = Field(
        description="Debt portion (acquisition_cost * (1 - equity_pct))"
    )

    # Cost breakdown
    soft_costs: float = Field(
        description="Soft costs (construction_cost * soft_cost_pct)"
    )
    total_interest_cost: float = Field(
        description="Total interest over hold period (debt_amount * interest_rate * hold_period_months / 12)"
    )
    total_project_cost: float = Field(
        description="Sum of acquisition + construction + soft costs + interest"
    )

    # Profitability
    net_profit: float = Field(description="gross_revenue - total_project_cost")
    roi: float = Field(
        description="Return on investment (net_profit / total_project_cost)"
    )
    roe: float = Field(description="Return on equity (net_profit / equity_required)")
    cash_on_cash: float = Field(
        description="Cash-on-cash return (net_profit / equity_required)"
    )
    irr_estimate: float = Field(
        description="Simplified annualized return: (1 + roi)^(12/hold_period_months) - 1"
    )

    # Breakeven
    breakeven_price_psf: Optional[float] = Field(
        default=None,
        description="Breakeven price per sellable sqft (total_project_cost / sellable_sqft)",
    )

    # Viability
    is_viable: bool = Field(description="True when net_profit > 0")

    # Scenarios
    scenarios: dict[str, ScenarioResult] = Field(
        description="Bull / base / bear scenario variants"
    )


# ────────────────────────────────────────────────────────────────────────────
# Core Calculator
# ────────────────────────────────────────────────────────────────────────────


class FinancingCalculator:
    """Financing and deal viability calculator for real estate projects."""

    @staticmethod
    def calculate(
        acquisition_cost: float,
        equity_pct: float,
        interest_rate: float,
        hold_period_months: int,
        construction_cost: float,
        gross_revenue: float,
        soft_cost_pct: float = 0.18,
        sellable_sqft: float = 0.0,
    ) -> FinancingResult:
        """
        Run a full financing / deal model calculation.

        Args:
            acquisition_cost: Property purchase price in CAD.
            equity_pct: Equity percentage (0.0 - 1.0).
            interest_rate: Annual interest rate (0.0 - 1.0).
            hold_period_months: Hold period in months (>= 1).
            construction_cost: Total construction (hard) cost.
            gross_revenue: Expected total sales revenue.
            soft_cost_pct: Soft costs as % of hard costs (default 0.18).
            sellable_sqft: Sellable area in sqft (for breakeven PSF).

        Returns:
            FinancingResult with full deal metrics and scenarios.

        Raises:
            ValueError: If inputs violate constraints.
        """
        # ── Input validation ────────────────────────────────────────
        if acquisition_cost <= 0:
            raise ValueError("acquisition_cost must be positive")
        if not (0.0 <= equity_pct <= 1.0):
            raise ValueError("equity_pct must be between 0.0 and 1.0")
        if not (0.0 <= interest_rate <= 1.0):
            raise ValueError("interest_rate must be between 0.0 and 1.0")
        if hold_period_months < 1:
            raise ValueError("hold_period_months must be >= 1")
        if construction_cost < 0:
            raise ValueError("construction_cost must be non-negative")
        if gross_revenue < 0:
            raise ValueError("gross_revenue must be non-negative")
        if not (0.0 <= soft_cost_pct <= 1.0):
            raise ValueError("soft_cost_pct must be between 0.0 and 1.0")

        # ── Capital structure ───────────────────────────────────────
        equity_required = acquisition_cost * equity_pct
        debt_amount = acquisition_cost * (1.0 - equity_pct)

        # ── Cost breakdown ──────────────────────────────────────────
        soft_costs = construction_cost * soft_cost_pct
        total_interest_cost = debt_amount * interest_rate * (hold_period_months / 12.0)
        total_project_cost = (
            acquisition_cost + construction_cost + soft_costs + total_interest_cost
        )

        # ── Profitability ───────────────────────────────────────────
        net_profit = gross_revenue - total_project_cost

        roi = net_profit / total_project_cost if total_project_cost != 0 else 0.0
        roe = net_profit / equity_required if equity_required != 0 else 0.0
        cash_on_cash = roe  # same as ROE for simple model

        # Simplified annualized return (IRR estimate)
        if hold_period_months > 0 and total_project_cost != 0:
            try:
                irr_estimate = (1.0 + roi) ** (12.0 / hold_period_months) - 1.0
            except (OverflowError, ZeroDivisionError):
                irr_estimate = 0.0
        else:
            irr_estimate = 0.0

        # ── Breakeven ───────────────────────────────────────────────
        breakeven_price_psf: Optional[float] = None
        if sellable_sqft > 0:
            breakeven_price_psf = round(total_project_cost / sellable_sqft, 2)

        # ── Viability ───────────────────────────────────────────────
        is_viable = net_profit > 0

        # ── Scenarios ───────────────────────────────────────────────
        scenarios = FinancingCalculator.calculate_scenarios(
            acquisition_cost=acquisition_cost,
            equity_pct=equity_pct,
            interest_rate=interest_rate,
            hold_period_months=hold_period_months,
            construction_cost=construction_cost,
            gross_revenue=gross_revenue,
            soft_cost_pct=soft_cost_pct,
        )

        return FinancingResult(
            equity_required=round(equity_required, 2),
            debt_amount=round(debt_amount, 2),
            soft_costs=round(soft_costs, 2),
            total_interest_cost=round(total_interest_cost, 2),
            total_project_cost=round(total_project_cost, 2),
            net_profit=round(net_profit, 2),
            roi=round(roi, 6),
            roe=round(roe, 6),
            cash_on_cash=round(cash_on_cash, 6),
            irr_estimate=round(irr_estimate, 6),
            breakeven_price_psf=breakeven_price_psf,
            is_viable=is_viable,
            scenarios=scenarios,
        )

    @staticmethod
    def calculate_scenarios(
        acquisition_cost: float,
        equity_pct: float,
        interest_rate: float,
        hold_period_months: int,
        construction_cost: float,
        gross_revenue: float,
        soft_cost_pct: float = 0.18,
    ) -> dict[str, ScenarioResult]:
        """
        Generate bull / base / bear scenario variants.

        - **Bull**: +10% revenue, -5% costs
        - **Base**: as-is
        - **Bear**: -10% revenue, +10% costs

        Returns:
            Dict mapping scenario label to ScenarioResult.
        """
        scenarios: dict[str, ScenarioResult] = {}

        variants = {
            "bull": {"revenue_mult": 1.10, "cost_mult": 0.95},
            "base": {"revenue_mult": 1.00, "cost_mult": 1.00},
            "bear": {"revenue_mult": 0.90, "cost_mult": 1.10},
        }

        equity_required = acquisition_cost * equity_pct
        debt_amount = acquisition_cost * (1.0 - equity_pct)

        for label, mults in variants.items():
            adj_construction = construction_cost * mults["cost_mult"]
            adj_soft = adj_construction * soft_cost_pct
            adj_interest = debt_amount * interest_rate * (hold_period_months / 12.0)
            adj_total_cost = (
                acquisition_cost + adj_construction + adj_soft + adj_interest
            )

            adj_revenue = gross_revenue * mults["revenue_mult"]
            adj_profit = adj_revenue - adj_total_cost
            adj_roi = adj_profit / adj_total_cost if adj_total_cost != 0 else 0.0
            adj_roe = adj_profit / equity_required if equity_required != 0 else 0.0

            scenarios[label] = ScenarioResult(
                label=label,
                gross_revenue=round(adj_revenue, 2),
                total_project_cost=round(adj_total_cost, 2),
                net_profit=round(adj_profit, 2),
                roi=round(adj_roi, 6),
                roe=round(adj_roe, 6),
                is_viable=adj_profit > 0,
            )

        return scenarios
