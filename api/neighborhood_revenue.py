"""
VanCity Lens — Neighborhood Revenue Adjustment for Entitlement Valuation
Implements property-type-specific revenue per square foot by Vancouver neighborhood.
Database-backed with hardcoded fallback for resilience.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import asyncpg
from pydantic import BaseModel, Field


NEIGHBORHOOD_ADJUSTMENT_FACTORS: dict[str, float] = {
    "Downtown": 1.35,
    "Coal Harbour": 1.35,
    "Kitsilano": 1.25,
    "West Point Grey": 1.25,
    "West End": 1.25,
    "Kerrisdale": 1.20,
    "Shaughnessy": 1.20,
    "Dunbar-Southlands": 1.20,
    "Arbutus-Ridge": 1.15,
    "South Cambie": 1.15,
    "Mount Pleasant": 1.15,
    "Fairview": 1.15,
    "Riley Park": 1.10,
    "Cambie": 1.10,
    "Oakridge": 1.10,
    "Grandview-Woodland": 1.00,
    "Marpole": 0.95,
    "Hastings-Sunrise": 0.95,
    "Strathcona": 0.95,
    "Kensington-Cedar Cottage": 0.95,
    "Musqueam": 0.95,
    "Renfrew-Collingwood": 0.85,
    "Killarney": 0.85,
    "Victoria-Fraserview": 0.85,
    "Sunset": 0.85,
    "Knight": 0.85,
    "South Vancouver": 0.75,
}

REVENUE_PSF_BY_NEIGHBORHOOD: dict[str, dict[str, float]] = {
    "Downtown": {
        "condo": 1400,
        "rental": 55,
        "commercial": 45,
        "townhouse": 900,
    },
    "Coal Harbour": {
        "condo": 1350,
        "rental": 52,
        "commercial": 42,
        "townhouse": 880,
    },
    "Kitsilano": {
        "condo": 1200,
        "rental": 48,
        "commercial": 38,
        "townhouse": 820,
    },
    "West Point Grey": {
        "condo": 1180,
        "rental": 47,
        "commercial": 37,
        "townhouse": 810,
    },
    "West End": {
        "condo": 1150,
        "rental": 45,
        "commercial": 35,
        "townhouse": 790,
    },
    "Kerrisdale": {
        "condo": 1050,
        "rental": 42,
        "commercial": 32,
        "townhouse": 720,
    },
    "Shaughnessy": {
        "condo": 1100,
        "rental": 44,
        "commercial": 34,
        "townhouse": 750,
    },
    "Dunbar-Southlands": {
        "condo": 1080,
        "rental": 43,
        "commercial": 33,
        "townhouse": 740,
    },
    "Arbutus-Ridge": {
        "condo": 950,
        "rental": 38,
        "commercial": 29,
        "townhouse": 650,
    },
    "South Cambie": {
        "condo": 920,
        "rental": 37,
        "commercial": 28,
        "townhouse": 630,
    },
    "Mount Pleasant": {
        "condo": 900,
        "rental": 36,
        "commercial": 27,
        "townhouse": 620,
    },
    "Fairview": {
        "condo": 880,
        "rental": 35,
        "commercial": 26,
        "townhouse": 610,
    },
    "Riley Park": {
        "condo": 800,
        "rental": 32,
        "commercial": 24,
        "townhouse": 550,
    },
    "Cambie": {
        "condo": 820,
        "rental": 33,
        "commercial": 25,
        "townhouse": 560,
    },
    "Oakridge": {
        "condo": 810,
        "rental": 32,
        "commercial": 24,
        "townhouse": 555,
    },
    "Grandview-Woodland": {
        "condo": 750,
        "rental": 30,
        "commercial": 22,
        "townhouse": 515,
    },
    "Marpole": {
        "condo": 720,
        "rental": 29,
        "commercial": 21,
        "townhouse": 495,
    },
    "Hastings-Sunrise": {
        "condo": 680,
        "rental": 27,
        "commercial": 20,
        "townhouse": 470,
    },
    "Strathcona": {
        "condo": 700,
        "rental": 28,
        "commercial": 21,
        "townhouse": 480,
    },
    "Kensington-Cedar Cottage": {
        "condo": 690,
        "rental": 28,
        "commercial": 20,
        "townhouse": 475,
    },
    "Musqueam": {
        "condo": 710,
        "rental": 28,
        "commercial": 21,
        "townhouse": 485,
    },
    "Renfrew-Collingwood": {
        "condo": 650,
        "rental": 26,
        "commercial": 19,
        "townhouse": 450,
    },
    "Killarney": {
        "condo": 640,
        "rental": 25,
        "commercial": 19,
        "townhouse": 440,
    },
    "Victoria-Fraserview": {
        "condo": 630,
        "rental": 25,
        "commercial": 18,
        "townhouse": 435,
    },
    "Sunset": {
        "condo": 620,
        "rental": 25,
        "commercial": 18,
        "townhouse": 430,
    },
    "Knight": {
        "condo": 610,
        "rental": 24,
        "commercial": 18,
        "townhouse": 425,
    },
    "South Vancouver": {
        "condo": 580,
        "rental": 23,
        "commercial": 17,
        "townhouse": 400,
    },
}

DEFAULT_PSF: dict[str, float] = {
    "condo": 750,
    "rental": 30,
    "commercial": 22,
    "townhouse": 515,
}

DEFAULT_ADJUSTMENT_FACTOR = 1.0
MIN_ADJUSTMENT_FACTOR = 0.7
MAX_ADJUSTMENT_FACTOR = 1.5


class RevenueFactorResponse(BaseModel):
    """Revenue data for a single neighborhood."""

    neighborhood: str
    adjustment_factor: float = Field(..., ge=0.7, le=1.5)
    condo_psf: float = Field(..., ge=580, le=1800)
    rental_psf: float = Field(..., ge=20, le=70)
    commercial_psf: float = Field(..., ge=15, le=50)
    townhouse_psf: float = Field(..., ge=400, le=1200)


class RevenueMapResponse(BaseModel):
    """All neighborhoods with revenue data."""

    neighborhoods: list[RevenueFactorResponse]
    total_neighborhoods: int


RevenueMapResponse.model_rebuild()


class NeighborhoodRevenueAdjuster:
    """
    Computes neighborhood-level revenue adjustments for Bill 47 entitlement valuation.
    """

    def __init__(self, pool: asyncpg.Pool | None = None):
        self.pool = pool

    async def get_adjustment_factor(self, neighborhood: str) -> float:
        """
        Get revenue adjustment multiplier for a neighborhood.
        Range: 0.7 to 1.5. Default: 1.0.
        """
        normalized = self._normalize_neighborhood(neighborhood)

        if not normalized:
            return DEFAULT_ADJUSTMENT_FACTOR

        if self.pool:
            try:
                row = await self.pool.fetchrow(
                    """
                    SELECT adjustment_factor
                    FROM neighborhood_revenue_factors
                    WHERE LOWER(neighborhood) = LOWER($1)
                    LIMIT 1
                    """,
                    normalized,
                )
                if row:
                    factor = float(row["adjustment_factor"])
                    return max(
                        MIN_ADJUSTMENT_FACTOR,
                        min(MAX_ADJUSTMENT_FACTOR, factor),
                    )
            except Exception:
                pass

        factor = NEIGHBORHOOD_ADJUSTMENT_FACTORS.get(
            normalized, DEFAULT_ADJUSTMENT_FACTOR
        )
        return max(
            MIN_ADJUSTMENT_FACTOR,
            min(MAX_ADJUSTMENT_FACTOR, factor),
        )

    async def get_revenue_per_sqft(self, neighborhood: str) -> dict[str, float]:
        """
        Get property-type-specific revenue per square foot.
        Returns {condo, rental, commercial, townhouse} in dollars/sqft.
        """
        normalized = self._normalize_neighborhood(neighborhood)

        if not normalized:
            return DEFAULT_PSF.copy()

        if self.pool:
            try:
                rows = await self.pool.fetch(
                    """
                    SELECT property_type, psf
                    FROM neighborhood_revenue_factors
                    WHERE LOWER(neighborhood) = LOWER($1)
                    """,
                    normalized,
                )
                if rows:
                    result = {}
                    for row in rows:
                        result[row["property_type"]] = float(row["psf"])
                    if len(result) == 4:
                        return result
            except Exception:
                pass

        return REVENUE_PSF_BY_NEIGHBORHOOD.get(
            normalized, DEFAULT_PSF
        ).copy()

    async def compute_adjusted_revenue(
        self, base_revenue: float, neighborhood: str
    ) -> float:
        """
        Compute adjusted revenue: base_revenue * adjustment_factor.
        """
        if base_revenue < 0:
            return 0.0

        factor = await self.get_adjustment_factor(neighborhood)
        return base_revenue * factor

    def _normalize_neighborhood(self, neighborhood: str) -> str:
        """Normalize neighborhood name for lookup."""
        if not neighborhood:
            return ""

        trimmed = neighborhood.strip()
        if not trimmed:
            return ""

        return trimmed
