"""
VanCity Lens — Webhook/CRM Integration Routes (BIZ-016)

FastAPI routes for webhook management: register, list, delete, test, and delivery status.
"""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from .user_auth import get_current_user_from_request
from .webhooks import (
    WebhookConfig,
    WebhookDelivery,
    WebhookEventType,
    webhook_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["webhooks"])


# ────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ────────────────────────────────────────────────────────────────────────────


class WebhookRegisterRequest(BaseModel):
    """Request body for registering a new webhook."""
    model_config = ConfigDict(str_strip_whitespace=True)

    url: str = Field(..., min_length=1, description="Delivery URL (http or https)")
    events: list[WebhookEventType] = Field(
        ..., min_length=1, description="Event types to subscribe to"
    )
    secret: Optional[str] = Field(
        None, description="HMAC signing secret (auto-generated if omitted)"
    )


class WebhookResponse(BaseModel):
    """Response for a single webhook."""
    id: str
    user_id: str
    url: str
    events: list[WebhookEventType]
    secret: Optional[str] = None
    is_active: bool
    created_at: str  # ISO formatted


class DeliveryStatusResponse(BaseModel):
    """Response for webhook delivery status."""
    id: str
    webhook_id: str
    event_type: str
    payload: dict
    status: str
    response_code: Optional[int] = None
    attempts: int
    created_at: str  # ISO formatted


class TestEventResponse(BaseModel):
    """Response for test event delivery."""
    delivery_ids: list[str]
    message: str


# ────────────────────────────────────────────────────────────────────────────
# Helper
# ────────────────────────────────────────────────────────────────────────────


def _webhook_to_response(webhook: WebhookConfig) -> WebhookResponse:
    """Convert a WebhookConfig to a WebhookResponse."""
    return WebhookResponse(
        id=webhook.id,
        user_id=webhook.user_id,
        url=webhook.url,
        events=webhook.events,
        secret=webhook.secret,
        is_active=webhook.is_active,
        created_at=webhook.created_at.isoformat(),
    )


def _delivery_to_response(delivery: WebhookDelivery) -> DeliveryStatusResponse:
    """Convert a WebhookDelivery to a DeliveryStatusResponse."""
    return DeliveryStatusResponse(
        id=delivery.id,
        webhook_id=delivery.webhook_id,
        event_type=delivery.event_type,
        payload=delivery.payload,
        status=delivery.status,
        response_code=delivery.response_code,
        attempts=delivery.attempts,
        created_at=delivery.created_at.isoformat(),
    )


# ────────────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────────────


@router.post(
    "/webhooks",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new webhook",
)
async def register_webhook(
    body: WebhookRegisterRequest,
    user: Dict = Depends(get_current_user_from_request),
) -> WebhookResponse:
    """
    Register a new webhook endpoint for the authenticated user.

    The webhook will receive POST requests for subscribed event types,
    signed with HMAC-SHA256 using the provided (or auto-generated) secret.
    """
    config = WebhookConfig(
        user_id=str(user["id"]),
        url=body.url,
        events=body.events,
        secret=body.secret,
    )

    try:
        registered = webhook_manager.register_webhook(config)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info("Webhook registered via API: id=%s user=%s", registered.id, user["id"])
    return _webhook_to_response(registered)


@router.get(
    "/webhooks",
    response_model=list[WebhookResponse],
    summary="List user's webhooks",
)
async def list_webhooks(
    user: Dict = Depends(get_current_user_from_request),
) -> list[WebhookResponse]:
    """List all webhooks registered by the authenticated user."""
    webhooks = webhook_manager.list_webhooks(str(user["id"]))
    return [_webhook_to_response(w) for w in webhooks]


@router.delete(
    "/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unregister a webhook",
)
async def unregister_webhook(
    webhook_id: str,
    user: Dict = Depends(get_current_user_from_request),
):
    """Unregister (deactivate) a webhook owned by the authenticated user."""
    success = webhook_manager.unregister_webhook(webhook_id, str(user["id"]))
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found or not authorized",
        )


@router.post(
    "/webhooks/test/{webhook_id}",
    response_model=TestEventResponse,
    summary="Send a test event to a webhook",
)
async def test_webhook(
    webhook_id: str,
    user: Dict = Depends(get_current_user_from_request),
) -> TestEventResponse:
    """
    Send a test event to a specific webhook.

    Queues a test delivery with a sample payload for the first
    subscribed event type of the webhook.
    """
    webhook = webhook_manager.get_webhook(webhook_id, str(user["id"]))
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found or not authorized",
        )

    if not webhook.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook is not active",
        )

    # Use the first subscribed event type for testing
    test_event = webhook.events[0]
    test_payload = {
        "test": True,
        "message": "This is a test webhook delivery from VanCity Lens",
        "webhook_id": webhook.id,
    }

    delivery_ids = webhook_manager.queue_delivery(
        event_type=test_event,
        payload=test_payload,
        user_id=str(user["id"]),
    )

    return TestEventResponse(
        delivery_ids=delivery_ids,
        message=f"Test event '{test_event.value}' queued for delivery",
    )


@router.get(
    "/webhooks/deliveries/{delivery_id}",
    response_model=DeliveryStatusResponse,
    summary="Check delivery status",
)
async def get_delivery_status(
    delivery_id: str,
) -> DeliveryStatusResponse:
    """Check the delivery status of a specific webhook event."""
    delivery = webhook_manager.get_delivery_status(delivery_id)
    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found",
        )
    return _delivery_to_response(delivery)
