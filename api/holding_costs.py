"""
VCL-109 [VAL-003] Holding Cost / Time Value of Money Engine
VanCity Lens real estate holding cost and project finance calculations.

Provides comprehensive cost modeling for:
- Holding period costs (property tax, insurance, maintenance, financing)
- Time value of money calculations (NPV, IRR)
- Total project cost summaries with Vancouver-specific defaults
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# ────────────────────────────────────────────────────────────────────────────
# Vancouver Defaults
# ────────────────────────────────────────────────────────────────────────────

VANCOUVER_PROPERTY_TAX_RATE = 0.00278  # 0.278% effective tax rate
VANCOUVER_ANNUAL_INSURANCE = 2400.0    # Per year
VANCOUVER_MONTHLY_MAINTENANCE = 200.0  # Per month


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Models (Request/Response)
# ────────────────────────────────────────────────────────────────────────────


class HoldingCostRequest(BaseModel):
    """Request payload for holding cost calculation."""
    model_config = ConfigDict(str_strip_whitespace=True)

    purchase_price: float = Field(..., gt=0, description="Purchase price in CAD")
    holding_months: int = Field(..., ge=0, description="Holding period in months")
    annual_property_tax_rate: Optional[float] = Field(
        default=VANCOUVER_PROPERTY_TAX_RATE,
        ge=0,
        description="Annual property tax as decimal (0.278% = 0.00278)"
    )
    annual_insurance: Optional[float] = Field(
        default=VANCOUVER_ANNUAL_INSURANCE,
        ge=0,
        description="Annual insurance cost in CAD"
    )
    monthly_maintenance: Optional[float] = Field(
        default=VANCOUVER_MONTHLY_MAINTENANCE,
        ge=0,
        description="Monthly maintenance cost in CAD"
    )
    financing_rate: Optional[float] = Field(
        default=0.06,
        ge=0,
        le=1,
        description="Annual financing rate as decimal (6% = 0.06)"
    )
    ltv_ratio: Optional[float] = Field(
        default=0.75,
        ge=0,
        le=1,
        description="Loan-to-value ratio (0 = all-cash, 1.0 = 100% financed)"
    )


class HoldingCostResult(BaseModel):
    """Holding cost calculation result."""
    model_config = ConfigDict(str_strip_whitespace=True)

    purchase_price: float
    holding_months: int
    property_tax_total: float = Field(description="Total property tax for holding period")
    insurance_total: float = Field(description="Total insurance for holding period")
    maintenance_total: float = Field(description="Total maintenance for holding period")
    financing_cost_total: float = Field(description="Total financing cost (interest)")
    opportunity_cost_total: float = Field(description="Opportunity cost at discount rate")
    total_monthly_average: float = Field(description="Average monthly holding cost")
    total_holding_cost: float = Field(description="Total holding cost for period")


class NPVRequest(BaseModel):
    """Request payload for net present value calculation."""
    model_config = ConfigDict(str_strip_whitespace=True)

    future_value: float = Field(..., description="Cash flow at future time")
    discount_rate: float = Field(
        ...,
        ge=0,
        le=1,
        description="Annual discount rate as decimal (5% = 0.05)"
    )
    years: float = Field(..., gt=0, description="Number of years to discount")


class NPVResult(BaseModel):
    """Net present value result."""
    model_config = ConfigDict(str_strip_whitespace=True)

    future_value: float
    discount_rate: float
    years: float
    present_value: float = Field(description="Discounted present value")


class IRRRequest(BaseModel):
    """Request payload for IRR calculation."""
    model_config = ConfigDict(str_strip_whitespace=True)

    cash_flows: list[float] = Field(
        ...,
        description="Sequence of cash flows (initial investment negative, inflows positive)"
    )


class IRRResult(BaseModel):
    """IRR calculation result."""
    model_config = ConfigDict(str_strip_whitespace=True)

    cash_flows: list[float]
    irr: Optional[float] = Field(
        default=None,
        description="Internal rate of return as decimal (None if no IRR found)"
    )
    converged: bool = Field(
        default=False,
        description="Whether Newton-Raphson converged to solution"
    )


class ProjectCostSummary(BaseModel):
    """Total project cost breakdown."""
    model_config = ConfigDict(str_strip_whitespace=True)

    land_cost: float = Field(description="Land acquisition cost")
    hard_costs: float = Field(description="Construction and build costs")
    soft_costs: float = Field(description="Professional, permitting, financing costs")
    holding_costs: float = Field(description="Costs during holding period")
    financing_costs: float = Field(description="Interest on construction financing")
    total_project_cost: float = Field(description="Sum of all costs")
    cost_per_sqft: Optional[float] = Field(
        default=None,
        description="Cost per square foot (if building_sqft provided)"
    )


# ────────────────────────────────────────────────────────────────────────────
# Core Calculator Class
# ────────────────────────────────────────────────────────────────────────────


class HoldingCostCalculator:
    """Comprehensive holding cost and time value of money calculator."""

    @staticmethod
    def compute_holding_costs(
        purchase_price: float,
        holding_months: int,
        annual_property_tax_rate: float = VANCOUVER_PROPERTY_TAX_RATE,
        annual_insurance: float = VANCOUVER_ANNUAL_INSURANCE,
        monthly_maintenance: float = VANCOUVER_MONTHLY_MAINTENANCE,
        financing_rate: float = 0.06,
        ltv_ratio: float = 0.75,
    ) -> HoldingCostResult:
        """
        Calculate all holding period costs (tax, insurance, maintenance, financing).

        Args:
            purchase_price: Property purchase price in CAD
            holding_months: Number of months held
            annual_property_tax_rate: Property tax as decimal (0.278% = 0.00278)
            annual_insurance: Annual insurance cost in CAD
            monthly_maintenance: Monthly maintenance cost in CAD
            financing_rate: Annual financing rate as decimal
            ltv_ratio: Loan-to-value ratio (0 = cash, 1.0 = 100% financed)

        Returns:
            HoldingCostResult with itemized costs
        """
        # Calculate property tax (monthly)
        monthly_property_tax = (purchase_price * annual_property_tax_rate) / 12.0
        property_tax_total = monthly_property_tax * holding_months

        # Calculate insurance (monthly)
        monthly_insurance = annual_insurance / 12.0
        insurance_total = monthly_insurance * holding_months

        # Calculate maintenance (already monthly)
        maintenance_total = monthly_maintenance * holding_months

        # Calculate financing cost (interest only on borrowed portion)
        loan_amount = purchase_price * ltv_ratio
        monthly_financing_rate = financing_rate / 12.0
        monthly_financing_cost = loan_amount * monthly_financing_rate
        financing_cost_total = monthly_financing_cost * holding_months

        # Opportunity cost (cost of capital not earning elsewhere)
        opportunity_rate = financing_rate  # Use financing rate as opportunity cost proxy
        monthly_opportunity_cost = purchase_price * (opportunity_rate / 12.0)
        opportunity_cost_total = monthly_opportunity_cost * holding_months

        # Total holding costs
        total_holding_cost = (
            property_tax_total +
            insurance_total +
            maintenance_total +
            financing_cost_total +
            opportunity_cost_total
        )

        total_monthly_average = (
            total_holding_cost / holding_months if holding_months > 0 else 0.0
        )

        return HoldingCostResult(
            purchase_price=purchase_price,
            holding_months=holding_months,
            property_tax_total=round(property_tax_total, 2),
            insurance_total=round(insurance_total, 2),
            maintenance_total=round(maintenance_total, 2),
            financing_cost_total=round(financing_cost_total, 2),
            opportunity_cost_total=round(opportunity_cost_total, 2),
            total_monthly_average=round(total_monthly_average, 2),
            total_holding_cost=round(total_holding_cost, 2),
        )

    @staticmethod
    def compute_time_value_adjustment(
        future_value: float,
        discount_rate: float,
        years: float,
    ) -> NPVResult:
        """
        Calculate present value using NPV formula: PV = FV / (1 + r)^n

        Args:
            future_value: Cash flow at future time
            discount_rate: Annual discount rate as decimal (5% = 0.05)
            years: Number of years to discount

        Returns:
            NPVResult with present value
        """
        if discount_rate < 0:
            discount_rate = 0.0

        if years <= 0:
            present_value = future_value
        else:
            denominator = (1.0 + discount_rate) ** years
            present_value = future_value / denominator

        return NPVResult(
            future_value=round(future_value, 2),
            discount_rate=discount_rate,
            years=years,
            present_value=round(present_value, 2),
        )

    @staticmethod
    def compute_irr(
        cash_flows: list[float],
        max_iterations: int = 100,
        tolerance: float = 1e-6,
    ) -> IRRResult:
        """
        Calculate internal rate of return using Newton-Raphson method.

        Newton-Raphson: r_new = r_old - f(r) / f_prime(r)
        where f(r) = sum(cf_t / (1 + r)^t)

        Args:
            cash_flows: Sequence of cash flows (initial negative, inflows positive)
            max_iterations: Maximum Newton-Raphson iterations
            tolerance: Convergence tolerance

        Returns:
            IRRResult with IRR value and convergence status
        """
        if not cash_flows or len(cash_flows) < 2:
            return IRRResult(cash_flows=cash_flows, irr=None, converged=False)

        # Check if any valid cash flows exist
        total_inflows = sum(cf for cf in cash_flows if cf > 0)
        total_outflows = abs(sum(cf for cf in cash_flows if cf < 0))

        if total_inflows == 0 or total_outflows == 0:
            return IRRResult(cash_flows=cash_flows, irr=None, converged=False)

        # Initial guess: 10% (0.10)
        r = 0.10

        for iteration in range(max_iterations):
            # Calculate NPV at current rate
            npv = 0.0
            npv_derivative = 0.0

            for t, cf in enumerate(cash_flows):
                discount_factor = (1.0 + r) ** t
                npv += cf / discount_factor

                # Derivative: d/dr[cf / (1+r)^t] = -t * cf / (1+r)^(t+1)
                if discount_factor != 0:
                    npv_derivative -= t * cf / (discount_factor * (1.0 + r))

            # Newton-Raphson update
            if abs(npv_derivative) < 1e-12:
                # Flat slope, cannot improve
                break

            r_new = r - npv / npv_derivative

            # Check convergence
            if abs(r_new - r) < tolerance:
                r = r_new
                return IRRResult(
                    cash_flows=cash_flows,
                    irr=round(r, 6),
                    converged=True,
                )

            r = r_new

        # Did not converge to tolerance, but return best estimate
        return IRRResult(
            cash_flows=cash_flows,
            irr=round(r, 6),
            converged=False,
        )

    @staticmethod
    def compute_total_project_cost(
        land_cost: float,
        hard_costs: float,
        soft_costs: float,
        holding_months: int,
        financing_rate: float = 0.06,
        building_sqft: Optional[float] = None,
    ) -> ProjectCostSummary:
        """
        Calculate total project cost including holding and financing.

        Args:
            land_cost: Land acquisition cost
            hard_costs: Construction costs
            soft_costs: Professional, permitting costs
            holding_months: Holding period in months
            financing_rate: Construction financing rate
            building_sqft: Building square footage (for cost per sqft)

        Returns:
            ProjectCostSummary with total cost breakdown
        """
        # Calculate holding costs on the full project budget
        total_soft_and_land = land_cost + soft_costs
        holding_calc = HoldingCostCalculator.compute_holding_costs(
            purchase_price=total_soft_and_land,
            holding_months=holding_months,
            financing_rate=financing_rate,
            ltv_ratio=0.75,
        )
        holding_costs = holding_calc.total_holding_cost

        # Financing costs on construction (hard costs)
        monthly_financing_rate = financing_rate / 12.0
        financing_costs = hard_costs * monthly_financing_rate * holding_months

        # Total project cost
        total_project_cost = (
            land_cost +
            hard_costs +
            soft_costs +
            holding_costs +
            financing_costs
        )

        # Cost per sqft (if building size provided)
        cost_per_sqft = None
        if building_sqft and building_sqft > 0:
            cost_per_sqft = total_project_cost / building_sqft

        return ProjectCostSummary(
            land_cost=round(land_cost, 2),
            hard_costs=round(hard_costs, 2),
            soft_costs=round(soft_costs, 2),
            holding_costs=round(holding_costs, 2),
            financing_costs=round(financing_costs, 2),
            total_project_cost=round(total_project_cost, 2),
            cost_per_sqft=round(cost_per_sqft, 2) if cost_per_sqft else None,
        )
