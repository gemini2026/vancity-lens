"""
VCL-114 [BIZ-013] Financing Calculator / Deal Modeling Routes
VanCity Lens API endpoints for financing and deal viability analysis.

Provides:
- POST /api/v1/financing/calculate — Full deal model from request body
- GET  /api/v1/financing/quick-calc — Simplified query-param version for quick estimates
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from .financing import FinancingCalculator, FinancingRequest, FinancingResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/financing", tags=["financing"])


# ────────────────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────────────────


@router.post(
    "/calculate",
    response_model=FinancingResult,
    summary="Run full financing / deal model calculation",
    description=(
        "Accepts a FinancingRequest body and returns a comprehensive "
        "deal model including capital structure, cost breakdown, return "
        "metrics (ROI, ROE, Cash-on-Cash, IRR estimate), breakeven PSF, "
        "viability flag, and bull/base/bear scenarios."
    ),
)
async def calculate_financing(request: FinancingRequest) -> FinancingResult:
    """
    Run a full financing / deal model calculation.

    Args:
        request: FinancingRequest with all deal parameters.

    Returns:
        FinancingResult with complete deal metrics and scenarios.

    Raises:
        422: Validation errors from Pydantic.
        400: Business-logic validation (e.g. negative profit with bad inputs).
    """
    try:
        result = FinancingCalculator.calculate(
            acquisition_cost=request.acquisition_cost,
            equity_pct=request.equity_pct,
            interest_rate=request.interest_rate,
            hold_period_months=request.hold_period_months,
            construction_cost=request.construction_cost,
            gross_revenue=request.gross_revenue,
            soft_cost_pct=request.soft_cost_pct,
            sellable_sqft=request.sellable_sqft,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Financing calculation error: {e}")
        raise HTTPException(status_code=500, detail="Internal calculation error")


@router.get(
    "/quick-calc",
    response_model=FinancingResult,
    summary="Quick financing estimate via query parameters",
    description=(
        "Simplified query-parameter version of the financing calculator "
        "for quick browser / cURL estimates. Uses sensible defaults for "
        "soft_cost_pct (18%) and sellable_sqft (0)."
    ),
)
async def quick_calc(
    acquisition_cost: float = Query(..., gt=0, description="Purchase price in CAD"),
    equity_pct: float = Query(..., ge=0.0, le=1.0, description="Equity % as decimal (0.25 = 25%)"),
    interest_rate: float = Query(..., ge=0.0, le=1.0, description="Annual rate as decimal (0.065 = 6.5%)"),
    hold_period_months: int = Query(..., ge=1, description="Hold period in months"),
    construction_cost: float = Query(..., ge=0, description="Construction cost in CAD"),
    gross_revenue: float = Query(..., ge=0, description="Expected total revenue in CAD"),
    soft_cost_pct: float = Query(0.18, ge=0.0, le=1.0, description="Soft costs as % of hard costs"),
    sellable_sqft: float = Query(0.0, ge=0.0, description="Sellable sqft for breakeven PSF"),
) -> FinancingResult:
    """
    Quick financing estimate using query parameters.

    Convenient for browser / cURL usage without JSON body.
    All core parameters are required; soft_cost_pct and sellable_sqft
    use defaults if omitted.

    Returns:
        FinancingResult with complete deal metrics and scenarios.

    Raises:
        422: Validation errors from FastAPI/Pydantic.
        400: Business-logic validation errors.
    """
    try:
        result = FinancingCalculator.calculate(
            acquisition_cost=acquisition_cost,
            equity_pct=equity_pct,
            interest_rate=interest_rate,
            hold_period_months=hold_period_months,
            construction_cost=construction_cost,
            gross_revenue=gross_revenue,
            soft_cost_pct=soft_cost_pct,
            sellable_sqft=sellable_sqft,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Quick financing calculation error: {e}")
        raise HTTPException(status_code=500, detail="Internal calculation error")
