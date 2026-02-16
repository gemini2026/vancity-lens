"""
VanCity Lens — Bill 47 Entitlement Engine
Core business logic: spatial query → domain model → API response.
"""

import re
from decimal import Decimal
from typing import Optional

import asyncpg

from .models import (
    DataQualityWarning,
    DataSource,
    ParcelEntitlementResponse,
    SourceAttribution,
    StationEntitlement,
    TOATier,
    ValueEstimate,
)
from .bill44_entitlement import compute_bill44
from .community_plan_rules import compute_community_plan_bonus
from .setback_rules import compute_setbacks
from .validation import compute_validation

from datetime import datetime

# DV-HBU-001: PID format — 9 digits, optionally separated by hyphens (NNN-NNN-NNN)
_PID_PATTERN = re.compile(r"^\d{3}-?\d{3}-?\d{3}$")

# AC-HBU-007: Market data assumptions last verified date
MARKET_DATA_DATE = "2025-Q4"

# Sprint 10.2: Multi-source conflict precedence
# When multiple sources provide conflicting data for the same field,
# the higher-precedence source wins. Higher number = higher priority.
SOURCE_PRECEDENCE = {
    "BC Assessment Authority": 100,   # Government authority — highest
    "BC Assessment via Vancouver Open Data": 90,  # BCA data via CoV portal
    "Bill 47 — Housing Statutes (TOA) Amendment Act, 2023": 85,  # Legislation
    "TransLink GTFS": 80,            # Official transit data
    "City of Vancouver Open Data": 70,  # CoV datasets
    "Vancouver Open Data": 70,        # Alias
    "CMHC Housing Market Indicators": 60,
    "Statistics Canada Census API": 60,
    "BC Ministry of Environment": 55,
    "REW.ca Listings": 40,           # Commercial listing — lower trust
    "VanCity Lens Model": 30,        # Our own calculations — lowest
}


def resolve_source_conflict(
    field: str,
    values: list[dict],
) -> dict:
    """Resolve conflicting values from multiple sources using precedence.

    Each value dict: {"value": ..., "origin": str, "confidence": str}
    Returns the winning value dict with conflict_note added.
    """
    if not values:
        return {}
    if len(values) == 1:
        return values[0]

    # Sort by precedence (highest first)
    ranked = sorted(
        values,
        key=lambda v: SOURCE_PRECEDENCE.get(v.get("origin", ""), 0),
        reverse=True,
    )
    winner = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None

    if runner_up and winner.get("value") != runner_up.get("value"):
        winner["conflict_note"] = (
            f"Conflict resolved: {winner['origin']} (precedence "
            f"{SOURCE_PRECEDENCE.get(winner.get('origin', ''), 0)}) "
            f"preferred over {runner_up['origin']} "
            f"(precedence {SOURCE_PRECEDENCE.get(runner_up.get('origin', ''), 0)})"
        )
    return winner

# DV-HBU-005: Storey-to-metres conversion constants
_GROUND_FLOOR_HEIGHT_M = Decimal("3.5")  # commercial ground floor
_UPPER_FLOOR_HEIGHT_M = Decimal("3.0")   # residential upper floors


def _storeys_to_metres(storeys: int) -> Decimal:
    """Convert storeys to metres: 3.5m ground floor + 3.0m per additional storey."""
    if storeys <= 0:
        return Decimal("0")
    if storeys == 1:
        return _GROUND_FLOOR_HEIGHT_M
    return _GROUND_FLOOR_HEIGHT_M + _UPPER_FLOOR_HEIGHT_M * (storeys - 1)


def validate_pid_format(pid: str) -> str:
    """DV-HBU-001: Validate PID is 9-digit NNN-NNN-NNN format. Returns normalized PID."""
    if not _PID_PATTERN.match(pid):
        raise InvalidPIDFormatError(pid)
    return pid

# ── SQL Queries ──────────────────────────────────────────────

SQL_PARCEL_INFO = """
    SELECT pid, civic_address, current_zoning, current_height,
           current_fsr, lot_area_sqm, assessed_value, assessed_year,
           asking_price,
           land_value, improvement_value, year_built, geo_local_area
    FROM parcels
    WHERE pid = $1
"""

SQL_ENTITLEMENTS = """
    WITH parcel AS (
        SELECT geom, current_height, current_fsr
        FROM parcels WHERE pid = $1
    )
    SELECT DISTINCT ON (b.station_name)
        b.station_name,
        b.tier,
        b.max_storeys,
        b.max_fsr,
        ROUND(
            ST_Distance(
                ST_Centroid(p.geom)::geography,
                s.geom::geography
            )::numeric, 1
        ) AS distance_m,
        p.current_height,
        p.current_fsr
    FROM parcel p
    CROSS JOIN toa_buffers b
    JOIN transit_stations s ON s.id = b.station_id
    WHERE ST_Intersects(p.geom, b.geom)
    ORDER BY b.station_name, b.max_storeys DESC
"""

# DV-HBU-008: Query the most restrictive view cone affecting this parcel
SQL_VIEW_CONE_CAP = """
    SELECT MIN(vc.max_height_m) AS view_cone_max_m
    FROM view_cones vc
    WHERE vc.is_active = TRUE
      AND vc.max_height_m IS NOT NULL
      AND ST_Intersects(vc.geom, (SELECT geom FROM parcels WHERE pid = $1))
"""


# F01-A: Heritage site proximity check (uses same ST_DWithin pattern as validation.py)
SQL_HERITAGE_CHECK = """
    SELECT hs.name, hs.category
    FROM heritage_sites hs
    WHERE ST_DWithin(
        hs.geom,
        (SELECT ST_Centroid(geom) FROM parcels WHERE pid = $1),
        0.0003
    )
    ORDER BY hs.category ASC
    LIMIT 1
"""

# F01-B: Market benchmark lookup for neighbourhood-specific revenue/cost data
SQL_MARKET_BENCHMARK = """
    SELECT revenue_per_sf, hard_cost_per_sf, effective_date::text
    FROM market_benchmarks
    WHERE neighbourhood = $1 AND product_type = 'condo'
    LIMIT 1
"""

# ── Engine ───────────────────────────────────────────────────

async def compute_entitlement(
    conn: asyncpg.Connection,
    pid: str,
) -> ParcelEntitlementResponse:
    """
    The core "magic trick":
    Given a parcel PID, return the full Bill 47 entitlement analysis.
    """
    data_warnings: list[DataQualityWarning] = []

    # 1. Fetch parcel info
    parcel = await conn.fetchrow(SQL_PARCEL_INFO, pid)
    if parcel is None:
        raise ParcelNotFoundError(pid)

    # DV-HBU-002: Lot area range check (0–500K SF warning)
    if parcel["lot_area_sqm"]:
        lot_sqft = float(parcel["lot_area_sqm"]) * 10.7639
        if lot_sqft <= 0 or lot_sqft > 500_000:
            data_warnings.append(DataQualityWarning(
                code="LOT_AREA_ANOMALY",
                message=f"Lot area {lot_sqft:,.0f} SF is outside expected range (0–500,000 SF). Possible data error.",
                field="lot_area_sqm",
            ))

    # DV-HBU-003: FSR range check (0.1–15.0)
    if parcel["current_fsr"] is not None:
        fsr_val = float(parcel["current_fsr"])
        if fsr_val < 0.1 or fsr_val > 15.0:
            data_warnings.append(DataQualityWarning(
                code="FSR_ANOMALY",
                message=f"Current FSR {fsr_val} is outside expected range (0.1–15.0). Flagged as anomalous.",
                field="current_fsr",
            ))

    # DV-HBU-006: BC Assessment staleness (>18 months)
    # BC Assessment rolls are typically dated July 1 of the prior year
    now = datetime.now()
    # Assessment year 2024 → data from Jul 2024 → stale after Jan 2026
    assessment_cutoff = datetime(now.year - 1, 1, 1) if now.month >= 7 else datetime(now.year - 2, 7, 1)
    if parcel["assessed_value"] and parcel.get("year_built"):
        # We use year_built as a proxy — if the assessment is old, warn
        pass  # Assessment year not stored separately; we warn based on static date
    # Static staleness: our seed data is from 2024 assessment roll
    _ASSESSMENT_YEAR = 2024
    months_old = (now.year - _ASSESSMENT_YEAR) * 12 + now.month - 7  # July roll date
    if months_old > 18:
        data_warnings.append(DataQualityWarning(
            code="ASSESSMENT_STALE",
            message=f"BC Assessment data is from the {_ASSESSMENT_YEAR} roll year ({months_old} months old). Values may not reflect current market.",
            field="assessed_value",
        ))

    # 2. Run spatial intersection against TOA buffers
    rows = await conn.fetch(SQL_ENTITLEMENTS, pid)

    # 2b. DV-HBU-008: Query view cone hard cap
    view_cone_row = await conn.fetchrow(SQL_VIEW_CONE_CAP, pid)
    view_cone_max_m: Optional[Decimal] = None
    if view_cone_row and view_cone_row["view_cone_max_m"] is not None:
        view_cone_max_m = Decimal(str(view_cone_row["view_cone_max_m"]))

    # 2c. F01-A: Heritage site proximity check
    heritage_row = await conn.fetchrow(SQL_HERITAGE_CHECK, pid)
    heritage_site = heritage_row is not None
    heritage_category: Optional[str] = None
    if heritage_row:
        heritage_category = heritage_row["category"]
        if heritage_category == "A":
            data_warnings.append(DataQualityWarning(
                code="HERITAGE_CATEGORY_A",
                message=f"Heritage Category A designation: '{heritage_row['name']}'. "
                        "Demolition restricted; development requires Heritage Commission approval.",
                field="heritage_site",
            ))
        else:
            data_warnings.append(DataQualityWarning(
                code=f"HERITAGE_CATEGORY_{heritage_category}",
                message=f"Heritage Category {heritage_category} designation: '{heritage_row['name']}'. "
                        "Additional review required; development subject to heritage regulations.",
                field="heritage_site",
            ))

    # 2d. F01-B: Market benchmark lookup for neighbourhood-specific pricing
    neighbourhood = parcel.get("geo_local_area") or ""
    benchmark_row = await conn.fetchrow(SQL_MARKET_BENCHMARK, neighbourhood)
    if benchmark_row:
        price_per_sqft = Decimal(str(benchmark_row["revenue_per_sf"]))
        market_data_date = benchmark_row["effective_date"]
    else:
        price_per_sqft = Decimal("800")
        market_data_date = MARKET_DATA_DATE
        data_warnings.append(DataQualityWarning(
            code="market_data_default",
            message=f"No neighbourhood-specific market data for '{neighbourhood}'. Using default $800/sqft.",
            severity="medium",
            field="price_per_sqft",
        ))

    # 3. Build entitlement objects
    #    CRITICAL: Bill 47 sets MINIMUM density floors, not replacements.
    #    If current zoning already exceeds Bill 47, the parcel keeps its
    #    existing zoning rights. Effective entitlement = max(current, bill47).
    entitlements: list[StationEntitlement] = []
    for row in rows:
        current_h = row["current_height"] or 0
        current_f = row["current_fsr"] or Decimal("0")
        bill47_storeys = row["max_storeys"]
        bill47_fsr = row["max_fsr"]

        # Effective entitlement is the GREATER of current zoning or Bill 47
        effective_storeys = max(bill47_storeys, current_h)
        effective_fsr = max(bill47_fsr, current_f)

        # Uplift is only what Bill 47 ADDS beyond current zoning (never negative)
        storey_uplift = max(0, bill47_storeys - current_h)
        fsr_uplift = max(Decimal("0"), bill47_fsr - current_f)

        # DV-HBU-005: Convert storeys to metres
        entitled_height_m = _storeys_to_metres(effective_storeys)

        # DV-HBU-008: Apply view cone hard cap if it restricts height
        view_cone_capped = False
        ent_view_cone_max_m: Optional[Decimal] = None
        if view_cone_max_m is not None and entitled_height_m > view_cone_max_m:
            view_cone_capped = True
            ent_view_cone_max_m = view_cone_max_m
            # Cap the effective storeys to what the view cone allows
            # Reverse: metres → storeys (3.5m ground + 3.0m per upper)
            if view_cone_max_m <= _GROUND_FLOOR_HEIGHT_M:
                effective_storeys = 1
            else:
                effective_storeys = 1 + int(
                    (view_cone_max_m - _GROUND_FLOOR_HEIGHT_M) / _UPPER_FLOOR_HEIGHT_M
                )
            entitled_height_m = view_cone_max_m
            storey_uplift = max(0, effective_storeys - current_h)

        ent = StationEntitlement(
            station_name=row["station_name"],
            distance_m=row["distance_m"],
            tier=TOATier(row["tier"]),
            bill47_storeys=bill47_storeys,
            bill47_fsr=bill47_fsr,
            entitled_storeys=effective_storeys,
            entitled_fsr=effective_fsr,
            current_storeys=row["current_height"],
            current_fsr=row["current_fsr"],
            storey_uplift=storey_uplift,
            fsr_uplift=fsr_uplift,
            zoning_already_exceeds=current_h > bill47_storeys or current_f > bill47_fsr,
            entitled_height_m=entitled_height_m,
            view_cone_capped=view_cone_capped,
            view_cone_max_m=ent_view_cone_max_m,
        )
        entitlements.append(ent)

    # Sort: best (highest storeys) first
    entitlements.sort(key=lambda e: e.entitled_storeys, reverse=True)
    best = entitlements[0] if entitlements else None
    in_toa = len(entitlements) > 0

    # 4. Value estimate (only if parcel is in a TOA)
    value_estimate: Optional[ValueEstimate] = None
    if best and parcel["lot_area_sqm"]:
        lot_sqm = parcel["lot_area_sqm"]
        buildable_sqft = Decimal(str(lot_sqm)) * best.entitled_fsr * Decimal("10.7639")
        est_value = int(buildable_sqft * price_per_sqft)
        compare_to = parcel["asking_price"] or parcel["assessed_value"] or 0

        # NLA / Unit Count calculations (Phase 2.5)
        # Avg unit sizes: highrise 700sqft, midrise 900sqft, townhouse 1200sqft
        # Efficiency ratios: highrise 0.85, midrise 0.88, townhouse 0.92
        entitled_storeys = best.entitled_storeys
        if entitled_storeys >= 12:
            avg_unit_size, efficiency = 700, Decimal("0.85")
        elif entitled_storeys >= 5:
            avg_unit_size, efficiency = 900, Decimal("0.88")
        else:
            avg_unit_size, efficiency = 1200, Decimal("0.92")

        nla_sqft = int(buildable_sqft * efficiency)
        estimated_units = max(1, int(buildable_sqft / avg_unit_size))

        value_estimate = ValueEstimate(
            lot_area_sqm=lot_sqm,
            entitled_fsr=best.entitled_fsr,
            buildable_sqft=Decimal(str(round(buildable_sqft))),
            estimated_land_value=est_value,
            current_assessed=parcel["assessed_value"],
            asking_price=parcel["asking_price"],
            value_delta=est_value - compare_to,
            price_per_sqft_assumption=price_per_sqft,
            estimated_units=estimated_units,
            nla_sqft=nla_sqft,
        )

    # 5. Build source attribution
    sources = _build_sources(pid, parcel, best, value_estimate)

    # 6. Run validation engine
    validation = await compute_validation(conn, pid, parcel, best, value_estimate)

    # 7. FR-HBU-008: Compute setbacks and site coverage
    setback_result = await compute_setbacks(
        conn,
        parcel["current_zoning"],
        parcel["lot_area_sqm"],
    )
    setbacks_dict = setback_result.model_dump() if setback_result else None

    # 8. FR-HBU-004: Bill 44 small-scale multi-unit housing
    bill44_result = await compute_bill44(
        conn,
        pid,
        parcel["current_zoning"],
        parcel["lot_area_sqm"],
    )
    bill44_dict = bill44_result.model_dump() if bill44_result else None

    # 9. FR-HBU-005: Community plan density bonuses
    cp_result = await compute_community_plan_bonus(
        conn,
        parcel["current_zoning"],
    )
    cp_dict = cp_result.model_dump() if cp_result and cp_result.has_bonus else None

    # Staleness warnings (DV-F01-006, DV-F01-007)
    from datetime import date as date_cls
    current_year = date_cls.today().year
    assessed_year = parcel.get("assessed_year")
    if assessed_year and assessed_year < current_year - 1:
        data_warnings.append(DataQualityWarning(
            code="STALE_ASSESSMENT",
            field="assessed_value",
            message=f"Assessment data is from {assessed_year} -- may not reflect current values",
        ))

    if market_data_date:
        try:
            md = date_cls.fromisoformat(str(market_data_date))
            if (date_cls.today() - md).days > 365:
                data_warnings.append(DataQualityWarning(
                    code="STALE_MARKET_DATA",
                    field="market_data",
                    message=f"Cost data may be outdated -- last updated {market_data_date}",
                ))
        except ValueError:
            pass  # Non-ISO date format (e.g. "2025-Q4") — skip staleness check

    # 10. Parcel Click Enrichment: ILR computation
    land_val = parcel.get("land_value") or None
    improvement_val = parcel.get("improvement_value") or None
    yr_built = parcel.get("year_built") or None
    ilr: Optional[float] = None
    if land_val is not None and improvement_val is not None:
        total = land_val + improvement_val
        if total > 0:
            ilr = round(improvement_val / total, 4)

    return ParcelEntitlementResponse(
        pid=pid,
        civic_address=parcel["civic_address"],
        current_zoning=parcel["current_zoning"],
        in_toa=in_toa,
        entitlements=entitlements,
        best_entitlement=best,
        value_estimate=value_estimate,
        sources=sources,
        validation=validation,
        data_warnings=data_warnings,
        market_data_date=market_data_date,
        setbacks=setbacks_dict,
        bill44=bill44_dict,
        community_plan=cp_dict,
        heritage_site=heritage_site,
        heritage_category=heritage_category,
        land_value=land_val,
        improvement_value=improvement_val,
        year_built=yr_built,
        improvement_to_land_ratio=ilr,
    )


def _build_sources(pid: str, parcel, best, value_estimate) -> SourceAttribution:
    """Build verifiable source links for every data point.

    Each link should point to a page where the user can actually verify
    the specific data point — not a generic dataset landing page.
    """
    clean_pid = pid.replace("-", "")
    addr = parcel["civic_address"] or ""
    addr_encoded = addr.replace(" ", "+")
    sources = []

    # PID — link to the exact parcel record in Vancouver Open Data
    sources.append(DataSource(
        field="pid",
        label="Parcel ID (PID)",
        value=pid,
        origin="Vancouver Open Data",
        confidence="verified",
        url=f"https://opendata.vancouver.ca/explore/dataset/property-parcel-polygons/table/?refine.site_id={clean_pid}",
        note=f"BC Land Title PID sourced from City of Vancouver parcel fabric (site_id: {clean_pid})",
    ))

    # Address — link to Google Maps for visual confirmation
    if addr:
        sources.append(DataSource(
            field="civic_address",
            label="Civic Address",
            value=addr,
            origin="Vancouver Open Data",
            confidence="verified",
            url=f"https://www.google.com/maps/search/{addr_encoded}+Vancouver+BC",
        ))

    # Zoning — link to the City of Vancouver zoning map
    if parcel["current_zoning"]:
        sources.append(DataSource(
            field="current_zoning",
            label="Current Zoning",
            value=parcel["current_zoning"],
            origin="Vancouver Open Data",
            confidence="verified",
            url=f"https://maps.vancouver.ca/van-zoning/?search={addr_encoded}",
            note="Zoning assigned via spatial join of parcel centroid to City of Vancouver zoning polygons",
        ))

    # Bill 47 Entitlement — link to the specific legislation section
    if best:
        sources.append(DataSource(
            field="entitlement",
            label=f"Tier {best.tier.value} Entitlement ({best.entitled_storeys} storeys, FSR {best.entitled_fsr})",
            value=f"{best.distance_m:.0f}m from {best.station_name}",
            origin="Bill 47 — Housing Statutes (TOA) Amendment Act, 2023",
            confidence="calculated",
            url="https://www.bclaws.gov.bc.ca/civix/document/id/bills/billsprevious/4th42nd:gov47-1",
            note=f"Distance calculated via PostGIS geodesic ST_Distance (WGS84 geography) from parcel centroid to station. "
                 f"Tier {best.tier.value}: {best.tier.value == 1 and '0-200m' or best.tier.value == 2 and '200-400m' or '400-800m'} radius per Bill 47 s.481.1",
        ))

    # Station — link to Google Maps for the specific station
    if best:
        station_encoded = best.station_name.replace(" ", "+")
        sources.append(DataSource(
            field="station",
            label=f"Station: {best.station_name}",
            value="TransLink SkyTrain",
            origin="TransLink GTFS",
            confidence="verified",
            url=f"https://www.google.com/maps/search/{station_encoded}+SkyTrain+Station+Vancouver",
            note="Station coordinates from TransLink's official GTFS static feed",
        ))

    # Lot area — link to parcel map view showing the polygon
    if parcel["lot_area_sqm"]:
        sources.append(DataSource(
            field="lot_area_sqm",
            label="Lot Area",
            value=f"{parcel['lot_area_sqm']:,.1f} sqm ({float(parcel['lot_area_sqm']) * 10.7639:,.0f} sqft)",
            origin="Calculated from Vancouver Open Data geometry",
            confidence="calculated",
            url=f"https://opendata.vancouver.ca/explore/dataset/property-parcel-polygons/map/?refine.site_id={clean_pid}",
            note="Area calculated via PostGIS ST_Area(ST_Transform(geom, 3005)) from official parcel polygon",
        ))

    # Assessed value — link to the specific tax record in Vancouver Open Data
    if parcel["assessed_value"]:
        sources.append(DataSource(
            field="assessed_value",
            label="Assessed Value",
            value=f"${parcel['assessed_value']:,}",
            origin="BC Assessment via Vancouver Open Data",
            confidence="estimated",
            url=f"https://opendata.vancouver.ca/explore/dataset/property-tax-report/table/?refine.pid={pid}",
            note="Assessed value from Vancouver Open Data property-tax-report dataset (sourced from BC Assessment). "
                 "Click to see the specific tax record for this PID.",
        ))

    # Asking price — Google search scoped to REW.ca for the address
    if value_estimate and value_estimate.asking_price:
        # Try direct REW.ca URL if column exists; otherwise use Google search
        rew_url = None
        try:
            rew_url = parcel.get("rew_url") if hasattr(parcel, "get") else parcel["rew_url"]
        except (KeyError, TypeError):
            pass
        if rew_url:
            verify_url = rew_url
            verify_note = "Direct link to the REW.ca listing page."
        else:
            verify_url = f"https://www.google.com/search?q=site%3Arew.ca+{addr_encoded}+Vancouver+BC"
            verify_note = "Google search scoped to REW.ca for this address. Click to find the listing."
        sources.append(DataSource(
            field="asking_price",
            label="Asking Price",
            value=f"${value_estimate.asking_price:,}",
            origin="REW.ca Listings",
            confidence="estimated",
            url=verify_url,
            note=verify_note,
        ))

    # Estimated land value — our calculation (no external verify link)
    if value_estimate:
        sources.append(DataSource(
            field="estimated_land_value",
            label="Entitled Land Value (Est.)",
            value=f"${value_estimate.estimated_land_value:,}",
            origin="VanCity Lens Model",
            confidence="calculated",
            url=None,
            note=f"Formula: lot_area ({parcel['lot_area_sqm']:,.1f} sqm) x entitled_FSR ({value_estimate.entitled_fsr}) "
                 f"x 10.7639 (sqm-sqft) x ${value_estimate.price_per_sqft_assumption}/sqft = ${value_estimate.estimated_land_value:,}.",
        ))

    # BC Assessment official lookup — direct link with address pre-filled
    sources.append(DataSource(
        field="bc_assessment_lookup",
        label="BC Assessment — Official Lookup",
        value="Click to verify assessed value",
        origin="BC Assessment Authority",
        confidence="verified",
        url=f"https://www.bcassessment.ca/Property/Search/GetByAddress?addr={addr_encoded or pid}+Vancouver",
        note="Opens BC Assessment's official property search to verify the government-assessed value.",
    ))

    return SourceAttribution(
        sources=sources,
        last_updated=datetime.now().isoformat(),
    )


class ParcelNotFoundError(Exception):
    """Raised when a PID doesn't exist in our parcel fabric."""
    def __init__(self, pid: str):
        self.pid = pid
        super().__init__(f"Parcel {pid} not found")


class InvalidPIDFormatError(Exception):
    """DV-HBU-001: Raised when a PID doesn't match the 9-digit NNN-NNN-NNN format."""
    def __init__(self, pid: str):
        self.pid = pid
        super().__init__(
            f"Invalid PID format: '{pid}'. "
            "A valid BC Land Title PID is a 9-digit number in the format NNN-NNN-NNN (e.g., 012-345-678)."
        )
