"""
VanCity Lens — Bill 47 Entitlement Engine
Core business logic: spatial query → domain model → API response.
"""

from decimal import Decimal
from typing import Optional

import asyncpg

from .models import (
    DataSource,
    ParcelEntitlementResponse,
    SourceAttribution,
    StationEntitlement,
    TOATier,
    ValueEstimate,
)
from .validation import compute_validation

from datetime import datetime

# ── SQL Queries ──────────────────────────────────────────────

SQL_PARCEL_INFO = """
    SELECT pid, civic_address, current_zoning, current_height,
           current_fsr, lot_area_sqm, assessed_value, asking_price,
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
                ST_Transform(ST_Centroid(p.geom), 3005),
                ST_Transform(s.geom, 3005)
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


# ── Engine ───────────────────────────────────────────────────

async def compute_entitlement(
    conn: asyncpg.Connection,
    pid: str,
    price_per_sqft: Decimal = Decimal("800"),
) -> ParcelEntitlementResponse:
    """
    The core "magic trick":
    Given a parcel PID, return the full Bill 47 entitlement analysis.
    """

    # 1. Fetch parcel info
    parcel = await conn.fetchrow(SQL_PARCEL_INFO, pid)
    if parcel is None:
        raise ParcelNotFoundError(pid)

    # 2. Run spatial intersection against TOA buffers
    rows = await conn.fetch(SQL_ENTITLEMENTS, pid)

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
            note=f"Distance calculated via PostGIS ST_Distance in EPSG:3005 (BC Albers) from parcel centroid to station. "
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
