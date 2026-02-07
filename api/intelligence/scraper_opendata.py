"""Open data scrapers for neighborhood quality-of-life metrics.

Sources:
- VPD Open Data: Crime statistics per neighborhood
- CoV Open Data: Parks, building permits, property tax
- TransLink GTFS: Transit stop density
- Intelligence signals: Development activity (internal)

All scrapers follow the same pattern:
1. Fetch data from source (CSV, JSON, or GeoJSON)
2. Aggregate by neighborhood
3. Return list of metric dicts: {neighborhood, category, metric_name, value, ...}

Error handling: scrapers return [] on failure and log the error.
"""

from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict
from datetime import date
from typing import Optional

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

# Approximate bounding boxes for each neighborhood (simplified assignment)
# Format: {name: (lat_min, lat_max, lon_min, lon_max)}
# These are approximations — production should use PostGIS ST_Contains with official boundaries.
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
    """Assign a point to a neighborhood using simple bounding boxes.

    Note: Boxes may overlap. First match wins. For production, use PostGIS
    boundary polygons via ST_Contains for accuracy.
    """
    for name, (lat_min, lat_max, lon_min, lon_max) in NEIGHBORHOOD_BOUNDS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return None


def _current_period() -> tuple[date, date]:
    """Get current measurement period (calendar year)."""
    today = date.today()
    return date(today.year, 1, 1), date(today.year, 12, 31)


# ── VPD Crime Data ────────────────────────────────────────────

# Updated URL: VPD migrated to a new open data portal
VPD_CRIME_URL = "https://vpd.ca/opendata/crimedata_csv_all_years.zip?type=csv"
# Fallback: CoV also hosts crime data
COV_CRIME_URL = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/crimedata_csv_all_years/exports/csv"


async def scrape_vpd_crime(session, url: str = COV_CRIME_URL) -> list[dict]:
    """Scrape crime statistics from CoV Open Data (originally VPD).

    Returns crime count per neighborhood as safety metrics.
    Uses CoV open data portal as primary source (more reliable than VPD direct).
    """
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning("Crime data API returned %s, trying fallback", response.status)
                return []

            text = await response.text()
    except Exception as e:
        logger.error("Failed to fetch crime data: %s", e)
        return []

    reader = csv.DictReader(io.StringIO(text))
    neighborhood_counts: dict[str, int] = defaultdict(int)

    # Validate we have the expected columns
    if reader.fieldnames and "NEIGHBOURHOOD" not in reader.fieldnames:
        # Try case-insensitive lookup
        hood_col = next(
            (f for f in reader.fieldnames if f.upper() == "NEIGHBOURHOOD"),
            None,
        )
        if not hood_col:
            logger.error("Crime CSV missing NEIGHBOURHOOD column. Found: %s", reader.fieldnames)
            return []
    else:
        hood_col = "NEIGHBOURHOOD"

    for row in reader:
        hood = (row.get(hood_col, "") or "").strip()
        canonical = VPD_NEIGHBORHOOD_MAP.get(hood, hood)
        if canonical in VANCOUVER_NEIGHBORHOODS:
            neighborhood_counts[canonical] += 1

    logger.info("Scraped %d crime records across %d neighborhoods", sum(neighborhood_counts.values()), len(neighborhood_counts))
    period_start, period_end = _current_period()

    return [
        {
            "neighborhood": hood,
            "category": "safety",
            "metric_name": "crime_count",
            "value": count,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source": "CoV Open Data (VPD)",
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
                logger.warning("CoV parks API returned %s", response.status)
                return []

            data = await response.json()
    except Exception as e:
        logger.error("Failed to fetch CoV parks data: %s", e)
        return []

    neighborhood_hectares: dict[str, float] = defaultdict(float)

    for feature in data.get("features", []):
        props = feature.get("properties", {})
        # Try multiple possible field names
        hood = (
            props.get("NEIGHBOURHOOD_NAME", "")
            or props.get("neighbourhood_name", "")
            or ""
        ).strip()
        hectares = props.get("HECTARE", props.get("hectare", 0)) or 0

        if hood in VANCOUVER_NEIGHBORHOODS:
            try:
                neighborhood_hectares[hood] += float(hectares)
            except (ValueError, TypeError):
                pass

    logger.info("Scraped park data for %d neighborhoods", len(neighborhood_hectares))
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

# TransLink GTFS requires accepting their developer agreement.
# Fallback: use CoV transit data or static GTFS from openmobilitydata.
TRANSLINK_STOPS_URL = "https://gtfs.translink.ca/static/latest/stops.txt"
COV_TRANSIT_URL = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/rapid-transit-stations/exports/json"


async def scrape_translink_transit(session, url: str = TRANSLINK_STOPS_URL) -> list[dict]:
    """Scrape TransLink GTFS stops or fallback to CoV transit data.

    Returns transit stop count per neighborhood.
    """
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning("TransLink GTFS returned %s, trying CoV fallback", response.status)
                return await _scrape_cov_transit_fallback(session)

            text = await response.text()
    except Exception as e:
        logger.warning("TransLink GTFS failed: %s, trying CoV fallback", e)
        return await _scrape_cov_transit_fallback(session)

    reader = csv.DictReader(io.StringIO(text))
    neighborhood_stops: dict[str, int] = defaultdict(int)

    for row in reader:
        try:
            lat = float(row.get("stop_lat", ""))
            lon = float(row.get("stop_lon", ""))
        except (ValueError, TypeError):
            continue

        # Skip obviously out-of-range coordinates
        if not (49.19 < lat < 49.31 and -123.25 < lon < -123.01):
            continue

        hood = _assign_neighborhood_by_coords(lat, lon)
        if hood:
            neighborhood_stops[hood] += 1

    logger.info("Scraped %d transit stops across %d neighborhoods", sum(neighborhood_stops.values()), len(neighborhood_stops))
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


async def _scrape_cov_transit_fallback(session) -> list[dict]:
    """Fallback: use CoV rapid transit stations dataset."""
    try:
        async with session.get(COV_TRANSIT_URL) as response:
            if response.status != 200:
                logger.warning("CoV transit fallback returned %s", response.status)
                return []
            data = await response.json()
    except Exception as e:
        logger.error("CoV transit fallback failed: %s", e)
        return []

    neighborhood_stops: dict[str, int] = defaultdict(int)
    for item in data if isinstance(data, list) else []:
        hood = (item.get("geo_local_area") or "").strip()
        if hood in VANCOUVER_NEIGHBORHOODS:
            neighborhood_stops[hood] += 1

    period_start, period_end = _current_period()
    return [
        {
            "neighborhood": hood,
            "category": "transit",
            "metric_name": "transit_stop_count",
            "value": count,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source": "CoV Open Data (transit)",
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
        logger.error("Failed to compute development metrics: %s", e)
        return []

    period_start, period_end = _current_period()

    return [
        {
            "neighborhood": row["neighborhood"],
            "category": "development",
            "metric_name": "development_activity_score",
            "value": row["signal_count"],
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source": "VanCity Lens Intelligence",
        }
        for row in rows
    ]


# ── CoV Building Permits ──────────────────────────────────────

COV_PERMITS_URL = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/issued-building-permits/exports/json"


async def scrape_cov_permits(session, url: str = COV_PERMITS_URL) -> list[dict]:
    """Scrape City of Vancouver issued building permits.

    Returns permit count per neighborhood.
    Source: opendata.vancouver.ca
    """
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning("CoV permits API returned %s", response.status)
                return []

            data = await response.json()
    except Exception as e:
        logger.error("Failed to fetch CoV permits data: %s", e)
        return []

    neighborhood_counts: dict[str, int] = defaultdict(int)

    for item in data if isinstance(data, list) else []:
        hood = (item.get("geo_local_area") or item.get("geom_area", "") or "").strip()
        if hood in VANCOUVER_NEIGHBORHOODS:
            neighborhood_counts[hood] += 1

    logger.info("Scraped %d permits across %d neighborhoods", sum(neighborhood_counts.values()), len(neighborhood_counts))
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
                logger.warning("CoV property tax API returned %s", response.status)
                return []

            data = await response.json()
    except Exception as e:
        logger.error("Failed to fetch CoV property tax data: %s", e)
        return []

    neighborhood_values: dict[str, list[float]] = defaultdict(list)

    for item in data if isinstance(data, list) else []:
        hood = (item.get("geo_local_area") or "").strip()
        raw_value = item.get("current_land_value") or item.get("current_improvement_value")
        if hood in VANCOUVER_NEIGHBORHOODS and raw_value:
            try:
                # Strip formatting ($, commas) before conversion
                cleaned = str(raw_value).replace(",", "").replace("$", "").strip()
                neighborhood_values[hood].append(float(cleaned))
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


# ── Database Persistence ─────────────────────────────────────

async def _persist_metrics(db_pool, metrics: list[dict]) -> int:
    """Insert scraped metrics into the neighborhood_metrics table.

    Returns count of rows inserted.
    """
    if not metrics:
        return 0

    inserted = 0
    async with db_pool.acquire() as conn:
        # Resolve neighborhood name → id
        hood_rows = await conn.fetch("SELECT id, name FROM neighborhoods")
        hood_map = {row["name"]: row["id"] for row in hood_rows}

        for m in metrics:
            hood_id = hood_map.get(m["neighborhood"])
            if not hood_id:
                logger.debug("Skipping metric for unknown neighborhood: %s", m["neighborhood"])
                continue

            try:
                await conn.execute("""
                    INSERT INTO neighborhood_metrics
                        (neighborhood_id, category, metric_name, metric_value, source_name, period_start, period_end, ingested_at)
                    VALUES ($1, $2, $3, $4, $5, $6::date, $7::date, NOW())
                    ON CONFLICT (neighborhood_id, category, metric_name, period_start)
                    DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                  source_name = EXCLUDED.source_name,
                                  ingested_at = NOW()
                """, hood_id, m["category"], m["metric_name"], m["value"],
                     m["source"], m["period_start"], m["period_end"])
                inserted += 1
            except Exception as e:
                logger.error("Failed to persist metric %s/%s: %s", m["neighborhood"], m["metric_name"], e)

    logger.info("Persisted %d/%d metrics to neighborhood_metrics", inserted, len(metrics))
    return inserted


async def _compute_and_store_scores(db_pool) -> int:
    """Compute normalized scores from raw metrics and store them.

    For each neighborhood and category, normalize the raw metric values
    across all neighborhoods, then compute composite scores.

    Returns count of score rows written.
    """
    from api.intelligence.neighborhoods import (
        normalize_metric, compute_composite_score, DEFAULT_WEIGHTS, METRIC_DIRECTIONS,
    )

    async with db_pool.acquire() as conn:
        period_start, period_end = _current_period()

        # Get latest metrics for each neighborhood+category
        rows = await conn.fetch("""
            SELECT DISTINCT ON (neighborhood_id, category)
                neighborhood_id, category, metric_name, metric_value
            FROM neighborhood_metrics
            ORDER BY neighborhood_id, category, period_start DESC
        """)

        if not rows:
            logger.warning("No metrics found to compute scores from")
            return 0

        # Organize by category → {hood_id: value}
        cat_values: dict[str, dict[int, float]] = defaultdict(dict)
        for row in rows:
            cat_values[row["category"]][row["neighborhood_id"]] = float(row["metric_value"])

        # Normalize each category and write scores
        written = 0
        all_hood_scores: dict[int, dict[str, float]] = defaultdict(dict)

        for category, hood_vals in cat_values.items():
            if not hood_vals:
                continue

            values = list(hood_vals.values())
            min_val = min(values)
            max_val = max(values)
            higher = METRIC_DIRECTIONS.get(category, "higher_is_better") == "higher_is_better"

            for hood_id, raw_value in hood_vals.items():
                score = normalize_metric(raw_value, min_val, max_val, higher)
                all_hood_scores[hood_id][category] = score

                # Get previous score for trend detection
                prev = await conn.fetchval("""
                    SELECT score FROM neighborhood_scores
                    WHERE neighborhood_id = $1 AND category = $2 AND period_start < $3::date
                    ORDER BY period_start DESC LIMIT 1
                """, hood_id, category, period_start.isoformat())

                from api.intelligence.neighborhoods import detect_trend
                trend, trend_change = detect_trend(score, float(prev) if prev else None)

                await conn.execute("""
                    INSERT INTO neighborhood_scores
                        (neighborhood_id, category, score, raw_value, trend, trend_change, period_start, period_end)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::date, $8::date)
                    ON CONFLICT (neighborhood_id, category, period_start)
                    DO UPDATE SET score = EXCLUDED.score,
                                  raw_value = EXCLUDED.raw_value,
                                  trend = EXCLUDED.trend,
                                  trend_change = EXCLUDED.trend_change
                """, hood_id, category, score, raw_value, trend, trend_change,
                     period_start.isoformat(), period_end.isoformat())
                written += 1

        # Compute and store composite scores
        hood_names = dict(await conn.fetch("SELECT id, name FROM neighborhoods"))
        ranked = []
        for hood_id, cat_scores in all_hood_scores.items():
            composite = compute_composite_score(cat_scores, DEFAULT_WEIGHTS)
            ranked.append((hood_id, composite, cat_scores))

        ranked.sort(key=lambda x: x[1], reverse=True)

        for rank, (hood_id, composite, cat_scores) in enumerate(ranked, 1):
            import json
            await conn.execute("""
                INSERT INTO neighborhood_composite_scores
                    (neighborhood_id, overall_score, rank, category_scores, weights_used, period_start, period_end)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::date, $7::date)
                ON CONFLICT (neighborhood_id, period_start)
                DO UPDATE SET overall_score = EXCLUDED.overall_score,
                              rank = EXCLUDED.rank,
                              category_scores = EXCLUDED.category_scores,
                              weights_used = EXCLUDED.weights_used,
                              computed_at = NOW()
            """, hood_id, composite, rank,
                 json.dumps(cat_scores), json.dumps(DEFAULT_WEIGHTS),
                 period_start.isoformat(), period_end.isoformat())

        logger.info("Computed scores for %d neighborhoods, wrote %d category scores", len(ranked), written)
        return written


# ── Master Ingestion Pipeline ─────────────────────────────────

async def run_all_scrapers(session, db_pool) -> dict:
    """Run all open data scrapers, persist to DB, and compute scores.

    Returns dict with counts per source for status reporting.
    """
    results = {
        "vpd_crime": 0,
        "cov_parks": 0,
        "translink_transit": 0,
        "development": 0,
        "cov_permits": 0,
        "cov_property_tax": 0,
        "total_scraped": 0,
        "total_persisted": 0,
        "total_scores": 0,
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
            results["total_scraped"] += len(metrics)
            all_metrics.extend(metrics)
            logger.info("Scraper %s: %d metrics", name, len(metrics))
        except Exception as e:
            logger.error("Scraper %s failed: %s", name, e)
            results["errors"].append(f"{name}: {str(e)}")

    # Persist raw metrics to database
    try:
        persisted = await _persist_metrics(db_pool, all_metrics)
        results["total_persisted"] = persisted
    except Exception as e:
        logger.error("Failed to persist metrics: %s", e)
        results["errors"].append(f"persist: {str(e)}")

    # Compute normalized scores and composites
    try:
        scores = await _compute_and_store_scores(db_pool)
        results["total_scores"] = scores
    except Exception as e:
        logger.error("Failed to compute scores: %s", e)
        results["errors"].append(f"scoring: {str(e)}")

    return results
