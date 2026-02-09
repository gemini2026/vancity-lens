"""
VCL-78 [BIZ-002] Tiered subscription model for VanCity Lens

Subscription tier management, user subscriptions, usage tracking, and rate limiting.
"""

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, Dict, List
from decimal import Decimal

from pydantic import BaseModel, model_validator
import asyncpg

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Enums
# ────────────────────────────────────────────────────────────────────────────

class SubscriptionTier(str, Enum):
    """Available subscription tiers."""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    """Subscription status states."""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ────────────────────────────────────────────────────────────────────────────

class TierInfo(BaseModel):
    """Information about a subscription tier."""
    id: int
    name: str
    display_name: str
    price_monthly: Optional[Decimal]
    price_annual: Optional[Decimal]
    max_watchlists: Optional[int]
    max_api_calls_daily: Optional[int]
    max_signals_per_query: Optional[int]
    features: Dict
    is_active: bool

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def parse_features_json(cls, data: Any) -> Any:
        """Parse features from JSON string if needed (DB stores as TEXT)."""
        if isinstance(data, dict) and isinstance(data.get("features"), str):
            import json
            data["features"] = json.loads(data["features"])
        return data


class UserSubscription(BaseModel):
    """User's current subscription."""
    id: int
    user_id: int
    tier_id: int
    tier_name: str
    tier_display_name: str
    status: str
    trial_ends_at: Optional[datetime]
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UsageStats(BaseModel):
    """Usage statistics for a specific date."""
    user_id: int
    usage_date: str
    api_calls: int
    signals_queried: int
    chat_messages: int
    exports: int

    class Config:
        from_attributes = True


class UsageLimits(BaseModel):
    """Usage limits for a subscription tier."""
    max_watchlists: Optional[int]
    max_api_calls_daily: Optional[int]
    max_signals_per_query: Optional[int]


class SubscriptionStatusResponse(BaseModel):
    """Complete subscription status for a user."""
    subscription: UserSubscription
    tier: TierInfo
    usage_today: UsageStats
    limits: UsageLimits
    days_until_renewal: Optional[int]
    is_trial: bool


# ────────────────────────────────────────────────────────────────────────────
# Subscription Manager
# ────────────────────────────────────────────────────────────────────────────

class SubscriptionManager:
    """Manages subscription tiers, user subscriptions, and usage tracking."""

    @staticmethod
    async def get_tiers(db_pool: asyncpg.Pool) -> List[TierInfo]:
        """
        Get all active subscription tiers.

        Args:
            db_pool: Database connection pool

        Returns:
            List of TierInfo objects
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, display_name, price_monthly, price_annual,
                       max_watchlists, max_api_calls_daily, max_signals_per_query,
                       features, is_active
                FROM subscription_tiers
                WHERE is_active = true
                ORDER BY id ASC
                """
            )

        return [TierInfo(**dict(row)) for row in rows]

    @staticmethod
    async def get_tier(db_pool: asyncpg.Pool, tier_name: str) -> Optional[TierInfo]:
        """
        Get a specific subscription tier by name.

        Args:
            db_pool: Database connection pool
            tier_name: The tier name (e.g., "free", "starter", "professional", "enterprise")

        Returns:
            TierInfo object or None if not found
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, display_name, price_monthly, price_annual,
                       max_watchlists, max_api_calls_daily, max_signals_per_query,
                       features, is_active
                FROM subscription_tiers
                WHERE name = $1 AND is_active = true
                """,
                tier_name,
            )

        return TierInfo(**dict(row)) if row else None

    @staticmethod
    async def get_user_subscription(
        db_pool: asyncpg.Pool, user_id: int
    ) -> Optional[UserSubscription]:
        """
        Get a user's current subscription.

        Args:
            db_pool: Database connection pool
            user_id: The user ID

        Returns:
            UserSubscription object or None if not subscribed
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT us.id, us.user_id, us.tier_id, st.name as tier_name,
                       st.display_name as tier_display_name, us.status,
                       us.trial_ends_at, us.current_period_start,
                       us.current_period_end, us.cancel_at_period_end,
                       us.created_at, us.updated_at
                FROM user_subscriptions us
                JOIN subscription_tiers st ON us.tier_id = st.id
                WHERE us.user_id = $1
                """,
                user_id,
            )

        return UserSubscription(**dict(row)) if row else None

    @staticmethod
    async def create_subscription(
        db_pool: asyncpg.Pool,
        user_id: int,
        tier_name: str,
        trial_days: int = 14,
    ) -> UserSubscription:
        """
        Create a new subscription for a user (with optional trial).

        Args:
            db_pool: Database connection pool
            user_id: The user ID
            tier_name: The subscription tier name
            trial_days: Days for trial period (0 = no trial)

        Returns:
            UserSubscription object

        Raises:
            ValueError: If tier not found or user already subscribed
        """
        async with db_pool.acquire() as conn:
            # Verify tier exists
            tier = await conn.fetchrow(
                "SELECT id FROM subscription_tiers WHERE name = $1",
                tier_name,
            )
            if not tier:
                raise ValueError(f"Tier '{tier_name}' not found")

            # Check if user already has a subscription
            existing = await conn.fetchrow(
                "SELECT id FROM user_subscriptions WHERE user_id = $1",
                user_id,
            )
            if existing:
                raise ValueError(f"User {user_id} already has a subscription")

            now = datetime.now(tz=timezone.utc)
            trial_ends_at = None
            status = SubscriptionStatus.ACTIVE.value

            if trial_days > 0:
                trial_ends_at = now + timedelta(days=trial_days)
                status = SubscriptionStatus.TRIAL.value

            row = await conn.fetchrow(
                """
                INSERT INTO user_subscriptions (
                    user_id, tier_id, status, trial_ends_at,
                    current_period_start, current_period_end, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, user_id, tier_id,
                          (SELECT name FROM subscription_tiers WHERE id = user_subscriptions.tier_id) as tier_name,
                          (SELECT display_name FROM subscription_tiers WHERE id = user_subscriptions.tier_id) as tier_display_name,
                          status, trial_ends_at, current_period_start,
                          current_period_end, cancel_at_period_end,
                          created_at, updated_at
                """,
                user_id,
                tier["id"],
                status,
                trial_ends_at,
                now,
                now + timedelta(days=30),
                now,
                now,
            )

        return UserSubscription(**dict(row))

    @staticmethod
    async def upgrade_subscription(
        db_pool: asyncpg.Pool,
        user_id: int,
        new_tier: str,
    ) -> UserSubscription:
        """
        Upgrade a user's subscription tier.

        Args:
            db_pool: Database connection pool
            user_id: The user ID
            new_tier: The new tier name

        Returns:
            Updated UserSubscription object

        Raises:
            ValueError: If tier not found or user not subscribed
        """
        async with db_pool.acquire() as conn:
            # Verify new tier exists
            tier = await conn.fetchrow(
                "SELECT id FROM subscription_tiers WHERE name = $1",
                new_tier,
            )
            if not tier:
                raise ValueError(f"Tier '{new_tier}' not found")

            now = datetime.now(tz=timezone.utc)

            row = await conn.fetchrow(
                """
                UPDATE user_subscriptions
                SET tier_id = $1, status = $2, cancel_at_period_end = false, updated_at = $3
                WHERE user_id = $4
                RETURNING us.id, us.user_id, us.tier_id,
                          (SELECT name FROM subscription_tiers WHERE id = us.tier_id) as tier_name,
                          (SELECT display_name FROM subscription_tiers WHERE id = us.tier_id) as tier_display_name,
                          us.status, us.trial_ends_at, us.current_period_start,
                          us.current_period_end, us.cancel_at_period_end,
                          us.created_at, us.updated_at
                """,
                tier["id"],
                SubscriptionStatus.ACTIVE.value,
                now,
                user_id,
            )

        if not row:
            raise ValueError(f"User {user_id} has no subscription")

        return UserSubscription(**dict(row))

    @staticmethod
    async def downgrade_subscription(
        db_pool: asyncpg.Pool,
        user_id: int,
        new_tier: str,
    ) -> UserSubscription:
        """
        Downgrade a user's subscription tier.

        Args:
            db_pool: Database connection pool
            user_id: The user ID
            new_tier: The new tier name

        Returns:
            Updated UserSubscription object

        Raises:
            ValueError: If tier not found or user not subscribed
        """
        async with db_pool.acquire() as conn:
            # Verify new tier exists
            tier = await conn.fetchrow(
                "SELECT id FROM subscription_tiers WHERE name = $1",
                new_tier,
            )
            if not tier:
                raise ValueError(f"Tier '{new_tier}' not found")

            now = datetime.now(tz=timezone.utc)

            row = await conn.fetchrow(
                """
                UPDATE user_subscriptions
                SET tier_id = $1, status = $2, updated_at = $3
                WHERE user_id = $4
                RETURNING us.id, us.user_id, us.tier_id,
                          (SELECT name FROM subscription_tiers WHERE id = us.tier_id) as tier_name,
                          (SELECT display_name FROM subscription_tiers WHERE id = us.tier_id) as tier_display_name,
                          us.status, us.trial_ends_at, us.current_period_start,
                          us.current_period_end, us.cancel_at_period_end,
                          us.created_at, us.updated_at
                """,
                tier["id"],
                SubscriptionStatus.ACTIVE.value,
                now,
                user_id,
            )

        if not row:
            raise ValueError(f"User {user_id} has no subscription")

        return UserSubscription(**dict(row))

    @staticmethod
    async def cancel_subscription(
        db_pool: asyncpg.Pool,
        user_id: int,
    ) -> UserSubscription:
        """
        Cancel a user's subscription (effective at period end).

        Args:
            db_pool: Database connection pool
            user_id: The user ID

        Returns:
            Updated UserSubscription object

        Raises:
            ValueError: If user not subscribed
        """
        async with db_pool.acquire() as conn:
            now = datetime.now(tz=timezone.utc)

            row = await conn.fetchrow(
                """
                UPDATE user_subscriptions
                SET cancel_at_period_end = true, updated_at = $1
                WHERE user_id = $2
                RETURNING us.id, us.user_id, us.tier_id,
                          (SELECT name FROM subscription_tiers WHERE id = us.tier_id) as tier_name,
                          (SELECT display_name FROM subscription_tiers WHERE id = us.tier_id) as tier_display_name,
                          us.status, us.trial_ends_at, us.current_period_start,
                          us.current_period_end, us.cancel_at_period_end,
                          us.created_at, us.updated_at
                """,
                now,
                user_id,
            )

        if not row:
            raise ValueError(f"User {user_id} has no subscription")

        return UserSubscription(**dict(row))

    @staticmethod
    async def reactivate_subscription(
        db_pool: asyncpg.Pool,
        user_id: int,
    ) -> UserSubscription:
        """
        Reactivate a cancelled subscription.

        Args:
            db_pool: Database connection pool
            user_id: The user ID

        Returns:
            Updated UserSubscription object

        Raises:
            ValueError: If user not subscribed
        """
        async with db_pool.acquire() as conn:
            now = datetime.now(tz=timezone.utc)

            row = await conn.fetchrow(
                """
                UPDATE user_subscriptions
                SET cancel_at_period_end = false, updated_at = $1
                WHERE user_id = $2
                RETURNING us.id, us.user_id, us.tier_id,
                          (SELECT name FROM subscription_tiers WHERE id = us.tier_id) as tier_name,
                          (SELECT display_name FROM subscription_tiers WHERE id = us.tier_id) as tier_display_name,
                          us.status, us.trial_ends_at, us.current_period_start,
                          us.current_period_end, us.cancel_at_period_end,
                          us.created_at, us.updated_at
                """,
                now,
                user_id,
            )

        if not row:
            raise ValueError(f"User {user_id} has no subscription")

        return UserSubscription(**dict(row))

    @staticmethod
    async def check_limit(
        db_pool: asyncpg.Pool,
        user_id: int,
        limit_type: str,
    ) -> bool:
        """
        Check if a user is within their tier's limit for a specific usage type.

        Args:
            db_pool: Database connection pool
            user_id: The user ID
            limit_type: The limit type ('api_calls', 'signals_queried', 'chat_messages', 'exports')

        Returns:
            True if user is within limit, False if over limit

        Raises:
            ValueError: If user has no subscription or invalid limit_type
        """
        valid_limit_types = [
            "api_calls",
            "signals_queried",
            "chat_messages",
            "exports",
        ]
        if limit_type not in valid_limit_types:
            raise ValueError(
                f"Invalid limit_type '{limit_type}'. Must be one of {valid_limit_types}"
            )

        async with db_pool.acquire() as conn:
            # Get user's tier and today's usage
            result = await conn.fetchrow(
                """
                SELECT
                    CASE
                        WHEN $2 = 'api_calls' THEN st.max_api_calls_daily
                        WHEN $2 = 'signals_queried' THEN st.max_signals_per_query
                        ELSE NULL
                    END as limit_value,
                    COALESCE(
                        CASE
                            WHEN $2 = 'api_calls' THEN ut.api_calls
                            WHEN $2 = 'signals_queried' THEN ut.signals_queried
                            WHEN $2 = 'chat_messages' THEN ut.chat_messages
                            WHEN $2 = 'exports' THEN ut.exports
                            ELSE 0
                        END,
                        0
                    ) as current_usage
                FROM user_subscriptions us
                JOIN subscription_tiers st ON us.tier_id = st.id
                LEFT JOIN usage_tracking ut ON us.user_id = ut.user_id
                    AND ut.usage_date = CURRENT_DATE
                WHERE us.user_id = $1
                """,
                user_id,
                limit_type,
            )

        if not result:
            raise ValueError(f"User {user_id} has no subscription")

        limit_value = result["limit_value"]
        current_usage = result["current_usage"]

        # Enterprise tier has no limits
        if limit_value is None:
            return True

        return current_usage < limit_value

    @staticmethod
    async def track_usage(
        db_pool: asyncpg.Pool,
        user_id: int,
        usage_type: str,
        count: int = 1,
    ) -> None:
        """
        Track usage for a user on the current day.

        Args:
            db_pool: Database connection pool
            user_id: The user ID
            usage_type: The usage type ('api_calls', 'signals_queried', 'chat_messages', 'exports')
            count: The amount to increment (default 1)

        Raises:
            ValueError: If usage_type is invalid or user has no subscription
        """
        valid_usage_types = [
            "api_calls",
            "signals_queried",
            "chat_messages",
            "exports",
        ]
        if usage_type not in valid_usage_types:
            raise ValueError(
                f"Invalid usage_type '{usage_type}'. Must be one of {valid_usage_types}"
            )

        # Verify user has subscription
        async with db_pool.acquire() as conn:
            sub = await conn.fetchval(
                "SELECT id FROM user_subscriptions WHERE user_id = $1",
                user_id,
            )
            if not sub:
                raise ValueError(f"User {user_id} has no subscription")

        # Update or create today's usage record
        column_name = usage_type
        async with db_pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO usage_tracking (user_id, usage_date, {column_name}, created_at)
                VALUES ($1, CURRENT_DATE, $2, NOW())
                ON CONFLICT (user_id, usage_date) DO UPDATE
                SET {column_name} = usage_tracking.{column_name} + $2
                """,
                user_id,
                count,
            )

    @staticmethod
    async def get_usage(
        db_pool: asyncpg.Pool,
        user_id: int,
        date: Optional[str] = None,
    ) -> UsageStats:
        """
        Get usage stats for a specific date (default today).

        Args:
            db_pool: Database connection pool
            user_id: The user ID
            date: The date in YYYY-MM-DD format (default today)

        Returns:
            UsageStats object

        Raises:
            ValueError: If user has no subscription
        """
        async with db_pool.acquire() as conn:
            # Verify user has subscription
            sub = await conn.fetchval(
                "SELECT id FROM user_subscriptions WHERE user_id = $1",
                user_id,
            )
            if not sub:
                raise ValueError(f"User {user_id} has no subscription")

            # Get or create usage record
            usage_date = date or datetime.now(tz=timezone.utc).date().isoformat()

            row = await conn.fetchrow(
                """
                SELECT user_id, usage_date, api_calls, signals_queried,
                       chat_messages, exports
                FROM usage_tracking
                WHERE user_id = $1 AND usage_date = $2::date
                """,
                user_id,
                usage_date,
            )

            if row:
                return UsageStats(
                    user_id=row["user_id"],
                    usage_date=row["usage_date"].isoformat(),
                    api_calls=row["api_calls"],
                    signals_queried=row["signals_queried"],
                    chat_messages=row["chat_messages"],
                    exports=row["exports"],
                )

        # Return zero usage if no record
        return UsageStats(
            user_id=user_id,
            usage_date=usage_date,
            api_calls=0,
            signals_queried=0,
            chat_messages=0,
            exports=0,
        )

    @staticmethod
    async def get_usage_summary(
        db_pool: asyncpg.Pool,
        user_id: int,
        days: int = 30,
    ) -> Dict:
        """
        Get aggregated usage summary for the last N days.

        Args:
            db_pool: Database connection pool
            user_id: The user ID
            days: Number of days to include (default 30)

        Returns:
            Dict with aggregated usage data

        Raises:
            ValueError: If user has no subscription
        """
        async with db_pool.acquire() as conn:
            # Verify user has subscription
            sub = await conn.fetchval(
                "SELECT id FROM user_subscriptions WHERE user_id = $1",
                user_id,
            )
            if not sub:
                raise ValueError(f"User {user_id} has no subscription")

            row = await conn.fetchrow(
                """
                SELECT
                    SUM(api_calls) as total_api_calls,
                    SUM(signals_queried) as total_signals_queried,
                    SUM(chat_messages) as total_chat_messages,
                    SUM(exports) as total_exports,
                    COUNT(DISTINCT usage_date) as days_active
                FROM usage_tracking
                WHERE user_id = $1
                  AND usage_date >= CURRENT_DATE - ($2::int || ' days')::interval
                """,
                user_id,
                days,
            )

        return {
            "total_api_calls": row["total_api_calls"] or 0,
            "total_signals_queried": row["total_signals_queried"] or 0,
            "total_chat_messages": row["total_chat_messages"] or 0,
            "total_exports": row["total_exports"] or 0,
            "days_active": row["days_active"] or 0,
            "period_days": days,
        }


# ────────────────────────────────────────────────────────────────────────────
# FastAPI Dependencies
# ────────────────────────────────────────────────────────────────────────────

def require_tier(min_tier: str):
    """
    Factory function to create a dependency that checks minimum subscription tier.

    Usage:
        @app.get("/api/v1/signals")
        async def query_signals(
            user: Dict = Depends(get_current_user(db_pool)),
            _: None = Depends(require_tier("starter")(db_pool))
        ):
            return {"signals": [...]}

    Args:
        min_tier: The minimum required tier name ('free', 'starter', 'professional', 'enterprise')

    Returns:
        Async dependency function
    """
    tier_hierarchy = {
        "free": 0,
        "starter": 1,
        "professional": 2,
        "enterprise": 3,
    }

    if min_tier not in tier_hierarchy:
        raise ValueError(f"Invalid tier '{min_tier}'")

    min_level = tier_hierarchy[min_tier]

    def _require_tier_impl(db_pool: asyncpg.Pool):
        async def _check_tier(user: Dict) -> None:
            from fastapi import HTTPException, status

            subscription = await SubscriptionManager.get_user_subscription(
                db_pool, user["id"]
            )

            if not subscription:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Subscription required for this feature",
                )

            user_level = tier_hierarchy.get(subscription.tier_name, 0)

            if user_level < min_level:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This feature requires at least {min_tier} tier",
                )

        return _check_tier

    return _require_tier_impl


def check_rate_limit(limit_type: str):
    """
    Factory function to create a dependency that checks and tracks usage limits.

    Usage:
        @app.post("/api/v1/signals/query")
        async def query_signals(
            user: Dict = Depends(get_current_user(db_pool)),
            _: None = Depends(check_rate_limit("signals_queried")(db_pool))
        ):
            await SubscriptionManager.track_usage(db_pool, user["id"], "signals_queried", 1)
            return {"result": "..."}

    Args:
        limit_type: The limit type to check ('api_calls', 'signals_queried', 'chat_messages', 'exports')

    Returns:
        Async dependency function
    """

    def _check_rate_limit_impl(db_pool: asyncpg.Pool):
        async def _check_limit(user: Dict) -> None:
            from fastapi import HTTPException, status

            within_limit = await SubscriptionManager.check_limit(
                db_pool, user["id"], limit_type
            )

            if not within_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Daily {limit_type} limit exceeded",
                )

        return _check_limit

    return _check_rate_limit_impl
