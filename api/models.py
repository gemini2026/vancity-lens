"""
VanCity Lens — Bill 47 (TOA) Domain Models
Pydantic v2 models for the entitlement engine.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field


# ── Enums ────────────────────────────────────────────────────

class StationType(str, Enum):
    SKYTRAIN = "skytrain"
    BUS_EXCHANGE = "bus_exchange"


class TOATier(int, Enum):
    """Bill 47 proximity tiers. Lower tier = closer = more density."""
    TIER_1 = 1  # 0–200m
    TIER_2 = 2  # 201–400m
    TIER_3 = 3  # 401–800m


class EntitlementSignal(str, Enum):
    """Traffic-light signal for the frontend map."""
    HIGH_ALPHA = "high_alpha"       # value_delta > $1M
    MODERATE = "moderate"           # value_delta $250K–$1M
    LOW = "low"                     # value_delta < $250K
    ALREADY_ZONED = "already_zoned" # current zoning already exceeds Bill 47
    NO_ENTITLEMENT = "none"         # outside all TOA zones


# ── Core Models ──────────────────────────────────────────────

class GeoPoint(BaseModel):
    """A lon/lat coordinate pair."""
    lng: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)


class TransitStation(BaseModel):
    """A transit station that generates TOA buffers."""
    id: int
    name: str
    line: str
    type: StationType
    location: GeoPoint


class TierRule(BaseModel):
    """A single Bill 47 tier rule."""
    tier: TOATier
    station_type: StationType
    min_distance_m: int
    max_distance_m: int
    max_storeys: int
    max_fsr: Decimal


# ── Entitlement Result ───────────────────────────────────────

class StationEntitlement(BaseModel):
    """Entitlement from a single nearby station."""
    station_name: str
    distance_m: Decimal = Field(..., description="Distance from parcel centroid to station")
    tier: TOATier
    bill47_storeys: int = Field(..., description="Raw Bill 47 tier max storeys")
    bill47_fsr: Decimal = Field(..., description="Raw Bill 47 tier max FSR")
    entitled_storeys: int = Field(..., description="Effective entitlement = max(current, bill47)")
    entitled_fsr: Decimal = Field(..., description="Effective FSR = max(current, bill47)")
    current_storeys: Optional[int] = None
    current_fsr: Optional[Decimal] = None
    storey_uplift: int = Field(..., description="Additional storeys unlocked by Bill 47 (never negative)")
    fsr_uplift: Decimal = Field(..., description="Additional FSR unlocked by Bill 47 (never negative)")
    zoning_already_exceeds: bool = Field(
        default=False,
        description="True if current zoning already exceeds Bill 47 minimums"
    )


class ValueEstimate(BaseModel):
    """Land value estimate based on entitled density."""
    lot_area_sqm: Decimal
    entitled_fsr: Decimal
    buildable_sqft: Decimal = Field(..., description="lot_area * FSR * 10.7639")
    estimated_land_value: int = Field(..., description="Estimated value in dollars")
    current_assessed: Optional[int] = None
    asking_price: Optional[int] = None
    value_delta: int = Field(..., description="estimated_value - max(asking, assessed)")
    price_per_sqft_assumption: Decimal = Field(
        default=Decimal("800"),
        description="$/sqft of buildable area used in estimate"
    )


class ParcelEntitlementResponse(BaseModel):
    """
    The main API response: everything Colin needs to see
    when he clicks a parcel on the map.
    """
    pid: str = Field(..., description="BC Land Title PID")
    civic_address: Optional[str] = None
    current_zoning: Optional[str] = None
    in_toa: bool = Field(..., description="Is this parcel inside any TOA zone?")
    entitlements: list[StationEntitlement] = Field(
        default_factory=list,
        description="All overlapping station entitlements, best first"
    )
    best_entitlement: Optional[StationEntitlement] = Field(
        None, description="Highest density entitlement"
    )
    value_estimate: Optional[ValueEstimate] = None
    sources: Optional[SourceAttribution] = None
    validation: Optional[DealValidation] = None

    @computed_field
    @property
    def signal(self) -> EntitlementSignal:
        """Traffic-light signal for the map marker colour."""
        if not self.in_toa or self.value_estimate is None:
            return EntitlementSignal.NO_ENTITLEMENT
        # If current zoning already exceeds Bill 47, no Bill 47 alpha
        if self.best_entitlement and self.best_entitlement.zoning_already_exceeds:
            return EntitlementSignal.ALREADY_ZONED
        delta = self.value_estimate.value_delta
        if delta > 1_000_000:
            return EntitlementSignal.HIGH_ALPHA
        elif delta > 250_000:
            return EntitlementSignal.MODERATE
        return EntitlementSignal.LOW

    @computed_field
    @property
    def headline(self) -> str:
        """
        The one-liner for the popup tooltip.
        e.g. "ZONING ALERT: Approved for 20 Stories. Est. Land Value: $5.2M"
        """
        if not self.in_toa or self.best_entitlement is None:
            return "No Bill 47 entitlement detected."
        be = self.best_entitlement
        val = self.value_estimate
        val_str = ""
        if val:
            millions = val.estimated_land_value / 1_000_000
            val_str = f" Est. Land Value: ${millions:,.1f}M."
        # If current zoning already exceeds Bill 47, flag it clearly
        if be.zoning_already_exceeds:
            zoning_label = self.current_zoning or "existing zoning"
            return (
                f"ALREADY ZONED HIGHER: {zoning_label} allows "
                f"{be.current_storeys} storeys / FSR {be.current_fsr} "
                f"(exceeds Bill 47 Tier {be.tier.value}: {be.bill47_storeys} storeys / FSR {be.bill47_fsr})."
                f"{val_str}"
            )
        return (
            f"ZONING ALERT: Approved for {be.entitled_storeys} Stories "
            f"(Tier {be.tier.value}, {be.distance_m:.0f}m from {be.station_name})."
            f"{val_str}"
        )


# ── Data Source Attribution ───────────────────────────────────

class DataSource(BaseModel):
    """A single verifiable source for a data point."""
    field: str = Field(..., description="Which field this sources (e.g. 'pid', 'zoning', 'assessed_value')")
    label: str = Field(..., description="Human-readable data point label")
    value: str = Field(..., description="The actual value being sourced")
    origin: str = Field(..., description="Source name: 'Vancouver Open Data', 'BC Assessment', 'Bill 47 Legislation', etc.")
    confidence: str = Field(..., description="'verified' = from government source, 'estimated' = model/benchmark, 'calculated' = derived from verified inputs")
    url: Optional[str] = Field(None, description="Direct URL to verify this data point")
    note: Optional[str] = Field(None, description="Extra context about the data point")


class SourceAttribution(BaseModel):
    """All source links for a parcel entitlement response."""
    sources: list[DataSource] = Field(default_factory=list)
    last_updated: Optional[str] = None
    disclaimer: str = Field(
        default="Entitlement calculations are based on Bill 47 legislation and verified government data. "
                "Assessed and asking values may be estimates. Always verify with a licensed appraiser before making investment decisions."
    )


# ── Risk & Validation Models ─────────────────────────────────

class RiskFlag(BaseModel):
    """A single risk or friction flag for a parcel."""
    code: str = Field(..., description="Machine-readable risk code")
    severity: str = Field(..., description="'red' = deal killer, 'yellow' = cost adder, 'green' = positive signal")
    label: str = Field(..., description="Short human-readable label")
    detail: str = Field(..., description="Explanation with specifics")
    cost_impact: Optional[str] = Field(None, description="Estimated $ or timeline impact")
    verify_url: Optional[str] = Field(None, description="URL to verify this risk factor")


class DeveloperProForma(BaseModel):
    """Professional-grade residual land value analysis with V2 enhancements."""
    buildable_sqft: Decimal
    # Revenue side
    revenue_per_sqft: Decimal = Field(default=Decimal("1100"), description="Pre-sale $/sqft — adjusted by neighborhood")
    gross_revenue: int
    # Cost side
    construction_type: str = Field(..., description="'concrete_highrise', 'woodframe_midrise', 'woodframe_lowrise'")
    hard_cost_per_sqft: Decimal
    hard_cost_total: int
    soft_cost_pct: Decimal = Field(default=Decimal("0.18"))
    soft_cost_total: int
    cac_dcl_total: int = Field(description="Community Amenity Contribution + Development Cost Levy")
    # Bottom line
    developer_profit_pct: Decimal = Field(default=Decimal("0.18"))
    developer_profit: int
    residual_land_value: int = Field(description="What a developer would actually pay for this land")
    # Comparison
    asking_price: Optional[int] = None
    assessed_value: Optional[int] = None
    true_alpha: int = Field(description="residual_land_value - max(asking, assessed) — the REAL opportunity")
    # V2: Neighborhood adjustment
    neighborhood: Optional[str] = Field(None, description="Neighborhood name for revenue adjustment")
    neighborhood_multiplier: Optional[Decimal] = Field(None, description="Revenue multiplier (e.g. 1.20 for Kitsilano)")
    # V2: Holding cost (time value of money)
    holding_cost: Optional[int] = Field(None, description="Interest cost during predevelopment hold")
    holding_months: Optional[int] = Field(None, description="Estimated months from acquisition to construction start")


class ScenarioProForma(BaseModel):
    """Single scenario pro forma (used inside ThreeScenarioProForma)."""
    scenario: str = Field(..., description="'bull', 'base', or 'bear'")
    buildable_sqft: Decimal
    sellable_sqft: Decimal
    # Revenue
    revenue_per_sqft: Decimal
    absorption_discount: Decimal = Field(default=Decimal("0"))
    gross_revenue: int
    net_revenue: int = Field(..., description="gross_revenue × (1 - absorption_discount)")
    # Costs
    construction_type: str
    hard_cost_per_sqft: Decimal
    hard_cost_inflation: Decimal = Field(default=Decimal("0"))
    hard_cost_total: int
    soft_cost_total: int
    contingency_total: int = Field(default=0)
    marketing_total: int = Field(default=0)
    cac_dcl_total: int
    hidden_costs_total: int = Field(default=0, description="Demolition + enviro + tenants + soil + rezoning")
    holding_cost: int = Field(default=0)
    holding_months: int = Field(default=0)
    # Profit
    developer_profit: int
    # Bottom line
    total_costs: int
    residual_land_value: int
    true_alpha: int
    # Flags
    is_viable: bool = Field(default=True, description="residual > 0 and alpha > 0")


class HiddenCostItem(BaseModel):
    """A single hidden cost line item."""
    category: str = Field(..., description="'Demolition', 'Environmental', 'Tenant Displacement', etc.")
    cost: int
    explanation: str


class ThreeScenarioProForma(BaseModel):
    """V3: Bull / Base / Bear scenarios side by side."""
    bull: ScenarioProForma
    base: ScenarioProForma
    bear: ScenarioProForma
    hidden_costs: list[HiddenCostItem] = Field(default_factory=list, description="Itemized hidden cost breakdown")
    hidden_costs_total: int = Field(default=0)
    # Grading uses BASE case
    grade_scenario: str = Field(default="base", description="Which scenario drives the grade")


class DueDiligenceItem(BaseModel):
    """A single due diligence checklist item."""
    item: str = Field(..., description="Checklist item name")
    description: str = Field(..., description="What to check and why")
    url: Optional[str] = Field(None, description="URL to perform this check")
    priority: str = Field(default="medium", description="'critical', 'high', 'medium'")


class DealValidation(BaseModel):
    """V3 comprehensive validation — multi-axis grading with three-scenario pro forma."""
    # Composite grade (Economics axis) — NOW GRADED ON BASE CASE
    deal_grade: str = Field(..., description="A/B/C/D/F economics grade (graded on BASE scenario)")
    deal_score: int = Field(..., ge=0, le=100, description="0-100 economics score")
    confidence_level: str = Field(..., description="'high', 'medium', 'low' — based on data completeness")
    # V2: Multi-axis grading
    confidence_stars: int = Field(default=1, ge=1, le=3, description="1-3 stars for data confidence")
    friction_level: str = Field(default="low", description="'low', 'medium', 'high' — path-to-permit difficulty")
    friction_score: int = Field(default=0, ge=0, description="Raw friction points accumulated")
    neighborhood: Optional[str] = Field(None, description="Neighborhood name")

    # Key metrics
    price_per_buildable_sqft: Optional[Decimal] = Field(None, description="Asking price / buildable sqft — THE metric developers use")
    assessed_ratio: Optional[Decimal] = Field(None, description="asking_price / assessed_value — below 1.0 is interesting")
    land_to_total_ratio: Optional[Decimal] = Field(None, description="land_value / (land + improvement) — >0.75 = likely teardown")

    # Lot analysis
    lot_adequate: bool = Field(default=True, description="Is lot large enough for entitled building type?")
    lot_adequacy_note: Optional[str] = None
    min_lot_sqm_required: Optional[Decimal] = None

    # Supply/competition
    competing_parcels: int = Field(default=0, description="Similar parcels in same tier within 400m")
    supply_saturation: str = Field(default="low", description="'low', 'moderate', 'high'")

    # Risk flags
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    red_flag_count: int = 0
    yellow_flag_count: int = 0
    green_flag_count: int = 0

    # Developer pro forma (V2 backward compat — populated with BASE case)
    pro_forma: Optional[DeveloperProForma] = None

    # V3: Three-scenario pro forma
    three_scenario_proforma: Optional[ThreeScenarioProForma] = Field(
        None, description="Bull/Base/Bear pro formas with hidden costs"
    )

    # V3: Gap analysis — "Why The Gap Exists"
    gap_analysis: Optional[str] = Field(
        None, description="Plain-English explanation of where the theoretical alpha goes"
    )

    # V3: Execution difficulty (1-10)
    execution_difficulty_score: int = Field(default=0, ge=0, le=10, description="1-10 how hard to execute")
    execution_difficulty_factors: list[str] = Field(
        default_factory=list, description="What contributes to execution difficulty"
    )

    # V2: Due diligence checklist
    due_diligence_checklist: list[dict] = Field(default_factory=list, description="Title/legal checklist items for manual verification")

    # Summary
    one_liner: str = Field(..., description="Executive summary with multi-axis awareness")


# ── Request Models ───────────────────────────────────────────

class EntitlementRequest(BaseModel):
    """Optional overrides for value estimation."""
    price_per_sqft: Decimal = Field(
        default=Decimal("800"),
        ge=100,
        le=3000,
        description="Override $/sqft of buildable area for value calc"
    )
