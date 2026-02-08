"""
VCL-86 [BIZ-004] Analytics API routes for VanCity Lens.

FastAPI routes for tracking analytics events and retrieving platform metrics.
Admin-only endpoints for dashboard data.
"""

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .user_auth import get_current_user_from_request
from .analytics import (
    AnalyticsTracker,
    EventType,
    AnalyticsEvent,
    UserActivitySummary,
    PlatformMetrics,
    TopItemsResponse,
    ActiveUsersMetrics,
    RetentionMetrics,
)
from .db import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["analytics"])


# ────────────────────────────────────────────────────────────────────────────
# User Analytics Routes (Authenticated)
# ────────────────────────────────────────────────────────────────────────────


@router.post("/analytics/track")
async def track_event(
    event_type: str = Query(...),
    metadata: Optional[Dict[str, Any]] = None,
    user: Dict = Depends(get_current_user_from_request),
) -> Dict[str, Any]:
    """
    Track an analytics event for the current user.

    Authenticated endpoint. Logs user interactions like parcel lookups,
    chat queries, signal views, etc.

    Args:
        event_type: Event type (one of EventType enum values)
        metadata: Optional JSON metadata about the event
        user: Current authenticated user (injected by dependency)

    Returns:
        Dict with event_id and confirmation

    Raises:
        HTTPException: If event_type is invalid or database error occurs
    """
    # Validate event type
    valid_types = {e.value for e in EventType}
    if event_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event_type. Must be one of: {', '.join(valid_types)}",
        )

    try:
        event_id = await AnalyticsTracker.track_event(
            db.pool,
            user_id=user["id"],
            event_type=event_type,
            metadata=metadata,
        )

        logger.info(
            f"Tracked event {event_id}: {event_type} for user {user['id']}",
            extra={"user_id": user["id"], "event_type": event_type},
        )

        return {
            "event_id": event_id,
            "user_id": user["id"],
            "event_type": event_type,
            "status": "recorded",
        }
    except Exception as e:
        logger.error(f"Failed to track event: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record event",
        )


@router.get("/analytics/my-activity")
async def get_my_activity(
    days: int = Query(30, ge=1, le=365),
    user: Dict = Depends(get_current_user_from_request),
) -> UserActivitySummary:
    """
    Get current user's activity summary.

    Authenticated endpoint. Returns a summary of the user's interactions
    over the specified number of days.

    Args:
        days: Number of days to look back (default 30, max 365)
        user: Current authenticated user (injected by dependency)

    Returns:
        UserActivitySummary with event counts by type

    Raises:
        HTTPException: If database error occurs
    """
    try:
        summary = await AnalyticsTracker.get_user_activity(
            db.pool,
            user_id=user["id"],
            days=days,
        )

        logger.info(
            f"Retrieved activity for user {user['id']}",
            extra={"user_id": user["id"], "days": days},
        )

        return summary
    except Exception as e:
        logger.error(f"Failed to get user activity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve activity data",
        )


# ────────────────────────────────────────────────────────────────────────────
# Admin Analytics Routes
# ────────────────────────────────────────────────────────────────────────────


@router.get("/admin/analytics/metrics")
async def get_platform_metrics(
    period: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    user: Dict = Depends(get_current_user_from_request),
) -> PlatformMetrics:
    """
    Get platform-wide analytics metrics (admin only).

    Admin-only endpoint. Returns aggregated platform metrics for the
    specified time period.

    Args:
        period: Time period - "daily", "weekly", or "monthly"
        user: Current authenticated user (injected by dependency)

    Returns:
        PlatformMetrics with aggregated stats

    Raises:
        HTTPException: If not admin, or database error occurs
    """
    # Admin check
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    try:
        metrics = await AnalyticsTracker.get_platform_metrics(
            db.pool,
            period=period,
        )

        logger.info(
            f"Retrieved platform metrics for period {period} by admin {user['id']}",
            extra={"admin_id": user["id"], "period": period},
        )

        return metrics
    except Exception as e:
        logger.error(f"Failed to get platform metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metrics",
        )


@router.get("/admin/analytics/top-neighborhoods")
async def get_top_neighborhoods(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    user: Dict = Depends(get_current_user_from_request),
) -> TopItemsResponse:
    """
    Get most searched neighborhoods (admin only).

    Admin-only endpoint. Returns the neighborhoods with the most searches
    in the specified time period.

    Args:
        days: Number of days to look back (default 30, max 365)
        limit: Number of results (default 10, max 100)
        user: Current authenticated user (injected by dependency)

    Returns:
        TopItemsResponse with neighborhoods and search counts

    Raises:
        HTTPException: If not admin, or database error occurs
    """
    # Admin check
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    try:
        results = await AnalyticsTracker.get_top_neighborhoods(
            db.pool,
            days=days,
            limit=limit,
        )

        logger.info(
            f"Retrieved top neighborhoods by admin {user['id']}",
            extra={"admin_id": user["id"], "days": days, "limit": limit},
        )

        return results
    except Exception as e:
        logger.error(f"Failed to get top neighborhoods: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve data",
        )


@router.get("/admin/analytics/top-signals")
async def get_top_signals(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    user: Dict = Depends(get_current_user_from_request),
) -> TopItemsResponse:
    """
    Get most viewed signal types (admin only).

    Admin-only endpoint. Returns the signal types with the most views
    in the specified time period.

    Args:
        days: Number of days to look back (default 30, max 365)
        limit: Number of results (default 10, max 100)
        user: Current authenticated user (injected by dependency)

    Returns:
        TopItemsResponse with signal types and view counts

    Raises:
        HTTPException: If not admin, or database error occurs
    """
    # Admin check
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    try:
        results = await AnalyticsTracker.get_top_signals(
            db.pool,
            days=days,
            limit=limit,
        )

        logger.info(
            f"Retrieved top signals by admin {user['id']}",
            extra={"admin_id": user["id"], "days": days, "limit": limit},
        )

        return results
    except Exception as e:
        logger.error(f"Failed to get top signals: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve data",
        )


@router.get("/admin/analytics/active-users")
async def get_active_users(
    period: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    user: Dict = Depends(get_current_user_from_request),
) -> ActiveUsersMetrics:
    """
    Get active user counts (admin only).

    Admin-only endpoint. Returns active user counts, returning users,
    new users, and churn rate for the specified period.

    Args:
        period: Time period - "daily", "weekly", or "monthly"
        user: Current authenticated user (injected by dependency)

    Returns:
        ActiveUsersMetrics with user counts and churn rate

    Raises:
        HTTPException: If not admin, or database error occurs
    """
    # Admin check
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    try:
        metrics = await AnalyticsTracker.get_active_users(
            db.pool,
            period=period,
        )

        logger.info(
            f"Retrieved active users metrics for period {period} by admin {user['id']}",
            extra={"admin_id": user["id"], "period": period},
        )

        return metrics
    except Exception as e:
        logger.error(f"Failed to get active users metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metrics",
        )


@router.get("/admin/analytics/retention")
async def get_retention_metrics(
    user: Dict = Depends(get_current_user_from_request),
) -> RetentionMetrics:
    """
    Get user retention cohort data (admin only).

    Admin-only endpoint. Returns user retention cohorts grouped by
    month of first activity.

    Args:
        user: Current authenticated user (injected by dependency)

    Returns:
        RetentionMetrics with cohort data

    Raises:
        HTTPException: If not admin, or database error occurs
    """
    # Admin check
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    try:
        metrics = await AnalyticsTracker.get_retention_metrics(db.pool)

        logger.info(
            f"Retrieved retention metrics by admin {user['id']}",
            extra={"admin_id": user["id"]},
        )

        return metrics
    except Exception as e:
        logger.error(f"Failed to get retention metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metrics",
        )
