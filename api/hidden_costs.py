"""
VanCity Lens — Hidden Cost Estimation Engine (V3)
Converts risk flags into dollar amounts for realistic pro forma scenarios.

These are heuristic estimates — good enough for pre-screening, not for closing.
Each function returns (cost_dollars, explanation_string).
"""

from decimal import Decimal
from typing import Optional


# ── Environmental Risk Business Types ────────────────────────
# Business types that indicate potential soil contamination
ENVIRO_RISK_TYPES = {
    "Gasoline Station",
    "Gas Station",
    "Service Station",
    "Auto Service",
    "Auto Repair",
    "Auto Body",
    "Auto Painting",
    "Dry Cleaning",
    "Dry Cleaning Plant",
    "Laundry Plant",
    "Chemical",
    "Printer",
    "Printing",
    "Photo Processing",
    "Metal",
    "Welding",
    "Machine Shop",
    "Manufacturing",
}


def estimate_demolition(
    improvement_value: Optional[int],
    year_built: Optional[int],
    lot_area_sqm: Decimal,
    entitled_storeys: int,
) -> tuple[int, str]:
    """
    Estimate demolition cost based on structure characteristics.

    Heuristics:
    - Base: $15-25/sqft of existing structure footprint
    - Older structures (pre-1960): +20% for asbestos abatement
    - Larger lots: scale up for more structure/parking to demo
    - If improvement_value very low (< $200K): minimal demo, just site clearing

    Returns (cost, explanation).
    """
    lot_sqft = float(lot_area_sqm) * 10.7639

    # If improvement is trivial, minimal demo cost
    if improvement_value and improvement_value < 200_000:
        cost = 50_000
        return cost, f"Minimal demolition (improvement only ${improvement_value:,}) — est. $50K site clearing"

    # Base demolition: assume existing building covers ~40% of lot
    existing_footprint = lot_sqft * 0.4
    base_rate = 20  # $/sqft

    # Asbestos premium for pre-1980 buildings (VCL-44 / TEST-009: fixed ordering)
    # IMPORTANT: Check pre-1960 FIRST — pre-1960 is a subset of pre-1980,
    # so the broader check must come second to avoid shadowing the higher premium.
    asbestos_mult = 1.0
    asbestos_note = ""
    if year_built and year_built < 1960:
        asbestos_mult = 1.40
        asbestos_note = " (includes 40% asbestos/hazmat premium for pre-1960 structure)"
    elif year_built and year_built < 1980:
        asbestos_mult = 1.25
        asbestos_note = " (includes 25% asbestos abatement premium for pre-1980 structure)"

    # Scale by lot size — bigger lots have more to demolish
    if lot_sqft > 15_000:
        base_rate = 25
    elif lot_sqft > 8_000:
        base_rate = 22

    cost = int(existing_footprint * base_rate * asbestos_mult)
    # Floor at $150K, cap at $1.2M for single-site
    cost = max(150_000, min(cost, 1_200_000))

    year_str = f" ({year_built} structure)" if year_built else ""
    return cost, f"Demolition of existing{year_str}: ~{existing_footprint:,.0f} sqft × ${base_rate}/sqft{asbestos_note}"


def estimate_environmental(
    nearby_business_types: list[str],
) -> tuple[int, str]:
    """
    Estimate environmental remediation cost based on nearby business types.

    If a gas station, dry cleaner, auto shop etc. operated on/near the site,
    Phase 1/2/3 Environmental Site Assessment + remediation is likely needed.

    Returns (cost, explanation).
    """
    # Check for high-risk business types
    risk_businesses = []
    for btype in nearby_business_types:
        btype_upper = btype.upper() if btype else ""
        for risk_type in ENVIRO_RISK_TYPES:
            if risk_type.upper() in btype_upper or btype_upper in risk_type.upper():
                risk_businesses.append(btype)
                break

    if not risk_businesses:
        return 0, ""

    # Gas stations are the worst — underground storage tank remediation
    is_gas_station = any("GAS" in b.upper() or "FUEL" in b.upper() or "SERVICE STATION" in b.upper()
                         for b in risk_businesses)

    if is_gas_station:
        cost = 500_000
        return cost, "Environmental remediation (former gas station/fuel site): Phase 1-3 ESA + UST removal + soil remediation — est. $500K"

    # Dry cleaners — solvent contamination
    is_dry_cleaner = any("DRY CLEAN" in b.upper() or "LAUNDRY PLANT" in b.upper()
                         for b in risk_businesses)
    if is_dry_cleaner:
        cost = 350_000
        return cost, "Environmental remediation (former dry cleaner): PERC solvent contamination likely — est. $350K"

    # Other industrial — moderate risk
    cost = 200_000
    types_str = ", ".join(risk_businesses[:3])
    return cost, f"Environmental assessment ({types_str}): Phase 1-2 ESA + potential remediation — est. $200K"


def estimate_tenant_displacement(
    active_licence_count: int,
) -> tuple[int, str]:
    """
    Estimate tenant displacement costs.

    Vancouver's Tenant Relocation Policy requires:
    - Notice period (4-6 months for commercial)
    - Relocation assistance ($40K-60K per commercial tenant)
    - Residential tenants: even more ($10K-20K per unit under RTA)

    We use business licences as a proxy for commercial tenants.
    """
    if active_licence_count <= 0:
        return 0, ""

    per_tenant = 40_000
    cost = active_licence_count * per_tenant
    return cost, f"{active_licence_count} active business licence(s) × $40K displacement/relocation = ${cost:,}"


def estimate_rezoning_cost(
    current_zoning: Optional[str],
    is_cd1: bool = False,
) -> tuple[int, str]:
    """
    Estimate rezoning application costs.

    CD-1 (Comprehensive Development) zones require full rezoning — $250K+ in
    consultant/legal fees + 12-24 month timeline.

    Standard rezoning under Bill 47 should be ministerial (no rezoning needed),
    but some complex cases still require it.
    """
    if is_cd1:
        return 250_000, "CD-1 zone requires full site-specific rezoning: planning consultant + legal + hearings — est. $250K + 12-24 months"

    # Check for other complex zoning scenarios
    if current_zoning and ("CD" in current_zoning.upper() or "FCCDD" in current_zoning.upper()):
        return 200_000, f"Complex zoning ({current_zoning}) may require rezoning even under Bill 47 — est. $200K"

    return 0, ""


def estimate_soft_soil(
    neighborhood: Optional[str],
    entitled_storeys: int,
) -> tuple[int, str]:
    """
    Estimate soft soil / geotechnical surcharge.

    False Creek flats, Olympic Village, and Fraser River delta areas have
    soft/liquefiable soils that require deep pile foundations for highrises.
    Adds $500K-$2M for concrete highrise construction.

    Only applies to buildings >6 storeys (concrete construction).
    """
    from .neighborhood_economics import SOFT_SOIL_ZONES

    if not neighborhood or entitled_storeys < 7:
        return 0, ""

    # Check if in soft soil zone
    neighborhood_upper = neighborhood.upper().strip()
    is_soft_soil = any(zone.upper() in neighborhood_upper or neighborhood_upper in zone.upper()
                       for zone in SOFT_SOIL_ZONES)

    if not is_soft_soil:
        return 0, ""

    if entitled_storeys >= 20:
        cost = 1_500_000
        return cost, f"Deep pile foundation required ({neighborhood}, {entitled_storeys} storeys): soft soil + seismic — est. $1.5M"
    elif entitled_storeys >= 13:
        cost = 800_000
        return cost, f"Enhanced foundation ({neighborhood}, {entitled_storeys} storeys): soft soil surcharge — est. $800K"
    else:
        cost = 400_000
        return cost, f"Foundation upgrade ({neighborhood}, {entitled_storeys} storeys): soft soil zone — est. $400K"


def calculate_total_hidden_costs(
    improvement_value: Optional[int],
    year_built: Optional[int],
    lot_area_sqm: Decimal,
    entitled_storeys: int,
    nearby_business_types: list[str],
    active_licence_count: int,
    current_zoning: Optional[str],
    is_cd1: bool,
    neighborhood: Optional[str],
) -> tuple[int, list[tuple[str, int, str]]]:
    """
    Calculate all hidden costs and return total + itemized breakdown.

    Returns: (total_cost, [(category, cost, explanation), ...])
    """
    items: list[tuple[str, int, str]] = []

    demo_cost, demo_note = estimate_demolition(improvement_value, year_built, lot_area_sqm, entitled_storeys)
    if demo_cost > 0:
        items.append(("Demolition", demo_cost, demo_note))

    enviro_cost, enviro_note = estimate_environmental(nearby_business_types)
    if enviro_cost > 0:
        items.append(("Environmental", enviro_cost, enviro_note))

    tenant_cost, tenant_note = estimate_tenant_displacement(active_licence_count)
    if tenant_cost > 0:
        items.append(("Tenant Displacement", tenant_cost, tenant_note))

    rezone_cost, rezone_note = estimate_rezoning_cost(current_zoning, is_cd1)
    if rezone_cost > 0:
        items.append(("Rezoning", rezone_cost, rezone_note))

    soil_cost, soil_note = estimate_soft_soil(neighborhood, entitled_storeys)
    if soil_cost > 0:
        items.append(("Soft Soil / Foundation", soil_cost, soil_note))

    total = sum(cost for _, cost, _ in items)
    return total, items
