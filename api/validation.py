"""
VanCity Lens — Deal Validation Engine V3
"Why The Gap Exists" — Three-scenario pro forma with hidden cost deductions,
gap analysis narrative, and execution difficulty scoring.

Grades on BASE case, not bull case. If only the optimistic scenario is profitable,
that's not a real deal.
"""

from decimal import Decimal
from typing import Optional
import asyncpg

from .models import (
    DealValidation, DeveloperProForma, RiskFlag, StationEntitlement, ValueEstimate,
    ScenarioProForma, HiddenCostItem, ThreeScenarioProForma,
)
from .neighborhood_economics import (
    get_neighborhood_multiplier,
    get_neighborhood_label,
    compute_holding_cost,
    SCENARIO_FACTORS,
)
from .hidden_costs import calculate_total_hidden_costs


# ── Construction Cost Parameters (Vancouver 2024-2025) ──────

CONSTRUCTION_COSTS = {
    "concrete_highrise": {"min": Decimal("360"), "max": Decimal("455"), "typical": Decimal("410")},
    "woodframe_midrise": {"min": Decimal("275"), "max": Decimal("365"), "typical": Decimal("320")},
    "woodframe_lowrise": {"min": Decimal("250"), "max": Decimal("320"), "typical": Decimal("285")},
}

# Base revenue assumptions (Vancouver 2024-2025) — adjusted by neighborhood
REVENUE_PER_SQFT = {
    "concrete_highrise": Decimal("1100"),
    "woodframe_midrise": Decimal("950"),
    "woodframe_lowrise": Decimal("850"),
}

# Municipal fees
CAC_PER_UNIT = 15000
DCL_PER_SQFT = 18
SOFT_COST_PCT = Decimal("0.18")
DEVELOPER_PROFIT_PCT = Decimal("0.18")

# Lot size minimums by building type (sqm)
MIN_LOT_SIZE = {
    "concrete_highrise": 900,
    "woodframe_midrise": 500,
    "woodframe_lowrise": 250,
}

AVG_UNIT_SIZE_SQFT = 650


def _determine_construction_type(entitled_storeys: int) -> str:
    """Determine building type from entitled height."""
    if entitled_storeys >= 13:
        return "concrete_highrise"
    elif entitled_storeys >= 7:
        return "woodframe_midrise"
    else:
        return "woodframe_lowrise"


# ── V3: Three-Scenario Pro Forma ─────────────────────────────

def _compute_scenario(
    scenario_name: str,
    lot_area_sqm: Decimal,
    entitled_fsr: Decimal,
    entitled_storeys: int,
    asking_price: Optional[int],
    assessed_value: Optional[int],
    neighborhood: Optional[str],
    hidden_costs_total: int,
) -> ScenarioProForma:
    """Compute a single scenario (bull/base/bear) pro forma."""
    factors = SCENARIO_FACTORS[scenario_name]
    buildable_sqft = lot_area_sqm * entitled_fsr * Decimal("10.7639")
    construction_type = _determine_construction_type(entitled_storeys)

    # Revenue — adjusted by neighborhood multiplier
    base_rev_per_sqft = REVENUE_PER_SQFT[construction_type]
    multiplier = get_neighborhood_multiplier(neighborhood)
    rev_per_sqft = base_rev_per_sqft * multiplier

    # 85% efficiency (common areas, parking, etc.)
    sellable_sqft = buildable_sqft * Decimal("0.85")
    gross_revenue = int(sellable_sqft * rev_per_sqft)

    # Apply absorption discount (presale discount to move units)
    absorption_discount = factors["absorption_discount"]
    net_revenue = int(gross_revenue * (1 - absorption_discount))

    # Hard costs with inflation
    hard_cost_per_sqft = CONSTRUCTION_COSTS[construction_type]["typical"]
    hard_cost_inflation = factors["hard_cost_inflation"]
    inflated_hard_cost = hard_cost_per_sqft * (1 + hard_cost_inflation)
    hard_cost_total = int(buildable_sqft * inflated_hard_cost)

    # Soft costs
    soft_cost_total = int(hard_cost_total * SOFT_COST_PCT)

    # Contingency (% of hard costs)
    contingency_total = int(hard_cost_total * factors["contingency"])

    # Marketing/sales (% of gross revenue)
    marketing_total = int(gross_revenue * factors["marketing_sales"])

    # Municipal fees
    est_units = max(1, int(sellable_sqft / AVG_UNIT_SIZE_SQFT))
    cac_dcl = (est_units * CAC_PER_UNIT) + int(buildable_sqft * DCL_PER_SQFT)

    # Developer profit
    developer_profit = int(net_revenue * DEVELOPER_PROFIT_PCT)

    # Hidden costs (only applied in base/bear via multiplier)
    scenario_hidden = int(hidden_costs_total * float(factors["hidden_cost_multiplier"]))

    # Holding cost with timeline extension
    land_cost = asking_price or assessed_value or 0
    base_holding_cost, base_months = compute_holding_cost(land_cost, construction_type)
    extension = factors["timeline_extension_months"]
    if extension > 0 and land_cost > 0:
        extra_cost = int(land_cost * 0.065 * extension / 12)
        holding_cost = base_holding_cost + extra_cost
        holding_months = base_months + extension
    else:
        holding_cost = base_holding_cost
        holding_months = base_months

    # Total costs
    total_costs = (hard_cost_total + soft_cost_total + contingency_total +
                   marketing_total + cac_dcl + scenario_hidden + holding_cost)

    # Residual = net revenue - all costs - profit
    residual = net_revenue - total_costs - developer_profit

    # True alpha
    compare_to = asking_price or assessed_value or 0
    true_alpha = residual - compare_to

    return ScenarioProForma(
        scenario=scenario_name,
        buildable_sqft=Decimal(str(round(buildable_sqft))),
        sellable_sqft=Decimal(str(round(float(sellable_sqft)))),
        revenue_per_sqft=rev_per_sqft,
        absorption_discount=absorption_discount,
        gross_revenue=gross_revenue,
        net_revenue=net_revenue,
        construction_type=construction_type,
        hard_cost_per_sqft=inflated_hard_cost,
        hard_cost_inflation=hard_cost_inflation,
        hard_cost_total=hard_cost_total,
        soft_cost_total=soft_cost_total,
        contingency_total=contingency_total,
        marketing_total=marketing_total,
        cac_dcl_total=cac_dcl,
        hidden_costs_total=scenario_hidden,
        holding_cost=holding_cost,
        holding_months=holding_months,
        developer_profit=developer_profit,
        total_costs=total_costs,
        residual_land_value=residual,
        true_alpha=true_alpha,
        is_viable=(residual > 0 and true_alpha > 0),
    )


def _compute_three_scenarios(
    lot_area_sqm: Decimal,
    entitled_fsr: Decimal,
    entitled_storeys: int,
    asking_price: Optional[int],
    assessed_value: Optional[int],
    neighborhood: Optional[str],
    hidden_costs_total: int,
    hidden_cost_items: list[tuple[str, int, str]],
) -> ThreeScenarioProForma:
    """Compute Bull / Base / Bear scenarios."""
    bull = _compute_scenario("bull", lot_area_sqm, entitled_fsr, entitled_storeys,
                             asking_price, assessed_value, neighborhood, hidden_costs_total)
    base = _compute_scenario("base", lot_area_sqm, entitled_fsr, entitled_storeys,
                             asking_price, assessed_value, neighborhood, hidden_costs_total)
    bear = _compute_scenario("bear", lot_area_sqm, entitled_fsr, entitled_storeys,
                             asking_price, assessed_value, neighborhood, hidden_costs_total)

    items = [HiddenCostItem(category=cat, cost=cost, explanation=expl)
             for cat, cost, expl in hidden_cost_items]

    return ThreeScenarioProForma(
        bull=bull,
        base=base,
        bear=bear,
        hidden_costs=items,
        hidden_costs_total=hidden_costs_total,
    )


def _build_v2_pro_forma_from_base(
    base: ScenarioProForma,
    neighborhood: Optional[str],
    neighborhood_multiplier: Decimal,
) -> DeveloperProForma:
    """Convert the BASE scenario into a V2-compatible DeveloperProForma for backward compat."""
    return DeveloperProForma(
        buildable_sqft=base.buildable_sqft,
        revenue_per_sqft=base.revenue_per_sqft,
        gross_revenue=base.net_revenue,  # Use net (after absorption discount)
        construction_type=base.construction_type,
        hard_cost_per_sqft=base.hard_cost_per_sqft,
        hard_cost_total=base.hard_cost_total,
        soft_cost_pct=SOFT_COST_PCT,
        soft_cost_total=base.soft_cost_total,
        cac_dcl_total=base.cac_dcl_total,
        developer_profit_pct=DEVELOPER_PROFIT_PCT,
        developer_profit=base.developer_profit,
        residual_land_value=base.residual_land_value,
        asking_price=None,  # Set by caller
        assessed_value=None,
        true_alpha=base.true_alpha,
        neighborhood=get_neighborhood_label(neighborhood),
        neighborhood_multiplier=neighborhood_multiplier,
        holding_cost=base.holding_cost,
        holding_months=base.holding_months,
    )


# ── V3: Gap Analysis ────────────────────────────────────────

def _generate_gap_analysis(
    bull: ScenarioProForma,
    base: ScenarioProForma,
    hidden_cost_items: list[tuple[str, int, str]],
) -> str:
    """
    Generate plain-English explanation of where the theoretical alpha goes.
    "The $2.1M gap exists because..."
    """
    bull_alpha = bull.true_alpha
    base_alpha = base.true_alpha

    if bull_alpha <= 0:
        return "No theoretical alpha exists even in the optimistic (bull) scenario."

    gap = bull_alpha - base_alpha
    if gap <= 0:
        return f"Base case alpha of {_fmt(base_alpha)} holds up — realistic costs don't erode the opportunity."

    parts = []

    # Absorption discount
    absorption_loss = bull.gross_revenue - base.net_revenue
    if absorption_loss > 0:
        parts.append(f"5% presale absorption discount = -{_fmt(absorption_loss)}")

    # Hard cost inflation
    cost_inflation = base.hard_cost_total - bull.hard_cost_total
    if cost_inflation > 0:
        parts.append(f"5% construction cost escalation = -{_fmt(cost_inflation)}")

    # Contingency
    if base.contingency_total > 0:
        parts.append(f"7% contingency = -{_fmt(base.contingency_total)}")

    # Marketing
    if base.marketing_total > 0:
        parts.append(f"3% marketing/sales = -{_fmt(base.marketing_total)}")

    # Hidden costs (itemized)
    for cat, cost, _ in hidden_cost_items:
        if cost > 0:
            parts.append(f"{cat.lower()} = -{_fmt(cost)}")

    # Extended holding cost
    holding_diff = base.holding_cost - bull.holding_cost
    if holding_diff > 0:
        parts.append(f"+6 month holding cost = -{_fmt(holding_diff)}")

    if not parts:
        return f"Bull case alpha: {_fmt(bull_alpha)}. Base case alpha: {_fmt(base_alpha)}."

    breakdown = ", ".join(f"({i+1}) {p}" for i, p in enumerate(parts))
    result = f"The {_fmt(bull_alpha)} theoretical gap exists because: {breakdown}."

    if base_alpha > 0:
        result += f" After all deductions, {_fmt(base_alpha)} of real alpha remains — if you can execute for less, the arbitrage is yours."
    else:
        result += f" After realistic costs, the alpha disappears (base case: {_fmt(base_alpha)}). This deal only works if you can beat industry benchmarks on execution."

    return result


# ── V3: Execution Difficulty Score ───────────────────────────

def _calculate_execution_difficulty(
    risk_flags: list[RiskFlag],
    lot_adequate: bool,
    is_cd1: bool,
    active_licence_count: int,
    neighborhood: Optional[str],
    entitled_storeys: int,
) -> tuple[int, list[str]]:
    """
    Calculate execution difficulty 1-10.
    Independent of economic grade — a parcel can be Grade A but difficulty 9.
    """
    score = 0
    factors = []

    # Assembly required (+3)
    if not lot_adequate:
        score += 3
        factors.append("Lot assembly required (+3)")

    # Existing tenants (+2)
    if active_licence_count > 0:
        score += min(2, active_licence_count)
        factors.append(f"{active_licence_count} existing tenant(s) (+{min(2, active_licence_count)})")

    # Heritage / view cone (+3)
    has_heritage = any(f.code == "HERITAGE_SITE" for f in risk_flags)
    has_view_cone = any(f.code == "VIEW_CONE" for f in risk_flags)
    if has_heritage or has_view_cone:
        score += 3
        if has_heritage and has_view_cone:
            factors.append("Heritage site + view cone (+3)")
        elif has_heritage:
            factors.append("Heritage site proximity (+3)")
        else:
            factors.append("View cone intersection (+3)")

    # CD-1 rezoning (+2)
    if is_cd1:
        score += 2
        factors.append("CD-1 zone — full rezoning required (+2)")

    # Environmental risk (+2)
    has_enviro = any(f.code == "ENVIRO_RISK" for f in risk_flags)
    if has_enviro:
        score += 2
        factors.append("Environmental contamination risk (+2)")

    # Soft soil + highrise (+1)
    from .neighborhood_economics import SOFT_SOIL_ZONES
    if neighborhood and entitled_storeys >= 13:
        n_upper = neighborhood.upper().strip()
        is_soft = any(z.upper() in n_upper or n_upper in z.upper() for z in SOFT_SOIL_ZONES)
        if is_soft:
            score += 1
            factors.append(f"Soft soil zone + highrise ({neighborhood}) (+1)")

    # Community opposition (+1)
    has_opposition = any(f.code in ("HIGH_OPPOSITION", "MODERATE_OPPOSITION") for f in risk_flags)
    if has_opposition:
        score += 1
        factors.append("Community opposition factors (+1)")

    # Floodplain (+1)
    has_flood = any(f.code == "FLOODPLAIN" for f in risk_flags)
    if has_flood:
        score += 1
        factors.append("Floodplain zone (+1)")

    return min(10, max(1, score)), factors


# ── Main Validation Function ────────────────────────────────

async def compute_validation(
    conn: asyncpg.Connection,
    pid: str,
    parcel: asyncpg.Record,
    best: Optional[StationEntitlement],
    value_estimate: Optional[ValueEstimate],
) -> DealValidation:
    """
    Run full V3 validation suite on a parcel.
    Three-scenario pro forma, gap analysis, execution difficulty.
    Grades on BASE case.
    """
    risk_flags: list[RiskFlag] = []
    econ_score = 100   # Economics axis
    friction_score = 0  # Friction axis
    data_points_available = 0
    data_points_possible = 10

    lot_area = parcel["lot_area_sqm"] or Decimal("0")
    asking = parcel["asking_price"]
    assessed = parcel["assessed_value"]
    addr = parcel["civic_address"] or ""
    addr_encoded = addr.replace(" ", "+")

    # V2 enrichment columns
    year_built = None
    geo_local_area = None
    land_val = None
    impr_val = None
    try:
        land_val = parcel["land_value"]
        impr_val = parcel["improvement_value"]
    except (KeyError, TypeError):
        pass
    try:
        year_built = parcel["year_built"]
    except (KeyError, TypeError):
        pass
    try:
        geo_local_area = parcel["geo_local_area"]
    except (KeyError, TypeError):
        pass

    # ══════════════════════════════════════════════════════════
    # ECONOMICS CHECKS
    # ══════════════════════════════════════════════════════════

    # ── 1. Price per buildable sqft ──
    price_per_bsf = None
    if asking and best and lot_area:
        buildable = float(lot_area) * float(best.entitled_fsr) * 10.7639
        if buildable > 0:
            price_per_bsf = Decimal(str(round(asking / buildable, 2)))
            data_points_available += 1

    # ── 2. Assessed value ratio ──
    assessed_ratio = None
    if asking and assessed and assessed > 0:
        assessed_ratio = Decimal(str(round(asking / assessed, 2)))
        data_points_available += 1
        if assessed_ratio < Decimal("0.9"):
            risk_flags.append(RiskFlag(
                code="BELOW_ASSESSED", severity="green",
                label="Below Assessed Value",
                detail=f"Listed at {float(assessed_ratio):.0%} of BC Assessment ({_fmt(assessed)}). Potential motivated seller.",
            ))
        elif assessed_ratio > Decimal("1.5"):
            risk_flags.append(RiskFlag(
                code="ABOVE_ASSESSED", severity="yellow",
                label="Premium Over Assessment",
                detail=f"Listed at {float(assessed_ratio):.0%} of assessment. Seller may be pricing in development potential.",
                cost_impact="Overpayment risk: negotiate down",
            ))
            econ_score -= 10

    # ── 3. Land-to-improvement ratio ──
    land_to_total = None
    if land_val and (land_val + (impr_val or 0)) > 0:
        total = land_val + (impr_val or 0)
        land_to_total = Decimal(str(round(land_val / total, 2)))
        data_points_available += 1
        if land_to_total > Decimal("0.85"):
            risk_flags.append(RiskFlag(
                code="TEARDOWN_LIKELY", severity="green",
                label="Likely Teardown Candidate",
                detail=f"Land is {float(land_to_total):.0%} of assessed value — improvement worth only {_fmt(impr_val)}. Low demolition friction.",
            ))
        elif land_to_total < Decimal("0.50"):
            risk_flags.append(RiskFlag(
                code="SIGNIFICANT_IMPROVEMENT", severity="yellow",
                label="Significant Existing Structure",
                detail=f"Improvement is {float(1-land_to_total):.0%} of assessed value ({_fmt(impr_val)}). Owner may resist selling for land value.",
                cost_impact="Higher acquisition premium likely",
            ))
            econ_score -= 8

    # ── 16. Building age assessment ──
    if year_built:
        data_points_available += 1
        import datetime
        building_age = datetime.datetime.now().year - year_built
        if building_age < 15:
            risk_flags.append(RiskFlag(
                code="YOUNG_BUILDING", severity="yellow",
                label=f"Recent Build ({year_built})",
                detail=f"Building is only {building_age} years old. Owner has significant improvement value — unlikely to sell for teardown.",
                cost_impact="May need 20-30% acquisition premium over land value",
            ))
            econ_score -= 8
            friction_score += 10
        elif building_age > 50:
            risk_flags.append(RiskFlag(
                code="AGING_BUILDING", severity="green",
                label=f"Aging Structure ({year_built})",
                detail=f"Building is {building_age} years old. Natural teardown candidate — lower demolition friction and likely motivated seller.",
            ))

    # ── 17. Neighborhood revenue adjustment ──
    neighborhood_mult = get_neighborhood_multiplier(geo_local_area)
    if geo_local_area:
        data_points_available += 1
        neighborhood_label = get_neighborhood_label(geo_local_area)
        if neighborhood_mult > Decimal("1.10"):
            risk_flags.append(RiskFlag(
                code="PREMIUM_NEIGHBORHOOD", severity="green",
                label=f"Premium Area: {neighborhood_label}",
                detail=f"Revenue adjusted {float(neighborhood_mult):.0%} of base — {neighborhood_label} commands above-average pre-sale prices.",
            ))
        elif neighborhood_mult < Decimal("0.92"):
            risk_flags.append(RiskFlag(
                code="VALUE_NEIGHBORHOOD", severity="yellow",
                label=f"Value Market: {neighborhood_label}",
                detail=f"Revenue adjusted to {float(neighborhood_mult):.0%} of base — {neighborhood_label} has below-average pre-sale absorption.",
                cost_impact="Pro forma revenue reduced by neighborhood discount",
            ))
            econ_score -= 5

    # ══════════════════════════════════════════════════════════
    # FRICTION CHECKS
    # ══════════════════════════════════════════════════════════

    # ── 4. Heritage risk ──
    try:
        heritage = await conn.fetchrow(
            "SELECT name, category FROM heritage_sites "
            "WHERE ST_DWithin(geom, (SELECT ST_Centroid(geom) FROM parcels WHERE pid = $1), 0.0003) "
            "ORDER BY ST_Distance(geom, (SELECT ST_Centroid(geom) FROM parcels WHERE pid = $1)) LIMIT 1",
            pid
        )
        data_points_available += 1
        if heritage:
            risk_flags.append(RiskFlag(
                code="HERITAGE_SITE", severity="red",
                label=f"Heritage Site ({heritage['category'] or '?'})",
                detail=f"Near heritage-registered '{heritage['name']}'. Heritage Alteration Permit required — adds 4-6 months + 15-25% soft cost premium.",
                cost_impact="+$150K-500K and 4-6 month delay",
                verify_url=f"https://opendata.vancouver.ca/explore/dataset/heritage-sites/table/?q={addr_encoded}",
            ))
            econ_score -= 25
            friction_score += 25
    except Exception:
        pass

    # ── 5. Floodplain risk ──
    try:
        flood = await conn.fetchrow(
            "SELECT zone_type FROM floodplain_zones "
            "WHERE ST_Intersects(geom, (SELECT geom FROM parcels WHERE pid = $1)) LIMIT 1",
            pid
        )
        data_points_available += 1
        if flood:
            risk_flags.append(RiskFlag(
                code="FLOODPLAIN", severity="red",
                label="Designated Floodplain",
                detail=f"In {flood['zone_type'] or 'designated'} floodplain. Flood Hazard Assessment required + flood-resistant construction standards.",
                cost_impact="+$15K-40K assessment + 5-10% construction premium",
                verify_url="https://opendata.vancouver.ca/explore/dataset/designated-floodplain/map/",
            ))
            econ_score -= 20
            friction_score += 20
    except Exception:
        pass

    # ── 6. Easement risk ──
    try:
        easement_count = await conn.fetchval(
            "SELECT count(*) FROM property_easements "
            "WHERE ST_Intersects(geom, (SELECT geom FROM parcels WHERE pid = $1))",
            pid
        )
        data_points_available += 1
        if easement_count and easement_count > 0:
            sev = "red" if easement_count >= 3 else "yellow"
            risk_flags.append(RiskFlag(
                code="EASEMENTS", severity=sev,
                label=f"{easement_count} Easement{'s' if easement_count > 1 else ''}",
                detail=f"{easement_count} registered easement(s) intersect this parcel. Each requires verification with servicing utility — relocation may cost $50K-200K.",
                cost_impact=f"~${50 * easement_count}K-{200 * easement_count}K potential relocation cost",
                verify_url=f"https://opendata.vancouver.ca/explore/dataset/property-easements/map/?q={addr_encoded}",
            ))
            econ_score -= (10 * min(easement_count, 3))
            friction_score += (8 * min(easement_count, 3))
    except Exception:
        pass

    # ── 11. View cone intersection (DEAL KILLER) ──
    view_cone_cap = None
    try:
        view_cone = await conn.fetchrow(
            "SELECT view_cone_name, description FROM view_cones "
            "WHERE ST_Intersects(geom, (SELECT geom FROM parcels WHERE pid = $1)) LIMIT 1",
            pid
        )
        data_points_available += 1
        if view_cone:
            cone_name = view_cone["view_cone_name"] or view_cone["description"] or "Protected View"
            risk_flags.append(RiskFlag(
                code="VIEW_CONE", severity="red",
                label=f"View Cone: {cone_name[:40]}",
                detail=f"Parcel falls within '{cone_name}' protected view corridor. The entitled height from Bill 47 may be CAPPED by the view cone — a Tier 1 parcel approved for 20 storeys could be limited to 8-12. This destroys the pro forma.",
                cost_impact="Height cap may reduce buildable sqft by 40-60%",
                verify_url="https://opendata.vancouver.ca/explore/dataset/view-cones/map/",
            ))
            econ_score -= 30
            friction_score += 30
            view_cone_cap = True
    except Exception:
        pass

    # ── 12. Protected trees ──
    try:
        tree_count = await conn.fetchval(
            "SELECT count(*) FROM protected_trees "
            "WHERE ST_DWithin(geom, (SELECT ST_Centroid(geom) FROM parcels WHERE pid = $1), 0.00015)",
            pid
        )
        data_points_available += 1
        if tree_count and tree_count > 0:
            sev = "red" if tree_count >= 4 else "yellow"
            per_tree_cost = "$5K-25K" if tree_count <= 3 else "$10K-30K"
            risk_flags.append(RiskFlag(
                code="PROTECTED_TREES", severity=sev,
                label=f"{tree_count} Protected Tree{'s' if tree_count > 1 else ''}",
                detail=f"{tree_count} large tree(s) (>30cm diameter) within 15m. Vancouver's tree protection bylaw requires arborist reports + removal permits. Large trees can delay permitting by 3-6 months.",
                cost_impact=f"~{per_tree_cost} per tree for arborist report + replacement planting",
                verify_url=f"https://opendata.vancouver.ca/explore/dataset/public-trees/map/?q={addr_encoded}",
            ))
            if tree_count >= 4:
                econ_score -= 10
            friction_score += (5 * min(tree_count, 5))
    except Exception:
        pass

    # ── 13. Building permit activity (competing supply) ──
    try:
        nearby_permits = await conn.fetchval(
            "SELECT count(*) FROM issued_building_permits "
            "WHERE project_value >= 5000000 "
            "AND issue_year >= 2024 "
            "AND ST_DWithin(geom, (SELECT ST_Centroid(geom) FROM parcels WHERE pid = $1), 0.005)",
            pid
        )
        if nearby_permits and nearby_permits > 0:
            if nearby_permits >= 6:
                sev = "red"
                econ_score -= 10
            elif nearby_permits >= 3:
                sev = "yellow"
                econ_score -= 5
            else:
                sev = "green"
            risk_flags.append(RiskFlag(
                code="COMPETING_PERMITS", severity=sev,
                label=f"{nearby_permits} Major Dev Permits Nearby",
                detail=f"{nearby_permits} building permits over $5M issued within 500m since 2024. {'Heavy' if nearby_permits >= 6 else 'Moderate' if nearby_permits >= 3 else 'Low'} competing supply — pre-sale absorption may be {'difficult' if nearby_permits >= 6 else 'competitive' if nearby_permits >= 3 else 'manageable'}.",
                cost_impact="Potential absorption delay: 3-12 months" if nearby_permits >= 3 else None,
                verify_url=f"https://opendata.vancouver.ca/explore/dataset/issued-building-permits/map/?q={addr_encoded}",
            ))
            friction_score += (3 * min(nearby_permits, 6))
    except Exception:
        pass

    # ── 14. Non-market housing proximity ──
    try:
        nmh = await conn.fetchrow(
            "SELECT name, address FROM non_market_housing "
            "WHERE ST_DWithin(geom, (SELECT ST_Centroid(geom) FROM parcels WHERE pid = $1), 0.001)",
            pid
        )
        if nmh:
            on_parcel = await conn.fetchrow(
                "SELECT name FROM non_market_housing "
                "WHERE ST_Intersects(geom, (SELECT geom FROM parcels WHERE pid = $1))",
                pid
            )
            if on_parcel:
                risk_flags.append(RiskFlag(
                    code="NMH_ON_PARCEL", severity="red",
                    label="Non-Market Housing On Parcel",
                    detail=f"Non-market housing '{nmh['name']}' exists on this parcel. City's Rental Replacement Policy may require 1:1 replacement of existing rental units — massive cost adder.",
                    cost_impact="$50K-150K per unit of rental replacement",
                    verify_url="https://opendata.vancouver.ca/explore/dataset/non-market-housing/map/",
                ))
                econ_score -= 25
                friction_score += 25
            else:
                risk_flags.append(RiskFlag(
                    code="NMH_NEARBY", severity="yellow",
                    label="Non-Market Housing Nearby",
                    detail=f"Non-market housing '{nmh['name']}' within 100m. May trigger rental replacement policy review during rezoning.",
                    cost_impact="Potential $50K-150K/unit if rental replacement triggered",
                    verify_url="https://opendata.vancouver.ca/explore/dataset/non-market-housing/map/",
                ))
                friction_score += 10
    except Exception:
        pass

    # ── 15. CD-1 zoning detection ──
    is_cd1 = False
    try:
        cd1 = await conn.fetchrow(
            "SELECT zoning_classification, cd_1_number FROM zoning_districts "
            "WHERE zoning_category = 'CD-1' "
            "AND ST_Intersects(geom, (SELECT geom FROM parcels WHERE pid = $1)) LIMIT 1",
            pid
        )
        if cd1:
            is_cd1 = True
            cd1_num = cd1["cd_1_number"] or "unknown"
            risk_flags.append(RiskFlag(
                code="CD1_ZONING", severity="yellow",
                label=f"CD-1 Zone (Bylaw {cd1_num})",
                detail=f"Parcel is in CD-1 (Comprehensive Development) zone with site-specific bylaw. Standard Bill 47 entitlement calculations may NOT apply — each CD-1 has its own height/FSR/use rules. Manual review of CD-1 Bylaw {cd1_num} required.",
                cost_impact="Entitlement may differ from Bill 47 calculations",
                verify_url=f"https://opendata.vancouver.ca/explore/dataset/zoning-districts-and-labels/table/?q=CD-1+{cd1_num}",
            ))
            friction_score += 15
    except Exception:
        pass

    # ── V3: Business licences (tenant count + environmental risk) ──
    active_licence_count = 0
    nearby_business_types: list[str] = []
    try:
        licences = await conn.fetch(
            "SELECT business_name, business_type FROM business_licences "
            "WHERE ST_DWithin(geom, (SELECT ST_Centroid(geom) FROM parcels WHERE pid = $1), 0.0003) "
            "AND status = 'Issued'",
            pid
        )
        active_licence_count = len(licences)
        nearby_business_types = [r["business_type"] for r in licences if r["business_type"]]

        if active_licence_count > 0:
            data_points_available += 1
            types_preview = ", ".join(set(nearby_business_types[:5]))
            if active_licence_count >= 5:
                risk_flags.append(RiskFlag(
                    code="MANY_TENANTS", severity="red",
                    label=f"{active_licence_count} Active Tenants",
                    detail=f"{active_licence_count} active business licences within 30m: {types_preview}. Significant tenant displacement costs and timeline risk.",
                    cost_impact=f"~${active_licence_count * 40}K displacement + 6-12 month delay",
                ))
                econ_score -= 15
                friction_score += 20
            elif active_licence_count >= 2:
                risk_flags.append(RiskFlag(
                    code="SOME_TENANTS", severity="yellow",
                    label=f"{active_licence_count} Active Tenants",
                    detail=f"{active_licence_count} active business licences within 30m: {types_preview}. Tenant displacement required.",
                    cost_impact=f"~${active_licence_count * 40}K displacement",
                ))
                friction_score += 10
            else:
                risk_flags.append(RiskFlag(
                    code="FEW_TENANTS", severity="yellow",
                    label="1 Active Tenant",
                    detail=f"1 active business licence within 30m: {types_preview}. Minor tenant displacement.",
                    cost_impact="~$40K displacement",
                ))
                friction_score += 5

        # Environmental risk from business types
        from .hidden_costs import ENVIRO_RISK_TYPES
        enviro_businesses = [bt for bt in nearby_business_types
                            if any(rt.upper() in bt.upper() for rt in ENVIRO_RISK_TYPES)]
        if enviro_businesses:
            risk_flags.append(RiskFlag(
                code="ENVIRO_RISK", severity="red",
                label=f"Environmental Risk ({enviro_businesses[0][:25]})",
                detail=f"Business types indicating potential contamination: {', '.join(enviro_businesses[:3])}. Phase 1-3 ESA likely required.",
                cost_impact="$200K-500K remediation",
                verify_url="https://apps.nrs.gov.bc.ca/gwells/registries",
            ))
            econ_score -= 15
            friction_score += 15
    except Exception:
        pass

    # ── 21. Community opposition score ──
    try:
        opposition_factors = 0
        garden = await conn.fetchrow(
            "SELECT name FROM community_gardens "
            "WHERE ST_DWithin(geom, (SELECT ST_Centroid(geom) FROM parcels WHERE pid = $1), 0.002)",
            pid
        )
        if garden:
            opposition_factors += 1
        if any(f.code == "HERITAGE_SITE" for f in risk_flags):
            opposition_factors += 1
        if any(f.code in ("NMH_ON_PARCEL", "NMH_NEARBY") for f in risk_flags):
            opposition_factors += 1

        if opposition_factors >= 3:
            risk_flags.append(RiskFlag(
                code="HIGH_OPPOSITION", severity="red",
                label="High Opposition Zone",
                detail=f"{opposition_factors} community sensitivity factors (heritage, non-market housing, community gardens). Expect strong NIMBY opposition during public hearings — could add 6-12 months to rezoning.",
                cost_impact="6-12 month rezoning delay + legal/consulting costs",
            ))
            friction_score += 20
        elif opposition_factors >= 1:
            risk_flags.append(RiskFlag(
                code="MODERATE_OPPOSITION", severity="yellow",
                label=f"Community Sensitivity ({opposition_factors} factor{'s' if opposition_factors > 1 else ''})",
                detail=f"{opposition_factors} community sensitivity factor(s) nearby. May face moderate opposition during public hearings — budget 3-6 extra months.",
                cost_impact="3-6 month potential delay",
            ))
            friction_score += 10
    except Exception:
        pass

    # ══════════════════════════════════════════════════════════
    # STRUCTURAL CHECKS
    # ══════════════════════════════════════════════════════════

    # ── 7. Lot adequacy ──
    lot_adequate = True
    lot_note = None
    min_lot_req = None
    if best and lot_area:
        construction_type = _determine_construction_type(best.entitled_storeys)
        min_req = MIN_LOT_SIZE.get(construction_type, 250)
        min_lot_req = Decimal(str(min_req))
        if float(lot_area) < min_req:
            lot_adequate = False
            lot_note = f"Lot ({float(lot_area):.0f} sqm) is below minimum {min_req} sqm for {construction_type.replace('_', ' ')}. Assembly with adjacent lot(s) required."
            risk_flags.append(RiskFlag(
                code="LOT_TOO_SMALL", severity="yellow",
                label="Assembly Required",
                detail=lot_note,
                cost_impact="Assembly adds 15-25% to land cost + 2-5 year timeline",
            ))
            econ_score -= 15
            friction_score += 15
        elif float(lot_area) >= min_req * 1.5:
            risk_flags.append(RiskFlag(
                code="LOT_OVERSIZED", severity="green",
                label="Standalone Development Viable",
                detail=f"Lot ({float(lot_area):.0f} sqm) is well above minimum {min_req} sqm — no assembly needed.",
            ))

    # ── 8. Supply saturation ──
    competing = 0
    saturation = "low"
    if best:
        try:
            competing = await conn.fetchval(
                """SELECT count(DISTINCT p.pid) FROM parcels p
                   JOIN toa_buffers b ON ST_Intersects(p.geom, b.geom)
                   WHERE b.tier = $1 AND b.station_id = (
                       SELECT station_id FROM toa_buffers b2
                       JOIN parcels p2 ON ST_Intersects(p2.geom, b2.geom)
                       WHERE p2.pid = $2 AND b2.tier = $1 LIMIT 1
                   ) AND p.pid != $2
                   AND p.lot_area_sqm BETWEEN 200 AND 10000""",
                best.tier.value, pid
            ) or 0
        except Exception:
            competing = 0
        if competing > 200:
            saturation = "high"
            econ_score -= 5
        elif competing > 50:
            saturation = "moderate"

    # ══════════════════════════════════════════════════════════
    # V3: THREE-SCENARIO PRO FORMA + HIDDEN COSTS
    # ══════════════════════════════════════════════════════════

    pro_forma = None
    three_scenario = None
    gap_analysis = None
    hidden_cost_items: list[tuple[str, int, str]] = []

    if best and lot_area:
        # Calculate hidden costs
        current_zoning = parcel.get("current_zoning", None) if hasattr(parcel, 'get') else None
        try:
            current_zoning = parcel["current_zoning"]
        except (KeyError, TypeError):
            current_zoning = None

        hidden_total, hidden_cost_items = calculate_total_hidden_costs(
            improvement_value=impr_val,
            year_built=year_built,
            lot_area_sqm=lot_area,
            entitled_storeys=best.entitled_storeys,
            nearby_business_types=nearby_business_types,
            active_licence_count=active_licence_count,
            current_zoning=current_zoning,
            is_cd1=is_cd1,
            neighborhood=get_neighborhood_label(geo_local_area),
        )

        # Three-scenario pro forma
        three_scenario = _compute_three_scenarios(
            lot_area_sqm=lot_area,
            entitled_fsr=best.entitled_fsr,
            entitled_storeys=best.entitled_storeys,
            asking_price=asking,
            assessed_value=assessed,
            neighborhood=geo_local_area,
            hidden_costs_total=hidden_total,
            hidden_cost_items=hidden_cost_items,
        )

        # Backward-compatible V2 pro forma from BASE case
        pro_forma = _build_v2_pro_forma_from_base(
            three_scenario.base, geo_local_area, neighborhood_mult
        )
        pro_forma.asking_price = asking
        pro_forma.assessed_value = assessed

        # Gap analysis narrative
        gap_analysis = _generate_gap_analysis(
            three_scenario.bull, three_scenario.base, hidden_cost_items
        )

        # ── V3 grading: use BASE case alpha ──
        base_alpha = three_scenario.base.true_alpha

        if three_scenario.base.residual_land_value < 0:
            risk_flags.append(RiskFlag(
                code="NEGATIVE_RESIDUAL", severity="red",
                label="Unviable (Base Case)",
                detail=f"Base case residual land value is negative ({_fmt(three_scenario.base.residual_land_value)}). After realistic costs, this deal doesn't work.",
                cost_impact="Deal is not viable at current market conditions",
            ))
            econ_score -= 30
        elif base_alpha < 0 and asking:
            # Check if bull case is positive (matters for narrative)
            bull_alpha = three_scenario.bull.true_alpha
            if bull_alpha > 0:
                risk_flags.append(RiskFlag(
                    code="BULL_ONLY_VIABLE", severity="yellow",
                    label="Only Viable in Bull Case",
                    detail=f"Bull case alpha: {_fmt(bull_alpha)}, but base case alpha: {_fmt(base_alpha)}. This deal only works if you beat industry benchmarks on every cost line.",
                    cost_impact=f"Base case gap: {_fmt(abs(base_alpha))} negative",
                ))
                econ_score -= 15
            else:
                risk_flags.append(RiskFlag(
                    code="OVERPRICED", severity="red",
                    label="Overpriced for Development",
                    detail=f"Asking price ({_fmt(asking)}) exceeds developer residual even in bull case ({_fmt(three_scenario.bull.residual_land_value)}). No rational developer would pay this.",
                    cost_impact=f"Negative alpha across all scenarios",
                ))
                econ_score -= 20
        elif base_alpha > 1_000_000:
            risk_flags.append(RiskFlag(
                code="STRONG_BASE_ALPHA", severity="green",
                label="Strong Base Case Alpha",
                detail=f"Even after realistic costs (contingency, hidden costs, absorption discount), {_fmt(base_alpha)} of true alpha remains. This is a real opportunity.",
            ))
        elif base_alpha > 0:
            risk_flags.append(RiskFlag(
                code="MODERATE_BASE_ALPHA", severity="green",
                label="Moderate Base Case Alpha",
                detail=f"Base case shows {_fmt(base_alpha)} alpha after hidden costs. Viable but tight — execution excellence required.",
            ))

    # ── 18. Holding cost warning ──
    if pro_forma and pro_forma.holding_cost and pro_forma.holding_cost > 100_000:
        risk_flags.append(RiskFlag(
            code="HIGH_HOLDING_COST", severity="yellow",
            label=f"Holding Cost: {_fmt(pro_forma.holding_cost)}",
            detail=f"Estimated {pro_forma.holding_months}-month predevelopment hold at 6.5% interest = {_fmt(pro_forma.holding_cost)}. This is already factored into the residual but represents real cash at risk.",
            cost_impact=f"{_fmt(pro_forma.holding_cost)} over {pro_forma.holding_months} months",
        ))

    # ── View cone pro forma warning ──
    if view_cone_cap and pro_forma:
        risk_flags.append(RiskFlag(
            code="VIEW_CONE_PROFORMA", severity="red",
            label="Pro Forma Unreliable (View Cone)",
            detail="The pro forma above uses Bill 47 entitled height, but this parcel is in a protected view cone. Actual buildable height may be significantly less — treat these numbers as a maximum. Verify with City planning before any LOI.",
            cost_impact="Actual residual may be 40-60% lower",
        ))

    # ══════════════════════════════════════════════════════════
    # V3: EXECUTION DIFFICULTY SCORE
    # ══════════════════════════════════════════════════════════

    exec_score, exec_factors = _calculate_execution_difficulty(
        risk_flags=risk_flags,
        lot_adequate=lot_adequate,
        is_cd1=is_cd1,
        active_licence_count=active_licence_count,
        neighborhood=get_neighborhood_label(geo_local_area),
        entitled_storeys=best.entitled_storeys if best else 0,
    )

    # ══════════════════════════════════════════════════════════
    # DUE DILIGENCE CHECKLIST
    # ══════════════════════════════════════════════════════════

    due_diligence: list[dict] = [
        {
            "item": "Title Search (LTSA)",
            "description": "Check for Certificates of Pending Litigation (CPL), restrictive covenants, statutory rights of way, existing mortgages/liens",
            "url": "https://ltsa.ca/products-services/title-search/",
            "priority": "critical",
        },
        {
            "item": "Strata Status (if applicable)",
            "description": "Strata dissolution requires 80% vote — verify strata status and any pending litigation",
            "url": "https://ltsa.ca/products-services/strata-plan-search/",
            "priority": "critical",
        },
        {
            "item": "Environmental Site Assessment",
            "description": "Check BC Contaminated Sites Registry. Former gas stations, dry cleaners, industrial sites require Phase 1/2/3 ESA",
            "url": "https://apps.nrs.gov.bc.ca/gwells/registries",
            "priority": "high",
        },
        {
            "item": "BC Assessment Official Lookup",
            "description": "Verify assessed value and property details directly with BC Assessment",
            "url": f"https://www.bcassessment.ca/Property/Search/GetByAddress?addr={addr_encoded}+Vancouver",
            "priority": "high",
        },
        {
            "item": "City Development Application Status",
            "description": "Check if any development/rezoning applications are already in progress for this or adjacent parcels",
            "url": f"https://shapeyourcity.ca/search?query={addr_encoded}",
            "priority": "medium",
        },
        {
            "item": "Soil & Geotechnical",
            "description": "Vancouver's soft soils (especially False Creek flats, Fraser River delta) may require deep foundations — $200K-1M+ adder",
            "url": None,
            "priority": "medium",
        },
    ]

    # ══════════════════════════════════════════════════════════
    # COMPOSITE SCORING — V3 GRADES ON BASE CASE
    # ══════════════════════════════════════════════════════════

    econ_score = max(0, min(100, econ_score))

    # Friction level
    if friction_score >= 50:
        friction_level = "high"
    elif friction_score >= 20:
        friction_level = "medium"
    else:
        friction_level = "low"

    # Confidence stars
    if data_points_available >= 8:
        confidence = "high"
        confidence_stars = 3
    elif data_points_available >= 5:
        confidence = "medium"
        confidence_stars = 2
    else:
        confidence = "low"
        confidence_stars = 1

    # Count flags by severity
    red_count = sum(1 for f in risk_flags if f.severity == "red")
    yellow_count = sum(1 for f in risk_flags if f.severity == "yellow")
    green_count = sum(1 for f in risk_flags if f.severity == "green")

    # V3 Grade: based on BASE case economics
    if red_count >= 3 or econ_score < 20:
        grade = "F"
    elif red_count >= 2 or econ_score < 40:
        grade = "D"
    elif red_count >= 1 or econ_score < 60:
        grade = "C"
    elif econ_score < 80:
        grade = "B"
    else:
        grade = "A"

    # One-liner
    one_liner = _build_one_liner(grade, friction_level, risk_flags, three_scenario, best, geo_local_area, exec_score)

    return DealValidation(
        deal_grade=grade,
        deal_score=econ_score,
        confidence_level=confidence,
        confidence_stars=confidence_stars,
        friction_level=friction_level,
        friction_score=friction_score,
        price_per_buildable_sqft=price_per_bsf,
        assessed_ratio=assessed_ratio,
        land_to_total_ratio=land_to_total,
        lot_adequate=lot_adequate,
        lot_adequacy_note=lot_note,
        min_lot_sqm_required=min_lot_req,
        competing_parcels=competing,
        supply_saturation=saturation,
        risk_flags=risk_flags,
        red_flag_count=red_count,
        yellow_flag_count=yellow_count,
        green_flag_count=green_count,
        pro_forma=pro_forma,
        three_scenario_proforma=three_scenario,
        gap_analysis=gap_analysis,
        execution_difficulty_score=exec_score,
        execution_difficulty_factors=exec_factors,
        one_liner=one_liner,
        due_diligence_checklist=due_diligence,
        neighborhood=get_neighborhood_label(geo_local_area),
    )


def _fmt(n) -> str:
    """Format a number as $XM or $XK."""
    if n is None:
        return "N/A"
    n = int(n)
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:,.1f}M"
    if abs(n) >= 1_000:
        return f"${n/1_000:,.0f}K"
    return f"${n:,}"


def _build_one_liner(grade, friction, flags, three_scenario, best, neighborhood, exec_score) -> str:
    """Generate V3 executive summary with scenario + execution awareness."""
    reds = [f for f in flags if f.severity == "red"]
    greens = [f for f in flags if f.severity == "green"]
    area_str = f" ({neighborhood})" if neighborhood else ""
    exec_str = f" Execution: {exec_score}/10." if exec_score > 0 else ""

    if grade == "F":
        issues = ", ".join(f.label for f in reds[:2])
        return f"Not recommended{area_str}. Critical issues: {issues}.{exec_str}"
    elif grade == "D":
        issue = reds[0].label if reds else "Multiple yellow flags"
        return f"High risk{area_str}. {issue} requires resolution before proceeding.{exec_str}"
    elif grade == "C":
        friction_str = f" Friction: {friction}." if friction != "low" else ""
        if three_scenario and three_scenario.base.true_alpha > 0:
            return (
                f"Moderate opportunity{area_str} "
                f"(base case: {_fmt(three_scenario.base.true_alpha)} alpha, "
                f"bull: {_fmt(three_scenario.bull.true_alpha)}) "
                f"but {len(flags)} risk factors need investigation.{friction_str}{exec_str}"
            )
        return f"Moderate risk{area_str}. {len(flags)} factors need investigation.{friction_str}{exec_str}"
    elif grade == "B":
        if three_scenario:
            alpha_str = f" Base alpha: {_fmt(three_scenario.base.true_alpha)}."
        else:
            alpha_str = ""
        tier_str = f"Tier {best.tier.value}" if best else ""
        friction_str = f" Friction: {friction}." if friction != "low" else ""
        return f"Good {tier_str} opportunity{area_str}.{alpha_str} Minor risks manageable.{friction_str}{exec_str}"
    else:  # A
        if three_scenario:
            base_alpha = _fmt(three_scenario.base.true_alpha)
        else:
            base_alpha = "N/A"
        positives = ", ".join(g.label for g in greens[:2]) if greens else "clean profile"
        return f"Strong opportunity{area_str} — {base_alpha} base case alpha. {positives}.{exec_str}"
