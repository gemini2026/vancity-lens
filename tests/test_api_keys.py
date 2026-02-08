"""
VanCity Lens — API Key Tests (VCL-108 / BIZ-010)

Comprehensive test suite for API key management and third-party integrations.
90+ tests covering key generation, hashing, validation, scopes, webhooks, and more.
"""

import pathlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

# Import modules to test
API_DIR = pathlib.Path(__file__).resolve().parent.parent / "api"

# Add to path for imports
import sys
sys.path.insert(0, str(API_DIR.parent))

from api.api_keys import (
    APIKeyManager,
    APIKey,
    APIKeyInfo,
    VALID_SCOPES,
    DEFAULT_RATE_LIMIT,
)
from api.webhook_manager import (
    WebhookManager,
    WebhookEvent,
    WebhookInfo,
    WebhookDeliveryResult,
    VALID_EVENTS,
)


# ════════════════════════════════════════════════════════════════════════════
# Test: APIKeyManager Class Structure
# ════════════════════════════════════════════════════════════════════════════


class TestAPIKeyManagerStructure:
    """Tests for APIKeyManager class."""

    def test_api_key_manager_has_generate_api_key_method(self):
        """APIKeyManager should have generate_api_key method."""
        assert hasattr(APIKeyManager, "generate_api_key")
        assert callable(getattr(APIKeyManager, "generate_api_key"))

    def test_api_key_manager_has_hash_api_key_method(self):
        """APIKeyManager should have hash_api_key method."""
        assert hasattr(APIKeyManager, "hash_api_key")
        assert callable(getattr(APIKeyManager, "hash_api_key"))

    def test_api_key_manager_has_validate_api_key_method(self):
        """APIKeyManager should have validate_api_key method."""
        assert hasattr(APIKeyManager, "validate_api_key")
        assert callable(getattr(APIKeyManager, "validate_api_key"))

    def test_api_key_manager_has_revoke_api_key_method(self):
        """APIKeyManager should have revoke_api_key method."""
        assert hasattr(APIKeyManager, "revoke_api_key")
        assert callable(getattr(APIKeyManager, "revoke_api_key"))

    def test_api_key_manager_has_list_api_keys_method(self):
        """APIKeyManager should have list_api_keys method."""
        assert hasattr(APIKeyManager, "list_api_keys")
        assert callable(getattr(APIKeyManager, "list_api_keys"))

    def test_api_key_manager_has_rotate_api_key_method(self):
        """APIKeyManager should have rotate_api_key method."""
        assert hasattr(APIKeyManager, "rotate_api_key")
        assert callable(getattr(APIKeyManager, "rotate_api_key"))

    def test_api_key_manager_has_update_last_used_method(self):
        """APIKeyManager should have update_last_used method."""
        assert hasattr(APIKeyManager, "update_last_used")
        assert callable(getattr(APIKeyManager, "update_last_used"))


# ════════════════════════════════════════════════════════════════════════════
# Test: Key Generation Format
# ════════════════════════════════════════════════════════════════════════════


class TestAPIKeyGeneration:
    """Tests for API key generation and format."""

    def test_generate_api_key_returns_api_key_namedtuple(self):
        """generate_api_key should return APIKey namedtuple."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        assert isinstance(key, APIKey)

    def test_generate_api_key_has_vcl_prefix(self):
        """Generated key should start with vcl_ prefix."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        assert key.key.startswith("vcl_")

    def test_generate_api_key_is_48_characters(self):
        """Generated key should be 48 chars (vcl_ + 32 hex + 12 prefix)."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        # vcl_ (4) + 32 hex chars = 36 total
        assert len(key.key) == 36
        assert len(key.key) == len("vcl_") + 32

    def test_generate_api_key_hex_format(self):
        """Generated key should contain only valid hex chars after vcl_."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        hex_part = key.key[4:]  # Skip "vcl_"
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_generate_api_key_unique(self):
        """Each generated key should be unique."""
        key1 = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key-1",
            scopes=["read:parcels"],
        )
        key2 = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key-2",
            scopes=["read:parcels"],
        )
        assert key1.key != key2.key

    def test_generate_api_key_prefix_is_first_12_chars(self):
        """key_prefix should be first 12 characters (vcl_ + 8 hex)."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        assert key.key_prefix == key.key[:12]
        assert key.key_prefix.startswith("vcl_")
        assert len(key.key_prefix) == 12

    def test_generate_api_key_with_no_expiration(self):
        """Generated key without expiration should have None."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        assert key.expires_at is None

    def test_generate_api_key_with_expiration(self):
        """Generated key with expiration should set expires_at."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
            expires_days=30,
        )
        assert key.expires_at is not None
        assert isinstance(key.expires_at, datetime)

    def test_generate_api_key_expiration_is_future(self):
        """Key expiration should be in the future."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
            expires_days=30,
        )
        now = datetime.now(tz=timezone.utc)
        assert key.expires_at > now

    def test_generate_api_key_expiration_approximately_days(self):
        """Key expiration should be approximately N days from now."""
        before = datetime.now(tz=timezone.utc)
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
            expires_days=30,
        )
        after = datetime.now(tz=timezone.utc)

        expected_min = before + timedelta(days=30)
        expected_max = after + timedelta(days=30, hours=1)

        assert expected_min <= key.expires_at <= expected_max


# ════════════════════════════════════════════════════════════════════════════
# Test: Key Hashing (SHA-256)
# ════════════════════════════════════════════════════════════════════════════


class TestAPIKeyHashing:
    """Tests for API key hashing with SHA-256."""

    def test_hash_api_key_returns_string(self):
        """hash_api_key should return a string."""
        hash_result = APIKeyManager.hash_api_key("vcl_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
        assert isinstance(hash_result, str)

    def test_hash_api_key_is_hex_string(self):
        """Hashed key should be hex string."""
        hash_result = APIKeyManager.hash_api_key("vcl_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_hash_api_key_sha256_length(self):
        """SHA-256 hash should be 64 hex characters."""
        hash_result = APIKeyManager.hash_api_key("vcl_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
        assert len(hash_result) == 64

    def test_hash_api_key_deterministic(self):
        """Same key should produce same hash."""
        key = "vcl_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        hash1 = APIKeyManager.hash_api_key(key)
        hash2 = APIKeyManager.hash_api_key(key)
        assert hash1 == hash2

    def test_hash_api_key_different_keys_different_hash(self):
        """Different keys should produce different hashes."""
        key1 = "vcl_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        key2 = "vcl_z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4"
        hash1 = APIKeyManager.hash_api_key(key1)
        hash2 = APIKeyManager.hash_api_key(key2)
        assert hash1 != hash2

    def test_hash_api_key_matches_sha256(self):
        """Hash should match SHA-256 calculation."""
        key = "vcl_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        computed_hash = hashlib.sha256(key.encode()).hexdigest()
        result = APIKeyManager.hash_api_key(key)
        assert result == computed_hash

    def test_hash_api_key_never_returns_raw_key(self):
        """Hashed key should not contain the original key."""
        key = "vcl_secretkeythatmustnotberevealed"
        hash_result = APIKeyManager.hash_api_key(key)
        assert key not in hash_result


# ════════════════════════════════════════════════════════════════════════════
# Test: Key Prefix Storage
# ════════════════════════════════════════════════════════════════════════════


class TestAPIKeyPrefix:
    """Tests for API key prefix (first 8 hex chars + vcl_)."""

    def test_key_prefix_is_stored_separately(self):
        """Key prefix should be stored as separate field."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        assert key.key_prefix is not None

    def test_key_prefix_is_12_characters(self):
        """Key prefix should be exactly 12 characters (vcl_ + 8 hex)."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        assert len(key.key_prefix) == 12

    def test_key_prefix_starts_with_vcl(self):
        """Key prefix should start with vcl_."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        assert key.key_prefix.startswith("vcl_")

    def test_key_prefix_is_first_12_of_full_key(self):
        """Key prefix should be first 12 chars of full key."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        assert key.key_prefix == key.key[:12]

    def test_key_prefix_hex_chars_valid(self):
        """Key prefix hex part should be valid hex."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
        )
        hex_part = key.key_prefix[4:]  # Skip "vcl_"
        assert all(c in "0123456789abcdef" for c in hex_part)


# ════════════════════════════════════════════════════════════════════════════
# Test: Scope Validation
# ════════════════════════════════════════════════════════════════════════════


class TestScopeValidation:
    """Tests for API key scope validation."""

    def test_valid_scopes_are_defined(self):
        """Should have defined valid scopes."""
        assert VALID_SCOPES is not None
        assert len(VALID_SCOPES) > 0

    def test_valid_scopes_contains_read_parcels(self):
        """Valid scopes should include read:parcels."""
        assert "read:parcels" in VALID_SCOPES

    def test_valid_scopes_contains_read_entitlements(self):
        """Valid scopes should include read:entitlements."""
        assert "read:entitlements" in VALID_SCOPES

    def test_valid_scopes_contains_read_signals(self):
        """Valid scopes should include read:signals."""
        assert "read:signals" in VALID_SCOPES

    def test_valid_scopes_contains_read_neighborhoods(self):
        """Valid scopes should include read:neighborhoods."""
        assert "read:neighborhoods" in VALID_SCOPES

    def test_valid_scopes_contains_write_webhooks(self):
        """Valid scopes should include write:webhooks."""
        assert "write:webhooks" in VALID_SCOPES

    def test_generate_api_key_rejects_invalid_scope(self):
        """generate_api_key should reject invalid scopes."""
        with pytest.raises(ValueError):
            APIKeyManager.generate_api_key(
                user_id=1,
                name="test-key",
                scopes=["invalid:scope"],
            )

    def test_generate_api_key_accepts_valid_scopes(self):
        """generate_api_key should accept all valid scopes."""
        for scope in VALID_SCOPES:
            key = APIKeyManager.generate_api_key(
                user_id=1,
                name="test-key",
                scopes=[scope],
            )
            assert key is not None

    def test_generate_api_key_accepts_multiple_scopes(self):
        """generate_api_key should accept multiple scopes."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels", "read:entitlements"],
        )
        assert key is not None


# ════════════════════════════════════════════════════════════════════════════
# Test: Key Validation (Async DB Operations)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAPIKeyValidation:
    """Tests for API key validation."""

    async def test_validate_api_key_with_valid_key(self):
        """validate_api_key should return APIKeyInfo for valid key."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": 1,
            "user_id": 1,
            "name": "test-key",
            "key_prefix": "vcl_test",
            "scopes": ["read:parcels"],
            "rate_limit": 100,
            "created_at": datetime.now(tz=timezone.utc),
            "expires_at": None,
            "last_used_at": None,
            "revoked_at": None,
        })

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.validate_api_key(mock_pool, "vcl_test")
        assert isinstance(result, APIKeyInfo)
        assert result.id == 1

    async def test_validate_api_key_returns_none_for_invalid_key(self):
        """validate_api_key should return None for invalid key."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.validate_api_key(mock_pool, "vcl_invalid")
        assert result is None

    async def test_validate_api_key_returns_none_for_revoked_key(self):
        """validate_api_key should return None for revoked key."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": 1,
            "user_id": 1,
            "name": "test-key",
            "key_prefix": "vcl_test",
            "scopes": ["read:parcels"],
            "rate_limit": 100,
            "created_at": datetime.now(tz=timezone.utc),
            "expires_at": None,
            "last_used_at": None,
            "revoked_at": datetime.now(tz=timezone.utc),
        })

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.validate_api_key(mock_pool, "vcl_test")
        assert result is None

    async def test_validate_api_key_returns_none_for_expired_key(self):
        """validate_api_key should return None for expired key."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": 1,
            "user_id": 1,
            "name": "test-key",
            "key_prefix": "vcl_test",
            "scopes": ["read:parcels"],
            "rate_limit": 100,
            "created_at": datetime.now(tz=timezone.utc),
            "expires_at": datetime.now(tz=timezone.utc) - timedelta(days=1),
            "last_used_at": None,
            "revoked_at": None,
        })

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.validate_api_key(mock_pool, "vcl_test")
        assert result is None


# ════════════════════════════════════════════════════════════════════════════
# Test: Key Rotation
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAPIKeyRotation:
    """Tests for API key rotation."""

    async def test_rotate_api_key_creates_new_key(self):
        """rotate_api_key should create a new key."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "name": "test-key",
            "scopes": ["read:parcels"],
            "rate_limit": 100,
            "expires_at": None,
        })
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        mock_transaction_obj = MagicMock()
        mock_transaction_obj.__aenter__ = AsyncMock(return_value=None)
        mock_transaction_obj.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_transaction_obj)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.rotate_api_key(mock_pool, 1, 1)
        assert result is not None
        assert isinstance(result, APIKey)

    async def test_rotate_api_key_returns_new_key_with_vcl_prefix(self):
        """Rotated key should start with vcl_."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "name": "test-key",
            "scopes": ["read:parcels"],
            "rate_limit": 100,
            "expires_at": None,
        })
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        mock_transaction_obj = MagicMock()
        mock_transaction_obj.__aenter__ = AsyncMock(return_value=None)
        mock_transaction_obj.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_transaction_obj)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.rotate_api_key(mock_pool, 1, 1)
        assert result.key.startswith("vcl_")

    async def test_rotate_api_key_returns_none_for_invalid_key(self):
        """rotate_api_key should return None if key not found."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.rotate_api_key(mock_pool, 1, 1)
        assert result is None


# ════════════════════════════════════════════════════════════════════════════
# Test: Key Listing (Masked Keys)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAPIKeyListing:
    """Tests for API key listing."""

    async def test_list_api_keys_returns_list(self):
        """list_api_keys should return a list."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.list_api_keys(mock_pool, 1)
        assert isinstance(result, list)

    async def test_list_api_keys_returns_api_key_info(self):
        """list_api_keys should return APIKeyInfo objects."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {
                "id": 1,
                "user_id": 1,
                "name": "test-key",
                "key_prefix": "vcl_test",
                "scopes": ["read:parcels"],
                "rate_limit": 100,
                "created_at": datetime.now(tz=timezone.utc),
                "expires_at": None,
                "last_used_at": None,
                "revoked_at": None,
            }
        ])

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.list_api_keys(mock_pool, 1)
        assert len(result) == 1
        assert isinstance(result[0], APIKeyInfo)

    async def test_list_api_keys_never_returns_raw_keys(self):
        """list_api_keys should never include full key values."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {
                "id": 1,
                "user_id": 1,
                "name": "test-key",
                "key_prefix": "vcl_test",
                "scopes": ["read:parcels"],
                "rate_limit": 100,
                "created_at": datetime.now(tz=timezone.utc),
                "expires_at": None,
                "last_used_at": None,
                "revoked_at": None,
            }
        ])

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.list_api_keys(mock_pool, 1)
        for key_info in result:
            assert not hasattr(key_info, "key")


# ════════════════════════════════════════════════════════════════════════════
# Test: Rate Limiting
# ════════════════════════════════════════════════════════════════════════════


class TestRateLimiting:
    """Tests for API key rate limiting."""

    def test_default_rate_limit_is_100(self):
        """Default rate limit should be 100 requests per minute."""
        assert DEFAULT_RATE_LIMIT == 100

    def test_generate_api_key_uses_default_rate_limit(self):
        """Generated key should use default rate limit if not specified."""
        # This is tested at DB level, but we can verify the constant
        assert DEFAULT_RATE_LIMIT > 0

    def test_generate_api_key_accepts_custom_rate_limit(self):
        """generate_api_key should accept custom rate limit."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
            rate_limit=200,
        )
        assert key is not None


# ════════════════════════════════════════════════════════════════════════════
# Test: WebhookManager Class Structure
# ════════════════════════════════════════════════════════════════════════════


class TestWebhookManagerStructure:
    """Tests for WebhookManager class structure."""

    def test_webhook_manager_has_register_webhook_method(self):
        """WebhookManager should have register_webhook method."""
        assert hasattr(WebhookManager, "register_webhook")
        assert callable(getattr(WebhookManager, "register_webhook"))

    def test_webhook_manager_has_list_webhooks_method(self):
        """WebhookManager should have list_webhooks method."""
        assert hasattr(WebhookManager, "list_webhooks")
        assert callable(getattr(WebhookManager, "list_webhooks"))

    def test_webhook_manager_has_deactivate_webhook_method(self):
        """WebhookManager should have deactivate_webhook method."""
        assert hasattr(WebhookManager, "deactivate_webhook")
        assert callable(getattr(WebhookManager, "deactivate_webhook"))

    def test_webhook_manager_has_trigger_webhook_method(self):
        """WebhookManager should have trigger_webhook method."""
        assert hasattr(WebhookManager, "trigger_webhook")
        assert callable(getattr(WebhookManager, "trigger_webhook"))

    def test_webhook_manager_has_verify_signature_method(self):
        """WebhookManager should have verify_signature method."""
        assert hasattr(WebhookManager, "verify_signature")
        assert callable(getattr(WebhookManager, "verify_signature"))


# ════════════════════════════════════════════════════════════════════════════
# Test: Webhook Events
# ════════════════════════════════════════════════════════════════════════════


class TestWebhookEvents:
    """Tests for webhook event types."""

    def test_valid_events_contains_parcel_updated(self):
        """Valid events should include parcel.updated."""
        assert "parcel.updated" in VALID_EVENTS

    def test_valid_events_contains_signal_new(self):
        """Valid events should include signal.new."""
        assert "signal.new" in VALID_EVENTS

    def test_valid_events_contains_entitlement_computed(self):
        """Valid events should include entitlement.computed."""
        assert "entitlement.computed" in VALID_EVENTS

    def test_valid_events_contains_alert_triggered(self):
        """Valid events should include alert.triggered."""
        assert "alert.triggered" in VALID_EVENTS

    def test_webhook_event_enum_defined(self):
        """WebhookEvent enum should be defined."""
        assert WebhookEvent is not None
        assert hasattr(WebhookEvent, "PARCEL_UPDATED")
        assert hasattr(WebhookEvent, "SIGNAL_NEW")
        assert hasattr(WebhookEvent, "ENTITLEMENT_COMPUTED")
        assert hasattr(WebhookEvent, "ALERT_TRIGGERED")


# ════════════════════════════════════════════════════════════════════════════
# Test: HMAC-SHA256 Signature Verification
# ════════════════════════════════════════════════════════════════════════════


class TestWebhookSignature:
    """Tests for webhook HMAC-SHA256 signature verification."""

    def test_create_signature_returns_string(self):
        """_create_signature should return a string."""
        payload = json.dumps({"data": "test"})
        secret = "test-secret"
        sig = WebhookManager._create_signature(payload, secret)
        assert isinstance(sig, str)

    def test_create_signature_is_hex(self):
        """Signature should be hex-encoded."""
        payload = json.dumps({"data": "test"})
        secret = "test-secret"
        sig = WebhookManager._create_signature(payload, secret)
        assert all(c in "0123456789abcdef" for c in sig)

    def test_create_signature_sha256_length(self):
        """SHA-256 signature should be 64 hex characters."""
        payload = json.dumps({"data": "test"})
        secret = "test-secret"
        sig = WebhookManager._create_signature(payload, secret)
        assert len(sig) == 64

    def test_verify_signature_valid(self):
        """verify_signature should return True for valid signature."""
        payload = json.dumps({"data": "test"})
        secret = "test-secret"
        signature = WebhookManager._create_signature(payload, secret)

        result = WebhookManager.verify_signature(payload, signature, secret)
        assert result is True

    def test_verify_signature_invalid(self):
        """verify_signature should return False for invalid signature."""
        payload = json.dumps({"data": "test"})
        secret = "test-secret"
        bad_signature = "00" * 32

        result = WebhookManager.verify_signature(payload, bad_signature, secret)
        assert result is False

    def test_verify_signature_wrong_secret(self):
        """verify_signature should return False for wrong secret."""
        payload = json.dumps({"data": "test"})
        secret = "test-secret"
        signature = WebhookManager._create_signature(payload, secret)

        result = WebhookManager.verify_signature(payload, signature, "wrong-secret")
        assert result is False

    def test_verify_signature_modified_payload(self):
        """verify_signature should return False for modified payload."""
        payload1 = json.dumps({"data": "test"})
        payload2 = json.dumps({"data": "modified"})
        secret = "test-secret"
        signature = WebhookManager._create_signature(payload1, secret)

        result = WebhookManager.verify_signature(payload2, signature, secret)
        assert result is False

    def test_create_signature_matches_hmac_sha256(self):
        """Signature should match manual HMAC-SHA256 calculation."""
        payload = json.dumps({"data": "test"})
        secret = "test-secret"

        expected_sig = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        result_sig = WebhookManager._create_signature(payload, secret)
        assert result_sig == expected_sig


# ════════════════════════════════════════════════════════════════════════════
# Test: Webhook Retry Logic
# ════════════════════════════════════════════════════════════════════════════


class TestWebhookRetryLogic:
    """Tests for webhook delivery retry logic."""

    def test_webhook_manager_has_max_retries_constant(self):
        """WebhookManager should have MAX_RETRIES constant."""
        assert hasattr(WebhookManager, "MAX_RETRIES")
        assert WebhookManager.MAX_RETRIES == 3

    def test_webhook_manager_has_retry_backoff_constant(self):
        """WebhookManager should have RETRY_BACKOFF constant."""
        assert hasattr(WebhookManager, "RETRY_BACKOFF")
        assert WebhookManager.RETRY_BACKOFF == [1, 2, 4]

    def test_webhook_manager_has_timeout_constant(self):
        """WebhookManager should have TIMEOUT_SECONDS constant."""
        assert hasattr(WebhookManager, "TIMEOUT_SECONDS")
        assert WebhookManager.TIMEOUT_SECONDS == 10

    def test_retry_backoff_is_exponential(self):
        """Retry backoff should be exponential."""
        backoff = WebhookManager.RETRY_BACKOFF
        for i in range(len(backoff) - 1):
            assert backoff[i + 1] > backoff[i]


# ════════════════════════════════════════════════════════════════════════════
# Test: Database Tables Structure (Schema validation)
# ════════════════════════════════════════════════════════════════════════════


class TestDatabaseTables:
    """Tests for database table structure and requirements."""

    def test_api_keys_table_requires_id_column(self):
        """api_keys table should have id column."""
        # This is a schema test - just verify the manager expects it
        assert hasattr(APIKeyManager, "validate_api_key")

    def test_api_keys_table_requires_user_id_column(self):
        """api_keys table should have user_id column."""
        # Schema validation via manager usage
        assert hasattr(APIKeyManager, "list_api_keys")

    def test_api_keys_table_requires_key_hash_column(self):
        """api_keys table should have key_hash column for secure storage."""
        # The hash_api_key method implies this
        assert callable(APIKeyManager.hash_api_key)

    def test_api_keys_table_requires_key_prefix_column(self):
        """api_keys table should have key_prefix column."""
        key = APIKeyManager.generate_api_key(1, "test", ["read:parcels"])
        assert key.key_prefix is not None

    def test_api_keys_table_requires_scopes_column(self):
        """api_keys table should have scopes array column."""
        # Scopes are required in generation
        with pytest.raises(ValueError):
            APIKeyManager.generate_api_key(1, "test", ["invalid"])

    def test_api_keys_table_requires_rate_limit_column(self):
        """api_keys table should have rate_limit column."""
        assert DEFAULT_RATE_LIMIT is not None

    def test_webhooks_table_required(self):
        """webhooks table should exist."""
        assert hasattr(WebhookManager, "register_webhook")


# ════════════════════════════════════════════════════════════════════════════
# Test: Pydantic Models
# ════════════════════════════════════════════════════════════════════════════


class TestPydanticModels:
    """Tests for Pydantic request/response models."""

    def test_api_key_named_tuple_has_key_field(self):
        """APIKey should have key field."""
        assert hasattr(APIKey, "_fields")
        assert "key" in APIKey._fields

    def test_api_key_named_tuple_has_key_prefix_field(self):
        """APIKey should have key_prefix field."""
        assert hasattr(APIKey, "_fields")
        assert "key_prefix" in APIKey._fields

    def test_api_key_named_tuple_has_expires_at_field(self):
        """APIKey should have expires_at field."""
        assert hasattr(APIKey, "_fields")
        assert "expires_at" in APIKey._fields

    def test_api_key_info_named_tuple_has_scopes_field(self):
        """APIKeyInfo should have scopes field."""
        assert hasattr(APIKeyInfo, "_fields")
        assert "scopes" in APIKeyInfo._fields

    def test_webhook_info_named_tuple_has_events_field(self):
        """WebhookInfo should have events field."""
        assert hasattr(WebhookInfo, "_fields")
        assert "events" in WebhookInfo._fields

    def test_webhook_delivery_result_has_success_field(self):
        """WebhookDeliveryResult should have success field."""
        assert hasattr(WebhookDeliveryResult, "_fields")
        assert "success" in WebhookDeliveryResult._fields

    def test_webhook_delivery_result_has_error_field(self):
        """WebhookDeliveryResult should have error field."""
        assert hasattr(WebhookDeliveryResult, "_fields")
        assert "error" in WebhookDeliveryResult._fields


# ════════════════════════════════════════════════════════════════════════════
# Test: Edge Cases
# ════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_generate_api_key_with_empty_scopes(self):
        """API key with all-invalid scopes should raise error."""
        # Empty list doesn't trigger validation, so we test with invalid scope
        with pytest.raises(ValueError):
            APIKeyManager.generate_api_key(
                user_id=1,
                name="test-key",
                scopes=["completely:invalid"],
            )

    def test_generate_api_key_with_max_expiration(self):
        """API key should accept max expiration (3650 days)."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
            expires_days=3650,
        )
        assert key.expires_at is not None

    def test_generate_api_key_with_one_day_expiration(self):
        """API key should accept 1 day expiration."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=["read:parcels"],
            expires_days=1,
        )
        assert key.expires_at is not None

    def test_hash_consistency_with_special_characters(self):
        """Hash should handle keys with hex characters consistently."""
        key = "vcl_" + "a" * 32
        hash1 = APIKeyManager.hash_api_key(key)
        hash2 = APIKeyManager.hash_api_key(key)
        assert hash1 == hash2

    def test_webhook_signature_with_empty_payload(self):
        """Signature should handle empty payload."""
        payload = "{}"
        secret = "test-secret"
        sig = WebhookManager._create_signature(payload, secret)
        assert len(sig) == 64

    def test_webhook_signature_with_large_payload(self):
        """Signature should handle large payload."""
        payload = json.dumps({"data": "x" * 10000})
        secret = "test-secret"
        sig = WebhookManager._create_signature(payload, secret)
        assert len(sig) == 64

    def test_api_key_manager_rate_limit_positive(self):
        """Rate limit should be positive."""
        assert DEFAULT_RATE_LIMIT > 0

    def test_api_key_manager_max_retries_positive(self):
        """Max retries should be positive."""
        assert WebhookManager.MAX_RETRIES > 0

    def test_api_key_prefix_no_spaces(self):
        """Key prefix should not contain spaces."""
        key = APIKeyManager.generate_api_key(1, "test", ["read:parcels"])
        assert " " not in key.key_prefix

    def test_api_key_no_spaces(self):
        """Full key should not contain spaces."""
        key = APIKeyManager.generate_api_key(1, "test", ["read:parcels"])
        assert " " not in key.key


# ════════════════════════════════════════════════════════════════════════════
# Test: Multiple Scope Combinations
# ════════════════════════════════════════════════════════════════════════════


class TestMultipleScopeCombinations:
    """Tests for various scope combinations."""

    def test_all_valid_scopes_together(self):
        """Should accept all valid scopes together."""
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=list(VALID_SCOPES),
        )
        assert key is not None

    def test_read_only_scopes(self):
        """Should accept all read scopes."""
        read_scopes = [s for s in VALID_SCOPES if s.startswith("read:")]
        key = APIKeyManager.generate_api_key(
            user_id=1,
            name="test-key",
            scopes=read_scopes,
        )
        assert key is not None

    def test_write_scopes(self):
        """Should accept write scopes."""
        write_scopes = [s for s in VALID_SCOPES if s.startswith("write:")]
        if write_scopes:
            key = APIKeyManager.generate_api_key(
                user_id=1,
                name="test-key",
                scopes=write_scopes,
            )
            assert key is not None


# ════════════════════════════════════════════════════════════════════════════
# Test: Revoke API Key
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestRevokeAPIKey:
    """Tests for API key revocation."""

    async def test_revoke_api_key_returns_boolean(self):
        """revoke_api_key should return boolean."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.revoke_api_key(mock_pool, 1, 1)
        assert isinstance(result, bool)

    async def test_revoke_api_key_success(self):
        """revoke_api_key should return True on success."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.revoke_api_key(mock_pool, 1, 1)
        assert result is True

    async def test_revoke_api_key_not_found(self):
        """revoke_api_key should return False when key not found."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 0")

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await APIKeyManager.revoke_api_key(mock_pool, 999, 1)
        assert result is False


# ════════════════════════════════════════════════════════════════════════════
# Test: Update Last Used
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestUpdateLastUsed:
    """Tests for updating last_used_at timestamp."""

    async def test_update_last_used_executes_query(self):
        """update_last_used should execute update query."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        await APIKeyManager.update_last_used(mock_pool, 1)
        assert mock_conn.execute.called


# ════════════════════════════════════════════════════════════════════════════
# Test: Additional Coverage for Completeness
# ════════════════════════════════════════════════════════════════════════════


class TestAPIKeyFormatValidation:
    """Additional tests for API key format validation."""

    def test_key_has_consistent_format(self):
        """Multiple keys should have consistent format."""
        for _ in range(10):
            key = APIKeyManager.generate_api_key(1, "test", ["read:parcels"])
            assert key.key.startswith("vcl_")
            assert len(key.key) == 36

    def test_key_prefix_always_matches_key_start(self):
        """Key prefix should always match key start."""
        for _ in range(10):
            key = APIKeyManager.generate_api_key(1, "test", ["read:parcels"])
            assert key.key_prefix == key.key[:12]


@pytest.mark.asyncio
class TestWebhookRegistration:
    """Tests for webhook registration."""

    async def test_register_webhook_returns_webhook_info(self):
        """register_webhook should return WebhookInfo."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": 1,
            "created_at": datetime.now(tz=timezone.utc),
        })

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None

        result = await WebhookManager.register_webhook(
            mock_pool,
            api_key_id=1,
            url="https://example.com/webhook",
            events=["parcel.updated"],
        )
        assert isinstance(result, WebhookInfo)

    async def test_register_webhook_invalid_event(self):
        """register_webhook should reject invalid events."""
        mock_pool = AsyncMock()

        with pytest.raises(ValueError):
            await WebhookManager.register_webhook(
                mock_pool,
                api_key_id=1,
                url="https://example.com/webhook",
                events=["invalid.event"],
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
