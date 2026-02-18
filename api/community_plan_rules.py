"""
VanCity Lens — Community Plan Density Bonus Engine
FR-HBU-005: Apply community-plan-specific density overrides.

Vancouver has adopted community plans that provide density bonuses beyond
both base zoning and Bill 47 TOD entitlements. When a community plan bonus
applies, the parcel gets the GREATER of:
  - Bill 47 TOD entitlement
  - Community plan bonus
  - Current zoning

This module queries structured community plan rules from the database
and returns applicable bonuses for a given parcel's zoning district.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ── Models ──────────────────────────────────────────────────────


class CommunityPlanBonus(BaseModel):
    """A single community plan density bonus applicable to a parcel."""

    plan_name: str
    plan_area: str
    bonus_fsr: Optional[Decimal] = Field(None, description="Additional FSR above base")
    bonus_storeys: Optional[int] = Field(
        None, description="Additional storeys above base"
    )
    max_fsr: Optional[Decimal] = Field(
        None, description="Absolute max FSR under this plan"
    )
    max_storeys: Optional[int] = Field(
        None, description="Absolute max storeys under this plan"
    )
    conditions: Optional[str] = Field(None, description="Conditions for the bonus")


class CommunityPlanResult(BaseModel):
    """Result of community plan bonus lookup for a parcel."""

    has_bonus: bool = Field(
        False, description="Whether any community plan bonus applies"
    )
    bonuses: list[CommunityPlanBonus] = Field(default_factory=list)
    best_bonus: Optional[CommunityPlanBonus] = Field(
        None, description="Highest FSR/storeys bonus"
    )
    effective_max_fsr: Optional[Decimal] = Field(
        None, description="Max FSR from best community plan"
    )
    effective_max_storeys: Optional[int] = Field(
        None, description="Max storeys from best community plan"
    )


# ── SQL ─────────────────────────────────────────────────────────

SQL_COMMUNITY_PLAN_BONUSES = """
    SELECT plan_name, plan_area, bonus_fsr, bonus_storeys,
           max_fsr, max_storeys, conditions
    FROM community_plan_bonuses
    WHERE is_active = true
      AND $1 = ANY(applicable_zoning)
    ORDER BY max_fsr DESC NULLS LAST
"""


# ── Engine ──────────────────────────────────────────────────────


async def compute_community_plan_bonus(
    conn,
    current_zoning: Optional[str],
) -> CommunityPlanResult:
    """
    Look up community plan density bonuses for a parcel's zoning district.

    Returns all applicable bonuses, with the best (highest density) first.
    """
    if not current_zoning:
        return CommunityPlanResult()

    rows = await conn.fetch(SQL_COMMUNITY_PLAN_BONUSES, current_zoning)

    if not rows:
        return CommunityPlanResult()

    bonuses = []
    for row in rows:
        bonuses.append(
            CommunityPlanBonus(
                plan_name=row["plan_name"],
                plan_area=row["plan_area"],
                bonus_fsr=row["bonus_fsr"],
                bonus_storeys=row["bonus_storeys"],
                max_fsr=row["max_fsr"],
                max_storeys=row["max_storeys"],
                conditions=row["conditions"],
            )
        )

    # Best bonus = highest max_fsr (already sorted DESC from SQL)
    best = bonuses[0] if bonuses else None

    return CommunityPlanResult(
        has_bonus=True,
        bonuses=bonuses,
        best_bonus=best,
        effective_max_fsr=best.max_fsr if best else None,
        effective_max_storeys=best.max_storeys if best else None,
    )
