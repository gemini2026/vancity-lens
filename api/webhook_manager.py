"""
VanCity Lens — Webhook Manager (VCL-108 / BIZ-010)

Webhook delivery system for third-party integrations with retry logic and verification.
"""

import logging
import hmac
import hashlib
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, NamedTuple
from enum import Enum

import asyncpg
import httpx

logger = logging.getLogger(__name__)


class WebhookEvent(str, Enum):
    """Supported webhook events."""

    PARCEL_UPDATED = "parcel.updated"
    SIGNAL_NEW = "signal.new"
    ENTITLEMENT_COMPUTED = "entitlement.computed"
    ALERT_TRIGGERED = "alert.triggered"


VALID_EVENTS = {
    "parcel.updated",
    "signal.new",
    "entitlement.computed",
    "alert.triggered",
}


class WebhookInfo(NamedTuple):
    """Webhook information for display."""

    id: int
    api_key_id: int
    url: str
    events: List[str]
    created_at: datetime
    active: bool


class WebhookDeliveryResult(NamedTuple):
    """Result of webhook delivery attempt."""

    success: bool
    status_code: Optional[int]
    error: Optional[str]
    delivery_time_ms: int


class WebhookManager:
    """Manages webhook registrations and delivery for third-party integrations."""

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_BACKOFF = [1, 2, 4]  # Seconds (exponential: 1s, 2s, 4s)
    TIMEOUT_SECONDS = 10

    @staticmethod
    def _generate_webhook_secret() -> str:
        """Generate a random webhook secret."""
        import secrets

        return secrets.token_urlsafe(32)

    @staticmethod
    def _create_signature(payload: str, secret: str) -> str:
        """
        Create HMAC-SHA256 signature for webhook payload.

        Args:
            payload: JSON payload as string
            secret: Webhook secret

        Returns:
            HMAC-SHA256 signature (hex-encoded)
        """
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def verify_signature(payload: str, signature: str, secret: str) -> bool:
        """
        Verify webhook signature.

        Args:
            payload: JSON payload as string
            signature: Signature from X-Webhook-Signature header
            secret: Webhook secret

        Returns:
            True if signature is valid
        """
        expected_signature = WebhookManager._create_signature(payload, secret)
        return hmac.compare_digest(expected_signature, signature)

    @staticmethod
    async def register_webhook(
        pool: asyncpg.Pool,
        api_key_id: int,
        url: str,
        events: List[str],
    ) -> WebhookInfo:
        """
        Register a webhook for an API key.

        Args:
            pool: Database connection pool
            api_key_id: The API key ID
            url: Webhook URL to send events to
            events: List of events to subscribe to

        Returns:
            WebhookInfo with webhook details
        """
        # Validate events
        invalid_events = set(events) - VALID_EVENTS
        if invalid_events:
            raise ValueError(f"Invalid events: {invalid_events}")

        # Generate webhook secret
        secret = WebhookManager._generate_webhook_secret()

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO webhooks
                (api_key_id, url, events, secret, created_at, active)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, created_at
                """,
                api_key_id,
                url,
                events,
                secret,
                datetime.now(tz=timezone.utc),
                True,
            )

        return WebhookInfo(
            id=result["id"],
            api_key_id=api_key_id,
            url=url,
            events=events,
            created_at=result["created_at"],
            active=True,
        )

    @staticmethod
    async def list_webhooks(pool: asyncpg.Pool, api_key_id: int) -> List[WebhookInfo]:
        """
        List all webhooks for an API key.

        Args:
            pool: Database connection pool
            api_key_id: The API key ID

        Returns:
            List of WebhookInfo
        """
        async with pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT id, api_key_id, url, events, created_at, active
                FROM webhooks
                WHERE api_key_id = $1
                ORDER BY created_at DESC
                """,
                api_key_id,
            )

        return [
            WebhookInfo(
                id=r["id"],
                api_key_id=r["api_key_id"],
                url=r["url"],
                events=r["events"],
                created_at=r["created_at"],
                active=r["active"],
            )
            for r in records
        ]

    @staticmethod
    async def deactivate_webhook(
        pool: asyncpg.Pool, webhook_id: int, api_key_id: int
    ) -> bool:
        """
        Deactivate a webhook.

        Args:
            pool: Database connection pool
            webhook_id: The webhook ID
            api_key_id: The API key ID (must own the webhook)

        Returns:
            True if deactivated, False if not found
        """
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE webhooks
                SET active = FALSE
                WHERE id = $1 AND api_key_id = $2
                """,
                webhook_id,
                api_key_id,
            )

        return result == "UPDATE 1"

    @staticmethod
    async def trigger_webhook(
        pool: asyncpg.Pool,
        event: str,
        payload: Dict,
        webhook_id: Optional[int] = None,
    ) -> WebhookDeliveryResult:
        """
        Send webhook event with automatic retry logic.

        Args:
            pool: Database connection pool
            event: Event type (e.g., parcel.updated)
            payload: Event payload as dict
            webhook_id: Specific webhook to trigger (None = all matching)

        Returns:
            WebhookDeliveryResult with delivery status
        """
        if event not in VALID_EVENTS:
            raise ValueError(f"Invalid event: {event}")

        # Get webhooks that subscribe to this event
        query = """
            SELECT id, url, secret
            FROM webhooks
            WHERE active = TRUE AND ($1 = ANY(events))
        """
        params = [event]

        if webhook_id:
            query += " AND id = $2"
            params.append(webhook_id)

        async with pool.acquire() as conn:
            webhooks = await conn.fetch(query, *params)

        if not webhooks:
            return WebhookDeliveryResult(
                success=False,
                status_code=None,
                error="No webhooks found",
                delivery_time_ms=0,
            )

        # Send to first webhook (or all in production)
        webhook = webhooks[0]
        return await WebhookManager._deliver_webhook(
            webhook["url"],
            webhook["secret"],
            event,
            payload,
        )

    @staticmethod
    async def _deliver_webhook(
        url: str,
        secret: str,
        event: str,
        payload: Dict,
    ) -> WebhookDeliveryResult:
        """
        Deliver a webhook with retry logic.

        Args:
            url: Webhook URL
            secret: Webhook secret for HMAC
            event: Event type
            payload: Event payload

        Returns:
            WebhookDeliveryResult
        """
        payload_json = json.dumps(
            {
                "event": event,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "data": payload,
            }
        )

        signature = WebhookManager._create_signature(payload_json, secret)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
            "X-Webhook-Signature": signature,
        }

        # Retry logic
        for attempt in range(WebhookManager.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(
                    timeout=WebhookManager.TIMEOUT_SECONDS
                ) as client:
                    start_time = datetime.now(tz=timezone.utc)
                    response = await client.post(
                        url, content=payload_json, headers=headers
                    )
                    end_time = datetime.now(tz=timezone.utc)
                    delivery_time_ms = int(
                        (end_time - start_time).total_seconds() * 1000
                    )

                    if response.status_code < 400:
                        return WebhookDeliveryResult(
                            success=True,
                            status_code=response.status_code,
                            error=None,
                            delivery_time_ms=delivery_time_ms,
                        )
                    elif response.status_code >= 500:
                        # Retry on 5xx
                        if attempt < WebhookManager.MAX_RETRIES - 1:
                            await asyncio.sleep(WebhookManager.RETRY_BACKOFF[attempt])
                            continue
                        return WebhookDeliveryResult(
                            success=False,
                            status_code=response.status_code,
                            error=f"Server error: {response.status_code}",
                            delivery_time_ms=delivery_time_ms,
                        )
                    else:
                        # Don't retry on 4xx
                        return WebhookDeliveryResult(
                            success=False,
                            status_code=response.status_code,
                            error=f"Client error: {response.status_code}",
                            delivery_time_ms=delivery_time_ms,
                        )

            except asyncio.TimeoutError:
                if attempt < WebhookManager.MAX_RETRIES - 1:
                    await asyncio.sleep(WebhookManager.RETRY_BACKOFF[attempt])
                    continue
                return WebhookDeliveryResult(
                    success=False,
                    status_code=None,
                    error="Timeout",
                    delivery_time_ms=WebhookManager.TIMEOUT_SECONDS * 1000,
                )
            except Exception as e:
                if attempt < WebhookManager.MAX_RETRIES - 1:
                    await asyncio.sleep(WebhookManager.RETRY_BACKOFF[attempt])
                    continue
                return WebhookDeliveryResult(
                    success=False,
                    status_code=None,
                    error=str(e),
                    delivery_time_ms=0,
                )

        return WebhookDeliveryResult(
            success=False,
            status_code=None,
            error="Max retries exceeded",
            delivery_time_ms=0,
        )
