"""
VanCity Lens — Webhook/CRM Integration (BIZ-016)

Webhook management and delivery logic for third-party CRM integrations.
In-memory storage for MVP with HMAC-SHA256 signature verification.
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────────────────────────────────


class WebhookEventType(str, Enum):
    """Supported webhook event types for CRM integration."""

    PARCEL_ANALYZED = "parcel.analyzed"
    ALERT_TRIGGERED = "alert.triggered"
    REPORT_READY = "report.ready"
    SIGNAL_NEW = "signal.new"


class WebhookConfig(BaseModel):
    """Configuration for a registered webhook endpoint."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    url: str  # Delivery URL
    events: list[WebhookEventType]
    secret: Optional[str] = None  # For HMAC signing
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WebhookDelivery(BaseModel):
    """Tracks the delivery status of a webhook event."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    webhook_id: str
    event_type: str
    payload: dict
    status: str = "pending"  # pending, delivered, failed
    response_code: Optional[int] = None
    attempts: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ────────────────────────────────────────────────────────────────────────────
# Webhook Manager (in-memory for MVP)
# ────────────────────────────────────────────────────────────────────────────


class WebhookManager:
    """
    In-memory webhook manager for MVP.

    Manages webhook registration, event delivery queuing,
    and HMAC-SHA256 signature generation/verification.
    """

    # Maximum webhooks a user can register
    MAX_WEBHOOKS_PER_USER = 10

    def __init__(self):
        # In-memory stores keyed by ID
        self._webhooks: dict[str, WebhookConfig] = {}
        self._deliveries: dict[str, WebhookDelivery] = {}

    def register_webhook(self, config: WebhookConfig) -> WebhookConfig:
        """
        Register a new webhook.

        Args:
            config: The webhook configuration to register.

        Returns:
            The registered WebhookConfig (with generated ID if not set).

        Raises:
            ValueError: If URL is invalid or user has too many webhooks.
        """
        # Validate URL
        if not config.url or not config.url.startswith(("http://", "https://")):
            raise ValueError("Webhook URL must start with http:// or https://")

        # Check max webhooks per user
        user_webhooks = [
            w
            for w in self._webhooks.values()
            if w.user_id == config.user_id and w.is_active
        ]
        if len(user_webhooks) >= self.MAX_WEBHOOKS_PER_USER:
            raise ValueError(
                f"Maximum {self.MAX_WEBHOOKS_PER_USER} active webhooks per user"
            )

        # Validate events list is not empty
        if not config.events:
            raise ValueError("At least one event type is required")

        # Generate a secret if none provided
        if config.secret is None:
            config.secret = str(uuid.uuid4())

        self._webhooks[config.id] = config
        logger.info(
            "Webhook registered: id=%s user=%s url=%s events=%s",
            config.id,
            config.user_id,
            config.url,
            [e.value for e in config.events],
        )
        return config

    def unregister_webhook(self, webhook_id: str, user_id: str) -> bool:
        """
        Unregister (deactivate) a webhook.

        Args:
            webhook_id: The webhook ID to unregister.
            user_id: The user ID (must own the webhook).

        Returns:
            True if the webhook was found and deactivated, False otherwise.
        """
        webhook = self._webhooks.get(webhook_id)
        if not webhook or webhook.user_id != user_id:
            return False

        webhook.is_active = False
        logger.info("Webhook unregistered: id=%s user=%s", webhook_id, user_id)
        return True

    def list_webhooks(self, user_id: str) -> list[WebhookConfig]:
        """
        List all webhooks for a user (active and inactive).

        Args:
            user_id: The user ID to list webhooks for.

        Returns:
            List of WebhookConfig objects belonging to the user.
        """
        return [w for w in self._webhooks.values() if w.user_id == user_id]

    def get_webhook(self, webhook_id: str, user_id: str) -> Optional[WebhookConfig]:
        """
        Get a specific webhook by ID and user.

        Args:
            webhook_id: The webhook ID.
            user_id: The user ID (must own the webhook).

        Returns:
            WebhookConfig if found and owned by user, None otherwise.
        """
        webhook = self._webhooks.get(webhook_id)
        if webhook and webhook.user_id == user_id:
            return webhook
        return None

    def queue_delivery(
        self, event_type: WebhookEventType, payload: dict, user_id: str
    ) -> list[str]:
        """
        Queue webhook deliveries for all active webhooks subscribed to the event.

        Args:
            event_type: The event type that occurred.
            payload: The event payload data.
            user_id: The user ID whose webhooks to trigger.

        Returns:
            List of delivery IDs for the queued deliveries.
        """
        delivery_ids = []

        for webhook in self._webhooks.values():
            if (
                webhook.user_id == user_id
                and webhook.is_active
                and event_type in webhook.events
            ):
                delivery = WebhookDelivery(
                    webhook_id=webhook.id,
                    event_type=event_type.value,
                    payload=payload,
                )
                self._deliveries[delivery.id] = delivery
                delivery_ids.append(delivery.id)
                logger.info(
                    "Webhook delivery queued: delivery_id=%s webhook_id=%s event=%s",
                    delivery.id,
                    webhook.id,
                    event_type.value,
                )

        return delivery_ids

    def get_delivery_status(self, delivery_id: str) -> Optional[WebhookDelivery]:
        """
        Get the delivery status for a specific delivery.

        Args:
            delivery_id: The delivery ID to check.

        Returns:
            WebhookDelivery if found, None otherwise.
        """
        return self._deliveries.get(delivery_id)

    @staticmethod
    def generate_signature(payload: dict, secret: str) -> str:
        """
        Generate an HMAC-SHA256 signature for a webhook payload.

        Args:
            payload: The payload dict to sign.
            secret: The webhook secret key.

        Returns:
            Hex-encoded HMAC-SHA256 signature string.
        """
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def verify_signature(payload: dict, secret: str, signature: str) -> bool:
        """
        Verify an HMAC-SHA256 signature for a webhook payload.

        Args:
            payload: The payload dict.
            secret: The webhook secret key.
            signature: The signature to verify.

        Returns:
            True if the signature is valid, False otherwise.
        """
        expected = WebhookManager.generate_signature(payload, secret)
        return hmac.compare_digest(expected, signature)


# ────────────────────────────────────────────────────────────────────────────
# Singleton instance for route handlers
# ────────────────────────────────────────────────────────────────────────────

webhook_manager = WebhookManager()
