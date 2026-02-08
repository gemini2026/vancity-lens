"""
VCL-82 [BIZ-003] Stripe payment integration for VanCity Lens

Stripe service layer: checkout sessions, webhook handling, subscription management.
"""

import logging
import os
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from decimal import Decimal

import asyncpg
import stripe

logger = logging.getLogger(__name__)

# Initialize Stripe with API key
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY


# ────────────────────────────────────────────────────────────────────────────
# Price ID Mapping (Stripe price IDs to internal tier names)
# ────────────────────────────────────────────────────────────────────────────

PRICE_ID_TO_TIER = {
    # Set from environment or defaults
    # Example: "price_1234..." -> "starter"
}


# ────────────────────────────────────────────────────────────────────────────
# Stripe Service Class
# ────────────────────────────────────────────────────────────────────────────

class StripeService:
    """Service for Stripe integration: checkout, webhooks, subscriptions."""

    # Grace period on failed payment (days)
    GRACE_PERIOD_DAYS = 7

    @staticmethod
    async def create_checkout_session(
        pool: asyncpg.Pool,
        user_id: int,
        tier_name: str,
        billing_period: str = "monthly",
        success_url: str = "https://localhost:3000/subscribe/success",
        cancel_url: str = "https://localhost:3000/subscribe/cancel",
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout session for subscription creation.

        Args:
            pool: Database connection pool
            user_id: User ID initiating checkout
            tier_name: Subscription tier name (free, starter, professional, enterprise)
            billing_period: "monthly" or "annual"
            success_url: Redirect URL after successful payment
            cancel_url: Redirect URL if user cancels

        Returns:
            Dict with session_id and checkout_url

        Raises:
            ValueError: If tier not found or Stripe API fails
        """
        if not STRIPE_API_KEY:
            raise ValueError("STRIPE_API_KEY not configured")

        try:
            # Get tier info from database
            async with pool.acquire() as conn:
                tier = await conn.fetchrow(
                    "SELECT id, name, stripe_price_id, price_monthly, price_annual "
                    "FROM subscription_tiers WHERE name = $1 AND is_active = true",
                    tier_name,
                )
                if not tier:
                    raise ValueError(f"Subscription tier not found: {tier_name}")

                # Get user info
                user = await conn.fetchrow(
                    "SELECT id, email, display_name FROM users WHERE id = $1",
                    user_id,
                )
                if not user:
                    raise ValueError(f"User not found: {user_id}")

            # Determine price ID
            price_id = tier["stripe_price_id"]
            if not price_id:
                raise ValueError(
                    f"Stripe price ID not configured for tier: {tier_name}"
                )

            # Create Checkout session
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                mode="subscription",
                line_items=[
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=user["email"],
                metadata={
                    "user_id": str(user_id),
                    "tier_name": tier_name,
                    "billing_period": billing_period,
                },
            )

            logger.info(
                f"Created Stripe checkout session {session.id} for user {user_id}"
            )

            return {
                "session_id": session.id,
                "checkout_url": session.url,
            }

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating checkout session: {e}")
            raise ValueError(f"Stripe checkout failed: {str(e)}")
        except Exception as e:
            logger.error(f"Error creating checkout session: {e}")
            raise

    @staticmethod
    async def handle_webhook(
        pool: asyncpg.Pool,
        payload: bytes,
        signature: str,
    ) -> Dict[str, Any]:
        """
        Verify and handle Stripe webhook event.

        Args:
            pool: Database connection pool
            payload: Raw webhook payload bytes
            signature: Stripe signature header

        Returns:
            Dict with event info and processing status

        Raises:
            ValueError: If signature verification fails
        """
        if not STRIPE_WEBHOOK_SECRET:
            raise ValueError("STRIPE_WEBHOOK_SECRET not configured")

        try:
            # Verify webhook signature
            event = stripe.Webhook.construct_event(
                payload, signature, STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            logger.error(f"Invalid webhook payload: {e}")
            raise ValueError("Invalid webhook signature")
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise ValueError("Webhook signature verification failed")

        event_type = event.get("type")
        event_data = event.get("data", {})
        event_id = event.get("id")

        logger.info(f"Processing Stripe webhook event: {event_type} ({event_id})")

        # Route to appropriate handler
        if event_type == "customer.subscription.created":
            return await StripeService.process_subscription_created(
                pool, event_id, event_data
            )
        elif event_type == "invoice.payment_succeeded":
            return await StripeService.process_invoice_paid(pool, event_id, event_data)
        elif event_type == "invoice.payment_failed":
            return await StripeService.process_invoice_payment_failed(
                pool, event_id, event_data
            )
        elif event_type == "customer.subscription.deleted":
            return await StripeService.process_subscription_deleted(
                pool, event_id, event_data
            )
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
            return {
                "event_id": event_id,
                "event_type": event_type,
                "status": "unhandled",
            }

    @staticmethod
    async def process_subscription_created(
        pool: asyncpg.Pool,
        event_id: str,
        event_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle customer.subscription.created event.

        Args:
            pool: Database connection pool
            event_id: Stripe event ID
            event_data: Event data from webhook

        Returns:
            Dict with processing status
        """
        try:
            subscription = event_data.get("object", {})
            stripe_customer_id = subscription.get("customer")
            stripe_subscription_id = subscription.get("id")
            metadata = subscription.get("metadata", {})
            user_id = int(metadata.get("user_id", 0))
            tier_name = metadata.get("tier_name", "")

            if not user_id or not tier_name:
                raise ValueError(
                    f"Missing user_id or tier_name in subscription metadata"
                )

            async with pool.acquire() as conn:
                # Record event in payment_events table
                await conn.execute(
                    """
                    INSERT INTO payment_events
                    (user_id, stripe_event_id, event_type, event_data)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (stripe_event_id) DO NOTHING
                    """,
                    user_id,
                    event_id,
                    "customer.subscription.created",
                    {
                        "stripe_subscription_id": stripe_subscription_id,
                        "stripe_customer_id": stripe_customer_id,
                    },
                )

                # Get tier ID
                tier = await conn.fetchrow(
                    "SELECT id FROM subscription_tiers WHERE name = $1",
                    tier_name,
                )
                if not tier:
                    raise ValueError(f"Tier not found: {tier_name}")

                # Update or create user subscription
                current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
                await conn.execute(
                    """
                    INSERT INTO user_subscriptions
                    (user_id, tier_id, status, stripe_customer_id,
                     stripe_subscription_id, current_period_start, current_period_end)
                    VALUES ($1, $2, $3, $4, $5, NOW(), $6)
                    ON CONFLICT (user_id) DO UPDATE SET
                        tier_id = $2,
                        status = $3,
                        stripe_customer_id = $4,
                        stripe_subscription_id = $5,
                        current_period_end = $6,
                        grace_period_ends_at = NULL,
                        updated_at = NOW()
                    """,
                    user_id,
                    tier["id"],
                    "active",
                    stripe_customer_id,
                    stripe_subscription_id,
                    current_period_end,
                )

                # Mark event as processed
                await conn.execute(
                    """
                    UPDATE payment_events
                    SET processed = true, processed_at = NOW()
                    WHERE stripe_event_id = $1
                    """,
                    event_id,
                )

            logger.info(
                f"Processed subscription.created for user {user_id}: {stripe_subscription_id}"
            )

            return {
                "event_id": event_id,
                "event_type": "customer.subscription.created",
                "status": "processed",
                "user_id": user_id,
                "stripe_subscription_id": stripe_subscription_id,
            }

        except Exception as e:
            logger.error(f"Error processing subscription.created: {e}")
            await StripeService._record_event_error(pool, event_id, str(e))
            raise

    @staticmethod
    async def process_invoice_paid(
        pool: asyncpg.Pool,
        event_id: str,
        event_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle invoice.payment_succeeded event.

        Args:
            pool: Database connection pool
            event_id: Stripe event ID
            event_data: Event data from webhook

        Returns:
            Dict with processing status
        """
        try:
            invoice = event_data.get("object", {})
            stripe_subscription_id = invoice.get("subscription")

            async with pool.acquire() as conn:
                # Record event
                await conn.execute(
                    """
                    INSERT INTO payment_events
                    (stripe_event_id, event_type, event_data)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (stripe_event_id) DO NOTHING
                    """,
                    event_id,
                    "invoice.payment_succeeded",
                    {
                        "stripe_subscription_id": stripe_subscription_id,
                        "amount_paid": invoice.get("amount_paid"),
                    },
                )

                # Update subscription: clear grace period, set to active
                result = await conn.execute(
                    """
                    UPDATE user_subscriptions
                    SET status = 'active',
                        grace_period_ends_at = NULL,
                        updated_at = NOW()
                    WHERE stripe_subscription_id = $1
                    """,
                    stripe_subscription_id,
                )

                # Mark event as processed
                await conn.execute(
                    """
                    UPDATE payment_events
                    SET processed = true, processed_at = NOW()
                    WHERE stripe_event_id = $1
                    """,
                    event_id,
                )

            logger.info(
                f"Processed invoice.payment_succeeded for subscription: {stripe_subscription_id}"
            )

            return {
                "event_id": event_id,
                "event_type": "invoice.payment_succeeded",
                "status": "processed",
                "stripe_subscription_id": stripe_subscription_id,
            }

        except Exception as e:
            logger.error(f"Error processing invoice.payment_succeeded: {e}")
            await StripeService._record_event_error(pool, event_id, str(e))
            raise

    @staticmethod
    async def process_invoice_payment_failed(
        pool: asyncpg.Pool,
        event_id: str,
        event_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle invoice.payment_failed event.

        Implements grace period: subscription remains active for 7 days.

        Args:
            pool: Database connection pool
            event_id: Stripe event ID
            event_data: Event data from webhook

        Returns:
            Dict with processing status
        """
        try:
            invoice = event_data.get("object", {})
            stripe_subscription_id = invoice.get("subscription")

            grace_period_ends = datetime.now(timezone.utc) + timedelta(
                days=StripeService.GRACE_PERIOD_DAYS
            )

            async with pool.acquire() as conn:
                # Record event
                await conn.execute(
                    """
                    INSERT INTO payment_events
                    (stripe_event_id, event_type, event_data)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (stripe_event_id) DO NOTHING
                    """,
                    event_id,
                    "invoice.payment_failed",
                    {
                        "stripe_subscription_id": stripe_subscription_id,
                        "amount": invoice.get("amount"),
                        "failure_code": invoice.get("last_payment_error", {}).get(
                            "code"
                        ),
                    },
                )

                # Set grace period (subscription stays active but marked for potential loss)
                await conn.execute(
                    """
                    UPDATE user_subscriptions
                    SET grace_period_ends_at = $1,
                        updated_at = NOW()
                    WHERE stripe_subscription_id = $2
                    """,
                    grace_period_ends,
                    stripe_subscription_id,
                )

                # Mark event as processed
                await conn.execute(
                    """
                    UPDATE payment_events
                    SET processed = true, processed_at = NOW()
                    WHERE stripe_event_id = $1
                    """,
                    event_id,
                )

            logger.info(
                f"Processed invoice.payment_failed for subscription: {stripe_subscription_id}. "
                f"Grace period until {grace_period_ends}"
            )

            return {
                "event_id": event_id,
                "event_type": "invoice.payment_failed",
                "status": "processed",
                "stripe_subscription_id": stripe_subscription_id,
                "grace_period_ends_at": grace_period_ends.isoformat(),
            }

        except Exception as e:
            logger.error(f"Error processing invoice.payment_failed: {e}")
            await StripeService._record_event_error(pool, event_id, str(e))
            raise

    @staticmethod
    async def process_subscription_deleted(
        pool: asyncpg.Pool,
        event_id: str,
        event_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle customer.subscription.deleted event.

        Args:
            pool: Database connection pool
            event_id: Stripe event ID
            event_data: Event data from webhook

        Returns:
            Dict with processing status
        """
        try:
            subscription = event_data.get("object", {})
            stripe_subscription_id = subscription.get("id")

            async with pool.acquire() as conn:
                # Record event
                await conn.execute(
                    """
                    INSERT INTO payment_events
                    (stripe_event_id, event_type, event_data)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (stripe_event_id) DO NOTHING
                    """,
                    event_id,
                    "customer.subscription.deleted",
                    {"stripe_subscription_id": stripe_subscription_id},
                )

                # Update subscription status to cancelled
                await conn.execute(
                    """
                    UPDATE user_subscriptions
                    SET status = 'cancelled',
                        cancel_at_period_end = true,
                        grace_period_ends_at = NULL,
                        updated_at = NOW()
                    WHERE stripe_subscription_id = $1
                    """,
                    stripe_subscription_id,
                )

                # Mark event as processed
                await conn.execute(
                    """
                    UPDATE payment_events
                    SET processed = true, processed_at = NOW()
                    WHERE stripe_event_id = $1
                    """,
                    event_id,
                )

            logger.info(
                f"Processed subscription.deleted for subscription: {stripe_subscription_id}"
            )

            return {
                "event_id": event_id,
                "event_type": "customer.subscription.deleted",
                "status": "processed",
                "stripe_subscription_id": stripe_subscription_id,
            }

        except Exception as e:
            logger.error(f"Error processing subscription.deleted: {e}")
            await StripeService._record_event_error(pool, event_id, str(e))
            raise

    @staticmethod
    async def generate_portal_url(
        pool: asyncpg.Pool,
        user_id: int,
        return_url: str = "https://localhost:3000/account",
    ) -> str:
        """
        Generate a Stripe Customer Portal URL for subscription management.

        Args:
            pool: Database connection pool
            user_id: User ID
            return_url: URL to return to after portal session

        Returns:
            Portal session URL

        Raises:
            ValueError: If user has no Stripe customer ID or API fails
        """
        if not STRIPE_API_KEY:
            raise ValueError("STRIPE_API_KEY not configured")

        try:
            async with pool.acquire() as conn:
                sub = await conn.fetchrow(
                    "SELECT stripe_customer_id FROM user_subscriptions WHERE user_id = $1",
                    user_id,
                )
                if not sub or not sub["stripe_customer_id"]:
                    raise ValueError(
                        f"User {user_id} has no associated Stripe customer"
                    )

            session = stripe.billing_portal.Session.create(
                customer=sub["stripe_customer_id"],
                return_url=return_url,
            )

            logger.info(
                f"Generated Stripe portal URL for user {user_id}: {session.url}"
            )

            return session.url

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error generating portal URL: {e}")
            raise ValueError(f"Failed to generate portal URL: {str(e)}")
        except Exception as e:
            logger.error(f"Error generating portal URL: {e}")
            raise

    @staticmethod
    async def cancel_subscription(
        pool: asyncpg.Pool,
        user_id: int,
    ) -> Dict[str, Any]:
        """
        Cancel a user's Stripe subscription immediately.

        Args:
            pool: Database connection pool
            user_id: User ID

        Returns:
            Dict with cancellation info

        Raises:
            ValueError: If user has no active subscription or API fails
        """
        if not STRIPE_API_KEY:
            raise ValueError("STRIPE_API_KEY not configured")

        try:
            async with pool.acquire() as conn:
                sub = await conn.fetchrow(
                    """
                    SELECT stripe_subscription_id FROM user_subscriptions
                    WHERE user_id = $1 AND status IN ('active', 'trial')
                    """,
                    user_id,
                )
                if not sub or not sub["stripe_subscription_id"]:
                    raise ValueError(f"User {user_id} has no active subscription")

                stripe_subscription_id = sub["stripe_subscription_id"]

            # Cancel subscription
            cancelled = stripe.Subscription.delete(stripe_subscription_id)

            logger.info(f"Cancelled Stripe subscription {stripe_subscription_id}")

            return {
                "stripe_subscription_id": stripe_subscription_id,
                "cancelled_at": cancelled.get("canceled_at"),
            }

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error cancelling subscription: {e}")
            raise ValueError(f"Failed to cancel subscription: {str(e)}")
        except Exception as e:
            logger.error(f"Error cancelling subscription: {e}")
            raise

    @staticmethod
    async def _record_event_error(
        pool: asyncpg.Pool,
        event_id: str,
        error_message: str,
    ) -> None:
        """
        Record a webhook processing error.

        Args:
            pool: Database connection pool
            event_id: Stripe event ID
            error_message: Error message
        """
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE payment_events
                    SET processed = true, error_message = $1, processed_at = NOW()
                    WHERE stripe_event_id = $2
                    """,
                    error_message,
                    event_id,
                )
        except Exception as e:
            logger.error(f"Error recording event error: {e}")
