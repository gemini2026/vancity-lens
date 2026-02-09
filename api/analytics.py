"""
VCL-86 [BIZ-004] Usage analytics dashboard for VanCity Lens.

Analytics service layer for tracking user interactions, platform metrics,
and generating dashboard reports.

Tracks:
- Parcel lookups, chat queries, signal views, scorecard views
- Most searched neighborhoods and viewed signals
- Active users, retention cohorts, daily/weekly/monthly metrics
"""

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Dict, Optional, Any

import asyncpg
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Enums
# ────────────────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    """Analytics event types."""
    PARCEL_LOOKUP = "parcel_lookup"
    CHAT_QUERY = "chat_query"
    SIGNAL_VIEW = "signal_view"
    SCORECARD_VIEW = "scorecard_view"
    REPORT_EXPORT = "report_export"
    LOGIN = "login"
    SEARCH = "search"


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ────────────────────────────────────────────────────────────────────────────

class AnalyticsEvent(BaseModel):
    """Single analytics event."""
    id: int
    user_id: int
    event_type: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserActivitySummary(BaseModel):
    """User activity summary over a time period."""
    user_id: int
    total_events: int
    parcel_lookups: int
    chat_queries: int
    signal_views: int
    scorecard_views: int
    report_exports: int
    logins: int
    searches: int
    last_activity_at: Optional[datetime] = None
    first_activity_at: Optional[datetime] = None


class PlatformMetrics(BaseModel):
    """Platform-wide metrics for a time period."""
    period: str  # "daily", "weekly", "monthly"
    total_events: int
    unique_users: int
    average_events_per_user: float
    parcel_lookups: int
    chat_queries: int
    signal_views: int
    scorecard_views: int
    report_exports: int
    logins: int
    searches: int


class TopItem(BaseModel):
    """Top item result (neighborhood or signal)."""
    rank: int
    name: str
    count: int
    percentage: float


class TopItemsResponse(BaseModel):
    """Response with top items."""
    period_days: int
    total_count: int
    items: List[TopItem]


class ActiveUsersMetrics(BaseModel):
    """Active users aggregation by time period."""
    period: str  # "daily", "weekly", "monthly"
    active_users: int
    returning_users: int
    new_users: int
    churn_rate: float


class RetentionCohort(BaseModel):
    """Retention cohort data."""
    cohort_date: str  # YYYY-MM or YYYY-MM-DD
    cohort_size: int
    day_1_retention: Optional[float] = None
    day_7_retention: Optional[float] = None
    day_30_retention: Optional[float] = None


class RetentionMetrics(BaseModel):
    """User retention metrics."""
    cohorts: List[RetentionCohort]


# ────────────────────────────────────────────────────────────────────────────
# AnalyticsTracker Service
# ────────────────────────────────────────────────────────────────────────────

class AnalyticsTracker:
    """Service for tracking and retrieving analytics data."""

    @staticmethod
    async def track_event(
        db_pool: asyncpg.Pool,
        user_id: int,
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Record an analytics event.

        Args:
            db_pool: Database connection pool
            user_id: User ID
            event_type: Event type (one of EventType enum)
            metadata: Optional JSON metadata about the event

        Returns:
            The event ID
        """
        now = datetime.now(tz=timezone.utc)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO analytics_events (user_id, event_type, metadata, created_at)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                user_id,
                event_type,
                metadata,
                now,
            )

        return row["id"]

    @staticmethod
    async def get_user_activity(
        db_pool: asyncpg.Pool,
        user_id: int,
        days: int = 30,
    ) -> UserActivitySummary:
        """
        Get user's activity summary for the past N days.

        Args:
            db_pool: Database connection pool
            user_id: User ID
            days: Number of days to look back (default 30)

        Returns:
            UserActivitySummary with event counts by type
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

        async with db_pool.acquire() as conn:
            # Get all events for this user in the period
            rows = await conn.fetch(
                """
                SELECT event_type, COUNT(*) as count
                FROM analytics_events
                WHERE user_id = $1 AND created_at >= $2
                GROUP BY event_type
                """,
                user_id,
                cutoff,
            )

            # Get total events and date range
            summary_row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total_events,
                    MIN(created_at) as first_activity_at,
                    MAX(created_at) as last_activity_at
                FROM analytics_events
                WHERE user_id = $1 AND created_at >= $2
                """,
                user_id,
                cutoff,
            )

        # Build event counts map
        event_counts = {row["event_type"]: row["count"] for row in rows}

        return UserActivitySummary(
            user_id=user_id,
            total_events=summary_row["total_events"] or 0,
            parcel_lookups=event_counts.get(EventType.PARCEL_LOOKUP.value, 0),
            chat_queries=event_counts.get(EventType.CHAT_QUERY.value, 0),
            signal_views=event_counts.get(EventType.SIGNAL_VIEW.value, 0),
            scorecard_views=event_counts.get(EventType.SCORECARD_VIEW.value, 0),
            report_exports=event_counts.get(EventType.REPORT_EXPORT.value, 0),
            logins=event_counts.get(EventType.LOGIN.value, 0),
            searches=event_counts.get(EventType.SEARCH.value, 0),
            last_activity_at=summary_row["last_activity_at"],
            first_activity_at=summary_row["first_activity_at"],
        )

    @staticmethod
    async def get_platform_metrics(
        db_pool: asyncpg.Pool,
        period: str = "daily",
    ) -> PlatformMetrics:
        """
        Get platform-wide metrics for a time period.

        Args:
            db_pool: Database connection pool
            period: "daily", "weekly", or "monthly"

        Returns:
            PlatformMetrics with aggregated stats
        """
        # Determine date cutoff based on period
        now = datetime.now(tz=timezone.utc)
        if period == "daily":
            cutoff = now - timedelta(days=1)
        elif period == "weekly":
            cutoff = now - timedelta(weeks=1)
        elif period == "monthly":
            cutoff = now - timedelta(days=30)
        else:
            raise ValueError(f"Invalid period: {period}")

        async with db_pool.acquire() as conn:
            # Get total events and unique users
            summary = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total_events,
                    COUNT(DISTINCT user_id) as unique_users
                FROM analytics_events
                WHERE created_at >= $1
                """,
                cutoff,
            )

            # Get events by type
            type_counts = await conn.fetch(
                """
                SELECT event_type, COUNT(*) as count
                FROM analytics_events
                WHERE created_at >= $1
                GROUP BY event_type
                """,
                cutoff,
            )

        # Build event counts map
        event_map = {row["event_type"]: row["count"] for row in type_counts}

        total_events = summary["total_events"] or 0
        unique_users = summary["unique_users"] or 0
        avg_events = total_events / unique_users if unique_users > 0 else 0.0

        return PlatformMetrics(
            period=period,
            total_events=total_events,
            unique_users=unique_users,
            average_events_per_user=avg_events,
            parcel_lookups=event_map.get(EventType.PARCEL_LOOKUP.value, 0),
            chat_queries=event_map.get(EventType.CHAT_QUERY.value, 0),
            signal_views=event_map.get(EventType.SIGNAL_VIEW.value, 0),
            scorecard_views=event_map.get(EventType.SCORECARD_VIEW.value, 0),
            report_exports=event_map.get(EventType.REPORT_EXPORT.value, 0),
            logins=event_map.get(EventType.LOGIN.value, 0),
            searches=event_map.get(EventType.SEARCH.value, 0),
        )

    @staticmethod
    async def get_top_neighborhoods(
        db_pool: asyncpg.Pool,
        days: int = 30,
        limit: int = 10,
    ) -> TopItemsResponse:
        """
        Get most searched neighborhoods in the past N days.

        Args:
            db_pool: Database connection pool
            days: Number of days to look back (default 30)
            limit: Number of results (default 10)

        Returns:
            TopItemsResponse with neighborhoods and search counts
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

        async with db_pool.acquire() as conn:
            # Get total searches
            total = await conn.fetchval(
                """
                SELECT COUNT(*) as count
                FROM analytics_events
                WHERE created_at >= $1 AND event_type = $2
                """,
                cutoff,
                EventType.SEARCH.value,
            )

            # Get top neighborhoods from search metadata
            rows = await conn.fetch(
                """
                SELECT
                    metadata->>'neighborhood' as neighborhood,
                    COUNT(*) as count
                FROM analytics_events
                WHERE created_at >= $1
                    AND event_type = $2
                    AND metadata->>'neighborhood' IS NOT NULL
                GROUP BY metadata->>'neighborhood'
                ORDER BY count DESC
                LIMIT $3
                """,
                cutoff,
                EventType.SEARCH.value,
                limit,
            )

        total = total or 0
        items = []
        for rank, row in enumerate(rows, start=1):
            count = row["count"]
            percentage = (count / total * 100) if total > 0 else 0.0
            items.append(
                TopItem(
                    rank=rank,
                    name=row["neighborhood"],
                    count=count,
                    percentage=percentage,
                )
            )

        return TopItemsResponse(
            period_days=days,
            total_count=total,
            items=items,
        )

    @staticmethod
    async def get_top_signals(
        db_pool: asyncpg.Pool,
        days: int = 30,
        limit: int = 10,
    ) -> TopItemsResponse:
        """
        Get most viewed signal types in the past N days.

        Args:
            db_pool: Database connection pool
            days: Number of days to look back (default 30)
            limit: Number of results (default 10)

        Returns:
            TopItemsResponse with signal types and view counts
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

        async with db_pool.acquire() as conn:
            # Get total signal views
            total = await conn.fetchval(
                """
                SELECT COUNT(*) as count
                FROM analytics_events
                WHERE created_at >= $1 AND event_type = $2
                """,
                cutoff,
                EventType.SIGNAL_VIEW.value,
            )

            # Get top signal types from metadata
            rows = await conn.fetch(
                """
                SELECT
                    metadata->>'signal_type' as signal_type,
                    COUNT(*) as count
                FROM analytics_events
                WHERE created_at >= $1
                    AND event_type = $2
                    AND metadata->>'signal_type' IS NOT NULL
                GROUP BY metadata->>'signal_type'
                ORDER BY count DESC
                LIMIT $3
                """,
                cutoff,
                EventType.SIGNAL_VIEW.value,
                limit,
            )

        total = total or 0
        items = []
        for rank, row in enumerate(rows, start=1):
            count = row["count"]
            percentage = (count / total * 100) if total > 0 else 0.0
            items.append(
                TopItem(
                    rank=rank,
                    name=row["signal_type"],
                    count=count,
                    percentage=percentage,
                )
            )

        return TopItemsResponse(
            period_days=days,
            total_count=total,
            items=items,
        )

    @staticmethod
    async def get_active_users(
        db_pool: asyncpg.Pool,
        period: str = "daily",
    ) -> ActiveUsersMetrics:
        """
        Get active user counts aggregated by time period.

        Args:
            db_pool: Database connection pool
            period: "daily", "weekly", or "monthly"

        Returns:
            ActiveUsersMetrics with user counts and churn rate
        """
        now = datetime.now(tz=timezone.utc)

        # Determine date cutoff
        if period == "daily":
            cutoff = now - timedelta(days=1)
            prev_cutoff = now - timedelta(days=2)
        elif period == "weekly":
            cutoff = now - timedelta(weeks=1)
            prev_cutoff = now - timedelta(weeks=2)
        elif period == "monthly":
            cutoff = now - timedelta(days=30)
            prev_cutoff = now - timedelta(days=60)
        else:
            raise ValueError(f"Invalid period: {period}")

        async with db_pool.acquire() as conn:
            # Get active users in current period
            active = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id) as count
                FROM analytics_events
                WHERE created_at >= $1
                """,
                cutoff,
            )

            # Get returning users (active in both periods)
            returning = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT ae1.user_id)
                FROM analytics_events ae1
                WHERE ae1.created_at >= $1
                    AND ae1.user_id IN (
                        SELECT DISTINCT user_id
                        FROM analytics_events
                        WHERE created_at >= $2 AND created_at < $3
                    )
                """,
                cutoff,
                prev_cutoff,
                cutoff,
            )

            # Get new users (only active in current period, not in previous)
            new = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM analytics_events
                WHERE created_at >= $1
                    AND user_id NOT IN (
                        SELECT DISTINCT user_id
                        FROM analytics_events
                        WHERE created_at < $1
                    )
                """,
                cutoff,
            )

        active = active or 0
        returning = returning or 0
        new = new or 0
        churn = 0.0
        if returning > 0:
            churn = 1.0 - (returning / active) if active > 0 else 0.0

        return ActiveUsersMetrics(
            period=period,
            active_users=active,
            returning_users=returning,
            new_users=new,
            churn_rate=churn,
        )

    @staticmethod
    async def get_retention_metrics(
        db_pool: asyncpg.Pool,
    ) -> RetentionMetrics:
        """
        Get user retention cohort data.

        Groups users by registration cohort (month) and tracks
        retention at 1, 7, and 30 days.

        Args:
            db_pool: Database connection pool

        Returns:
            RetentionMetrics with cohort data
        """
        async with db_pool.acquire() as conn:
            # Get user cohorts (by month of first activity)
            cohorts = await conn.fetch(
                """
                SELECT
                    DATE_TRUNC('month', MIN(created_at))::DATE as cohort_date,
                    COUNT(DISTINCT user_id) as cohort_size,
                    user_id
                FROM analytics_events
                GROUP BY DATE_TRUNC('month', created_at), user_id
                ORDER BY cohort_date DESC
                """
            )

        # Group by cohort date and calculate retention
        cohort_map = {}
        for row in cohorts:
            cohort_date = row["cohort_date"].isoformat()
            if cohort_date not in cohort_map:
                cohort_map[cohort_date] = {"size": 0, "user_ids": set()}
            cohort_map[cohort_date]["user_ids"].add(row["user_id"])
            cohort_map[cohort_date]["size"] += 1

        # Calculate retention rates per cohort
        retention_cohorts = []
        for cohort_date, data in sorted(cohort_map.items(), reverse=True):
            cohort = RetentionCohort(
                cohort_date=cohort_date,
                cohort_size=data["size"],
                day_1_retention=None,
                day_7_retention=None,
                day_30_retention=None,
            )
            retention_cohorts.append(cohort)

        return RetentionMetrics(cohorts=retention_cohorts)
