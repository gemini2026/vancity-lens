"""
VanCity Lens — Webhook/CRM Integration Tests (BIZ-016)

Comprehensive test suite for webhook management, HMAC signatures,
delivery queuing, and FastAPI route endpoints.
40+ tests covering registration, listing, deletion, signatures,
delivery, auth, and edge cases.
"""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.testclient import TestClient

from api.webhooks import (
    WebhookConfig,
    WebhookDelivery,
    WebhookEventType,
    WebhookManager,
)
from api.webhook_routes import router, webhook_manager as route_manager


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def manager():
    """Fresh WebhookManager instance for each test."""
    return WebhookManager()


@pytest.fixture
def sample_config():
    """Sample webhook config for tests."""
    return WebhookConfig(
        user_id="user-1",
        url="https://example.com/webhook",
        events=[WebhookEventType.PARCEL_ANALYZED, WebhookEventType.ALERT_TRIGGERED],
        secret="test-secret-key",
    )


@pytest.fixture
def sample_config_minimal():
    """Minimal webhook config (single event, no secret)."""
    return WebhookConfig(
        user_id="user-1",
        url="https://hooks.example.com/receive",
        events=[WebhookEventType.SIGNAL_NEW],
    )


@pytest.fixture
def registered_webhook(manager, sample_config):
    """A webhook that is already registered."""
    return manager.register_webhook(sample_config)


MOCK_USER = {"id": 42, "email": "test@example.com", "role": "user", "is_active": True}


def _make_app(override_user=None):
    """Build a minimal FastAPI app with the webhook router mounted."""
    app = FastAPI()
    app.include_router(router)

    if override_user is not None:
        from api.user_auth import get_current_user_from_request

        app.dependency_overrides[get_current_user_from_request] = lambda: override_user

    return app


@pytest.fixture
def auth_client():
    """TestClient with a mocked authenticated user."""
    app = _make_app(override_user=MOCK_USER)
    # Reset the singleton manager state between tests
    route_manager._webhooks.clear()
    route_manager._deliveries.clear()
    return TestClient(app)


@pytest.fixture
def unauth_client():
    """TestClient with auth override that raises 401 (simulating missing creds)."""
    from api.user_auth import get_current_user_from_request

    def _raise_unauth():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization credentials",
        )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_from_request] = _raise_unauth
    route_manager._webhooks.clear()
    route_manager._deliveries.clear()
    return TestClient(app, raise_server_exceptions=False)


# ════════════════════════════════════════════════════════════════════════════
# WebhookManager — Registration
# ════════════════════════════════════════════════════════════════════════════


class TestWebhookRegistration:
    """Tests for webhook registration."""

    def test_register_webhook_success(self, manager, sample_config):
        """Registering a valid webhook should return a WebhookConfig."""
        result = manager.register_webhook(sample_config)
        assert result.id == sample_config.id
        assert result.url == "https://example.com/webhook"
        assert result.user_id == "user-1"
        assert result.is_active is True
        assert len(result.events) == 2

    def test_register_webhook_generates_id(self, manager):
        """Each webhook should receive a unique UUID id."""
        config = WebhookConfig(
            user_id="u1",
            url="https://a.com/hook",
            events=[WebhookEventType.SIGNAL_NEW],
        )
        result = manager.register_webhook(config)
        assert result.id is not None
        assert len(result.id) > 0
        # Verify it's a valid UUID
        uuid.UUID(result.id)

    def test_register_webhook_auto_generates_secret(self, manager, sample_config_minimal):
        """When no secret is given, the manager should auto-generate one."""
        result = manager.register_webhook(sample_config_minimal)
        assert result.secret is not None
        assert len(result.secret) > 0

    def test_register_webhook_preserves_provided_secret(self, manager, sample_config):
        """Provided secret should be kept as-is."""
        result = manager.register_webhook(sample_config)
        assert result.secret == "test-secret-key"

    def test_register_webhook_invalid_url_no_scheme(self, manager):
        """URLs without http/https scheme should be rejected."""
        config = WebhookConfig(
            user_id="u1",
            url="ftp://bad.com/hook",
            events=[WebhookEventType.SIGNAL_NEW],
        )
        with pytest.raises(ValueError, match="must start with http"):
            manager.register_webhook(config)

    def test_register_webhook_invalid_url_empty(self, manager):
        """Empty URL should be rejected."""
        config = WebhookConfig(
            user_id="u1",
            url="",
            events=[WebhookEventType.SIGNAL_NEW],
        )
        with pytest.raises(ValueError, match="must start with http"):
            manager.register_webhook(config)

    def test_register_webhook_empty_events(self, manager):
        """Webhook with empty events list should be rejected."""
        config = WebhookConfig(
            user_id="u1",
            url="https://example.com/hook",
            events=[],
        )
        with pytest.raises(ValueError, match="At least one event"):
            manager.register_webhook(config)

    def test_register_webhook_max_per_user(self, manager):
        """Exceeding MAX_WEBHOOKS_PER_USER should raise ValueError."""
        for i in range(manager.MAX_WEBHOOKS_PER_USER):
            config = WebhookConfig(
                user_id="user-limited",
                url=f"https://example.com/hook{i}",
                events=[WebhookEventType.SIGNAL_NEW],
            )
            manager.register_webhook(config)

        # One more should fail
        config = WebhookConfig(
            user_id="user-limited",
            url="https://example.com/hook-overflow",
            events=[WebhookEventType.SIGNAL_NEW],
        )
        with pytest.raises(ValueError, match="Maximum"):
            manager.register_webhook(config)

    def test_register_webhook_http_url_accepted(self, manager):
        """http:// URLs should be accepted (not just https)."""
        config = WebhookConfig(
            user_id="u1",
            url="http://localhost:8080/hook",
            events=[WebhookEventType.REPORT_READY],
        )
        result = manager.register_webhook(config)
        assert result.url == "http://localhost:8080/hook"

    def test_register_webhook_created_at_set(self, manager, sample_config):
        """created_at should be set automatically."""
        result = manager.register_webhook(sample_config)
        assert isinstance(result.created_at, datetime)


# ════════════════════════════════════════════════════════════════════════════
# WebhookManager — Listing and Retrieval
# ════════════════════════════════════════════════════════════════════════════


class TestWebhookListingAndRetrieval:
    """Tests for listing and retrieving webhooks."""

    def test_list_webhooks_empty(self, manager):
        """Listing for a user with no webhooks should return empty list."""
        result = manager.list_webhooks("no-hooks-user")
        assert result == []

    def test_list_webhooks_returns_user_webhooks(self, manager, registered_webhook):
        """List should return only the user's own webhooks."""
        result = manager.list_webhooks("user-1")
        assert len(result) == 1
        assert result[0].id == registered_webhook.id

    def test_list_webhooks_excludes_other_users(self, manager, registered_webhook):
        """Listing should not include other users' webhooks."""
        result = manager.list_webhooks("other-user")
        assert result == []

    def test_list_webhooks_includes_inactive(self, manager, registered_webhook):
        """Listing should include inactive (unregistered) webhooks."""
        manager.unregister_webhook(registered_webhook.id, "user-1")
        result = manager.list_webhooks("user-1")
        assert len(result) == 1
        assert result[0].is_active is False

    def test_get_webhook_success(self, manager, registered_webhook):
        """get_webhook should return the webhook for the correct user."""
        result = manager.get_webhook(registered_webhook.id, "user-1")
        assert result is not None
        assert result.id == registered_webhook.id

    def test_get_webhook_wrong_user(self, manager, registered_webhook):
        """get_webhook should return None for a non-owning user."""
        result = manager.get_webhook(registered_webhook.id, "other-user")
        assert result is None

    def test_get_webhook_nonexistent(self, manager):
        """get_webhook should return None for a non-existent webhook."""
        result = manager.get_webhook("nonexistent-id", "user-1")
        assert result is None


# ════════════════════════════════════════════════════════════════════════════
# WebhookManager — Deletion
# ════════════════════════════════════════════════════════════════════════════


class TestWebhookDeletion:
    """Tests for webhook unregistration."""

    def test_unregister_webhook_success(self, manager, registered_webhook):
        """Unregistering should deactivate the webhook."""
        success = manager.unregister_webhook(registered_webhook.id, "user-1")
        assert success is True
        webhook = manager.get_webhook(registered_webhook.id, "user-1")
        assert webhook.is_active is False

    def test_unregister_webhook_wrong_user(self, manager, registered_webhook):
        """Unregistering someone else's webhook should fail."""
        success = manager.unregister_webhook(registered_webhook.id, "other-user")
        assert success is False

    def test_unregister_webhook_nonexistent(self, manager):
        """Unregistering a non-existent webhook should return False."""
        success = manager.unregister_webhook("nonexistent", "user-1")
        assert success is False

    def test_unregister_frees_slot(self, manager):
        """Unregistering a webhook should free a slot for a new one."""
        configs = []
        for i in range(manager.MAX_WEBHOOKS_PER_USER):
            config = WebhookConfig(
                user_id="user-slots",
                url=f"https://example.com/hook{i}",
                events=[WebhookEventType.SIGNAL_NEW],
            )
            configs.append(manager.register_webhook(config))

        # Unregister one
        manager.unregister_webhook(configs[0].id, "user-slots")

        # Should now be able to register a new one
        new_config = WebhookConfig(
            user_id="user-slots",
            url="https://example.com/hook-new",
            events=[WebhookEventType.SIGNAL_NEW],
        )
        result = manager.register_webhook(new_config)
        assert result.is_active is True


# ════════════════════════════════════════════════════════════════════════════
# WebhookManager — HMAC Signatures
# ════════════════════════════════════════════════════════════════════════════


class TestHMACSignatures:
    """Tests for HMAC-SHA256 signature generation and verification."""

    def test_generate_signature_returns_hex_string(self):
        """Signature should be a hex-encoded string."""
        sig = WebhookManager.generate_signature({"key": "value"}, "secret")
        assert isinstance(sig, str)
        # SHA-256 hex is 64 chars
        assert len(sig) == 64

    def test_generate_signature_deterministic(self):
        """Same payload + secret should produce the same signature."""
        payload = {"event": "test", "data": {"id": 123}}
        sig1 = WebhookManager.generate_signature(payload, "my-secret")
        sig2 = WebhookManager.generate_signature(payload, "my-secret")
        assert sig1 == sig2

    def test_generate_signature_differs_with_different_secret(self):
        """Different secrets should produce different signatures."""
        payload = {"event": "test"}
        sig1 = WebhookManager.generate_signature(payload, "secret-a")
        sig2 = WebhookManager.generate_signature(payload, "secret-b")
        assert sig1 != sig2

    def test_generate_signature_differs_with_different_payload(self):
        """Different payloads should produce different signatures."""
        sig1 = WebhookManager.generate_signature({"a": 1}, "secret")
        sig2 = WebhookManager.generate_signature({"b": 2}, "secret")
        assert sig1 != sig2

    def test_verify_signature_valid(self):
        """verify_signature should return True for a correct signature."""
        payload = {"event": "parcel.analyzed", "data": {"pid": "ABC"}}
        secret = "webhook-secret-123"
        sig = WebhookManager.generate_signature(payload, secret)
        assert WebhookManager.verify_signature(payload, secret, sig) is True

    def test_verify_signature_invalid(self):
        """verify_signature should return False for an incorrect signature."""
        payload = {"event": "test"}
        assert WebhookManager.verify_signature(payload, "secret", "bad-sig") is False

    def test_verify_signature_wrong_secret(self):
        """Verifying with a different secret should fail."""
        payload = {"test": True}
        sig = WebhookManager.generate_signature(payload, "correct-secret")
        assert WebhookManager.verify_signature(payload, "wrong-secret", sig) is False

    def test_signature_empty_payload(self):
        """Signature should work with an empty payload dict."""
        sig = WebhookManager.generate_signature({}, "secret")
        assert isinstance(sig, str)
        assert len(sig) == 64
        assert WebhookManager.verify_signature({}, "secret", sig) is True


# ════════════════════════════════════════════════════════════════════════════
# WebhookManager — Delivery Queuing
# ════════════════════════════════════════════════════════════════════════════


class TestDeliveryQueuing:
    """Tests for webhook delivery queuing."""

    def test_queue_delivery_matching_event(self, manager, registered_webhook):
        """Should queue a delivery for a matching event type."""
        ids = manager.queue_delivery(
            WebhookEventType.PARCEL_ANALYZED,
            {"pid": "123"},
            "user-1",
        )
        assert len(ids) == 1

    def test_queue_delivery_non_matching_event(self, manager, registered_webhook):
        """Should not queue a delivery for a non-subscribed event."""
        ids = manager.queue_delivery(
            WebhookEventType.REPORT_READY,
            {"report_id": "r1"},
            "user-1",
        )
        assert len(ids) == 0

    def test_queue_delivery_inactive_webhook(self, manager, registered_webhook):
        """Inactive webhooks should not receive deliveries."""
        manager.unregister_webhook(registered_webhook.id, "user-1")
        ids = manager.queue_delivery(
            WebhookEventType.PARCEL_ANALYZED,
            {"pid": "123"},
            "user-1",
        )
        assert len(ids) == 0

    def test_queue_delivery_wrong_user(self, manager, registered_webhook):
        """Delivery for a different user should not trigger this user's webhook."""
        ids = manager.queue_delivery(
            WebhookEventType.PARCEL_ANALYZED,
            {"pid": "123"},
            "other-user",
        )
        assert len(ids) == 0

    def test_queue_delivery_multiple_webhooks(self, manager):
        """Multiple webhooks subscribed to the same event should all get deliveries."""
        for i in range(3):
            config = WebhookConfig(
                user_id="multi-user",
                url=f"https://example.com/hook{i}",
                events=[WebhookEventType.ALERT_TRIGGERED],
            )
            manager.register_webhook(config)

        ids = manager.queue_delivery(
            WebhookEventType.ALERT_TRIGGERED,
            {"alert": "test"},
            "multi-user",
        )
        assert len(ids) == 3

    def test_queue_delivery_status_is_pending(self, manager, registered_webhook):
        """Newly queued deliveries should have 'pending' status."""
        ids = manager.queue_delivery(
            WebhookEventType.PARCEL_ANALYZED,
            {"pid": "123"},
            "user-1",
        )
        delivery = manager.get_delivery_status(ids[0])
        assert delivery.status == "pending"
        assert delivery.attempts == 0

    def test_queue_delivery_preserves_payload(self, manager, registered_webhook):
        """Delivery should preserve the original payload."""
        payload = {"pid": "ABC-123", "analyzed": True, "score": 95}
        ids = manager.queue_delivery(
            WebhookEventType.PARCEL_ANALYZED,
            payload,
            "user-1",
        )
        delivery = manager.get_delivery_status(ids[0])
        assert delivery.payload == payload

    def test_queue_delivery_event_type_stored(self, manager, registered_webhook):
        """Delivery should store the event type string."""
        ids = manager.queue_delivery(
            WebhookEventType.ALERT_TRIGGERED,
            {"alert": "fire"},
            "user-1",
        )
        delivery = manager.get_delivery_status(ids[0])
        assert delivery.event_type == "alert.triggered"


# ════════════════════════════════════════════════════════════════════════════
# WebhookManager — Delivery Status
# ════════════════════════════════════════════════════════════════════════════


class TestDeliveryStatus:
    """Tests for delivery status retrieval."""

    def test_get_delivery_status_found(self, manager, registered_webhook):
        """Should return delivery when ID exists."""
        ids = manager.queue_delivery(
            WebhookEventType.PARCEL_ANALYZED, {"x": 1}, "user-1"
        )
        result = manager.get_delivery_status(ids[0])
        assert result is not None
        assert isinstance(result, WebhookDelivery)

    def test_get_delivery_status_not_found(self, manager):
        """Should return None for non-existent delivery."""
        result = manager.get_delivery_status("does-not-exist")
        assert result is None

    def test_delivery_has_created_at(self, manager, registered_webhook):
        """Delivery should have a created_at timestamp."""
        ids = manager.queue_delivery(
            WebhookEventType.PARCEL_ANALYZED, {"x": 1}, "user-1"
        )
        delivery = manager.get_delivery_status(ids[0])
        assert isinstance(delivery.created_at, datetime)

    def test_delivery_has_webhook_id(self, manager, registered_webhook):
        """Delivery should reference its parent webhook ID."""
        ids = manager.queue_delivery(
            WebhookEventType.PARCEL_ANALYZED, {"x": 1}, "user-1"
        )
        delivery = manager.get_delivery_status(ids[0])
        assert delivery.webhook_id == registered_webhook.id


# ════════════════════════════════════════════════════════════════════════════
# Route Tests — Auth Required
# ════════════════════════════════════════════════════════════════════════════


class TestRoutesAuthRequired:
    """All webhook routes (except delivery status) require authentication."""

    def test_register_webhook_no_auth(self, unauth_client):
        """POST /webhooks without auth should return 401 or 403."""
        resp = unauth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["parcel.analyzed"],
            },
        )
        assert resp.status_code in (401, 403)

    def test_list_webhooks_no_auth(self, unauth_client):
        """GET /webhooks without auth should return 401 or 403."""
        resp = unauth_client.get("/api/v1/webhooks")
        assert resp.status_code in (401, 403)

    def test_delete_webhook_no_auth(self, unauth_client):
        """DELETE /webhooks/{id} without auth should return 401 or 403."""
        resp = unauth_client.delete("/api/v1/webhooks/some-id")
        assert resp.status_code in (401, 403)

    def test_test_webhook_no_auth(self, unauth_client):
        """POST /webhooks/test/{id} without auth should return 401 or 403."""
        resp = unauth_client.post("/api/v1/webhooks/test/some-id")
        assert resp.status_code in (401, 403)


# ════════════════════════════════════════════════════════════════════════════
# Route Tests — Registration
# ════════════════════════════════════════════════════════════════════════════


class TestRouteRegistration:
    """Tests for POST /api/v1/webhooks."""

    def test_register_webhook_success(self, auth_client):
        """Valid registration should return 201 with webhook data."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://crm.example.com/hook",
                "events": ["parcel.analyzed", "alert.triggered"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://crm.example.com/hook"
        assert data["is_active"] is True
        assert len(data["events"]) == 2
        assert data["user_id"] == "42"

    def test_register_webhook_invalid_url(self, auth_client):
        """Invalid URL should return 400."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "ftp://bad.example.com",
                "events": ["parcel.analyzed"],
            },
        )
        assert resp.status_code == 400

    def test_register_webhook_invalid_event_type(self, auth_client):
        """Invalid event type should return 422 (validation error)."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["invalid.event"],
            },
        )
        assert resp.status_code == 422

    def test_register_webhook_empty_events(self, auth_client):
        """Empty events array should return 422 (min_length=1)."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": [],
            },
        )
        assert resp.status_code == 422

    def test_register_webhook_with_secret(self, auth_client):
        """Custom secret should be preserved."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["signal.new"],
                "secret": "my-custom-secret",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["secret"] == "my-custom-secret"

    def test_register_webhook_auto_secret(self, auth_client):
        """Omitting secret should auto-generate one."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["report.ready"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["secret"] is not None
        assert len(data["secret"]) > 0


# ════════════════════════════════════════════════════════════════════════════
# Route Tests — Listing
# ════════════════════════════════════════════════════════════════════════════


class TestRouteListing:
    """Tests for GET /api/v1/webhooks."""

    def test_list_webhooks_empty(self, auth_client):
        """Empty list when user has no webhooks."""
        resp = auth_client.get("/api/v1/webhooks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_webhooks_after_registration(self, auth_client):
        """Should list registered webhooks."""
        auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook1",
                "events": ["parcel.analyzed"],
            },
        )
        auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook2",
                "events": ["alert.triggered"],
            },
        )
        resp = auth_client.get("/api/v1/webhooks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


# ════════════════════════════════════════════════════════════════════════════
# Route Tests — Deletion
# ════════════════════════════════════════════════════════════════════════════


class TestRouteDeletion:
    """Tests for DELETE /api/v1/webhooks/{webhook_id}."""

    def test_delete_webhook_success(self, auth_client):
        """Deleting an owned webhook should return 204."""
        create_resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["signal.new"],
            },
        )
        webhook_id = create_resp.json()["id"]

        resp = auth_client.delete(f"/api/v1/webhooks/{webhook_id}")
        assert resp.status_code == 204

    def test_delete_webhook_not_found(self, auth_client):
        """Deleting a non-existent webhook should return 404."""
        resp = auth_client.delete("/api/v1/webhooks/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_webhook_shows_inactive_in_list(self, auth_client):
        """After deletion, webhook should appear as inactive in listing."""
        create_resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["signal.new"],
            },
        )
        webhook_id = create_resp.json()["id"]

        auth_client.delete(f"/api/v1/webhooks/{webhook_id}")

        list_resp = auth_client.get("/api/v1/webhooks")
        webhooks = list_resp.json()
        assert len(webhooks) == 1
        assert webhooks[0]["is_active"] is False


# ════════════════════════════════════════════════════════════════════════════
# Route Tests — Test Event
# ════════════════════════════════════════════════════════════════════════════


class TestRouteTestEvent:
    """Tests for POST /api/v1/webhooks/test/{webhook_id}."""

    def test_test_event_success(self, auth_client):
        """Sending a test event should return delivery IDs."""
        create_resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["parcel.analyzed"],
            },
        )
        webhook_id = create_resp.json()["id"]

        resp = auth_client.post(f"/api/v1/webhooks/test/{webhook_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "delivery_ids" in data
        assert len(data["delivery_ids"]) >= 1
        assert "message" in data

    def test_test_event_webhook_not_found(self, auth_client):
        """Test event to non-existent webhook should return 404."""
        resp = auth_client.post("/api/v1/webhooks/test/nonexistent-id")
        assert resp.status_code == 404

    def test_test_event_inactive_webhook(self, auth_client):
        """Test event to inactive webhook should return 400."""
        create_resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["alert.triggered"],
            },
        )
        webhook_id = create_resp.json()["id"]

        # Deactivate it
        auth_client.delete(f"/api/v1/webhooks/{webhook_id}")

        resp = auth_client.post(f"/api/v1/webhooks/test/{webhook_id}")
        assert resp.status_code == 400


# ════════════════════════════════════════════════════════════════════════════
# Route Tests — Delivery Status
# ════════════════════════════════════════════════════════════════════════════


class TestRouteDeliveryStatus:
    """Tests for GET /api/v1/webhooks/deliveries/{delivery_id}."""

    def test_delivery_status_found(self, auth_client):
        """Valid delivery ID should return delivery data."""
        # Create webhook and trigger a test event
        create_resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["parcel.analyzed"],
            },
        )
        webhook_id = create_resp.json()["id"]

        test_resp = auth_client.post(f"/api/v1/webhooks/test/{webhook_id}")
        delivery_id = test_resp.json()["delivery_ids"][0]

        resp = auth_client.get(f"/api/v1/webhooks/deliveries/{delivery_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == delivery_id
        assert data["status"] == "pending"
        assert data["webhook_id"] == webhook_id

    def test_delivery_status_not_found(self, auth_client):
        """Non-existent delivery ID should return 404."""
        resp = auth_client.get("/api/v1/webhooks/deliveries/does-not-exist")
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# Model Validation Tests
# ════════════════════════════════════════════════════════════════════════════


class TestModels:
    """Tests for Pydantic model validation."""

    def test_webhook_event_type_values(self):
        """All event types should have expected string values."""
        assert WebhookEventType.PARCEL_ANALYZED.value == "parcel.analyzed"
        assert WebhookEventType.ALERT_TRIGGERED.value == "alert.triggered"
        assert WebhookEventType.REPORT_READY.value == "report.ready"
        assert WebhookEventType.SIGNAL_NEW.value == "signal.new"

    def test_webhook_config_default_id(self):
        """WebhookConfig should auto-generate a UUID id."""
        config = WebhookConfig(
            user_id="u1",
            url="https://example.com",
            events=[WebhookEventType.SIGNAL_NEW],
        )
        uuid.UUID(config.id)  # Should not raise

    def test_webhook_delivery_default_status(self):
        """WebhookDelivery default status should be 'pending'."""
        delivery = WebhookDelivery(
            webhook_id="w1",
            event_type="test",
            payload={"a": 1},
        )
        assert delivery.status == "pending"
        assert delivery.attempts == 0
        assert delivery.response_code is None

    def test_webhook_config_strips_whitespace(self):
        """WebhookConfig should strip whitespace from string fields."""
        config = WebhookConfig(
            user_id="  user-1  ",
            url="  https://example.com  ",
            events=[WebhookEventType.SIGNAL_NEW],
        )
        assert config.user_id == "user-1"
        assert config.url == "https://example.com"

    def test_webhook_config_is_active_default(self):
        """Default is_active should be True."""
        config = WebhookConfig(
            user_id="u1",
            url="https://x.com",
            events=[WebhookEventType.SIGNAL_NEW],
        )
        assert config.is_active is True
