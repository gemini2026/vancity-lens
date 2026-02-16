"""
VanCity Lens — Undervalued Parcel Scoring Engine (FR-DEAL-001..006)

Identifies parcels where assessed value is significantly below
implied development value based on comparable transactions.

Scoring: discount_pct = (implied_value - assessed_value) / implied_value * 100
Threshold: >25% discount flags as undervalued.
"""

import asyncio
import logging
from collections import defaultdict
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

    return averages


async def generate_undervalued_alerts(
    db_pool: asyncpg.Pool,
    scored_parcels: list,
) -> int:
    """
    Evaluate scored parcels against user watchlist rules and generate alerts.

    Args:
        db_pool: Database connection pool
        scored_parcels: List of dicts from scoring run with keys:
            pid, discount_pct, lot_area_sqft, tod_tier, is_undervalued, neighborhood

    Returns:
        Count of alerts generated.
    """
    from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType

    alerts_created = 0
    alerts_failed = 0

    async with db_pool.acquire() as conn:
        # Get active watchlists with undervalued-related rules
        watchlists = await conn.fetch("""
            SELECT w.id, w.user_id, wr.rule_type, wr.rule_value
            FROM watchlists w
            JOIN watchlist_rules wr ON wr.watchlist_id = w.id
            WHERE w.is_active = true
              AND wr.rule_type IN ('undervalued_discount', 'undervalued_lot_area', 'undervalued_tod_tier')
        """)

        if not watchlists:
            return 0

        # Group rules by watchlist_id
        wl_rules: dict = defaultdict(list)
        for row in watchlists:
            wl_rules[row["id"]].append(row)

        for parcel in scored_parcels:
            if not parcel.get("is_undervalued"):
                continue

            signal = {
                "discount_pct": parcel.get("discount_pct", 0),
                "lot_area_sqft": parcel.get("lot_area_sqft", 0),
                "tod_tier": parcel.get("tod_tier"),
            }

            for wl_id, rules in wl_rules.items():
                rule_objs = [
                    WatchlistRule(
                        rule_type=RuleType(r["rule_type"]),
                        rule_value=r["rule_value"],
                    )
                    for r in rules
                ]
                if AlertEngine.match_rules(signal, rule_objs):
                    try:
                        await conn.execute("""
                            INSERT INTO alerts (
                                watchlist_id, signal_id, alert_type,
                                headline, summary, severity, created_at
                            ) VALUES ($1, 0, 'undervalued_match', $2, $3, 'medium', NOW())
                            ON CONFLICT DO NOTHING
                        """,
                            wl_id,
                            f"Undervalued: {parcel.get('pid', '?')} ({parcel.get('discount_pct', 0):.0f}% below market)",
                            f"Parcel {parcel.get('pid')} in {parcel.get('neighborhood', 'N/A')} flagged as undervalued.",
                        )
                        alerts_created += 1
                    except Exception as e:
                        alerts_failed += 1
                        logger.warning("Error creating undervalued alert (%s): %s", type(e).__name__, e, exc_info=True)

        if alerts_failed > 0 and alerts_created == 0:
            logger.error("All %d alert creation attempts failed (last: %s)", alerts_failed, type(e).__name__)

    return alerts_created


async def score_parcels(
    db_pool: asyncpg.Pool,
    limit: int = 1000,
) -> dict:
    """
    Score parcels for undervaluation and store results.

    Returns stats: parcels_scored, undervalued_count, errors.
    """
    stats = {"parcels_scored": 0, "undervalued_count": 0, "errors": 0}
    scored_list = []  # Collect scored parcels for alert generation

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

                    # Look up TOD tier via spatial join with toa_buffers
                    tier_row = await conn.fetchrow("""
                        SELECT MIN(tb.tier) AS tier
                        FROM toa_buffers tb
                        JOIN parcels pp ON pp.pid = $1
                        WHERE ST_Intersects(pp.geom, tb.geom)
                    """, parcel["pid"])
                    parcel_tod_tier = tier_row["tier"] if tier_row else None

                    # Collect scored parcel for alert generation
                    lot_area_sqft = float(parcel["lot_area_sqm"] or 0) * 10.7639
                    scored_list.append({
                        "pid": parcel["pid"],
                        "discount_pct": discount or 0,
                        "lot_area_sqft": round(lot_area_sqft, 1),
                        "tod_tier": parcel_tod_tier,
                        "is_undervalued": flagged,
                        "neighborhood": neighborhood,
                    })

                except Exception as e:
                    logger.warning("Error scoring parcel %s (%s): %s", parcel["pid"], type(e).__name__, e)
                    stats["errors"] += 1

    except (asyncpg.InterfaceError, asyncpg.PostgresConnectionError, asyncio.TimeoutError):
        raise
    except Exception as e:
        logger.error("Scoring batch failed: %s", e, exc_info=True)

    # Generate alerts for matched watchlist rules
    try:
        alerts = await generate_undervalued_alerts(db_pool, scored_list)
        stats["alerts_generated"] = alerts
    except Exception as e:
        logger.warning("Error generating undervalued alerts: %s", e)

    logger.info("Undervalued scoring complete: %s", stats)
    return stats


async def get_top_opportunities(
    db_pool: asyncpg.Pool,
    top_n: int = 20,
    tod_tier: Optional[str] = None,
    neighborhood: Optional[str] = None,
) -> list[dict]:
    """
    Get top undervalued parcels (weekly opportunity alert).

    Excludes parcels with active applications.

    Args:
        db_pool: Database connection pool
        top_n: Maximum number of results to return
        tod_tier: Optional filter, e.g. "Tier 1", "Tier 2", "Tier 3"
        neighborhood: Optional filter by geo_local_area name
    """
    async with db_pool.acquire() as conn:
        # Build dynamic WHERE clauses and parameter list
        conditions = [
            "us.is_undervalued = TRUE",
            "us.has_active_application = FALSE",
        ]
        params: list = []
        param_idx = 0

        # Parse tod_tier string (e.g. "Tier 1") into integer for DB query
        tier_int: Optional[int] = None
        if tod_tier:
            # Accept formats like "Tier 1", "tier 2", "1", "2"
            tier_str = tod_tier.strip().lower().replace("tier", "").strip()
            try:
                tier_int = int(tier_str)
            except ValueError:
                tier_int = None  # Invalid tier string, ignore filter

        if tier_int is not None:
            param_idx += 1
            conditions.append(f"""
                EXISTS (
                    SELECT 1 FROM toa_buffers tb
                    WHERE ST_Intersects(p.geom, tb.geom)
                      AND tb.tier = ${param_idx}
                )
            """)
            params.append(tier_int)

        if neighborhood:
            param_idx += 1
            conditions.append(f"p.geo_local_area = ${param_idx}")
            params.append(neighborhood)

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT DISTINCT ON (us.pid)
                us.pid, us.neighborhood, us.assessed_value, us.implied_value,
                us.buildable_sqft, us.discount_pct, us.repeat_signal,
                us.has_contamination, us.has_heritage, us.caveats,
                us.comp_count, us.computed_at,
                p.civic_address, p.current_zoning,
                (
                    SELECT MIN(tb.tier)
                    FROM toa_buffers tb
                    WHERE ST_Intersects(p.geom, tb.geom)
                ) AS tod_tier
            FROM undervalued_scores us
            JOIN parcels p ON p.pid = us.pid
            WHERE {where_clause}
            ORDER BY us.pid, us.computed_at DESC
        """

        rows = await conn.fetch(query, *params)

        # Sort by discount and take top N
        results = []
        for r in rows:
            row_dict = dict(r)
            # Format tod_tier as human-readable string (e.g. "Tier 1")
            raw_tier = row_dict.get("tod_tier")
            row_dict["tod_tier"] = f"Tier {raw_tier}" if raw_tier is not None else None
            results.append(row_dict)

        results.sort(key=lambda x: float(x.get("discount_pct") or 0), reverse=True)
        return results[:top_n]


async def get_parcel_undervaluation(
    db_pool: asyncpg.Pool,
    pid: str,
) -> Optional[dict]:
    """Get latest undervaluation score for a specific parcel."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM undervalued_scores
            WHERE pid = $1
            ORDER BY computed_at DESC
            LIMIT 1
        """, pid)
        return dict(row) if row else None
