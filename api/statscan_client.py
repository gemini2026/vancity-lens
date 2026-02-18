"""
StatsCan Web Data Service (WDS) client.

Public REST API — no auth, no API key, no registration required.
Rate limit: 25 req/sec (we use 20 to be safe).

Tables used:
  - 98-10-0035-01: Census tract demographics (2021 Census)
  - 17-10-0142-01: Population estimates by census subdivision
  - 34-10-0327-01: Building permits by census metropolitan area

API Docs: https://www.statcan.gc.ca/en/developers/wds
Base URL: https://www150.statcan.gc.ca/t1/tbl/en/dtl!downloadTbl/getData

Architecture:
  - Async HTTP client with rate limiting
  - Bulk CSV download for census data
  - On-demand JSON API for population/permits
  - Data validation (DV-DS008-001..005)
  - Stores to statscan_demographics, statscan_population, statscan_building_permits tables
"""

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Any

import aiohttp
import asyncpg

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────

WDS_BASE = "https://www150.statcan.gc.ca/t1/tbl/en"

# Table IDs (without hyphens for API)
TABLE_DEMOGRAPHICS = "98100035"     # Census tract demographics
TABLE_POPULATION = "17100142"       # Population estimates
TABLE_BUILDING_PERMITS = "34100327"  # Building permits

# Vancouver CMA code for StatsCan
VANCOUVER_CMA = "933"
VANCOUVER_CSD = "5915022"  # Census subdivision code for Vancouver proper

# Rate limit: 20 req/sec (safe margin below 25)
RATE_LIMIT_DELAY = 0.05  # 20 req/sec

HEADERS = {
    "User-Agent": "VanCityLensBot/0.1 (real-estate-intelligence)",
    "Accept": "application/json",
}

# ── Data Validation Rules (DV-DS008) ────────────────────────────

VALID_CENSUS_YEAR_RANGE = (2016, 2026)
VALID_POPULATION_RANGE = (0, 10_000_000)
VALID_INCOME_RANGE = (0, 500_000)
VALID_HOUSEHOLD_SIZE_RANGE = (0.5, 10.0)
VALID_PCT_RANGE = (0.0, 100.0)


class ValidationError(Exception):
    """Raised when data fails validation rules."""
    pass


def validate_census_year(year: int) -> bool:
    """DV-DS008-001: Census year must be in valid range."""
    return VALID_CENSUS_YEAR_RANGE[0] <= year <= VALID_CENSUS_YEAR_RANGE[1]


def validate_population(pop: int) -> bool:
    """DV-DS008-002: Population must be non-negative and reasonable."""
    return VALID_POPULATION_RANGE[0] <= pop <= VALID_POPULATION_RANGE[1]


def validate_income(income: int) -> bool:
    """DV-DS008-003: Median income must be in valid range."""
    return VALID_INCOME_RANGE[0] <= income <= VALID_INCOME_RANGE[1]


def validate_percentage(pct: float) -> bool:
    """DV-DS008-004: Percentages must be 0-100."""
    return VALID_PCT_RANGE[0] <= pct <= VALID_PCT_RANGE[1]


def validate_household_size(size: float) -> bool:
    """DV-DS008-005: Avg household size must be reasonable."""
    return VALID_HOUSEHOLD_SIZE_RANGE[0] <= size <= VALID_HOUSEHOLD_SIZE_RANGE[1]


class StatsCanclient:
    """Async client for StatsCan Web Data Service."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self._last_request = 0.0

    async def _rate_limit(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request
        if elapsed < RATE_LIMIT_DELAY:
            await asyncio.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request = asyncio.get_event_loop().time()

    async def _fetch_json(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        await self._rate_limit()
        try:
            async with self.session.get(
                url, headers=HEADERS, params=params,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                logger.warning("StatsCan fetch %s returned %d", url, resp.status)
                return None
        except Exception as e:
            logger.error("StatsCan fetch error %s: %s", url, e)
            return None

    async def _fetch_csv(self, url: str) -> Optional[str]:
        await self._rate_limit()
        try:
            async with self.session.get(
                url, headers={**HEADERS, "Accept": "text/csv"},
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
                logger.warning("StatsCan CSV fetch %s returned %d", url, resp.status)
                return None
        except Exception as e:
            logger.error("StatsCan CSV fetch error %s: %s", url, e)
            return None

    async def get_population_estimates(
        self, geo_code: str = VANCOUVER_CSD
    ) -> List[dict]:
        """
        Fetch population estimates for a census subdivision.
        Table 17-10-0142-01.
        """
        url = f"{WDS_BASE}/dtl!downloadTbl/getData"
        params = {
            "pid": TABLE_POPULATION,
            "type": "json",
        }
        data = await self._fetch_json(url, params)
        if not data:
            return []

        results = []
        try:
            # StatsCan WDS returns nested structure
            rows = data if isinstance(data, list) else data.get("data", data.get("rows", []))
            for row in rows:
                if isinstance(row, dict):
                    row_geo = str(row.get("GEO", row.get("geo_code", "")))
                    if geo_code in row_geo:
                        pop_val = row.get("VALUE", row.get("value"))
                        if pop_val is not None:
                            pop = int(float(pop_val))
                            if validate_population(pop):
                                results.append({
                                    "geo_code": geo_code,
                                    "geo_name": row.get("GEO", ""),
                                    "ref_date": str(row.get("REF_DATE", row.get("ref_date", ""))),
                                    "population": pop,
                                    "raw_data": row,
                                })
        except (ValueError, TypeError, KeyError) as e:
            logger.error("Error parsing population data: %s", e)

        return results

    async def get_building_permits(
        self, geo_code: str = VANCOUVER_CMA
    ) -> List[dict]:
        """
        Fetch building permit data for a CMA.
        Table 34-10-0327-01.
        """
        url = f"{WDS_BASE}/dtl!downloadTbl/getData"
        params = {
            "pid": TABLE_BUILDING_PERMITS,
            "type": "json",
        }
        data = await self._fetch_json(url, params)
        if not data:
            return []

        results = []
        try:
            rows = data if isinstance(data, list) else data.get("data", data.get("rows", []))
            for row in rows:
                if isinstance(row, dict):
                    row_geo = str(row.get("GEO", row.get("geo_code", "")))
                    if geo_code in row_geo or "Vancouver" in str(row.get("GEO", "")):
                        results.append({
                            "geo_code": geo_code,
                            "geo_name": row.get("GEO", ""),
                            "ref_date": str(row.get("REF_DATE", row.get("ref_date", ""))),
                            "permit_type": row.get("Type of building", row.get("type", "total")),
                            "num_permits": _safe_int(row.get("VALUE", row.get("value"))),
                            "value_thousands": _safe_decimal(row.get("VALUE", row.get("value"))),
                            "raw_data": row,
                        })
        except (ValueError, TypeError, KeyError) as e:
            logger.error("Error parsing building permits data: %s", e)

        return results


def _safe_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_decimal(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return None


# ── SQL ──────────────────────────────────────────────────────────

SQL_UPSERT_POPULATION = """
INSERT INTO statscan_population (geo_code, geo_name, ref_date, population, raw_data, retrieved_at)
VALUES ($1, $2, $3, $4, $5, NOW())
ON CONFLICT (geo_code, ref_date) DO UPDATE SET
    population = EXCLUDED.population,
    raw_data = EXCLUDED.raw_data,
    retrieved_at = NOW()
"""

SQL_UPSERT_PERMITS = """
INSERT INTO statscan_building_permits (geo_code, geo_name, ref_date, permit_type, num_permits, value_thousands, raw_data, retrieved_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
ON CONFLICT (geo_code, ref_date, permit_type) DO UPDATE SET
    num_permits = EXCLUDED.num_permits,
    value_thousands = EXCLUDED.value_thousands,
    raw_data = EXCLUDED.raw_data,
    retrieved_at = NOW()
"""

SQL_UPSERT_DEMOGRAPHICS = """
INSERT INTO statscan_demographics (
    census_tract, census_year, population, population_5yr_growth,
    median_household_income, avg_household_size, owner_pct, renter_pct,
    dominant_dwelling_type, total_dwellings, median_age, raw_data, retrieved_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
ON CONFLICT (census_tract, census_year) DO UPDATE SET
    population = EXCLUDED.population,
    population_5yr_growth = EXCLUDED.population_5yr_growth,
    median_household_income = EXCLUDED.median_household_income,
    avg_household_size = EXCLUDED.avg_household_size,
    owner_pct = EXCLUDED.owner_pct,
    renter_pct = EXCLUDED.renter_pct,
    dominant_dwelling_type = EXCLUDED.dominant_dwelling_type,
    total_dwellings = EXCLUDED.total_dwellings,
    median_age = EXCLUDED.median_age,
    raw_data = EXCLUDED.raw_data,
    retrieved_at = NOW()
"""


async def ingest_population(db_pool: asyncpg.Pool) -> Dict[str, int]:
    """Fetch and store population estimates."""
    stats = {"found": 0, "stored": 0, "errors": 0}

    async with aiohttp.ClientSession() as session:
        client = StatsCanclient(session)
        records = await client.get_population_estimates()
        stats["found"] = len(records)

        async with db_pool.acquire() as conn:
            for rec in records:
                try:
                    await conn.execute(
                        SQL_UPSERT_POPULATION,
                        rec["geo_code"],
                        rec["geo_name"],
                        rec["ref_date"],
                        rec["population"],
                        json.dumps(rec.get("raw_data", {})),
                    )
                    stats["stored"] += 1
                except Exception as e:
                    logger.error("Error storing population record: %s", e)
                    stats["errors"] += 1

    return stats


async def ingest_building_permits(db_pool: asyncpg.Pool) -> Dict[str, int]:
    """Fetch and store building permit data."""
    stats = {"found": 0, "stored": 0, "errors": 0}

    async with aiohttp.ClientSession() as session:
        client = StatsCanclient(session)
        records = await client.get_building_permits()
        stats["found"] = len(records)

        async with db_pool.acquire() as conn:
            for rec in records:
                try:
                    await conn.execute(
                        SQL_UPSERT_PERMITS,
                        rec["geo_code"],
                        rec["geo_name"],
                        rec["ref_date"],
                        rec.get("permit_type", "total"),
                        rec.get("num_permits"),
                        rec.get("value_thousands"),
                        json.dumps(rec.get("raw_data", {})),
                    )
                    stats["stored"] += 1
                except Exception as e:
                    logger.error("Error storing permits record: %s", e)
                    stats["errors"] += 1

    return stats


async def scrape_and_store(
    db_pool: asyncpg.Pool,
    start_date: datetime,
    end_date: datetime,
) -> Dict[str, int]:
    """
    Main entry point for StatsCan data ingestion.
    Called by the scheduler with standard signature.
    """
    stats: Dict[str, int] = {
        "documents_found": 0,
        "documents_new": 0,
        "documents_skipped": 0,
        "errors": 0,
    }

    pop_stats = await ingest_population(db_pool)
    permit_stats = await ingest_building_permits(db_pool)

    stats["documents_found"] = pop_stats["found"] + permit_stats["found"]
    stats["documents_new"] = pop_stats["stored"] + permit_stats["stored"]
    stats["errors"] = pop_stats["errors"] + permit_stats["errors"]

    logger.info("StatsCan ingestion complete: pop=%s, permits=%s", pop_stats, permit_stats)
    return stats
