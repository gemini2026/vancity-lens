"""
VanCity Lens — Neighborhood Revenue Adjustment
Replaces flat $/sqft with area-specific multipliers based on real market data.
"""

from decimal import Decimal

# Neighborhood revenue multipliers based on 2024-2025 Vancouver pre-sale data
# Source: Vancouver Real Estate Board area benchmarks, pre-sale comparables
NEIGHBORHOOD_MULTIPLIERS: dict[str, Decimal] = {
    # West Side premium
    "West End": Decimal("1.25"),
    "Coal Harbour": Decimal("1.25"),
    "Downtown": Decimal("1.20"),
    "Kitsilano": Decimal("1.20"),
    "West Point Grey": Decimal("1.20"),
    "Kerrisdale": Decimal("1.15"),
    "Dunbar-Southlands": Decimal("1.15"),
    "Shaughnessy": Decimal("1.15"),
    "Arbutus-Ridge": Decimal("1.10"),
    "South Cambie": Decimal("1.10"),
    "Fairview": Decimal("1.10"),
    # Central / Transit-rich
    "Mount Pleasant": Decimal("1.10"),
    "Riley Park": Decimal("1.05"),
    "Cambie": Decimal("1.05"),
    "Oakridge": Decimal("1.05"),
    "Marpole": Decimal("1.00"),
    # East side
    "Grandview-Woodland": Decimal("1.00"),
    "Strathcona": Decimal("0.95"),
    "Hastings-Sunrise": Decimal("0.95"),
    "Kensington-Cedar Cottage": Decimal("0.95"),
    "Renfrew-Collingwood": Decimal("0.90"),
    "Killarney": Decimal("0.90"),
    "Victoria-Fraserview": Decimal("0.90"),
    "Sunset": Decimal("0.90"),
    "Knight": Decimal("0.90"),
    # South / Value
    "South Vancouver": Decimal("0.85"),
    "Musqueam": Decimal("0.95"),
}

# Fallback: geo_local_area values from Vancouver Open Data may use slightly
# different names. This maps common variations.
AREA_ALIASES: dict[str, str] = {
    "WEST END": "West End",
    "DOWNTOWN": "Downtown",
    "KITSILANO": "Kitsilano",
    "MOUNT PLEASANT": "Mount Pleasant",
    "FAIRVIEW": "Fairview",
    "KERRISDALE": "Kerrisdale",
    "DUNBAR-SOUTHLANDS": "Dunbar-Southlands",
    "SHAUGHNESSY": "Shaughnessy",
    "ARBUTUS-RIDGE": "Arbutus-Ridge",
    "ARBUTUS RIDGE": "Arbutus-Ridge",
    "SOUTH CAMBIE": "South Cambie",
    "RILEY PARK": "Riley Park",
    "GRANDVIEW-WOODLAND": "Grandview-Woodland",
    "STRATHCONA": "Strathcona",
    "HASTINGS-SUNRISE": "Hastings-Sunrise",
    "KENSINGTON-CEDAR COTTAGE": "Kensington-Cedar Cottage",
    "RENFREW-COLLINGWOOD": "Renfrew-Collingwood",
    "KILLARNEY": "Killarney",
    "VICTORIA-FRASERVIEW": "Victoria-Fraserview",
    "SUNSET": "Sunset",
    "MARPOLE": "Marpole",
    "OAKRIDGE": "Oakridge",
    "SOUTH VANCOUVER": "South Vancouver",
    "WEST POINT GREY": "West Point Grey",
    "KNIGHT": "Knight",
    "MUSQUEAM": "Musqueam",
}


def get_neighborhood_multiplier(geo_local_area: str | None) -> Decimal:
    """
    Get the revenue multiplier for a neighborhood.
    Returns Decimal("1.00") if area is unknown.
    """
    if not geo_local_area:
        return Decimal("1.00")

    # Try exact match first
    if geo_local_area in NEIGHBORHOOD_MULTIPLIERS:
        return NEIGHBORHOOD_MULTIPLIERS[geo_local_area]

    # Try alias lookup
    canonical = AREA_ALIASES.get(geo_local_area.upper().strip())
    if canonical and canonical in NEIGHBORHOOD_MULTIPLIERS:
        return NEIGHBORHOOD_MULTIPLIERS[canonical]

    # Try case-insensitive partial match
    upper_area = geo_local_area.upper().strip()
    for name, mult in NEIGHBORHOOD_MULTIPLIERS.items():
        if name.upper() in upper_area or upper_area in name.upper():
            return mult

    return Decimal("1.00")


# ── Soft Soil Zones ─────────────────────────────────────────
# Areas with known soft/liquefiable soils requiring enhanced foundations
# Source: Vancouver Geotechnical Database, BC Building Code seismic Class E/F
SOFT_SOIL_ZONES: list[str] = [
    "False Creek",
    "Olympic Village",
    "Southeast False Creek",
    "Mount Pleasant",  # southern portion near False Creek
    "Strathcona",  # eastern False Creek flats
    "Marpole",  # Fraser River delta soils
    "South Vancouver",  # Fraser River delta
    "Victoria-Fraserview",  # Fraser River floodplain
    "Killarney",  # delta edge
    "Sunset",  # delta fringe
]


# ── Three-Scenario Escalation Factors ───────────────────────
# Used by V3 pro forma to create Bull / Base / Bear scenarios
SCENARIO_FACTORS = {
    "bull": {
        "absorption_discount": Decimal("0.00"),  # No presale discount
        "hard_cost_inflation": Decimal("0.00"),  # No cost escalation
        "contingency": Decimal("0.00"),  # No contingency
        "marketing_sales": Decimal("0.00"),  # No marketing cost
        "hidden_cost_multiplier": Decimal("0.00"),  # Ignore hidden costs
        "timeline_extension_months": 0,  # No delays
    },
    "base": {
        "absorption_discount": Decimal("0.05"),  # 5% presale discount
        "hard_cost_inflation": Decimal("0.05"),  # 5% cost escalation
        "contingency": Decimal("0.07"),  # 7% contingency
        "marketing_sales": Decimal("0.03"),  # 3% marketing
        "hidden_cost_multiplier": Decimal("1.00"),  # Full hidden costs
        "timeline_extension_months": 6,  # +6 months
    },
    "bear": {
        "absorption_discount": Decimal("0.10"),  # 10% presale discount
        "hard_cost_inflation": Decimal("0.10"),  # 10% cost escalation
        "contingency": Decimal("0.07"),  # 7% contingency (same as base)
        "marketing_sales": Decimal("0.03"),  # 3% marketing (same as base)
        "hidden_cost_multiplier": Decimal("1.00"),  # Full hidden costs
        "timeline_extension_months": 12,  # +12 months
    },
}


def get_neighborhood_label(geo_local_area: str | None) -> str:
    """Get the canonical neighborhood name for display."""
    if not geo_local_area:
        return "Unknown"
    canonical = AREA_ALIASES.get(geo_local_area.upper().strip())
    return canonical or geo_local_area


# Holding cost parameters
INTEREST_RATE = Decimal("0.065")  # 6.5% — current Canadian prime + developer spread

# Holding period estimates by construction type (months)
HOLDING_PERIODS: dict[str, int] = {
    "concrete_highrise": 30,  # rezoning + permit + preconstruction
    "woodframe_midrise": 24,
    "woodframe_lowrise": 18,
}


def compute_holding_cost(
    land_cost: int,
    construction_type: str,
) -> tuple[int, int]:
    """
    Compute holding cost (interest on land during pre-development).
    Returns (holding_cost_dollars, holding_months).
    """
    months = HOLDING_PERIODS.get(construction_type, 24)
    # Simple interest: principal × rate × time
    holding_cost = int(land_cost * float(INTEREST_RATE) * months / 12)
    return holding_cost, months
