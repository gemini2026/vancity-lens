"""
VanCity Lens — Undervalued Parcel Scoring Engine (FR-DEAL-001..006)

Identifies parcels where assessed value is significantly below
implied development value based on comparable transactions.

Scoring: discount_pct = (implied_value - assessed_value) / implied_value * 100
Threshold: >25% discount flags as undervalued.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# Scoring thresholds
UNDERVALUED_THRESHOLD_PCT = 25.0
MIN_COMPARABLES = 3
MAX_BCA_AGE_MONTHS = 18
COMP_LOOKBACK_MONTHS = 12


def compute_implied_value(
    buildable_sqft: float,
    avg_comp_per_bsf: float,
) -> int:
    """Compute implied development value from buildable SF and comp average."""
    if buildable_sqft <= 0 or avg_comp_per_bsf <= 0:
        return 0
    return int(buildable_sqft * avg_comp_per_bsf)


def compute_discount_pct(
    assessed_value: int,
    implied_value: int,
) -> Optional[float]:
    """
    Compute discount percentage.

    Positive = undervalued (assessed < implied).
    Negative = overvalued (assessed > implied).
    """
    if implied_value <= 0 or assessed_value is None:
        return None
    return round(((implied_value - assessed_value) / implied_value) * 100, 2)


def is_undervalued(discount_pct: Optional[float]) -> bool:
    """Check if discount exceeds threshold."""
    if discount_pct is None:
        return False
    return discount_pct > UNDERVALUED_THRESHOLD_PCT


def build_caveats(
    has_contamination: bool,
    has_heritage: bool,
    comp_count: int,
    bca_age_months: Optional[int],
) -> list[str]:
    """Build caveat list for the parcel."""
    caveats = []
    if has_contamination:
        caveats.append("Potential environmental contamination nearby")
    if has_heritage:
        caveats.append("Heritage register listing may restrict development")
    if comp_count < 5:
        caveats.append(f"Limited comparable data ({comp_count} transactions)")
    if bca_age_months and bca_age_months > MAX_BCA_AGE_MONTHS:
        caveats.append(f"BC Assessment data is {bca_age_months} months old")
    return caveats


async def compute_comp_averages(
    db_pool: asyncpg.Pool,
    lookback_months: int = COMP_LOOKBACK_MONTHS,
) -> dict[str, dict]:
    """
    Compute average $/buildable-SF per neighborhood from comparable sales.

    Returns {neighborhood: {avg_price_per_sqft, count, latest_date}}.
    """
    cutoff = date.today() - timedelta(days=lookback_months * 30)
    averages = {}

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    neighborhood,
                    AVG(price_per_lot_sqft) AS avg_price,
                    COUNT(*) AS comp_count,
                    MAX(sale_date) AS latest_date
                FROM comparable_sales
                WHERE sale_date >= $1
                  AND price_per_lot_sqft > 0
                  AND neighborhood IS NOT NULL
                GROUP BY neighborhood
                HAVING COUNT(*) >= $2
            """, cutoff, MIN_COMPARABLES)

            for row in rows:
                averages[row["neighborhood"]] = {
                    "avg_price_per_sqft": float(row["avg_price"]),
                    "count": row["comp_count"],
                    "latest_date": str(row["latest_date"]) if row["latest_date"] else None,
                }
    except Exception as e:
        logger.warning("Failed to compute comp averages: %s", str(e)[:200])

    return averages


async def score_parcels(
    db_pool: asyncpg.Pool,
    limit: int = 1000,
) -> dict:
    """
    Score parcels for undervaluation and store results.

    Returns stats: parcels_scored, undervalued_count, errors.
    """
    stats = {"parcels_scored": 0, "undervalued_count": 0, "errors": 0}

    # Get comp averages per neighborhood
    comp_avgs = await compute_comp_averages(db_pool)
    if not comp_avgs:
        logger.warning("No comparable averages available, skipping scoring")
        return stats

    try:
        async with db_pool.acquire() as conn:
            # Get parcels with entitlements and assessed values
            parcels = await conn.fetch("""
                SELECT
                    p.pid, p.geo_local_area AS neighborhood,
                    p.assessed_value, p.lot_area_sqm,
                    pe.entitled_fsr, pe.buildable_sqft
                FROM parcels p
                LEFT JOIN parcel_entitlements pe ON pe.pid = p.pid
                WHERE p.assessed_value IS NOT NULL
                  AND p.assessed_value > 0
                  AND pe.entitled_fsr IS NOT NULL
                  AND p.geo_local_area IS NOT NULL
                ORDER BY p.pid
                LIMIT $1
            """, limit)

            for parcel in parcels:
                try:
                    neighborhood = parcel["neighborhood"]
                    if neighborhood not in comp_avgs:
                        continue

                    avg_data = comp_avgs[neighborhood]
                    buildable = float(parcel["buildable_sqft"] or 0)
                    if buildable <= 0:
                        # Compute from lot area and FSR
                        lot_sqm = float(parcel["lot_area_sqm"] or 0)
                        fsr = float(parcel["entitled_fsr"] or 0)
                        buildable = lot_sqm * 10.7639 * fsr

                    if buildable <= 0:
                        continue

                    assessed = int(parcel["assessed_value"])
                    avg_comp = avg_data["avg_price_per_sqft"]
                    comp_count = avg_data["count"]

                    implied = compute_implied_value(buildable, avg_comp)
                    discount = compute_discount_pct(assessed, implied)
                    flagged = is_undervalued(discount)

                    # Check for active application
                    active_app = await conn.fetchrow("""
                        SELECT 1 FROM supply_pipeline
                        WHERE parcel_pid = $1
                          AND pipeline_stage NOT IN ('completed', 'withdrawn')
                        LIMIT 1
                    """, parcel["pid"])
                    has_active = active_app is not None

                    # Check for contamination
                    contam = await conn.fetchrow("""
                        SELECT 1 FROM contaminated_sites
                        WHERE associated_pid = $1
                        LIMIT 1
                    """, parcel["pid"])
                    has_contam = contam is not None

                    # Check for heritage
                    heritage = await conn.fetchrow("""
                        SELECT 1 FROM heritage_sites
                        WHERE pid = $1
                        LIMIT 1
                    """, parcel["pid"])
                    has_heritage = heritage is not None

                    caveats = build_caveats(has_contam, has_heritage, comp_count, None)

                    # Check if previously flagged (repeat signal)
                    prev = await conn.fetchrow("""
                        SELECT 1 FROM undervalued_scores
                        WHERE pid = $1 AND is_undervalued = TRUE
                        LIMIT 1
                    """, parcel["pid"])
                    repeat = prev is not None

                    await conn.execute("""
                        INSERT INTO undervalued_scores (
                            pid, neighborhood, assessed_value, implied_value,
                            buildable_sqft, avg_comp_per_bsf, comp_count,
                            discount_pct, is_undervalued, repeat_signal,
                            has_active_application, has_contamination,
                            has_heritage, caveats
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                    """,
                        parcel["pid"], neighborhood, assessed, implied,
                        round(buildable, 1), round(avg_comp, 2), comp_count,
                        discount, flagged, repeat,
                        has_active, has_contam, has_heritage, caveats,
                    )

                    stats["parcels_scored"] += 1
                    if flagged and not has_active:
                        stats["undervalued_count"] += 1

                except Exception as e:
                    logger.debug("Error scoring parcel %s: %s", parcel["pid"], str(e)[:100])
                    stats["errors"] += 1

    except Exception as e:
        logger.error("Scoring batch failed: %s", str(e)[:200])

    logger.info("Undervalued scoring complete: %s", stats)
    return stats


async def get_top_opportunities(
    db_pool: asyncpg.Pool,
    top_n: int = 20,
) -> list[dict]:
    """
    Get top undervalued parcels (weekly opportunity alert).

    Excludes parcels with active applications.
    """
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT ON (us.pid)
                    us.pid, us.neighborhood, us.assessed_value, us.implied_value,
                    us.buildable_sqft, us.discount_pct, us.repeat_signal,
                    us.has_contamination, us.has_heritage, us.caveats,
                    us.comp_count, us.computed_at,
                    p.civic_address, p.current_zoning
                FROM undervalued_scores us
                JOIN parcels p ON p.pid = us.pid
                WHERE us.is_undervalued = TRUE
                  AND us.has_active_application = FALSE
                ORDER BY us.pid, us.computed_at DESC
            """)

            # Sort by discount and take top N
            results = [dict(r) for r in rows]
            results.sort(key=lambda x: float(x.get("discount_pct") or 0), reverse=True)
            return results[:top_n]
    except Exception as e:
        logger.warning("Failed to get top opportunities: %s", str(e)[:200])
        return []


async def get_parcel_undervaluation(
    db_pool: asyncpg.Pool,
    pid: str,
) -> Optional[dict]:
    """Get latest undervaluation score for a specific parcel."""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM undervalued_scores
                WHERE pid = $1
                ORDER BY computed_at DESC
                LIMIT 1
            """, pid)
            return dict(row) if row else None
    except Exception as e:
        logger.debug("Error fetching undervaluation for %s: %s", pid, e)
        return None
