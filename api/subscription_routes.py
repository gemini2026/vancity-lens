"""
VCL-78 [BIZ-002] Subscription management API endpoints

FastAPI routes for subscription tiers, user subscriptions, and usage tracking.
"""

import logging
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Request, status, Depends
import asyncpg

from .user_auth import get_current_user_from_request
from .db import db
from .subscriptions import (
    SubscriptionManager,
    TierInfo,
    UserSubscription,
    SubscriptionStatusResponse,
    UsageStats,
    UsageLimits,
)


def get_db_pool(request: Request) -> asyncpg.Pool:
    """Get database pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        pool = db.pool
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool

logger = logging.getLogger(__name__)

# Create router for subscription endpoints
router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ────────────────────────────────────────────────────────────────────────────
# Public Endpoints
# ────────────────────────────────────────────────────────────────────────────

@router.get("/tiers", response_model=List[TierInfo])
async def list_tiers(db_pool: asyncpg.Pool = Depends(get_db_pool)) -> List[TierInfo]:
    """
    List all available subscription tiers.

    Returns:
        List of TierInfo objects
    """
    try:
        tiers = await SubscriptionManager.get_tiers(db_pool)
        return tiers
    except Exception as e:
        logger.error(f"Error listing tiers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch subscription tiers",
        )


@router.get("/current", response_model=SubscriptionStatusResponse)
async def get_current_subscription(
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> SubscriptionStatusResponse:
    """
    Get the current user's subscription details including usage.

    Returns:
        SubscriptionStatusResponse with subscription, tier, usage, and limits
    """
    try:
        # Get user subscription
        subscription = await SubscriptionManager.get_user_subscription(
            db_pool, user["id"]
        )
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User has no active subscription",
            )

        # Get tier details
        tier = await SubscriptionManager.get_tier(db_pool, subscription.tier_name)
        if not tier:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Tier information not found",
            )

        # Get today's usage
        usage_today = await SubscriptionManager.get_usage(db_pool, user["id"])

        # Prepare limits
        limits = UsageLimits(
            max_watchlists=tier.max_watchlists,
            max_api_calls_daily=tier.max_api_calls_daily,
            max_signals_per_query=tier.max_signals_per_query,
        )

        # Calculate days until renewal
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        days_until_renewal = (
            (subscription.current_period_end.date() - now.date()).days
            if subscription.current_period_end
            else None
        )

        is_trial = subscription.status == "trial"

        return SubscriptionStatusResponse(
            subscription=subscription,
            tier=tier,
            usage_today=usage_today,
            limits=limits,
            days_until_renewal=days_until_renewal,
            is_trial=is_trial,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch subscription details",
        )


@router.post("/subscribe", response_model=UserSubscription)
async def subscribe_to_tier(
    tier_name: str,
    trial_days: int = 14,
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> UserSubscription:
    """
    Subscribe a user to a subscription tier.

    Args:
        tier_name: The subscription tier name
        trial_days: Days for trial period (0 = no trial, default 14)

    Returns:
        UserSubscription object
    """
    try:
        subscription = await SubscriptionManager.create_subscription(
            db_pool, user["id"], tier_name, trial_days
        )
        return subscription
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subscription",
        )


@router.post("/upgrade", response_model=UserSubscription)
async def upgrade_subscription(
    new_tier: str,
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> UserSubscription:
    """
    Upgrade a user's subscription to a higher tier.

    Args:
        new_tier: The new subscription tier name

    Returns:
        Updated UserSubscription object
    """
    try:
        subscription = await SubscriptionManager.upgrade_subscription(
            db_pool, user["id"], new_tier
        )
        logger.info(f"User {user['id']} upgraded to tier {new_tier}")
        return subscription
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error upgrading subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upgrade subscription",
        )


@router.post("/downgrade", response_model=UserSubscription)
async def downgrade_subscription(
    new_tier: str,
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> UserSubscription:
    """
    Downgrade a user's subscription to a lower tier.

    Args:
        new_tier: The new subscription tier name

    Returns:
        Updated UserSubscription object
    """
    try:
        subscription = await SubscriptionManager.downgrade_subscription(
            db_pool, user["id"], new_tier
        )
        logger.info(f"User {user['id']} downgraded to tier {new_tier}")
        return subscription
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error downgrading subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to downgrade subscription",
        )


@router.post("/cancel", response_model=UserSubscription)
async def cancel_subscription(
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> UserSubscription:
    """
    Cancel a user's subscription (effective at period end).

    Returns:
        Updated UserSubscription object
    """
    try:
        subscription = await SubscriptionManager.cancel_subscription(
            db_pool, user["id"]
        )
        logger.info(f"User {user['id']} cancelled subscription")
        return subscription
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription",
        )


@router.post("/reactivate", response_model=UserSubscription)
async def reactivate_subscription(
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> UserSubscription:
    """
    Reactivate a cancelled subscription.

    Returns:
        Updated UserSubscription object
    """
    try:
        subscription = await SubscriptionManager.reactivate_subscription(
            db_pool, user["id"]
        )
        logger.info(f"User {user['id']} reactivated subscription")
        return subscription
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error reactivating subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reactivate subscription",
        )


@router.get("/usage", response_model=UsageStats)
async def get_usage_stats(
    date: str = None,
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> UsageStats:
    """
    Get usage statistics for a specific date (default today).

    Args:
        date: Optional date in YYYY-MM-DD format (default today)

    Returns:
        UsageStats object
    """
    try:
        usage = await SubscriptionManager.get_usage(db_pool, user["id"], date)
        return usage
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error fetching usage stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch usage statistics",
        )


@router.get("/usage/summary", response_model=Dict)
async def get_usage_summary(
    days: int = 30,
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> Dict:
    """
    Get aggregated usage summary for the last N days.

    Args:
        days: Number of days to include (default 30, max 365)

    Returns:
        Dict with aggregated usage data
    """
    try:
        if days < 1 or days > 365:
            raise ValueError("days must be between 1 and 365")

        summary = await SubscriptionManager.get_usage_summary(
            db_pool, user["id"], days
        )
        return summary
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error fetching usage summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch usage summary",
        )


# ────────────────────────────────────────────────────────────────────────────
# Admin Endpoints
# ────────────────────────────────────────────────────────────────────────────

@admin_router.get("/subscriptions/stats", response_model=Dict)
async def get_subscription_stats(
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> Dict:
    """
    Get admin subscription distribution statistics.

    Requires admin role.

    Returns:
        Dict with subscription statistics
    """
    # Check admin role
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    try:
        async with db_pool.acquire() as conn:
            # Get distribution by tier
            tier_dist = await conn.fetch(
                """
                SELECT
                    st.name,
                    st.display_name,
                    COUNT(us.id) as user_count,
                    COUNT(CASE WHEN us.status = 'trial' THEN 1 END) as trial_count
                FROM subscription_tiers st
                LEFT JOIN user_subscriptions us ON st.id = us.tier_id
                WHERE st.is_active = true
                GROUP BY st.id, st.name, st.display_name
                ORDER BY st.id ASC
                """
            )

            # Get total stats
            stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(DISTINCT user_id) as total_subscribers,
                    COUNT(CASE WHEN status = 'active' THEN 1 END) as active_subscriptions,
                    COUNT(CASE WHEN status = 'trial' THEN 1 END) as trial_subscriptions,
                    COUNT(CASE WHEN cancel_at_period_end = true THEN 1 END) as cancellations_pending
                FROM user_subscriptions
                """
            )

        return {
            "total_subscribers": stats["total_subscribers"],
            "active_subscriptions": stats["active_subscriptions"],
            "trial_subscriptions": stats["trial_subscriptions"],
            "cancellations_pending": stats["cancellations_pending"],
            "distribution_by_tier": [dict(row) for row in tier_dist],
        }
    except Exception as e:
        logger.error(f"Error fetching subscription stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch subscription statistics",
        )
