"""
VCL-82 [BIZ-003] Stripe payment integration API endpoints

FastAPI routes for Stripe checkout, webhook handling, and subscription management.
"""

import logging
from typing import Dict

from fastapi import APIRouter, HTTPException, Request, status, Depends, Body
from pydantic import BaseModel
import asyncpg

from .user_auth import get_current_user_from_request
from .db import db
from .stripe_integration import StripeService


logger = logging.getLogger(__name__)

# Create router for Stripe endpoints
router = APIRouter(prefix="/api/v1/stripe", tags=["stripe"])


# ────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ────────────────────────────────────────────────────────────────────────────


class CreateCheckoutSessionRequest(BaseModel):
    """Request to create a Stripe checkout session."""

    tier_name: str  # free, starter, professional, enterprise
    billing_period: str = "monthly"  # monthly or annual
    success_url: str = "https://localhost:3000/subscribe/success"
    cancel_url: str = "https://localhost:3000/subscribe/cancel"


class CheckoutSessionResponse(BaseModel):
    """Response with Stripe checkout session info."""

    session_id: str
    checkout_url: str


class CancelSubscriptionRequest(BaseModel):
    """Request to cancel subscription."""

    confirm: bool = False


class WebhookResponse(BaseModel):
    """Response from webhook endpoint."""

    event_id: str
    event_type: str
    status: str


# ────────────────────────────────────────────────────────────────────────────
# Dependencies
# ────────────────────────────────────────────────────────────────────────────


def get_db_pool(request: Request) -> asyncpg.Pool:
    """Get database pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        pool = db.pool
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool


# ────────────────────────────────────────────────────────────────────────────
# Public Endpoints
# ────────────────────────────────────────────────────────────────────────────


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CreateCheckoutSessionRequest,
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> CheckoutSessionResponse:
    """
    Create a Stripe Checkout session for subscription.

    Authenticated endpoint. Returns a URL to redirect user to Stripe Checkout.

    Args:
        request: Subscription details (tier, billing period, etc.)
        user: Current user from JWT token
        db_pool: Database connection pool

    Returns:
        CheckoutSessionResponse with session_id and checkout_url

    Raises:
        HTTPException 400: Invalid tier or billing period
        HTTPException 402: Payment processing error
        HTTPException 500: Internal server error
    """
    try:
        # Validate tier name
        valid_tiers = ["free", "starter", "professional", "enterprise"]
        if request.tier_name not in valid_tiers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tier: {request.tier_name}. Must be one of {valid_tiers}",
            )

        # Validate billing period
        if request.billing_period not in ["monthly", "annual"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid billing_period. Must be 'monthly' or 'annual'",
            )

        # Free tier should not use Stripe checkout
        if request.tier_name == "free":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Free tier does not require Stripe checkout",
            )

        # Create checkout session
        result = await StripeService.create_checkout_session(
            db_pool,
            user["id"],
            request.tier_name,
            request.billing_period,
            request.success_url,
            request.cancel_url,
        )

        return CheckoutSessionResponse(
            session_id=result["session_id"],
            checkout_url=result["checkout_url"],
        )

    except ValueError as e:
        logger.warning(f"Checkout session creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error creating checkout session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session",
        )


@router.post("/webhook", response_model=WebhookResponse)
async def stripe_webhook(
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> WebhookResponse:
    """
    Handle Stripe webhook events.

    Unauthenticated endpoint. Verifies Stripe signature before processing.

    Supported events:
    - customer.subscription.created
    - invoice.payment_succeeded
    - invoice.payment_failed
    - customer.subscription.deleted

    Args:
        request: HTTP request with payload and signature
        db_pool: Database connection pool

    Returns:
        WebhookResponse with event status

    Raises:
        HTTPException 401: Invalid signature
        HTTPException 400: Invalid payload
        HTTPException 500: Processing error
    """
    try:
        # Get payload and signature
        payload = await request.body()
        signature = request.headers.get("stripe-signature")

        if not signature:
            logger.warning("Webhook received without stripe-signature header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing stripe-signature header",
            )

        # Handle webhook
        result = await StripeService.handle_webhook(db_pool, payload, signature)

        return WebhookResponse(
            event_id=result["event_id"],
            event_type=result["event_type"],
            status=result["status"],
        )

    except ValueError as e:
        logger.warning(f"Webhook signature verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error handling webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook",
        )


@router.get("/portal")
async def get_portal_url(
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> Dict:
    """
    Generate a Stripe Customer Portal URL.

    Authenticated endpoint. Returns a URL to Stripe Customer Portal where users
    can manage their subscription, update payment method, etc.

    Args:
        user: Current user from JWT token
        db_pool: Database connection pool

    Returns:
        Dict with portal_url

    Raises:
        HTTPException 404: User has no active Stripe subscription
        HTTPException 402: Stripe API error
        HTTPException 500: Internal server error
    """
    try:
        portal_url = await StripeService.generate_portal_url(
            db_pool, user["id"]
        )

        return {"portal_url": portal_url}

    except ValueError as e:
        logger.warning(f"Portal URL generation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error generating portal URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate portal URL",
        )


@router.post("/cancel")
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    user: Dict = Depends(get_current_user_from_request),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> Dict:
    """
    Cancel the current user's subscription immediately.

    Authenticated endpoint. Requires confirmation flag to prevent accidental cancellation.

    Args:
        request: Cancellation request with confirm flag
        user: Current user from JWT token
        db_pool: Database connection pool

    Returns:
        Dict with cancellation info

    Raises:
        HTTPException 400: Confirmation not provided
        HTTPException 404: User has no active subscription
        HTTPException 402: Stripe API error
        HTTPException 500: Internal server error
    """
    try:
        if not request.confirm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription cancellation must be confirmed (confirm=true)",
            )

        result = await StripeService.cancel_subscription(db_pool, user["id"])

        return {
            "status": "cancelled",
            "stripe_subscription_id": result["stripe_subscription_id"],
            "cancelled_at": result["cancelled_at"],
        }

    except ValueError as e:
        logger.warning(f"Subscription cancellation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error cancelling subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription",
        )
