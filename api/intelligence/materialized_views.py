"""
Materialized view management and queries for neighborhood composite scores.

Provides functions to:
- Refresh materialized views for performance optimization
- Query neighborhood rankings and detail
- Compare multiple neighborhoods
- Manage background refresh scheduling
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
import asyncpg

from .models import (
    NeighborhoodScorecard,
    NeighborhoodSummary,
    NeighborhoodComparison,
    NeighborhoodBase,
    CategoryScore,
    MetricCategory,
    TrendDirection,
)

logger = logging.getLogger(__name__)


# ── Refresh Functions ────────────────────────────────────────────

async def refresh_neighborhood_scores(db_pool: asyncpg.Pool) -> dict:
    """
    Refresh the mv_neighborhood_scores materialized view.

    Returns timing information and row count.

    Args:
        db_pool: AsyncPG connection pool

    Returns:
        dict with keys:
            - view_name: 'mv_neighborhood_scores'
            - rows_refreshed: Number of rows in view
            - duration_ms: Refresh duration in milliseconds
            - success: Whether refresh succeeded
            - timestamp: ISO timestamp of refresh
    """
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT view_name, rows_refreshed, duration_ms, success "
                "FROM refresh_mv_neighborhood_scores()"
            )

            if row:
                return {
                    "view_name": row["view_name"],
                    "rows_refreshed": row["rows_refreshed"],
                    "duration_ms": row["duration_ms"],
                    "success": row["success"],
                    "timestamp": datetime.utcnow().isoformat(),
                }
    except Exception as e:
        logger.error(f"Error refreshing neighborhood scores view: {e}")
        return {
            "view_name": "mv_neighborhood_scores",
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


async def refresh_signal_activity(db_pool: asyncpg.Pool) -> dict:
    """
    Refresh the mv_neighborhood_signal_activity materialized view.

    Returns timing information and row count.

    Args:
        db_pool: AsyncPG connection pool

    Returns:
        dict with keys:
            - view_name: 'mv_neighborhood_signal_activity'
            - rows_refreshed: Number of rows in view
            - duration_ms: Refresh duration in milliseconds
            - success: Whether refresh succeeded
            - timestamp: ISO timestamp of refresh
    """
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT view_name, rows_refreshed, duration_ms, success "
                "FROM refresh_mv_neighborhood_signal_activity()"
            )

            if row:
                return {
                    "view_name": row["view_name"],
                    "rows_refreshed": row["rows_refreshed"],
                    "duration_ms": row["duration_ms"],
                    "success": row["success"],
                    "timestamp": datetime.utcnow().isoformat(),
                }
    except Exception as e:
        logger.error(f"Error refreshing signal activity view: {e}")
        return {
            "view_name": "mv_neighborhood_signal_activity",
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


async def refresh_all_views(db_pool: asyncpg.Pool) -> dict:
    """
    Refresh all materialized views.

    Returns combined results from both view refreshes.

    Args:
        db_pool: AsyncPG connection pool

    Returns:
        dict with keys:
            - views: list of refresh result dicts
            - total_duration_ms: Combined refresh duration
            - all_success: Whether all refreshes succeeded
            - timestamp: ISO timestamp of refresh
    """
    results = []
    total_duration = 0

    try:
        async with db_pool.acquire() as conn:
            # Refresh toa_buffers (spatial TOA zone buffers used by entitlement engine)
            try:
                import time as _time
                t0 = _time.monotonic()
                await conn.execute("REFRESH MATERIALIZED VIEW toa_buffers")
                dur_ms = int((_time.monotonic() - t0) * 1000)
                row_count = await conn.fetchval("SELECT COUNT(*) FROM toa_buffers")
                results.append({
                    "view_name": "toa_buffers",
                    "rows_refreshed": row_count,
                    "duration_ms": dur_ms,
                    "success": True,
                })
                total_duration += dur_ms
                logger.info(f"toa_buffers refreshed: {row_count} rows in {dur_ms}ms")
            except Exception as toa_err:
                logger.warning(f"Could not refresh toa_buffers: {toa_err}")
                results.append({
                    "view_name": "toa_buffers",
                    "rows_refreshed": 0,
                    "duration_ms": 0,
                    "success": False,
                })

            # Refresh neighborhood scores and signal activity views
            rows = await conn.fetch(
                "SELECT view_name, rows_refreshed, duration_ms, success "
                "FROM refresh_all_materialized_views()"
            )

            for row in rows:
                view_result = {
                    "view_name": row["view_name"],
                    "rows_refreshed": row["rows_refreshed"],
                    "duration_ms": row["duration_ms"],
                    "success": row["success"],
                }
                results.append(view_result)
                total_duration += row["duration_ms"]

            # Log the refresh event
            try:
                await conn.execute(
                    """
                    INSERT INTO materialized_view_refreshes
                    (view_name, rows_refreshed, duration_ms, success)
                    SELECT view_name, rows_refreshed, duration_ms, success
                    FROM refresh_all_materialized_views()
                    """
                )
            except Exception as log_err:
                logger.warning(f"Could not log refresh event: {log_err}")

        all_success = all(r.get("success", False) for r in results)

        return {
            "views": results,
            "total_duration_ms": total_duration,
            "all_success": all_success,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error refreshing all views: {e}")
        return {
            "views": results,
            "total_duration_ms": total_duration,
            "all_success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


# ── Query Functions ─────────────────────────────────────────────

async def get_neighborhood_rankings(
    db_pool: asyncpg.Pool, limit: int = 50
) -> list[NeighborhoodSummary]:
    """
    Get neighborhood rankings from materialized view (fast).

    Returns top neighborhoods by overall_score with summary info.

    Args:
        db_pool: AsyncPG connection pool
        limit: Maximum neighborhoods to return (default 50, typically 22 for Vancouver)

    Returns:
        List of NeighborhoodSummary objects sorted by rank
    """
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    name,
                    slug,
                    overall_score,
                    rank,
                    category_scores
                FROM mv_neighborhood_scores
                ORDER BY rank ASC
                LIMIT $1
                """,
                limit,
            )

            summaries = []
            for row in rows:
                # Find top and bottom categories
                cat_scores = row["category_scores"] or {}
                top_cat = None
                bottom_cat = None

                if cat_scores:
                    sorted_cats = sorted(cat_scores.items(), key=lambda x: x[1], reverse=True)
                    if sorted_cats:
                        top_cat = sorted_cats[0][0]
                        bottom_cat = sorted_cats[-1][0]

                summary = NeighborhoodSummary(
                    name=row["name"],
                    slug=row["slug"],
                    overall_score=float(row["overall_score"]),
                    rank=row["rank"],
                    top_category=top_cat,
                    bottom_category=bottom_cat,
                )
                summaries.append(summary)

            return summaries

    except Exception as e:
        logger.error(f"Error retrieving neighborhood rankings: {e}")
        return []


async def get_neighborhood_detail(
    db_pool: asyncpg.Pool, slug: str
) -> Optional[NeighborhoodScorecard]:
    """
    Get full neighborhood scorecard from materialized view (fast).

    Returns complete scorecard with category breakdown, rank, and intelligence stats.

    Args:
        db_pool: AsyncPG connection pool
        slug: Neighborhood slug (e.g., 'kitsilano')

    Returns:
        NeighborhoodScorecard or None if not found
    """
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    name,
                    slug,
                    overall_score,
                    rank,
                    category_scores,
                    active_rezonings,
                    recent_permits,
                    signal_activity_score
                FROM mv_neighborhood_scores
                WHERE slug = $1
                """,
                slug,
            )

            if not row:
                return None

            # Parse category scores
            cat_scores_dict = row["category_scores"] or {}
            category_scores = []

            for category in MetricCategory:
                score_val = cat_scores_dict.get(category.value, 5.0)
                cat_score = CategoryScore(
                    category=category,
                    score=float(score_val),
                    percentile=None,
                    trend=TrendDirection.STABLE,
                    trend_delta=None,
                )
                category_scores.append(cat_score)

            # Build scorecard
            scorecard = NeighborhoodScorecard(
                neighborhood=NeighborhoodBase(
                    name=row["name"],
                    slug=row["slug"],
                ),
                overall_score=float(row["overall_score"]),
                rank=row["rank"],
                category_scores=category_scores,
                active_rezonings=row["active_rezonings"] or 0,
                recent_permits=row["recent_permits"] or 0,
            )

            return scorecard

    except Exception as e:
        logger.error(f"Error retrieving neighborhood detail for {slug}: {e}")
        return None


async def compare_neighborhoods(
    db_pool: asyncpg.Pool, slugs: list[str]
) -> Optional[NeighborhoodComparison]:
    """
    Compare 2-4 neighborhoods side-by-side.

    Returns category-by-category comparison of selected neighborhoods.

    Args:
        db_pool: AsyncPG connection pool
        slugs: List of neighborhood slugs (2-4)

    Returns:
        NeighborhoodComparison with all selected neighborhoods and categories
    """
    if len(slugs) < 2 or len(slugs) > 4:
        logger.warning(f"Invalid slug count for comparison: {len(slugs)}")
        return None

    try:
        scorecards = []

        for slug in slugs:
            scorecard = await get_neighborhood_detail(db_pool, slug)
            if scorecard:
                scorecards.append(scorecard)

        if not scorecards:
            return None

        # Get all unique categories from all scorecards
        all_categories = set()
        for scorecard in scorecards:
            for cat_score in scorecard.category_scores:
                all_categories.add(cat_score.category)

        comparison = NeighborhoodComparison(
            neighborhoods=scorecards,
            categories=sorted(all_categories, key=lambda x: x.value),
        )

        return comparison

    except Exception as e:
        logger.error(f"Error comparing neighborhoods {slugs}: {e}")
        return None


# ── Scheduled Refresh ────────────────────────────────────────────

class ScheduledRefresh:
    """
    Background task for periodic materialized view refresh.

    Manages timing, logging, and error handling for scheduled refreshes.
    """

    def __init__(self, db_pool: asyncpg.Pool, interval_seconds: int = 3600):
        """
        Initialize scheduled refresh task.

        Args:
            db_pool: AsyncPG connection pool
            interval_seconds: Refresh interval in seconds (default 1 hour = 3600s)
        """
        self.db_pool = db_pool
        self.interval_seconds = interval_seconds
        self.is_running = False
        self.task = None

    async def start(self):
        """Start the scheduled refresh task."""
        if self.is_running:
            logger.warning("Scheduled refresh task is already running")
            return

        self.is_running = True
        self.task = asyncio.create_task(self._run())
        logger.info(
            f"Started scheduled materialized view refresh (interval: {self.interval_seconds}s)"
        )

    async def stop(self):
        """Stop the scheduled refresh task."""
        if not self.is_running:
            return

        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped scheduled materialized view refresh")

    async def _run(self):
        """Background refresh loop."""
        while self.is_running:
            try:
                logger.info(
                    f"Starting scheduled refresh of materialized views "
                    f"(next in {self.interval_seconds}s)"
                )
                result = await refresh_all_views(self.db_pool)

                if result.get("all_success"):
                    logger.info(
                        f"Materialized views refreshed successfully "
                        f"({result.get('total_duration_ms')}ms)"
                    )
                else:
                    logger.warning(
                        f"Materialized view refresh completed with errors: "
                        f"{result.get('error', 'Unknown error')}"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error during scheduled refresh: {e}", exc_info=True)

            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break
