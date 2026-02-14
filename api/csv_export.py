"""
VanCity Lens — CSV Export Service (VCL-101 / FE-012)

Service for exporting signals, neighborhood comparisons, and parcels to CSV format.
Provides protection against CSV injection attacks and proper formatting.
"""

import csv
import io
import logging
from datetime import date, datetime
from typing import Optional, List, Any, Dict

from pydantic import BaseModel, Field
import asyncpg

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Export Filter Models (Pydantic v2)
# ────────────────────────────────────────────────────────────────────────────


class SignalExportFilters(BaseModel):
    """Filters for signal feed export."""
    neighborhood: Optional[str] = Field(None, description="Filter by neighborhood")
    category: Optional[str] = Field(None, description="Filter by signal category/type")
    date_from: Optional[date] = Field(None, description="Filter signals from this date onwards")
    date_to: Optional[date] = Field(None, description="Filter signals up to this date")
    severity: Optional[str] = Field(None, description="Filter by severity level")
    limit: int = Field(default=1000, ge=1, le=10000, description="Max rows to export")

    class Config:
        from_attributes = True


class ParcelExportFilters(BaseModel):
    """Filters for parcel data export."""
    neighborhood: Optional[str] = Field(None, description="Filter by neighborhood")
    zoning: Optional[str] = Field(None, description="Filter by zoning code")
    min_lot_sqft: Optional[float] = Field(None, ge=0, description="Minimum lot size in sqft")
    max_lot_sqft: Optional[float] = Field(None, ge=0, description="Maximum lot size in sqft")
    limit: int = Field(default=1000, ge=1, le=5000, description="Max rows to export")

    class Config:
        from_attributes = True


class ExportMetadata(BaseModel):
    """Metadata about exported data."""
    export_type: str = Field(..., description="Type of export: 'signals', 'neighborhood', 'parcels'")
    row_count: int = Field(..., description="Number of rows exported")
    exported_at: datetime = Field(..., description="Timestamp of export")
    filters_applied: Dict[str, Any] = Field(default_factory=dict, description="Filters used")
    source_url: Optional[str] = Field(None, description="Original data source URL")

    class Config:
        from_attributes = True


# ────────────────────────────────────────────────────────────────────────────
# CSV Exporter Service
# ────────────────────────────────────────────────────────────────────────────


class CSVExporter:
    """
    Service for exporting signals, neighborhoods, and parcels to CSV format.

    Handles:
    - CSV generation with proper quoting and escaping
    - CSV injection prevention
    - Filename generation with date and context
    - StreamingResponse-compatible output
    """

    # CSV Injection dangerous prefixes to strip
    DANGEROUS_CSV_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

    @staticmethod
    def _sanitize_csv_value(value: Any) -> str:
        """
        Sanitize a value to prevent CSV injection attacks.

        Removes leading characters that could be interpreted as formulas:
        =, +, -, @, tab, carriage return

        Args:
            value: Any value to sanitize

        Returns:
            String representation safe for CSV
        """
        if value is None:
            return ""

        # Convert to string
        str_value = str(value)

        # Strip dangerous prefixes (iteratively to catch multiple)
        while str_value and str_value[0] in CSVExporter.DANGEROUS_CSV_PREFIXES:
            str_value = str_value[1:]

        return str_value

    @staticmethod
    def _build_filename(
        export_type: str,
        context: Optional[str] = None,
        export_date: Optional[date] = None,
    ) -> str:
        """
        Build a CSV filename with type, context, and date.

        Format: {type}_{context}_{YYYY-MM-DD}.csv

        Args:
            export_type: Type of export ('signals', 'neighborhoods', 'parcels')
            context: Optional context string (neighborhood, filter, etc)
            export_date: Date to include in filename (defaults to today)

        Returns:
            Sanitized filename string
        """
        if export_date is None:
            export_date = date.today()

        date_str = export_date.strftime("%Y-%m-%d")

        if context:
            # Sanitize context for filename (alphanumeric, dash, underscore only)
            context = context.replace(" ", "_")
            context = "".join(c if c.isalnum() or c == "_" else "_" for c in context)
            return f"{export_type}_{context}_{date_str}.csv"
        else:
            return f"{export_type}_{date_str}.csv"

    @staticmethod
    async def export_signals(
        pool: asyncpg.Pool,
        filters: SignalExportFilters,
    ) -> tuple[io.StringIO, str]:
        """
        Export filtered signals to CSV format.

        Includes all visible fields plus metadata (source URL, confidence).

        Args:
            pool: asyncpg connection pool
            filters: SignalExportFilters with neighborhood, category, date range, etc

        Returns:
            Tuple of (StringIO buffer, filename)

        Raises:
            Exception: Database query errors
        """
        # Fetch signals from database
        signals = await _fetch_signals_for_export(pool, filters)

        # CSV headers
        fieldnames = [
            "signal_id",
            "signal_type",
            "headline",
            "summary",
            "neighborhood",
            "addresses",
            "event_date",
            "severity",
            "confidence",
            "zoning_from",
            "zoning_to",
            "height_before",
            "height_after",
            "fsr_before",
            "fsr_after",
            "unit_count",
            "project_value_dollars",
            "decision",
            "vote_for",
            "vote_against",
            "conditions",
            "sentiment",
            "source_title",
            "source_url",
            "source_type",
            "source_date",
        ]

        # Write to StringIO buffer
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for signal in signals:
            row = {
                "signal_id": signal.get("id"),
                "signal_type": signal.get("signal_type"),
                "headline": CSVExporter._sanitize_csv_value(signal.get("headline")),
                "summary": CSVExporter._sanitize_csv_value(signal.get("summary")),
                "neighborhood": signal.get("neighborhood"),
                "addresses": CSVExporter._sanitize_csv_value(
                    ",".join(signal.get("addresses") or [])
                ),
                "event_date": signal.get("event_date"),
                "severity": signal.get("severity"),
                "confidence": signal.get("confidence"),
                "zoning_from": signal.get("zoning_from"),
                "zoning_to": signal.get("zoning_to"),
                "height_before": signal.get("height_before"),
                "height_after": signal.get("height_after"),
                "fsr_before": signal.get("fsr_before"),
                "fsr_after": signal.get("fsr_after"),
                "unit_count": signal.get("unit_count"),
                "project_value_dollars": signal.get("project_value_dollars"),
                "decision": signal.get("decision"),
                "vote_for": signal.get("vote_for"),
                "vote_against": signal.get("vote_against"),
                "conditions": CSVExporter._sanitize_csv_value(
                    ",".join(signal.get("conditions") or [])
                ),
                "sentiment": signal.get("sentiment"),
                "source_title": CSVExporter._sanitize_csv_value(signal.get("source_title")),
                "source_url": signal.get("source_url"),
                "source_type": signal.get("source_type"),
                "source_date": signal.get("source_date"),
            }
            writer.writerow(row)

        # Generate filename
        context = filters.neighborhood or "all"
        filename = CSVExporter._build_filename("signals", context)

        output.seek(0)
        return output, filename

    @staticmethod
    async def export_neighborhood_comparison(
        pool: asyncpg.Pool,
        neighborhoods: List[str],
    ) -> tuple[io.StringIO, str]:
        """
        Export neighborhood comparison scorecard to CSV.

        Includes all scorecard fields for selected neighborhoods side-by-side.

        Args:
            pool: asyncpg connection pool
            neighborhoods: List of neighborhood names to compare

        Returns:
            Tuple of (StringIO buffer, filename)

        Raises:
            Exception: Database query errors
        """
        # Fetch neighborhood scorecard data
        scorecard_data = await _fetch_neighborhood_scorecard(pool, neighborhoods)

        # CSV headers (metric + one column per neighborhood)
        fieldnames = ["metric"] + neighborhoods

        # Write to StringIO buffer
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        # Define scorecard metrics to include
        metrics = [
            "population",
            "median_age",
            "household_income",
            "property_tax_rate",
            "average_home_price",
            "price_per_sqft",
            "vacancy_rate",
            "zoning_density_score",
            "development_pipeline_count",
            "transit_accessibility_score",
            "walkability_score",
            "bike_score",
            "school_rating_avg",
            "crime_rate_per_100k",
            "parks_per_100k_residents",
        ]

        for metric in metrics:
            row = {"metric": metric}
            for neighborhood in neighborhoods:
                value = scorecard_data.get(neighborhood, {}).get(metric, "N/A")
                row[neighborhood] = CSVExporter._sanitize_csv_value(value)
            writer.writerow(row)

        # Generate filename
        context = "_vs_".join(neighborhoods[:3])  # Limit context length
        filename = CSVExporter._build_filename("neighborhood_comparison", context)

        output.seek(0)
        return output, filename

    @staticmethod
    async def export_neighborhood_summaries(
        pool: asyncpg.Pool,
    ) -> tuple[io.StringIO, str]:
        """
        Export neighborhood scorecard summaries (rank + overall score) to CSV.

        This is the "list view" export used by the UI when no comparison set is provided.
        """
        from api.intelligence.neighborhoods import get_all_neighborhood_summaries

        summaries = await get_all_neighborhood_summaries(pool)

        fieldnames = [
            "name",
            "slug",
            "overall_score",
            "rank",
            "top_category",
            "bottom_category",
        ]

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for s in summaries:
            writer.writerow(
                {
                    "name": CSVExporter._sanitize_csv_value(s.get("name")),
                    "slug": CSVExporter._sanitize_csv_value(s.get("slug")),
                    "overall_score": s.get("overall_score"),
                    "rank": s.get("rank"),
                    "top_category": CSVExporter._sanitize_csv_value(s.get("top_category")),
                    "bottom_category": CSVExporter._sanitize_csv_value(s.get("bottom_category")),
                }
            )

        filename = CSVExporter._build_filename("neighborhood_scorecards", "all")
        output.seek(0)
        return output, filename

    @staticmethod
    async def export_parcels(
        pool: asyncpg.Pool,
        filters: ParcelExportFilters,
    ) -> tuple[io.StringIO, str]:
        """
        Export parcel data to CSV format.

        Includes parcel ID, address, zoning, lot size, valuation, and entitlement data.

        Args:
            pool: asyncpg connection pool
            filters: ParcelExportFilters with neighborhood, zoning, lot size range, etc

        Returns:
            Tuple of (StringIO buffer, filename)

        Raises:
            Exception: Database query errors
        """
        # Fetch parcels from database
        parcels = await _fetch_parcels_for_export(pool, filters)

        # CSV headers
        fieldnames = [
            "pid",
            "civic_address",
            "neighborhood",
            "zoning",
            "lot_area_sqft",
            "lot_area_sqm",
            "assessed_value",
            "asking_price",
            "price_per_sqft",
            "current_storeys",
            "current_fsr",
            "entitled_storeys",
            "entitled_fsr",
            "storey_uplift",
            "fsr_uplift",
            "estimated_land_value",
            "value_delta",
            "signal",
            "in_toa",
            "zoning_already_exceeds",
            "nearest_station",
            "distance_to_station_m",
            "bill47_tier",
        ]

        # Write to StringIO buffer
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for parcel in parcels:
            lot_sqm = parcel.get("lot_area_sqm")
            lot_sqft = float(lot_sqm) * 10.764 if lot_sqm else None
            row = {
                "pid": parcel.get("pid"),
                "civic_address": CSVExporter._sanitize_csv_value(parcel.get("civic_address")),
                "neighborhood": parcel.get("geo_local_area"),
                "zoning": parcel.get("current_zoning"),
                "lot_area_sqft": round(lot_sqft, 1) if lot_sqft else None,
                "lot_area_sqm": lot_sqm,
                "assessed_value": parcel.get("assessed_value"),
                "asking_price": parcel.get("asking_price"),
                "price_per_sqft": None,
                "current_storeys": parcel.get("current_height"),
                "current_fsr": parcel.get("current_fsr"),
                "entitled_storeys": parcel.get("entitled_storeys"),
                "entitled_fsr": parcel.get("entitled_fsr"),
                "storey_uplift": parcel.get("storey_uplift"),
                "fsr_uplift": parcel.get("fsr_uplift"),
                "estimated_land_value": parcel.get("estimated_land_value"),
                "value_delta": parcel.get("value_delta"),
                "signal": parcel.get("signal"),
                "in_toa": parcel.get("in_toa"),
                "zoning_already_exceeds": parcel.get("zoning_already_exceeds"),
                "nearest_station": parcel.get("nearest_station"),
                "distance_to_station_m": parcel.get("distance_to_station_m"),
                "bill47_tier": parcel.get("bill47_tier"),
            }
            writer.writerow(row)

        # Generate filename
        context = filters.neighborhood or "all"
        filename = CSVExporter._build_filename("parcels", context)

        output.seek(0)
        return output, filename


# ────────────────────────────────────────────────────────────────────────────
# Database Query Helpers
# ────────────────────────────────────────────────────────────────────────────


async def _fetch_signals_for_export(
    pool: asyncpg.Pool,
    filters: SignalExportFilters,
) -> List[Dict[str, Any]]:
    """
    Fetch signals from database matching export filters.

    Args:
        pool: asyncpg connection pool
        filters: SignalExportFilters

    Returns:
        List of signal dictionaries
    """
    query = "SELECT * FROM intelligence_signals WHERE 1=1"
    params = []
    param_count = 1

    if filters.neighborhood:
        query += f" AND neighborhood = ${param_count}"
        params.append(filters.neighborhood)
        param_count += 1

    if filters.category:
        query += f" AND signal_type = ${param_count}"
        params.append(filters.category)
        param_count += 1

    if filters.date_from:
        query += f" AND event_date >= ${param_count}"
        params.append(filters.date_from)
        param_count += 1

    if filters.date_to:
        query += f" AND event_date <= ${param_count}"
        params.append(filters.date_to)
        param_count += 1

    if filters.severity:
        query += f" AND severity = ${param_count}"
        params.append(filters.severity)
        param_count += 1

    query += f" ORDER BY event_date DESC LIMIT ${param_count}"
    params.append(filters.limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def _fetch_neighborhood_scorecard(
    pool: asyncpg.Pool,
    neighborhoods: List[str],
) -> Dict[str, Dict[str, Any]]:
    """
    Fetch neighborhood scorecard data.

    Args:
        pool: asyncpg connection pool
        neighborhoods: List of neighborhood names

    Returns:
        Dict mapping neighborhood -> metric -> value
    """
    query = """
        SELECT
            n.name,
            n.population,
            n.area_km2,
            n.metadata
        FROM neighborhoods n
        WHERE n.name = ANY($1)
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, neighborhoods)

    # Transform to nested dict, extracting metadata fields
    result = {}
    for row in rows:
        neighborhood_name = row["name"]
        meta = row.get("metadata") or {}
        result[neighborhood_name] = {
            "population": row.get("population"),
            "area_km2": row.get("area_km2"),
            "median_age": meta.get("median_age"),
            "household_income": meta.get("household_income"),
            "average_home_price": meta.get("average_home_price"),
            "transit_accessibility_score": meta.get("transit_accessibility_score"),
            "walkability_score": meta.get("walkability_score"),
        }

    return result


async def _fetch_parcels_for_export(
    pool: asyncpg.Pool,
    filters: ParcelExportFilters,
) -> List[Dict[str, Any]]:
    """
    Fetch parcel data from database matching export filters.

    Args:
        pool: asyncpg connection pool
        filters: ParcelExportFilters

    Returns:
        List of parcel dictionaries
    """
    query = "SELECT * FROM parcels WHERE 1=1"
    params = []
    param_count = 1

    if filters.neighborhood:
        query += f" AND geo_local_area = ${param_count}"
        params.append(filters.neighborhood)
        param_count += 1

    if filters.zoning:
        query += f" AND current_zoning = ${param_count}"
        params.append(filters.zoning)
        param_count += 1

    if filters.min_lot_sqft:
        # Convert sqft filter to sqm for the query (1 sqft = 0.0929 sqm)
        query += f" AND lot_area_sqm >= ${param_count}"
        params.append(filters.min_lot_sqft * 0.0929)
        param_count += 1

    if filters.max_lot_sqft:
        query += f" AND lot_area_sqm <= ${param_count}"
        params.append(filters.max_lot_sqft * 0.0929)
        param_count += 1

    query += f" ORDER BY pid ASC LIMIT ${param_count}"
    params.append(filters.limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]
