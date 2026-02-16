"""
VanCity Lens — Bill 44 Small-Scale Multi-Unit Housing (SSMUH) Engine
FR-HBU-004: Determine Bill 44 multiplex entitlement for eligible parcels.

Bill 44 (Housing Statutes Amendment Act, 2023) requires BC municipalities to
allow small-scale multi-unit housing on single-family and duplex-zoned lots.

Vancouver's implementation (effective June 2024):
- Lots <280 sqm: up to 3 units
- Lots 280–560 sqm: up to 4 units
- Lots >560 sqm: up to 6 units
- Near frequent transit (800m): secondary suite not counted toward unit cap
- Heritage lots may have additional constraints
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

# ── Bill 44 unit thresholds (Vancouver implementation) ──────────

_SMALL_LOT_THRESHOLD_SQM = Decimal("280")
_MEDIUM_LOT_THRESHOLD_SQM = Decimal("560")

_SMALL_LOT_MAX_UNITS = 3
_MEDIUM_LOT_MAX_UNITS = 4
_LARGE_LOT_MAX_UNITS = 6

# Transit proximity bonus: within 800m of frequent transit
_TRANSIT_BONUS_RADIUS_M = 800
_TRANSIT_BONUS_UNITS = 1  # secondary suite doesn't count toward cap


# ── Models ──────────────────────────────────────────────────────

class Bill44Result(BaseModel):
    """Result of Bill 44 small-scale multi-unit housing analysis."""
    is_eligible: bool = Field(..., description="Whether the parcel's zoning is eligible for Bill 44")
    zone_category: Optional[str] = Field(None, description="'single_family', 'duplex', or None")
    max_units: int = Field(0, description="Maximum units allowed under Bill 44")
    lot_size_category: Optional[str] = Field(None, description="'small', 'medium', or 'large'")
    transit_bonus: bool = Field(False, description="True if near frequent transit (extra unit)")
    transit_bonus_units: int = Field(0, description="Additional units from transit proximity")
    effective_max_units: int = Field(0, description="max_units + transit_bonus_units")
    current_zoning: Optional[str] = Field(None, description="Current zoning district")
    notes: Optional[str] = Field(None, description="Explanatory notes")


# ── SQL Queries ─────────────────────────────────────────────────

SQL_CHECK_ELIGIBLE = """
    SELECT zoning_district, zone_category, is_eligible, notes
    FROM bill44_eligible_zones
    WHERE zoning_district = $1
"""

SQL_NEAREST_TRANSIT_DISTANCE = """
    SELECT MIN(
        ST_Distance(
            p.geom::geography,
            ts.geom::geography
        )
    ) AS min_distance_m
    FROM parcels p
    CROSS JOIN transit_stations ts
    WHERE p.pid = $1
"""


# ── Engine ──────────────────────────────────────────────────────

def _determine_lot_category(lot_area_sqm: Decimal) -> tuple[str, int]:
    """Determine lot size category and base max units."""
    if lot_area_sqm < _SMALL_LOT_THRESHOLD_SQM:
        return "small", _SMALL_LOT_MAX_UNITS
    elif lot_area_sqm < _MEDIUM_LOT_THRESHOLD_SQM:
        return "medium", _MEDIUM_LOT_MAX_UNITS
    else:
        return "large", _LARGE_LOT_MAX_UNITS


async def compute_bill44(
    conn,
    pid: str,
    current_zoning: Optional[str],
    lot_area_sqm: Optional[Decimal],
) -> Bill44Result:
    """
    Compute Bill 44 small-scale multi-unit housing entitlement.

    Steps:
    1. Check if current zoning is eligible for Bill 44
    2. Determine lot size category → base unit count
    3. Check transit proximity → bonus unit
    """
    if not current_zoning or not lot_area_sqm:
        return Bill44Result(
            is_eligible=False,
            current_zoning=current_zoning,
            notes="Missing zoning or lot area data",
        )

    # 1. Check eligibility
    eligibility = await conn.fetchrow(SQL_CHECK_ELIGIBLE, current_zoning)

    if not eligibility or not eligibility["is_eligible"]:
        return Bill44Result(
            is_eligible=False,
            current_zoning=current_zoning,
            notes=f"Zoning {current_zoning} is not eligible for Bill 44 SSMUH",
        )

    zone_category = eligibility["zone_category"]

    # 2. Determine lot category and base units
    lot_category, base_units = _determine_lot_category(Decimal(str(lot_area_sqm)))

    # 3. Check transit proximity
    transit_row = await conn.fetchrow(SQL_NEAREST_TRANSIT_DISTANCE, pid)
    transit_bonus = False
    bonus_units = 0
    if transit_row and transit_row["min_distance_m"] is not None:
        distance = Decimal(str(transit_row["min_distance_m"]))
        if distance <= _TRANSIT_BONUS_RADIUS_M:
            transit_bonus = True
            bonus_units = _TRANSIT_BONUS_UNITS

    effective_max = base_units + bonus_units

    return Bill44Result(
        is_eligible=True,
        zone_category=zone_category,
        max_units=base_units,
        lot_size_category=lot_category,
        transit_bonus=transit_bonus,
        transit_bonus_units=bonus_units,
        effective_max_units=effective_max,
        current_zoning=current_zoning,
        notes=eligibility["notes"],
    )
