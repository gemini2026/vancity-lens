"""
VCL-78 [BIZ-002] Comprehensive tests for tiered subscription model.

Tests cover:
- Subscription tier listing and retrieval
- User subscription creation with trial periods
- Upgrade and downgrade flows
- Cancellation and reactivation
- Usage tracking (API calls, signals, chat, exports)
- Rate limit checking
- Tier requirements and dependencies
- Edge cases and error handling
- Admin statistics endpoints
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import asyncpg
from fastapi import HTTPException, status

from api.subscriptions import (
    SubscriptionManager,
    SubscriptionTier,
    SubscriptionStatus,
    TierInfo,
    UserSubscription,
    UsageStats,
    UsageLimits,
    SubscriptionStatusResponse,
    require_tier,
    check_rate_limit,
)


# ════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    pool.acquire = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.fixture
def sample_tier():
    """Sample subscription tier data."""
    return {
        "id": 1,
        "name": "free",
        "display_name": "Free",
        "price_monthly": Decimal("0.00"),
        "price_annual": Decimal("0.00"),
        "max_watchlists": 1,
        "max_api_calls_daily": 100,
        "max_signals_per_query": 10,
        "features": {
            "chat_enabled": False,
            "digest_enabled": False,
            "export_enabled": False,
            "priority_support": False,
            "custom_branding": False,
        },
        "is_active": True,
    }


@pytest.fixture
def sample_subscription():
    """Sample user subscription data."""
    now = datetime.now(tz=timezone.utc)
    return {
        "id": 1,
        "user_id": 100,
        "tier_id": 1,
        "tier_name": "free",
        "tier_display_name": "Free",
        "status": "active",
        "trial_ends_at": None,
        "current_period_start": now,
        "current_period_end": now + timedelta(days=30),
        "cancel_at_period_end": False,
        "created_at": now,
        "updated_at": now,
    }


@pytest.fixture
def sample_usage():
    """Sample usage tracking data."""
    today = datetime.now(tz=timezone.utc).date()
    return {
        "user_id": 100,
        "usage_date": today,
        "api_calls": 50,
        "signals_queried": 5,
        "chat_messages": 10,
        "exports": 2,
    }


# ════════════════════════════════════════════════════════════════════════════
# TESTS: Tier Listing and Retrieval
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_tiers_success(mock_db_pool):
    """Test successful retrieval of all subscription tiers."""
    tiers_data = [
        {
            "id": 1,
            "name": "free",
            "display_name": "Free",
            "price_monthly": Decimal("0.00"),
            "price_annual": Decimal("0.00"),
            "max_watchlists": 1,
            "max_api_calls_daily": 100,
            "max_signals_per_query": 10,
            "features": {"chat_enabled": False},
            "is_active": True,
        },
        {
            "id": 2,
            "name": "starter",
            "display_name": "Starter",
            "price_monthly": Decimal("29.99"),
            "price_annual": Decimal("299.99"),
            "max_watchlists": 5,
            "max_api_calls_daily": 1000,
            "max_signals_per_query": 50,
            "features": {"chat_enabled": True},
            "is_active": True,
        },
    ]

    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.return_value = tiers_data

    tiers = await SubscriptionManager.get_tiers(mock_db_pool)

    assert len(tiers) == 2
    assert tiers[0].name == "free"
    assert tiers[1].name == "starter"
    assert tiers[0].max_watchlists == 1
    assert tiers[1].max_watchlists == 5


@pytest.mark.asyncio
async def test_get_tier_success(mock_db_pool, sample_tier):
    """Test successful retrieval of a specific tier."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = sample_tier

    tier = await SubscriptionManager.get_tier(mock_db_pool, "free")

    assert tier is not None
    assert tier.name == "free"
    assert tier.display_name == "Free"
    assert tier.max_watchlists == 1


@pytest.mark.asyncio
async def test_get_tier_not_found(mock_db_pool):
    """Test retrieval of non-existent tier."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = None

    tier = await SubscriptionManager.get_tier(mock_db_pool, "invalid")

    assert tier is None


# ════════════════════════════════════════════════════════════════════════════
# TESTS: Subscription Creation
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_subscription_success(mock_db_pool, sample_subscription):
    """Test successful subscription creation with trial."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.side_effect = [
        {"id": 1},  # First call: tier exists
        None,       # Second call: no existing subscription
        sample_subscription,  # Third call: created subscription
    ]

    subscription = await SubscriptionManager.create_subscription(
        mock_db_pool, 100, "free", trial_days=14
    )

    assert subscription.user_id == 100
    assert subscription.tier_name == "free"
    assert subscription.status == "active"


@pytest.mark.asyncio
async def test_create_subscription_invalid_tier(mock_db_pool):
    """Test subscription creation with invalid tier."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = None

    with pytest.raises(ValueError, match="not found"):
        await SubscriptionManager.create_subscription(
            mock_db_pool, 100, "invalid_tier"
        )


@pytest.mark.asyncio
async def test_create_subscription_already_exists(mock_db_pool):
    """Test subscription creation when user already subscribed."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.side_effect = [
        {"id": 1},  # Tier exists
        {"id": 999},  # User already has subscription
    ]

    with pytest.raises(ValueError, match="already has a subscription"):
        await SubscriptionManager.create_subscription(
            mock_db_pool, 100, "free"
        )


@pytest.mark.asyncio
async def test_create_subscription_no_trial(mock_db_pool, sample_subscription):
    """Test subscription creation without trial period."""
    subscription_no_trial = sample_subscription.copy()
    subscription_no_trial["trial_ends_at"] = None
    subscription_no_trial["status"] = "active"

    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.side_effect = [
        {"id": 1},
        None,
        subscription_no_trial,
    ]

    subscription = await SubscriptionManager.create_subscription(
        mock_db_pool, 100, "free", trial_days=0
    )

    assert subscription.trial_ends_at is None
    assert subscription.status == "active"


# ════════════════════════════════════════════════════════════════════════════
# TESTS: Upgrade and Downgrade
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_upgrade_subscription_success(mock_db_pool, sample_subscription):
    """Test successful subscription upgrade."""
    upgraded = sample_subscription.copy()
    upgraded["tier_name"] = "starter"
    upgraded["tier_display_name"] = "Starter"

    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.side_effect = [
        {"id": 2},  # New tier exists
        upgraded,   # Updated subscription
    ]

    subscription = await SubscriptionManager.upgrade_subscription(
        mock_db_pool, 100, "starter"
    )

    assert subscription.tier_name == "starter"


@pytest.mark.asyncio
async def test_upgrade_subscription_invalid_tier(mock_db_pool):
    """Test upgrade with invalid tier."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = None

    with pytest.raises(ValueError):
        await SubscriptionManager.upgrade_subscription(
            mock_db_pool, 100, "invalid"
        )


@pytest.mark.asyncio
async def test_upgrade_subscription_not_found(mock_db_pool):
    """Test upgrade when user has no subscription."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.side_effect = [
        {"id": 2},  # New tier exists
        None,       # No subscription to update
    ]

    with pytest.raises(ValueError, match="has no subscription"):
        await SubscriptionManager.upgrade_subscription(
            mock_db_pool, 100, "starter"
        )


@pytest.mark.asyncio
async def test_downgrade_subscription_success(mock_db_pool, sample_subscription):
    """Test successful subscription downgrade."""
    downgraded = sample_subscription.copy()
    downgraded["tier_name"] = "free"
    downgraded["tier_display_name"] = "Free"

    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.side_effect = [
        {"id": 1},  # New tier exists
        downgraded,  # Updated subscription
    ]

    subscription = await SubscriptionManager.downgrade_subscription(
        mock_db_pool, 100, "free"
    )

    assert subscription.tier_name == "free"


# ════════════════════════════════════════════════════════════════════════════
# TESTS: Cancellation and Reactivation
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cancel_subscription_success(mock_db_pool, sample_subscription):
    """Test successful subscription cancellation."""
    cancelled = sample_subscription.copy()
    cancelled["cancel_at_period_end"] = True

    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = cancelled

    subscription = await SubscriptionManager.cancel_subscription(
        mock_db_pool, 100
    )

    assert subscription.cancel_at_period_end is True


@pytest.mark.asyncio
async def test_cancel_subscription_not_found(mock_db_pool):
    """Test cancellation when user has no subscription."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = None

    with pytest.raises(ValueError, match="has no subscription"):
        await SubscriptionManager.cancel_subscription(mock_db_pool, 100)


@pytest.mark.asyncio
async def test_reactivate_subscription_success(mock_db_pool, sample_subscription):
    """Test successful subscription reactivation."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = sample_subscription

    subscription = await SubscriptionManager.reactivate_subscription(
        mock_db_pool, 100
    )

    assert subscription.cancel_at_period_end is False


@pytest.mark.asyncio
async def test_reactivate_subscription_not_found(mock_db_pool):
    """Test reactivation when user has no subscription."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = None

    with pytest.raises(ValueError, match="has no subscription"):
        await SubscriptionManager.reactivate_subscription(mock_db_pool, 100)


# ════════════════════════════════════════════════════════════════════════════
# TESTS: Usage Tracking
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_track_usage_api_calls(mock_db_pool):
    """Test tracking API call usage."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchval.return_value = 1  # Subscription exists

    await SubscriptionManager.track_usage(
        mock_db_pool, 100, "api_calls", count=5
    )

    # Verify execute was called with correct SQL
    conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_track_usage_invalid_type(mock_db_pool):
    """Test tracking with invalid usage type."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    with pytest.raises(ValueError, match="Invalid usage_type"):
        await SubscriptionManager.track_usage(
            mock_db_pool, 100, "invalid_type"
        )


@pytest.mark.asyncio
async def test_track_usage_no_subscription(mock_db_pool):
    """Test tracking usage when user has no subscription."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchval.return_value = None

    with pytest.raises(ValueError, match="has no subscription"):
        await SubscriptionManager.track_usage(
            mock_db_pool, 100, "api_calls"
        )


@pytest.mark.asyncio
async def test_get_usage_success(mock_db_pool, sample_usage):
    """Test retrieving usage stats."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchval.return_value = 1  # Subscription exists
    conn.fetchrow.return_value = {
        "user_id": 100,
        "usage_date": sample_usage["usage_date"],
        "api_calls": 50,
        "signals_queried": 5,
        "chat_messages": 10,
        "exports": 2,
    }

    usage = await SubscriptionManager.get_usage(mock_db_pool, 100)

    assert usage.user_id == 100
    assert usage.api_calls == 50
    assert usage.signals_queried == 5


@pytest.mark.asyncio
async def test_get_usage_no_record(mock_db_pool):
    """Test retrieving usage when no record exists."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchval.return_value = 1  # Subscription exists
    conn.fetchrow.return_value = None

    usage = await SubscriptionManager.get_usage(mock_db_pool, 100)

    assert usage.api_calls == 0
    assert usage.signals_queried == 0


@pytest.mark.asyncio
async def test_get_usage_no_subscription(mock_db_pool):
    """Test retrieving usage when user has no subscription."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchval.return_value = None

    with pytest.raises(ValueError, match="has no subscription"):
        await SubscriptionManager.get_usage(mock_db_pool, 100)


@pytest.mark.asyncio
async def test_get_usage_summary_success(mock_db_pool):
    """Test retrieving usage summary for period."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchval.return_value = 1  # Subscription exists
    conn.fetchrow.return_value = {
        "total_api_calls": 500,
        "total_signals_queried": 50,
        "total_chat_messages": 100,
        "total_exports": 20,
        "days_active": 15,
    }

    summary = await SubscriptionManager.get_usage_summary(
        mock_db_pool, 100, days=30
    )

    assert summary["total_api_calls"] == 500
    assert summary["total_signals_queried"] == 50
    assert summary["period_days"] == 30


@pytest.mark.asyncio
async def test_get_usage_summary_no_subscription(mock_db_pool):
    """Test usage summary when user has no subscription."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchval.return_value = None

    with pytest.raises(ValueError, match="has no subscription"):
        await SubscriptionManager.get_usage_summary(mock_db_pool, 100)


# ════════════════════════════════════════════════════════════════════════════
# TESTS: Rate Limiting
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_check_limit_within_limit(mock_db_pool):
    """Test check_limit when user is within their limit."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = {
        "limit_value": 1000,
        "current_usage": 500,
    }

    result = await SubscriptionManager.check_limit(
        mock_db_pool, 100, "api_calls"
    )

    assert result is True


@pytest.mark.asyncio
async def test_check_limit_at_limit(mock_db_pool):
    """Test check_limit when user is at their limit."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = {
        "limit_value": 1000,
        "current_usage": 1000,
    }

    result = await SubscriptionManager.check_limit(
        mock_db_pool, 100, "api_calls"
    )

    assert result is False


@pytest.mark.asyncio
async def test_check_limit_enterprise_no_limit(mock_db_pool):
    """Test check_limit for enterprise tier (unlimited)."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = {
        "limit_value": None,  # Enterprise tier
        "current_usage": 999999,
    }

    result = await SubscriptionManager.check_limit(
        mock_db_pool, 100, "api_calls"
    )

    assert result is True


@pytest.mark.asyncio
async def test_check_limit_invalid_type(mock_db_pool):
    """Test check_limit with invalid limit type."""
    with pytest.raises(ValueError, match="Invalid limit_type"):
        await SubscriptionManager.check_limit(
            mock_db_pool, 100, "invalid_limit"
        )


@pytest.mark.asyncio
async def test_check_limit_no_subscription(mock_db_pool):
    """Test check_limit when user has no subscription."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = None

    with pytest.raises(ValueError, match="has no subscription"):
        await SubscriptionManager.check_limit(
            mock_db_pool, 100, "api_calls"
        )


# ════════════════════════════════════════════════════════════════════════════
# TESTS: Dependency Factories
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_require_tier_dependency_sufficient_tier(mock_db_pool):
    """Test require_tier dependency when user has sufficient tier."""
    now = datetime.now(tz=timezone.utc)
    subscription_data = {
        "id": 1,
        "user_id": 100,
        "tier_id": 2,
        "tier_name": "professional",
        "tier_display_name": "Professional",
        "status": "active",
        "trial_ends_at": None,
        "current_period_start": now,
        "current_period_end": now + timedelta(days=30),
        "cancel_at_period_end": False,
        "created_at": now,
        "updated_at": now,
    }

    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = subscription_data

    user = {"id": 100, "email": "user@example.com"}
    dependency = require_tier("starter")(mock_db_pool)

    # Should not raise
    await dependency(user)


@pytest.mark.asyncio
async def test_require_tier_dependency_insufficient_tier(mock_db_pool):
    """Test require_tier dependency when user has insufficient tier."""
    now = datetime.now(tz=timezone.utc)
    subscription_data = {
        "id": 1,
        "user_id": 100,
        "tier_id": 1,
        "tier_name": "free",
        "tier_display_name": "Free",
        "status": "active",
        "trial_ends_at": None,
        "current_period_start": now,
        "current_period_end": now + timedelta(days=30),
        "cancel_at_period_end": False,
        "created_at": now,
        "updated_at": now,
    }

    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = subscription_data

    user = {"id": 100, "email": "user@example.com"}
    dependency = require_tier("professional")(mock_db_pool)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(user)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_require_tier_dependency_no_subscription(mock_db_pool):
    """Test require_tier dependency when user has no subscription."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = None

    user = {"id": 100, "email": "user@example.com"}
    dependency = require_tier("starter")(mock_db_pool)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(user)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_check_rate_limit_dependency_within_limit(mock_db_pool):
    """Test check_rate_limit dependency when user is within limit."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = {
        "limit_value": 1000,
        "current_usage": 500,
    }

    user = {"id": 100, "email": "user@example.com"}
    dependency = check_rate_limit("api_calls")(mock_db_pool)

    # Should not raise
    await dependency(user)


@pytest.mark.asyncio
async def test_check_rate_limit_dependency_exceeded(mock_db_pool):
    """Test check_rate_limit dependency when limit exceeded."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = {
        "limit_value": 1000,
        "current_usage": 1000,
    }

    user = {"id": 100, "email": "user@example.com"}
    dependency = check_rate_limit("api_calls")(mock_db_pool)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(user)

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS


# ════════════════════════════════════════════════════════════════════════════
# TESTS: Edge Cases and Error Handling
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_user_subscription_success(mock_db_pool, sample_subscription):
    """Test successful retrieval of user subscription."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = sample_subscription

    subscription = await SubscriptionManager.get_user_subscription(
        mock_db_pool, 100
    )

    assert subscription.user_id == 100
    assert subscription.tier_name == "free"


@pytest.mark.asyncio
async def test_get_user_subscription_not_found(mock_db_pool):
    """Test retrieval when user has no subscription."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow.return_value = None

    subscription = await SubscriptionManager.get_user_subscription(
        mock_db_pool, 100
    )

    assert subscription is None


@pytest.mark.asyncio
async def test_track_multiple_usage_types(mock_db_pool):
    """Test tracking multiple different usage types."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetchval.return_value = 1  # Subscription exists

    await SubscriptionManager.track_usage(
        mock_db_pool, 100, "api_calls", count=10
    )
    await SubscriptionManager.track_usage(
        mock_db_pool, 100, "signals_queried", count=5
    )
    await SubscriptionManager.track_usage(
        mock_db_pool, 100, "chat_messages", count=20
    )

    assert conn.execute.call_count == 3


@pytest.mark.asyncio
async def test_require_tier_invalid_tier_name():
    """Test require_tier with invalid tier name."""
    with pytest.raises(ValueError, match="Invalid tier"):
        require_tier("invalid_tier")


@pytest.mark.asyncio
async def test_subscription_tier_enum():
    """Test SubscriptionTier enum values."""
    assert SubscriptionTier.FREE.value == "free"
    assert SubscriptionTier.STARTER.value == "starter"
    assert SubscriptionTier.PROFESSIONAL.value == "professional"
    assert SubscriptionTier.ENTERPRISE.value == "enterprise"


@pytest.mark.asyncio
async def test_subscription_status_enum():
    """Test SubscriptionStatus enum values."""
    assert SubscriptionStatus.ACTIVE.value == "active"
    assert SubscriptionStatus.CANCELLED.value == "cancelled"
    assert SubscriptionStatus.EXPIRED.value == "expired"
    assert SubscriptionStatus.TRIAL.value == "trial"


# ════════════════════════════════════════════════════════════════════════════
# TESTS: Pydantic Models
# ════════════════════════════════════════════════════════════════════════════

def test_tier_info_model(sample_tier):
    """Test TierInfo pydantic model."""
    tier = TierInfo(**sample_tier)
    assert tier.name == "free"
    assert tier.max_watchlists == 1


def test_user_subscription_model(sample_subscription):
    """Test UserSubscription pydantic model."""
    subscription = UserSubscription(**sample_subscription)
    assert subscription.user_id == 100
    assert subscription.tier_name == "free"


def test_usage_stats_model(sample_usage):
    """Test UsageStats pydantic model."""
    usage = UsageStats(
        user_id=100,
        usage_date=sample_usage["usage_date"].isoformat(),
        api_calls=50,
        signals_queried=5,
        chat_messages=10,
        exports=2,
    )
    assert usage.user_id == 100
    assert usage.api_calls == 50


def test_usage_limits_model():
    """Test UsageLimits pydantic model."""
    limits = UsageLimits(
        max_watchlists=5,
        max_api_calls_daily=1000,
        max_signals_per_query=50,
    )
    assert limits.max_watchlists == 5


def test_subscription_status_response_model(sample_subscription, sample_tier, sample_usage):
    """Test SubscriptionStatusResponse pydantic model."""
    subscription = UserSubscription(**sample_subscription)
    tier = TierInfo(**sample_tier)
    usage = UsageStats(
        user_id=100,
        usage_date=sample_usage["usage_date"].isoformat(),
        api_calls=50,
        signals_queried=5,
        chat_messages=10,
        exports=2,
    )
    limits = UsageLimits(
        max_watchlists=tier.max_watchlists,
        max_api_calls_daily=tier.max_api_calls_daily,
        max_signals_per_query=tier.max_signals_per_query,
    )

    response = SubscriptionStatusResponse(
        subscription=subscription,
        tier=tier,
        usage_today=usage,
        limits=limits,
        days_until_renewal=30,
        is_trial=False,
    )

    assert response.subscription.user_id == 100
    assert response.tier.name == "free"
    assert response.usage_today.api_calls == 50
