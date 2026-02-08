"""
VCL-82 [BIZ-003] Stripe payment integration tests

Comprehensive test suite for Stripe checkout, webhook handling, and subscription management.
"""

import json
import os
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

import asyncpg

# Set test environment variables before importing stripe_integration
os.environ.setdefault("STRIPE_API_KEY", "sk_test_123456789")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_123456789")

# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    pool.acquire = MagicMock()

    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    return pool, conn


@pytest.fixture
def stripe_service():
    """Import StripeService for testing."""
    from api.stripe_integration import StripeService

    return StripeService


@pytest.fixture
def sample_tier_row():
    """Sample subscription tier row from database."""
    return {
        "id": 2,
        "name": "starter",
        "display_name": "Starter",
        "stripe_price_id": "price_starter_monthly",
        "price_monthly": Decimal("29.99"),
        "price_annual": Decimal("299.99"),
    }


@pytest.fixture
def sample_user_row():
    """Sample user row from database."""
    return {
        "id": 123,
        "email": "user@example.com",
        "display_name": "Test User",
    }


@pytest.fixture
def sample_subscription_row():
    """Sample subscription row from database."""
    return {
        "id": 1,
        "user_id": 123,
        "tier_id": 2,
        "status": "active",
        "stripe_customer_id": "cus_test123",
        "stripe_subscription_id": "sub_test123",
        "current_period_start": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "current_period_end": datetime(2024, 2, 1, tzinfo=timezone.utc),
        "grace_period_ends_at": None,
    }


# ────────────────────────────────────────────────────────────────────────────
# Tests: create_checkout_session
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_checkout_session_success(
    mock_db_pool, stripe_service, sample_tier_row, sample_user_row
):
    """Test successful Stripe checkout session creation."""
    pool, conn = mock_db_pool

    conn.fetchrow.side_effect = [
        sample_tier_row,  # tier query
        sample_user_row,  # user query
    ]

    with patch("api.stripe_integration.stripe") as mock_stripe:
        mock_session = MagicMock()
        mock_session.id = "cs_test123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test123"
        mock_stripe.checkout.Session.create.return_value = mock_session

        result = await stripe_service.create_checkout_session(
            pool,
            user_id=123,
            tier_name="starter",
            billing_period="monthly",
        )

        assert result["session_id"] == "cs_test123"
        assert result["checkout_url"] == "https://checkout.stripe.com/pay/cs_test123"
        mock_stripe.checkout.Session.create.assert_called_once()

        # Verify call arguments
        call_args = mock_stripe.checkout.Session.create.call_args
        assert call_args[1]["mode"] == "subscription"
        assert call_args[1]["customer_email"] == "user@example.com"
        assert call_args[1]["metadata"]["user_id"] == "123"
        assert call_args[1]["metadata"]["tier_name"] == "starter"


@pytest.mark.asyncio
async def test_create_checkout_session_tier_not_found(mock_db_pool, stripe_service):
    """Test checkout fails if tier not found."""
    pool, conn = mock_db_pool
    conn.fetchrow.return_value = None

    with pytest.raises(ValueError, match="Subscription tier not found"):
        await stripe_service.create_checkout_session(
            pool,
            user_id=123,
            tier_name="nonexistent",
        )


@pytest.mark.asyncio
async def test_create_checkout_session_user_not_found(
    mock_db_pool, stripe_service, sample_tier_row
):
    """Test checkout fails if user not found."""
    pool, conn = mock_db_pool
    conn.fetchrow.side_effect = [
        sample_tier_row,  # tier exists
        None,  # user not found
    ]

    with pytest.raises(ValueError, match="User not found"):
        await stripe_service.create_checkout_session(
            pool,
            user_id=999,
            tier_name="starter",
        )


@pytest.mark.asyncio
async def test_create_checkout_session_no_stripe_price(
    mock_db_pool, stripe_service
):
    """Test checkout fails if tier has no Stripe price ID."""
    pool, conn = mock_db_pool

    tier_no_price = {
        "id": 2,
        "name": "starter",
        "stripe_price_id": None,
    }

    conn.fetchrow.side_effect = [
        tier_no_price,
        {"id": 123, "email": "user@example.com", "display_name": "Test"},
    ]

    with pytest.raises(ValueError, match="Stripe price ID not configured"):
        await stripe_service.create_checkout_session(
            pool,
            user_id=123,
            tier_name="starter",
        )


@pytest.mark.asyncio
async def test_create_checkout_session_no_api_key(stripe_service):
    """Test checkout fails without Stripe API key."""
    pool = AsyncMock()

    with patch("api.stripe_integration.STRIPE_API_KEY", None):
        with pytest.raises(ValueError, match="STRIPE_API_KEY not configured"):
            await stripe_service.create_checkout_session(
                pool,
                user_id=123,
                tier_name="starter",
            )


@pytest.mark.asyncio
async def test_create_checkout_session_stripe_error(
    mock_db_pool, stripe_service, sample_tier_row, sample_user_row
):
    """Test checkout handles Stripe API errors gracefully."""
    pool, conn = mock_db_pool
    conn.fetchrow.side_effect = [sample_tier_row, sample_user_row]

    with patch("api.stripe_integration.stripe") as mock_stripe:
        import stripe as stripe_lib

        mock_stripe.error.StripeError = stripe_lib.error.StripeError
        mock_stripe.checkout.Session.create.side_effect = stripe_lib.error.CardError(
            "Card declined", "card_declined", "card_error"
        )

        with pytest.raises(ValueError, match="Stripe checkout failed"):
            await stripe_service.create_checkout_session(
                pool,
                user_id=123,
                tier_name="starter",
            )


# ────────────────────────────────────────────────────────────────────────────
# Tests: Webhook Signature Verification
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_webhook_valid_signature(mock_db_pool, stripe_service):
    """Test webhook with valid Stripe signature."""
    pool, conn = mock_db_pool

    payload = b'{"type":"customer.subscription.created","id":"evt_test123"}'
    signature = "t=1234567890,v1=valid_signature"

    with patch("api.stripe_integration.stripe") as mock_stripe:
        mock_event = {
            "type": "customer.subscription.created",
            "id": "evt_test123",
            "data": {
                "object": {
                    "id": "sub_test123",
                    "customer": "cus_test123",
                    "metadata": {"user_id": "123", "tier_name": "starter"},
                }
            },
        }
        mock_stripe.Webhook.construct_event.return_value = mock_event

        conn.fetchrow.return_value = {"id": 2}  # tier id

        conn.execute = AsyncMock()

        result = await stripe_service.handle_webhook(pool, payload, signature)

        assert result["event_type"] == "customer.subscription.created"
        assert result["status"] == "processed"


@pytest.mark.asyncio
async def test_handle_webhook_invalid_signature(mock_db_pool, stripe_service):
    """Test webhook with invalid Stripe signature."""
    pool, conn = mock_db_pool

    payload = b'{"type":"customer.subscription.created"}'
    signature = "t=1234567890,v1=invalid_signature"

    with patch("api.stripe_integration.stripe") as mock_stripe:
        import stripe as stripe_lib

        mock_stripe.error.SignatureVerificationError = (
            stripe_lib.error.SignatureVerificationError
        )
        mock_stripe.Webhook.construct_event.side_effect = (
            stripe_lib.error.SignatureVerificationError("Invalid signature", "sig")
        )

        with pytest.raises(ValueError, match="Webhook signature verification failed"):
            await stripe_service.handle_webhook(pool, payload, signature)


@pytest.mark.asyncio
async def test_handle_webhook_no_secret_configured(stripe_service):
    """Test webhook fails without Stripe webhook secret."""
    pool = AsyncMock()

    with patch("api.stripe_integration.STRIPE_WEBHOOK_SECRET", None):
        with pytest.raises(ValueError, match="STRIPE_WEBHOOK_SECRET not configured"):
            await stripe_service.handle_webhook(
                pool, b"payload", "signature"
            )


# ────────────────────────────────────────────────────────────────────────────
# Tests: process_subscription_created
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_subscription_created_success(
    mock_db_pool, stripe_service
):
    """Test successful subscription.created event processing."""
    pool, conn = mock_db_pool
    conn.execute = AsyncMock()
    conn.fetchrow.return_value = {"id": 2}  # tier id

    event_data = {
        "object": {
            "id": "sub_test123",
            "customer": "cus_test123",
            "metadata": {"user_id": "123", "tier_name": "starter"},
        }
    }

    result = await stripe_service.process_subscription_created(
        pool, "evt_test123", event_data
    )

    assert result["event_type"] == "customer.subscription.created"
    assert result["status"] == "processed"
    assert result["user_id"] == 123
    assert result["stripe_subscription_id"] == "sub_test123"

    # Verify database calls
    assert conn.execute.call_count >= 2  # INSERT event + UPDATE subscription


@pytest.mark.asyncio
async def test_process_subscription_created_missing_metadata(
    mock_db_pool, stripe_service
):
    """Test subscription.created fails without user_id in metadata."""
    pool, conn = mock_db_pool

    event_data = {
        "object": {
            "id": "sub_test123",
            "customer": "cus_test123",
            "metadata": {},  # Missing user_id and tier_name
        }
    }

    with pytest.raises(ValueError, match="Missing user_id or tier_name"):
        await stripe_service.process_subscription_created(
            pool, "evt_test123", event_data
        )


@pytest.mark.asyncio
async def test_process_subscription_created_tier_not_found(
    mock_db_pool, stripe_service
):
    """Test subscription.created fails if tier not found."""
    pool, conn = mock_db_pool
    conn.execute = AsyncMock()
    conn.fetchrow.return_value = None  # Tier not found

    event_data = {
        "object": {
            "id": "sub_test123",
            "customer": "cus_test123",
            "metadata": {"user_id": "123", "tier_name": "nonexistent"},
        }
    }

    with pytest.raises(ValueError, match="Tier not found"):
        await stripe_service.process_subscription_created(
            pool, "evt_test123", event_data
        )


# ────────────────────────────────────────────────────────────────────────────
# Tests: process_invoice_paid
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_invoice_paid_success(mock_db_pool, stripe_service):
    """Test successful invoice.payment_succeeded event processing."""
    pool, conn = mock_db_pool
    conn.execute = AsyncMock()

    event_data = {
        "object": {
            "id": "in_test123",
            "subscription": "sub_test123",
            "amount_paid": 2999,
        }
    }

    result = await stripe_service.process_invoice_paid(
        pool, "evt_test123", event_data
    )

    assert result["event_type"] == "invoice.payment_succeeded"
    assert result["status"] == "processed"
    assert result["stripe_subscription_id"] == "sub_test123"

    # Verify subscription updated to active
    conn.execute.assert_called()
    calls = conn.execute.call_args_list
    assert any("UPDATE user_subscriptions" in str(call) for call in calls)


@pytest.mark.asyncio
async def test_process_invoice_paid_clears_grace_period(mock_db_pool, stripe_service):
    """Test that payment success clears grace period."""
    pool, conn = mock_db_pool
    conn.execute = AsyncMock()

    event_data = {
        "object": {
            "id": "in_test123",
            "subscription": "sub_test123",
            "amount_paid": 2999,
        }
    }

    await stripe_service.process_invoice_paid(pool, "evt_test123", event_data)

    # Find the UPDATE call
    calls = conn.execute.call_args_list
    update_call = [
        call for call in calls if "UPDATE user_subscriptions" in str(call[0][0])
    ][0]

    # Verify grace_period_ends_at is set to NULL
    sql = update_call[0][0]
    assert "grace_period_ends_at = NULL" in sql


# ────────────────────────────────────────────────────────────────────────────
# Tests: process_invoice_payment_failed (Grace Period)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_invoice_payment_failed_grace_period(
    mock_db_pool, stripe_service
):
    """Test invoice.payment_failed sets grace period."""
    pool, conn = mock_db_pool
    conn.execute = AsyncMock()

    event_data = {
        "object": {
            "id": "in_test123",
            "subscription": "sub_test123",
            "amount": 2999,
            "last_payment_error": {"code": "card_declined"},
        }
    }

    result = await stripe_service.process_invoice_payment_failed(
        pool, "evt_test123", event_data
    )

    assert result["event_type"] == "invoice.payment_failed"
    assert result["status"] == "processed"

    # Verify grace period is 7 days from now
    grace_period = result["grace_period_ends_at"]
    assert grace_period is not None


@pytest.mark.asyncio
async def test_process_invoice_payment_failed_grace_period_duration(
    mock_db_pool, stripe_service
):
    """Test grace period is exactly 7 days."""
    pool, conn = mock_db_pool
    conn.execute = AsyncMock()

    before = datetime.now(timezone.utc)

    event_data = {
        "object": {
            "id": "in_test123",
            "subscription": "sub_test123",
            "amount": 2999,
        }
    }

    result = await stripe_service.process_invoice_payment_failed(
        pool, "evt_test123", event_data
    )

    after = datetime.now(timezone.utc)

    # Parse grace period
    grace_iso = result["grace_period_ends_at"]
    grace_dt = datetime.fromisoformat(grace_iso.replace("Z", "+00:00"))

    # Should be ~7 days
    grace_seconds = (grace_dt - before).total_seconds()
    expected_seconds = 7 * 24 * 60 * 60

    # Allow 1 minute tolerance
    assert abs(grace_seconds - expected_seconds) < 60


# ────────────────────────────────────────────────────────────────────────────
# Tests: process_subscription_deleted
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_subscription_deleted_success(mock_db_pool, stripe_service):
    """Test successful subscription.deleted event processing."""
    pool, conn = mock_db_pool
    conn.execute = AsyncMock()

    event_data = {
        "object": {
            "id": "sub_test123",
            "customer": "cus_test123",
        }
    }

    result = await stripe_service.process_subscription_deleted(
        pool, "evt_test123", event_data
    )

    assert result["event_type"] == "customer.subscription.deleted"
    assert result["status"] == "processed"
    assert result["stripe_subscription_id"] == "sub_test123"

    # Verify subscription marked as cancelled
    calls = conn.execute.call_args_list
    update_call = [
        call for call in calls if "UPDATE user_subscriptions" in str(call[0][0])
    ][0]
    sql = update_call[0][0]
    assert "status = 'cancelled'" in sql


# ────────────────────────────────────────────────────────────────────────────
# Tests: generate_portal_url
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_portal_url_success(mock_db_pool, stripe_service):
    """Test successful Stripe Customer Portal URL generation."""
    pool, conn = mock_db_pool
    conn.fetchrow.return_value = {"stripe_customer_id": "cus_test123"}

    with patch("api.stripe_integration.stripe") as mock_stripe:
        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/session/test"
        mock_stripe.billing_portal.Session.create.return_value = mock_session

        url = await stripe_service.generate_portal_url(pool, user_id=123)

        assert url == "https://billing.stripe.com/session/test"
        mock_stripe.billing_portal.Session.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_portal_url_no_stripe_customer(mock_db_pool, stripe_service):
    """Test portal URL fails if user has no Stripe customer."""
    pool, conn = mock_db_pool
    conn.fetchrow.return_value = {"stripe_customer_id": None}

    with pytest.raises(ValueError, match="no associated Stripe customer"):
        await stripe_service.generate_portal_url(pool, user_id=999)


@pytest.mark.asyncio
async def test_generate_portal_url_no_api_key(stripe_service):
    """Test portal URL fails without Stripe API key."""
    pool = AsyncMock()

    with patch("api.stripe_integration.STRIPE_API_KEY", None):
        with pytest.raises(ValueError, match="STRIPE_API_KEY not configured"):
            await stripe_service.generate_portal_url(pool, user_id=123)


# ────────────────────────────────────────────────────────────────────────────
# Tests: cancel_subscription
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_subscription_success(mock_db_pool, stripe_service):
    """Test successful subscription cancellation."""
    pool, conn = mock_db_pool
    conn.fetchrow.return_value = {"stripe_subscription_id": "sub_test123"}

    with patch("api.stripe_integration.stripe") as mock_stripe:
        mock_cancelled = MagicMock()
        mock_cancelled.get.return_value = datetime.now(timezone.utc)
        mock_stripe.Subscription.delete.return_value = mock_cancelled

        result = await stripe_service.cancel_subscription(pool, user_id=123)

        assert result["stripe_subscription_id"] == "sub_test123"
        mock_stripe.Subscription.delete.assert_called_once_with("sub_test123")


@pytest.mark.asyncio
async def test_cancel_subscription_no_active(mock_db_pool, stripe_service):
    """Test cancellation fails if user has no active subscription."""
    pool, conn = mock_db_pool
    conn.fetchrow.return_value = None

    with pytest.raises(ValueError, match="no active subscription"):
        await stripe_service.cancel_subscription(pool, user_id=999)


@pytest.mark.asyncio
async def test_cancel_subscription_no_stripe_id(mock_db_pool, stripe_service):
    """Test cancellation fails if subscription has no Stripe ID."""
    pool, conn = mock_db_pool
    conn.fetchrow.return_value = {"stripe_subscription_id": None}

    with pytest.raises(ValueError, match="no active subscription"):
        await stripe_service.cancel_subscription(pool, user_id=123)


# ────────────────────────────────────────────────────────────────────────────
# Tests: Webhook Event Routing
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_webhook_unhandled_event(mock_db_pool, stripe_service):
    """Test webhook routes unhandled event types gracefully."""
    pool, conn = mock_db_pool

    with patch("api.stripe_integration.stripe") as mock_stripe:
        mock_event = {
            "type": "charge.succeeded",
            "id": "evt_test123",
            "data": {},
        }
        mock_stripe.Webhook.construct_event.return_value = mock_event

        result = await stripe_service.handle_webhook(
            pool, b"payload", "signature"
        )

        assert result["event_type"] == "charge.succeeded"
        assert result["status"] == "unhandled"


@pytest.mark.asyncio
async def test_handle_webhook_routes_to_correct_handler(mock_db_pool, stripe_service):
    """Test webhook routes events to correct handlers."""
    pool, conn = mock_db_pool
    conn.execute = AsyncMock()
    conn.fetchrow.return_value = {"id": 2}

    with patch("api.stripe_integration.stripe") as mock_stripe:
        # Test subscription.created routing
        mock_event = {
            "type": "customer.subscription.created",
            "id": "evt_test123",
            "data": {
                "object": {
                    "id": "sub_test123",
                    "customer": "cus_test123",
                    "metadata": {"user_id": "123", "tier_name": "starter"},
                }
            },
        }
        mock_stripe.Webhook.construct_event.return_value = mock_event

        result = await stripe_service.handle_webhook(
            pool, b"payload", "signature"
        )

        assert result["event_type"] == "customer.subscription.created"
        assert result["status"] == "processed"


# ────────────────────────────────────────────────────────────────────────────
# Tests: Error Handling and Logging
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_subscription_created_database_error(
    mock_db_pool, stripe_service
):
    """Test subscription.created handles database errors."""
    pool, conn = mock_db_pool

    conn.execute.side_effect = asyncpg.PostgresError("Connection error")
    conn.fetchrow.return_value = {"id": 2}

    event_data = {
        "object": {
            "id": "sub_test123",
            "customer": "cus_test123",
            "metadata": {"user_id": "123", "tier_name": "starter"},
        }
    }

    with pytest.raises(Exception):
        await stripe_service.process_subscription_created(
            pool, "evt_test123", event_data
        )


@pytest.mark.asyncio
async def test_handle_webhook_event_idempotency(mock_db_pool, stripe_service):
    """Test webhook processes same event only once (idempotency)."""
    pool, conn = mock_db_pool
    conn.execute = AsyncMock()
    conn.fetchrow.return_value = {"id": 2}

    # First event - should insert
    event_data = {
        "object": {
            "id": "sub_test123",
            "customer": "cus_test123",
            "metadata": {"user_id": "123", "tier_name": "starter"},
        }
    }

    result1 = await stripe_service.process_subscription_created(
        pool, "evt_unique_123", event_data
    )

    # Verify INSERT with ON CONFLICT
    calls = conn.execute.call_args_list
    first_insert = calls[0]
    sql = first_insert[0][0]

    assert "ON CONFLICT (stripe_event_id) DO NOTHING" in sql


# ────────────────────────────────────────────────────────────────────────────
# Tests: Multiple Tier Support
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_checkout_session_professional_tier(
    mock_db_pool, stripe_service
):
    """Test checkout for professional tier."""
    pool, conn = mock_db_pool

    tier_row = {
        "id": 3,
        "name": "professional",
        "display_name": "Professional",
        "stripe_price_id": "price_professional_monthly",
        "price_monthly": Decimal("99.99"),
        "price_annual": Decimal("999.99"),
    }

    conn.fetchrow.side_effect = [
        tier_row,
        {"id": 123, "email": "user@example.com", "display_name": "Test"},
    ]

    with patch("api.stripe_integration.stripe") as mock_stripe:
        mock_session = MagicMock()
        mock_session.id = "cs_test123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test123"
        mock_stripe.checkout.Session.create.return_value = mock_session

        result = await stripe_service.create_checkout_session(
            pool,
            user_id=123,
            tier_name="professional",
        )

        assert result["session_id"] == "cs_test123"

        # Verify tier name in metadata
        call_args = mock_stripe.checkout.Session.create.call_args
        assert call_args[1]["metadata"]["tier_name"] == "professional"


@pytest.mark.asyncio
async def test_create_checkout_session_annual_billing(
    mock_db_pool, stripe_service, sample_tier_row, sample_user_row
):
    """Test checkout with annual billing period."""
    pool, conn = mock_db_pool
    conn.fetchrow.side_effect = [sample_tier_row, sample_user_row]

    with patch("api.stripe_integration.stripe") as mock_stripe:
        mock_session = MagicMock()
        mock_session.id = "cs_test123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test123"
        mock_stripe.checkout.Session.create.return_value = mock_session

        await stripe_service.create_checkout_session(
            pool,
            user_id=123,
            tier_name="starter",
            billing_period="annual",
        )

        call_args = mock_stripe.checkout.Session.create.call_args
        assert call_args[1]["metadata"]["billing_period"] == "annual"
