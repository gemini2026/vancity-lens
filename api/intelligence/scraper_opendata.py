"""Open data scrapers for neighborhood quality-of-life metrics.

Sources:
- VPD GeoDASH: Crime statistics per neighborhood
- CoV Open Data: Parks, building permits, property tax
- TransLink GTFS: Transit stop density
- Intelligence signals: Development activity (internal)

All scrapers follow the same pattern:
1. Fetch data from source (CSV, JSON, or GeoJSON)
2. Aggregate by neighborhood
3. Return list of metric dicts: {neighborhood, category, metric_name, value, ...}

Error handling: scrapers return [] on failure (no crash, just empty metrics).
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Vancouver's 22 official local areas (canonical names)
VANCOUVER_NEIGHBORHOODS = [
    "Arbutus Ridge", "Downtown", "Dunbar-Southlands", "Fairview",
    "Grandview-Woodland", "Hastings-Sunrise", "Kensington-Cedar Cottage",
    "Kerrisdale", "Killarney", "Kitsilano", "Marpole", "Mount Pleasant",
    "Oakridge", "Renfrew-Collingwood", "Riley Park", "Shaughnessy",
    "South Cambie", "Strathcona", "Sunset", "Victoria-Fraserview",
    "West End", "West Point Grey",
]

# Map VPD neighborhood names to official CoV names (some differ)
VPD_NEIGHBORHOOD_MAP = {
    "Arbutus Ridge": "Arbutus Ridge",
    "Central Business District": "Downtown",
    "Dunbar-Southlands": "Dunbar-Southlands",
    "Fairview": "Fairview",
    "Grandview-Woodland": "Grandview-Woodland",
    "Hastings-Sunrise": "Hastings-Sunrise",
    "Kensington-Cedar Cottage": "Kensington-Cedar Cottage",
    "Kerrisdale": "Kerrisdale",
    "Killarney": "Killarney",
    "Kitsilano": "Kitsilano",
    "Marpole": "Marpole",
    "Mount Pleasant": "Mount Pleasant",
    "Oakridge": "Oakridge",
    "Renfrew-Collingwood": "Renfrew-Collingwood",
    "Riley Park": "Riley Park",
    "Shaughnessy": "Shaughnessy",
    "South Cambie": "South Cambie",
    "Strathcona": "Strathcona",
    "Sunset": "Sunset",
    "Victoria-Fraserview": "Victoria-Fraserview",
    "West End": "West End",
    "West Point Grey": "West Point Grey",
    # VPD sometimes uses different names
    "Stanley Park": "West End",
    "Musqueam": "Dunbar-Southlands",
}

# Approximate neighborhood centroids for point-in-polygon checks
# (lat, lon) - used for GTFS stop assignment
NEIGHBORHOOD_CENTROIDS = {
    "Arbutus Ridge": (49.2493, -123.1554),
    "Downtown": (49.2827, -123.1207),
    "Dunbar-Southlands": (49.2440, -123.1855),
    "Fairview": (49.2650, -123.1300),
    "Grandview-Woodland": (49.2750, -123.0700),
    "Hastings-Sunrise": (49.2810, -123.0400),
    "Kensington-Cedar Cottage": (49.2490, -123.0710),
    "Kerrisdale": (49.2320, -123.1560),
    "Killarney": (49.2250, -123.0340),
    "Kitsilano": (49.2680, -123.1600),
    "Marpole": (49.2110, -123.1280),
    "Mount Pleasant": (49.2620, -123.1000),
    "Oakridge": (49.2270, -123.1230),
    "Renfrew-Collingwood": (49.2460, -123.0340),
    "Riley Park": (49.2430, -123.1020),
    "Shaughnessy": (49.2470, -123.1410),
    "South Cambie": (49.2470, -123.1170),
    "Strathcona": (49.2770, -123.0890),
    "Sunset": (49.2210, -123.0890),
    "Victoria-Fraserview": (49.2180, -123.0610),
    "West End": (49.2870, -123.1370),
    "West Point Grey": (49.2660, -123.2000),
}

# Approximate bounding boxes for each neighborhood (simplified assignment)
# Format: {name: (lat_min, lat_max, lon_min, lon_max)}
# Used for simple point-in-box assignment of transit stops
NEIGHBORHOOD_BOUNDS = {
    "Arbutus Ridge": (49.240, 49.258, -123.170, -123.145),
    "Downtown": (49.272, 49.292, -123.135, -123.105),
    "Dunbar-Southlands": (49.225, 49.260, -123.200, -123.170),
    "Fairview": (49.258, 49.275, -123.145, -123.115),
    "Grandview-Woodland": (49.265, 49.285, -123.085, -123.055),
    "Hastings-Sunrise": (49.275, 49.290, -123.055, -123.020),
    "Kensington-Cedar Cottage": (49.235, 49.260, -123.085, -123.055),
    "Kerrisdale": (49.220, 49.240, -123.170, -123.145),
    "Killarney": (49.215, 49.235, -123.050, -123.020),
    "Kitsilano": (49.260, 49.278, -123.175, -123.140),
    "Marpole": (49.200, 49.220, -123.145, -123.115),
    "Mount Pleasant": (49.255, 49.272, -123.115, -123.085),
    "Oakridge": (49.220, 49.240, -123.140, -123.110),
    "Renfrew-Collingwood": (49.235, 49.260, -123.050, -123.020),
    "Riley Park": (49.235, 49.255, -123.115, -123.090),
    "Shaughnessy": (49.237, 49.255, -123.155, -123.125),
    "South Cambie": (49.240, 49.255, -123.125, -123.110),
    "Strathcona": (49.270, 49.285, -123.105, -123.080),
    "Sunset": (49.210, 49.230, -123.105, -123.075),
    "Victoria-Fraserview": (49.205, 49.225, -123.075, -123.045),
    "West End": (49.278, 49.295, -123.150, -123.125),
    "West Point Grey": (49.258, 49.278, -123.210, -123.175),
}


def _assign_neighborhood_by_coords(lat: float, lon: float) -> Optional[str]:
    """Assign a point to a neighborhood using simple bounding boxes."""
    for name, (lat_min, lat_max, lon_min, lon_max) in NEIGHBORHOOD_BOUNDS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return None


def _current_period() -> tuple[date, date]:
    """Get current measurement period (calendar year)."""
    today = date.today()
    return date(today.year, 1, 1), date(today.year, 12, 31)


# ── VPD Crime Data ────────────────────────────────────────────

VPD_CRIME_URL = "https://geodash.vpd.ca/opendata/crimedata_csv_all_years.csv"


async def scrape_vpd_crime(session, url: str = VPD_CRIME_URL) -> list[dict]:
    """Scrape VPD GeoDASH crime statistics.

    Returns crime count per neighborhood as safety metrics.
    Source: geodash.vpd.ca/opendata/
    """
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(f"VPD crime API returned {response.status}")
                return []

            text = await response.text()
    except Exception as e:
        logger.error(f"Failed to fetch VPD crime data: {e}")
        return []

    # Parse CSV
    reader = csv.DictReader(io.StringIO(text))
    neighborhood_counts: dict[str, int] = {}

    for row in reader:
        hood = row.get("NEIGHBOURHOOD", "").strip()
        # Map VPD names to canonical names
        canonical = VPD_NEIGHBORHOOD_MAP.get(hood, hood)
        if canonical in VANCOUVER_NEIGHBORHOODS:
            neighborhood_counts[canonical] = neighborhood_counts.get(canonical, 0) + 1

    period_start, period_end = _current_period()

    return [
        {
            "neighborhood": hood,
            "category": "safety",
            "metric_name": "crime_count",
            "value": count,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source": "VPD GeoDASH",
        }
        for hood, count in neighborhood_counts.items()
    ]


# ── CoV Parks Data ────────────────────────────────────────────

COV_PARKS_URL = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/parks/exports/geojson"


async def scrape_cov_parks(session, url: str = COV_PARKS_URL) -> list[dict]:
    """Scrape City of Vancouver parks dataset.

    Returns total park hectares per neighborhood.
    Source: opendata.vancouver.ca
    """
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(f"CoV parks API returned {response.status}")
                return []

            data = await response.json()
    except Exception as e:
        logger.error(f"Failed to fetch CoV parks data: {e}")
        return []

    neighborhood_hectares: dict[str, float] = {}

    for feature in data.get("features", []):
        props = feature.get("properties", {})
        hood = props.get("NEIGHBOURHOOD_NAME", "").strip()
        hectares = props.get("HECTARE", 0) or 0

        if hood in VANCOUVER_NEIGHBORHOODS:
            neighborhood_hectares[hood] = neighborhood_hectares.get(hood, 0) + float(hectares)

    period_start, period_end = _current_period()

    return [
        {
            "neighborhood": hood,
            "category": "parks",
            "metric_name": "total_park_hectares",
            "value": round(hectares, 2),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source": "CoV Open Data",
        }
        for hood, hectares in neighborhood_hectares.items()
    ]


# ── TransLink GTFS Transit Data ───────────────────────────────

TRANSLINK_STOPS_URL = "https://gtfs.translink.ca/static/latest/stops.txt"


async def scrape_translink_transit(session, url: str = TRANSLINK_STOPS_URL) -> list[dict]:
    """Scrape TransLink GTFS stops data.

    Returns transit stop count per neighborhood.
    Source: translink.ca GTFS
    """
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(f"TransLink GTFS returned {response.status}")
                return []

            text = await response.text()
    except Exception as e:
        logger.error(f"Failed to fetch TransLink GTFS data: {e}")
        return []

    reader = csv.DictReader(io.StringIO(text))
    neighborhood_stops: dict[str, int] = {}

    for row in reader:
        try:
            lat = float(row.get("stop_lat", 0))
            lon = float(row.get("stop_lon", 0))
        except (ValueError, TypeError):
            continue

        hood = _assign_neighborhood_by_coords(lat, lon)
        if hood:
            neighborhood_stops[hood] = neighborhood_stops.get(hood, 0) + 1

    period_start, period_end = _current_period()

    return [
        {
            "neighborhood": hood,
            "category": "transit",
            "metric_name": "transit_stop_count",
            "value": count,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source": "TransLink GTFS",
        }
        for hood, count in neighborhood_stops.items()
    ]


# ── Development Metrics (from Intelligence Signals) ───────────

async def compute_development_metrics(db_pool) -> list[dict]:
    """Compute development activity metrics from intelligence signals.

    This uses internal data (not external API) — counts of recent
    signals, rezonings, and permits per neighborhood.
    """
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    neighborhood,
                    COUNT(*) as signal_count,
                    COUNT(*) FILTER (WHERE signal_type = 'rezoning_decision') as rezoning_count,
                    COUNT(*) FILTER (WHERE signal_type = 'permit_approval') as permit_count
                FROM intelligence_signals
                WHERE neighborhood IS NOT NULL
                  AND extracted_at > NOW() - INTERVAL '365 days'
                GROUP BY neighborhood
            """)
    except Exception as e:
        logger.error(f"Failed to compute development metrics: {e}")
        return []

    period_start, period_end = _current_period()

    return [
        {
            "neighborhood": row["neighborhood"],
            "category": "development",
            "metric_name": "development_activity_score",
            "value": row["signal_count"],  # Raw signal count; normalized later
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source": "VanCity Lens Intelligence",
            "metadata": {
                "rezoning_count": row["rezoning_count"],
                "permit_count": row["permit_count"],
            },
        }
        for row in rows
    ]


# ── CoV Building Permits ──────────────────────────────────────

COV_PERMITS_URL = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/issued-building-permits/exports/json"


async def scrape_cov_permits(session, url: str = COV_PERMITS_URL) -> list[dict]:
    """Scrape City of Vancouver issued building permits.

    Returns permit count per neighborhood (recent 12 months).
    Source: opendata.vancouver.ca
    """
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(f"CoV permits API returned {response.status}")
                return []

            data = await response.json()
    except Exception as e:
        logger.error(f"Failed to fetch CoV permits data: {e}")
        return []

    neighborhood_counts: dict[str, int] = {}

    for item in data if isinstance(data, list) else []:
        hood = (item.get("geo_local_area") or "").strip()
        if hood in VANCOUVER_NEIGHBORHOODS:
            neighborhood_counts[hood] = neighborhood_counts.get(hood, 0) + 1

    period_start, period_end = _current_period()

    return [
        {
            "neighborhood": hood,
            "category": "development",
            "metric_name": "building_permits_count",
            "value": count,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source": "CoV Open Data",
        }
        for hood, count in neighborhood_counts.items()
    ]


# ── CoV Property Tax (Affordability) ──────────────────────────

COV_PROPERTY_TAX_URL = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/property-tax-report/exports/json"


async def scrape_cov_property_tax(session, url: str = COV_PROPERTY_TAX_URL) -> list[dict]:
    """Scrape City of Vancouver property tax data for affordability metrics.

    Returns average assessed value per neighborhood.
    Source: opendata.vancouver.ca
    """
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(f"CoV property tax API returned {response.status}")
                return []

            data = await response.json()
    except Exception as e:
        logger.error(f"Failed to fetch CoV property tax data: {e}")
        return []

    neighborhood_values: dict[str, list[float]] = {}

    for item in data if isinstance(data, list) else []:
        hood = (item.get("geo_local_area") or "").strip()
        value = item.get("current_land_value") or item.get("current_improvement_value")
        if hood in VANCOUVER_NEIGHBORHOODS and value:
            if hood not in neighborhood_values:
                neighborhood_values[hood] = []
            try:
                neighborhood_values[hood].append(float(value))
            except (ValueError, TypeError):
                pass

    period_start, period_end = _current_period()

    return [
        {
            "neighborhood": hood,
            "category": "affordability",
            "metric_name": "avg_assessed_value",
            "value": round(sum(values) / len(values), 0),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source": "CoV Open Data",
        }
        for hood, values in neighborhood_values.items()
        if values
    ]


# ── Master Ingestion Pipeline ─────────────────────────────────

async def run_all_scrapers(session, db_pool) -> dict:
    """Run all open data scrapers and return combined metrics.

    Returns dict with counts per source for status reporting.
    """
    results = {
        "vpd_crime": 0,
        "cov_parks": 0,
        "translink_transit": 0,
        "development": 0,
        "cov_permits": 0,
        "cov_property_tax": 0,
        "total": 0,
        "errors": [],
    }

    scrapers = [
        ("vpd_crime", scrape_vpd_crime(session)),
        ("cov_parks", scrape_cov_parks(session)),
        ("translink_transit", scrape_translink_transit(session)),
        ("development", compute_development_metrics(db_pool)),
        ("cov_permits", scrape_cov_permits(session)),
        ("cov_property_tax", scrape_cov_property_tax(session)),
    ]

    all_metrics = []

    for name, coro in scrapers:
        try:
            metrics = await coro
            results[name] = len(metrics)
            results["total"] += len(metrics)
            all_metrics.extend(metrics)
        except Exception as e:
            logger.error(f"Scraper {name} failed: {e}")
            results["errors"].append(f"{name}: {str(e)}")

    return results
