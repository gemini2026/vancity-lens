"""
Neighborhood Investment Metrics for VanCity Lens.

Computes investment-oriented metrics for neighborhoods:
1. Supply pipeline count (active projects + proposed units)
2. Average approval timeline (months from first entry to approval)
3. Supply pressure (proposed units / parcel count)
4. Development momentum (signals last 90d / signals prior 90d)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def slug_to_neighborhood_name(slug: str) -> str:
    """Convert URL slug to neighborhood display name.

    Examples:
        'mount-pleasant' -> 'Mount Pleasant'
        'downtown' -> 'Downtown'
        'dunbar-southlands' -> 'Dunbar-Southlands'

    Note: This is a fallback. The endpoint should prefer looking up
    the name from the neighborhoods table using the slug column.
    """
    return slug.replace("-", " ").title()


async def resolve_neighborhood_name(conn, slug: str) -> Optional[str]:
    """Look up the official neighborhood name from the neighborhoods table.

    Falls back to slug_to_neighborhood_name() if the table doesn't exist
    or the slug is not found.
    """
    try:
        row = await conn.fetchrow(
            "SELECT name FROM neighborhoods WHERE slug = $1", slug
        )
        if row:
            return row["name"]
    except Exception as e:
        logger.debug("Could not resolve neighborhood name from DB: %s", e)
    return slug_to_neighborhood_name(slug)


async def get_supply_pipeline_count(conn, neighborhood_name: str) -> dict:
    """Get active project count and total proposed units for a neighborhood.

    Returns:
        {
            "active_projects": int,
            "proposed_units": int
        }
    """
    try:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS active_projects,
                COALESCE(SUM(proposed_units), 0) AS proposed_units
            FROM supply_pipeline
            WHERE neighborhood = $1
              AND pipeline_stage NOT IN ('completed', 'refused', 'withdrawn')
            """,
            neighborhood_name,
        )
        return {
            "active_projects": int(row["active_projects"]) if row else 0,
            "proposed_units": int(row["proposed_units"]) if row else 0,
        }
    except Exception as e:
        logger.warning("Error fetching supply pipeline count: %s", e)
        return {"active_projects": 0, "proposed_units": 0}


async def get_avg_approval_timeline(conn, neighborhood_name: str) -> Optional[float]:
    """Compute average months from first pipeline entry to approval stage.

    Looks at pipeline_stage_history for projects in this neighborhood.
    Computes the time between the earliest entry (from_stage IS NULL or
    first record) and the first record where to_stage contains 'approved'.

    Returns:
        Average months as float, or None if no data.
    """
    try:
        row = await conn.fetchrow(
            """
            WITH project_timelines AS (
                SELECT
                    sp.id AS pipeline_id,
                    MIN(psh.changed_at) AS first_entry,
                    MIN(CASE WHEN psh.to_stage IN ('approved', 'under_construction')
                        THEN psh.changed_at END) AS approval_date
                FROM supply_pipeline sp
                JOIN pipeline_stage_history psh ON psh.pipeline_id = sp.id
                WHERE sp.neighborhood = $1
                GROUP BY sp.id
                HAVING MIN(CASE WHEN psh.to_stage IN ('approved', 'under_construction')
                    THEN psh.changed_at END) IS NOT NULL
            )
            SELECT AVG(
                EXTRACT(EPOCH FROM (approval_date - first_entry)) / (30.44 * 86400)
            ) AS avg_months
            FROM project_timelines
            """,
            neighborhood_name,
        )
        if row and row["avg_months"] is not None:
            return round(float(row["avg_months"]), 1)
        return None
    except Exception as e:
        logger.warning("Error fetching approval timeline: %s", e)
        return None


async def get_supply_pressure(conn, neighborhood_name: str) -> Optional[float]:
    """Compute supply pressure: proposed_units / parcel_count.

    Returns:
        Ratio as float, or None if no parcels found.
    """
    try:
        row = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(sp.proposed_units), 0) AS proposed_units,
                (SELECT COUNT(*) FROM parcels WHERE geo_local_area = $1) AS parcel_count
            FROM supply_pipeline sp
            WHERE sp.neighborhood = $1
              AND sp.pipeline_stage NOT IN ('completed', 'refused', 'withdrawn')
            """,
            neighborhood_name,
        )
        if not row:
            return None
        parcel_count = int(row["parcel_count"])
        if parcel_count == 0:
            return None
        proposed_units = int(row["proposed_units"])
        return round(proposed_units / parcel_count, 3)
    except Exception as e:
        logger.warning("Error fetching supply pressure: %s", e)
        return None


async def get_development_momentum(conn, neighborhood_name: str) -> Optional[float]:
    """Compute development momentum: signals_last_90d / signals_prior_90d.

    Returns:
        Ratio as float, or None if no prior signals (avoids division by zero).
    """
    try:
        now = datetime.now(timezone.utc)
        d90_ago = now - timedelta(days=90)
        d180_ago = now - timedelta(days=180)

        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE extracted_at >= $2) AS signals_last_90d,
                COUNT(*) FILTER (WHERE extracted_at >= $3 AND extracted_at < $2) AS signals_prior_90d
            FROM intelligence_signals
            WHERE neighborhood = $1
              AND extracted_at >= $3
            """,
            neighborhood_name,
            d90_ago,
            d180_ago,
        )
        if not row:
            return None

        last_90 = int(row["signals_last_90d"])
        prior_90 = int(row["signals_prior_90d"])

        if prior_90 == 0:
            # If there are recent signals but none prior, return a high value
            # If no signals at all, return None
            if last_90 > 0:
                return float(last_90)  # Treat as "infinite" growth, capped at count
            return None

        return round(last_90 / prior_90, 2)
    except Exception as e:
        logger.warning("Error fetching development momentum: %s", e)
        return None


async def get_neighborhood_investment_metrics(conn, slug: str) -> Optional[dict]:
    """Get all investment metrics for a neighborhood.

    Args:
        conn: asyncpg connection
        slug: URL-friendly neighborhood slug (e.g., 'mount-pleasant')

    Returns:
        Dict with all metrics, or None if neighborhood not found.
    """
    neighborhood_name = await resolve_neighborhood_name(conn, slug)

    pipeline = await get_supply_pipeline_count(conn, neighborhood_name)
    avg_timeline = await get_avg_approval_timeline(conn, neighborhood_name)
    supply_pressure = await get_supply_pressure(conn, neighborhood_name)
    momentum = await get_development_momentum(conn, neighborhood_name)

    return {
        "neighborhood": neighborhood_name,
        "slug": slug,
        "active_projects": pipeline["active_projects"],
        "proposed_units": pipeline["proposed_units"],
        "avg_approval_months": avg_timeline,
        "supply_pressure": supply_pressure,
        "development_momentum": momentum,
    }
