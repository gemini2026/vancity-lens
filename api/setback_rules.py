"""
Setback & Site Coverage Calculation Engine (FR-HBU-008).

Computes:
- Front, rear, side setback distances based on zoning district
- Site coverage (max building footprint as % of lot area)
- Net developable area (lot area minus setbacks)
- Gross buildable area (net area × FSR)
"""

from decimal import Decimal
from typing import Optional

import asyncpg
from pydantic import BaseModel, Field


class SetbackResult(BaseModel):
    """Setback and site coverage analysis for a parcel."""
    zoning_district: str
    # Setback distances (metres)
    front_setback_m: Decimal
    rear_setback_m: Decimal
    side_setback_m: Decimal
    # Site coverage
    max_site_coverage: Decimal = Field(description="Max building footprint / lot area (0-1)")
    max_footprint_sqm: Optional[Decimal] = Field(None, description="Max building footprint in sqm")
    # Derived areas
    lot_area_sqm: Decimal
    net_site_area_sqm: Optional[Decimal] = Field(
        None, description="Lot area after setbacks subtracted (approximate)"
    )
    # Whether this is from a known zoning rule or defaults
    is_default: bool = Field(
        default=False, description="True if using default setbacks (zoning not in rules table)"
    )


# Default setbacks when zoning district not found in rules table
_DEFAULT_FRONT = Decimal("6.0")
_DEFAULT_REAR = Decimal("7.5")
_DEFAULT_SIDE = Decimal("1.2")
_DEFAULT_COVERAGE = Decimal("0.45")

SQL_GET_SETBACK_RULES = """
    SELECT front_setback_m, rear_setback_m, side_setback_m, max_site_coverage
    FROM zoning_setback_rules
    WHERE zoning_district = $1
"""

# Approximate net site area using a rectangular lot model:
# For a lot with width W and depth D (area = W × D):
#   net_width  = W - 2 × side_setback
#   net_depth  = D - front_setback - rear_setback
#   net_area   = net_width × net_depth
#
# We don't know W and D separately, so we estimate using a typical
# lot aspect ratio (width:depth ≈ 1:2.5 for Vancouver residential lots).
_TYPICAL_ASPECT_RATIO = Decimal("2.5")  # depth = 2.5 × width


def _estimate_net_area(
    lot_area_sqm: Decimal,
    front: Decimal,
    rear: Decimal,
    side: Decimal,
) -> Decimal:
    """Estimate net developable area after setbacks using rectangular lot model."""
    if lot_area_sqm <= 0:
        return Decimal("0")

    # Estimate width from area and aspect ratio: area = W × (2.5W) = 2.5W²
    import math
    w_sq = float(lot_area_sqm) / float(_TYPICAL_ASPECT_RATIO)
    width = Decimal(str(math.sqrt(w_sq)))
    depth = width * _TYPICAL_ASPECT_RATIO

    net_width = max(Decimal("0"), width - 2 * side)
    net_depth = max(Decimal("0"), depth - front - rear)
    return (net_width * net_depth).quantize(Decimal("0.01"))


async def compute_setbacks(
    conn: asyncpg.Connection,
    zoning_district: Optional[str],
    lot_area_sqm: Optional[Decimal],
) -> Optional[SetbackResult]:
    """
    Compute setback distances and site coverage for a given zoning district.

    Returns None if lot_area_sqm is missing.
    Falls back to defaults if zoning is unknown.
    """
    if not lot_area_sqm or lot_area_sqm <= 0:
        return None

    is_default = False
    front = _DEFAULT_FRONT
    rear = _DEFAULT_REAR
    side = _DEFAULT_SIDE
    coverage = _DEFAULT_COVERAGE

    if zoning_district:
        row = await conn.fetchrow(SQL_GET_SETBACK_RULES, zoning_district)
        if row:
            front = Decimal(str(row["front_setback_m"]))
            rear = Decimal(str(row["rear_setback_m"]))
            side = Decimal(str(row["side_setback_m"]))
            coverage = Decimal(str(row["max_site_coverage"]))
        else:
            is_default = True
    else:
        is_default = True

    net_area = _estimate_net_area(lot_area_sqm, front, rear, side)
    max_footprint = (lot_area_sqm * coverage).quantize(Decimal("0.01"))

    return SetbackResult(
        zoning_district=zoning_district or "unknown",
        front_setback_m=front,
        rear_setback_m=rear,
        side_setback_m=side,
        max_site_coverage=coverage,
        max_footprint_sqm=max_footprint,
        lot_area_sqm=lot_area_sqm,
        net_site_area_sqm=net_area,
        is_default=is_default,
    )
