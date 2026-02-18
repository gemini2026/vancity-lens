"""
CMHC Housing Data client — ingests from Open Canada bulk CSV downloads.

No auth, no API key, no registration required.
Datasets: Housing Starts, Completions, Under Construction, Absorptions.
Vancouver CMA = 933. Monthly refresh.

Source: https://search.open.canada.ca/opendata/?owner_org=cmhc-schl
Direct CSV: https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data

Architecture:
  - Downloads CSV files from CMHC open data portal
  - Parses and validates housing metrics
  - Stores to cmhc_housing table
  - Data validation (DV-DS009-001..006)
"""

import csv
import io
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
import asyncpg

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────

# CMHC Open Data CSV endpoints (stable URLs for programmatic access)
CMHC_DATA_URLS = {
    "starts": "https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data/data-tables/housing-starts",
    "completions": "https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data/data-tables/housing-completions",
    "under_construction": "https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data/data-tables/under-construction",
    "absorptions": "https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data/data-tables/absorptions",
}

# Vancouver CMA code
VANCOUVER_CMA = "933"
VANCOUVER_CMA_NAME = "Vancouver"

# Dwelling types we track
DWELLING_TYPES = ["single", "semi", "row", "apartment", "total"]

HEADERS = {
    "User-Agent": "VanCityLensBot/0.1 (real-estate-intelligence)",
}

# ── Data Validation Rules (DV-DS009) ────────────────────────────

VALID_METRICS = {"starts", "completions", "under_construction", "absorptions"}
VALID_VALUE_RANGE = (0, 100_000)  # No single metric should exceed this


def validate_metric(metric: str) -> bool:
    """DV-DS009-001: Metric must be a known type."""
    return metric in VALID_METRICS


def validate_value(value: int) -> bool:
    """DV-DS009-002: Values must be non-negative and reasonable."""
    return VALID_VALUE_RANGE[0] <= value <= VALID_VALUE_RANGE[1]


def validate_dwelling_type(dtype: str) -> bool:
    """DV-DS009-003: Dwelling type must be recognized."""
    return dtype.lower() in DWELLING_TYPES


def validate_ref_date(ref_date: str) -> bool:
    """DV-DS009-004: Reference date must be parseable (YYYY-MM or YYYY)."""
    if not ref_date:
        return False
    parts = ref_date.split("-")
    if len(parts) < 1:
        return False
    try:
        year = int(parts[0])
        return 1990 <= year <= 2030
    except ValueError:
        return False


def validate_cma_code(code: str) -> bool:
    """DV-DS009-005: CMA code must be numeric string."""
    return code.isdigit() and len(code) == 3


def validate_completeness(record: dict) -> bool:
    """DV-DS009-006: Required fields must be present."""
    required = ["cma_code", "ref_date", "metric", "value"]
    return all(record.get(f) is not None for f in required)


class CMHCClient:
    """Client for CMHC open data CSV ingestion."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def _fetch_csv(self, url: str) -> Optional[str]:
        try:
            async with self.session.get(
                url, headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 200:
                    content_type = resp.content_type or ""
                    if "csv" in content_type or "text" in content_type:
                        return await resp.text()
                    # Some CMHC endpoints return HTML — need to handle gracefully
                    body = await resp.text()
                    if body.startswith("<!") or "<html" in body[:200].lower():
                        logger.warning("CMHC URL returned HTML instead of CSV: %s", url)
                        return None
                    return body
                logger.warning("CMHC fetch %s returned %d", url, resp.status)
                return None
        except Exception as e:
            logger.error("CMHC fetch error %s: %s", url, e)
            return None

    async def fetch_housing_data(self, metric: str) -> List[dict]:
        """
        Fetch housing data for a specific metric.

        Returns records filtered to Vancouver CMA.
        """
        if not validate_metric(metric):
            logger.error("Invalid CMHC metric: %s", metric)
            return []

        url = CMHC_DATA_URLS.get(metric)
        if not url:
            logger.error("No URL configured for metric: %s", metric)
            return []

        csv_text = await self._fetch_csv(url)
        if not csv_text:
            return []

        return self._parse_csv(csv_text, metric)

    def _parse_csv(self, csv_text: str, metric: str) -> List[dict]:
        """Parse CMHC CSV data, filtering to Vancouver CMA."""
        records = []
        try:
            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                # CMHC CSVs typically have columns like:
                # Date, Geography, CMA/CA, Dwelling Type, Value
                # Column names vary by dataset, so we check multiple patterns
                cma = (
                    row.get("CMA/CA", "")
                    or row.get("cma_code", "")
                    or row.get("Centre", "")
                )
                geo_name = row.get("Geography", "") or row.get("geo_name", "")

                # Filter to Vancouver CMA
                if VANCOUVER_CMA not in str(cma) and "Vancouver" not in geo_name:
                    continue

                ref_date = (
                    row.get("Date", "")
                    or row.get("REF_DATE", "")
                    or row.get("ref_date", "")
                    or row.get("Period", "")
                )
                dwelling_type = (
                    row.get("Dwelling Type", "")
                    or row.get("dwelling_type", "")
                    or row.get("Type", "")
                    or "total"
                ).lower()
                value_str = (
                    row.get("Value", "")
                    or row.get("VALUE", "")
                    or row.get("Units", "")
                    or "0"
                )

                # Normalize dwelling type
                dtype = "total"
                if dwelling_type:
                    for known in DWELLING_TYPES:
                        if known in dwelling_type:
                            dtype = known
                            break

                try:
                    value = int(float(value_str.replace(",", ""))) if value_str else 0
                except (ValueError, TypeError):
                    value = 0

                record = {
                    "cma_code": VANCOUVER_CMA,
                    "cma_name": VANCOUVER_CMA_NAME,
                    "ref_date": ref_date,
                    "metric": metric,
                    "dwelling_type": dtype,
                    "value": value,
                    "raw_data": dict(row),
                }

                # Validate
                if validate_ref_date(ref_date) and validate_value(value):
                    records.append(record)

        except Exception as e:
            logger.error("Error parsing CMHC CSV for %s: %s", metric, e)

        logger.info("Parsed %d Vancouver CMA records for %s", len(records), metric)
        return records


# ── SQL ──────────────────────────────────────────────────────────

SQL_UPSERT_HOUSING = """
INSERT INTO cmhc_housing (cma_code, cma_name, ref_date, metric, dwelling_type, value, raw_data, retrieved_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
ON CONFLICT (cma_code, ref_date, metric, dwelling_type) DO UPDATE SET
    value = EXCLUDED.value,
    raw_data = EXCLUDED.raw_data,
    retrieved_at = NOW()
"""


async def ingest_all_metrics(db_pool: asyncpg.Pool) -> Dict[str, Dict[str, int]]:
    """Ingest all CMHC housing metrics."""
    all_stats = {}

    async with aiohttp.ClientSession() as session:
        client = CMHCClient(session)

        for metric in VALID_METRICS:
            stats = {"found": 0, "stored": 0, "errors": 0}
            records = await client.fetch_housing_data(metric)
            stats["found"] = len(records)

            async with db_pool.acquire() as conn:
                for rec in records:
                    try:
                        await conn.execute(
                            SQL_UPSERT_HOUSING,
                            rec["cma_code"],
                            rec["cma_name"],
                            rec["ref_date"],
                            rec["metric"],
                            rec["dwelling_type"],
                            rec["value"],
                            json.dumps(rec.get("raw_data", {})),
                        )
                        stats["stored"] += 1
                    except Exception as e:
                        logger.error("Error storing CMHC %s record: %s", metric, e)
                        stats["errors"] += 1

            all_stats[metric] = stats

    return all_stats


async def scrape_and_store(
    db_pool: asyncpg.Pool,
    start_date: datetime,
    end_date: datetime,
) -> Dict[str, int]:
    """
    Main entry point for CMHC data ingestion.
    Called by the scheduler with standard signature.
    """
    stats: Dict[str, int] = {
        "documents_found": 0,
        "documents_new": 0,
        "documents_skipped": 0,
        "errors": 0,
    }

    all_metrics = await ingest_all_metrics(db_pool)

    for metric, mstats in all_metrics.items():
        stats["documents_found"] += mstats["found"]
        stats["documents_new"] += mstats["stored"]
        stats["errors"] += mstats["errors"]

    logger.info("CMHC ingestion complete: %s", stats)
    return stats
