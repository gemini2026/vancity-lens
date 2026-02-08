"""
VanCity Lens — User Authentication Tests (VCL-74 / BIZ-001)

Comprehensive test suite for user registration, login, JWT tokens, API keys,
and role-based access control.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import jwt
import asyncpg

from api.user_auth import (
    UserCreate,
    UserLogin,
    TokenResponse,
    APIKeyCreate,
    hash_password,
    verify_password,
    validate_token,
    register_user,
    authenticate,
    refresh_access_token,
    deactivate_user,
    get_user_by_id,
    create_api_key,
    validate_api_key,
    revoke_api_key,
    list_user_api_keys,
    _get_current_user_impl,
    require_role,
    _create_jwt,
    _generate_api_key,
    _hash_api_key,
    JWT_SECRET,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from fastapi.testclient import TestClient
from fastapi import FastAPI, Depends, HTTPException


# ────────────────────────────────────────────────────────────────────────────
# Password Hashing Tests
# ────────────────────────────────────────────────────────────────────────────

class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password_returns_string(self):
        """Hash function should return a string."""
        hashed = hash_password("mypassword123")
        assert isinstance(hashed, str)
        assert len(hashed) > 20  # bcrypt hashes are long

    def test_hash_different_passwords_produces_different_hashes(self):
        """Same password hashed twice should produce different results (salt)."""
        password = "mypassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # Different salts

    def test_verify_password_succeeds_with_correct_password(self):
        """Verification should succeed with correct password."""
        password = "mypassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_fails_with_wrong_password(self):
        """Verification should fail with wrong password."""
        password = "mypassword123"
        hashed = hash_password(password)
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_fails_with_empty_password(self):
        """Verification should fail with empty password."""
        hashed = hash_password("mypassword123")
        assert verify_password("", hashed) is False


# ────────────────────────────────────────────────────────────────────────────
# JWT Token Tests
# ────────────────────────────────────────────────────────────────────────────

class TestJWTTokens:
    """Test JWT token creation and validation."""

    def test_create_access_token_returns_token_and_expiry(self):
        """Access token creation should return token and expiry in seconds."""
        token, expires_in = _create_jwt(user_id=123, token_type="access")
        assert isinstance(token, str)
        assert isinstance(expires_in, int)
        assert expires_in > 0
        assert expires_in == ACCESS_TOKEN_EXPIRE_MINUTES * 60

    def test_create_refresh_token_returns_token_and_expiry(self):
        """Refresh token creation should return token and longer expiry."""
        token, expires_in = _create_jwt(user_id=123, token_type="refresh")
        assert isinstance(token, str)
        assert isinstance(expires_in, int)
        assert expires_in > 0
        assert expires_in == REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600

    def test_create_token_with_invalid_type_raises_error(self):
        """Creating token with invalid type should raise ValueError."""
        with pytest.raises(ValueError):
            _create_jwt(user_id=123, token_type="invalid")

    def test_validate_token_extracts_user_id(self):
        """Validating a token should extract the user ID."""
        user_id = 456
        token, _ = _create_jwt(user_id=user_id, token_type="access")
        validated_user_id = validate_token(token)
        assert validated_user_id == user_id

    def test_validate_token_returns_none_for_invalid_token(self):
        """Validating invalid token should return None."""
        assert validate_token("invalid.token.here") is None

    def test_validate_token_returns_none_for_expired_token(self):
        """Validating expired token should return None."""
        # Create an expired token
        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": "123",
            "type": "access",
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),  # Expired
        }
        expired_token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        assert validate_token(expired_token) is None

    def test_validate_token_returns_none_for_wrong_secret(self):
        """Validating token with wrong secret should return None."""
        token, _ = _create_jwt(user_id=123, token_type="access")
        # Tamper with token
        with patch('api.user_auth.JWT_SECRET', 'wrong-secret'):
            # Token is invalid because it was signed with different secret
            assert validate_token(token) is None

    def test_jwt_token_contains_correct_claims(self):
        """JWT token should contain correct claims."""
        user_id = 789
        token, _ = _create_jwt(user_id=user_id, token_type="access")
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        assert decoded["sub"] == str(user_id)
        assert decoded["type"] == "access"
        assert "iat" in decoded
        assert "exp" in decoded


# ────────────────────────────────────────────────────────────────────────────
# User Registration Tests
# ────────────────────────────────────────────────────────────────────────────

class TestUserRegistration:
    """Test user registration."""

    @pytest.mark.asyncio
    async def test_register_user_success(self, mock_db_pool):
        """Successful user registration should create user in database."""
        user_data = {
            "id": 1,
            "email": "test@example.com",
            "display_name": "Test User",
            "role": "user",
            "is_active": True,
            "created_at": datetime.now(tz=timezone.utc),
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = user_data
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await register_user(
            mock_db_pool,
            email="test@example.com",
            password="securepass123",
            display_name="Test User",
        )

        assert result["id"] == 1
        assert result["email"] == "test@example.com"
        assert result["display_name"] == "Test User"
        assert result["role"] == "user"
        assert result["is_active"] is True

    @pytest.mark.asyncio
    async def test_register_user_weak_password_raises_error(self, mock_db_pool):
        """Weak password should raise ValueError."""
        with pytest.raises(ValueError, match="at least 8 characters"):
            await register_user(
                mock_db_pool,
                email="test@example.com",
                password="short",  # Too short
                display_name="Test User",
            )

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises_error(self, mock_db_pool):
        """Duplicate email should raise ValueError."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.side_effect = asyncpg.UniqueViolationError("duplicate")
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with pytest.raises(ValueError, match="already exists"):
            await register_user(
                mock_db_pool,
                email="duplicate@example.com",
                password="securepass123",
            )

    @pytest.mark.asyncio
    async def test_register_user_without_display_name(self, mock_db_pool):
        """Registration without display name should work."""
        user_data = {
            "id": 1,
            "email": "test@example.com",
            "display_name": None,
            "role": "user",
            "is_active": True,
            "created_at": datetime.now(tz=timezone.utc),
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = user_data
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await register_user(
            mock_db_pool,
            email="test@example.com",
            password="securepass123",
        )

        assert result["display_name"] is None


# ────────────────────────────────────────────────────────────────────────────
# User Authentication Tests
# ────────────────────────────────────────────────────────────────────────────

class TestUserAuthentication:
    """Test user authentication (login)."""

    @pytest.mark.asyncio
    async def test_authenticate_with_correct_credentials(self, mock_db_pool):
        """Authentication with correct credentials should return tokens."""
        password = "securepass123"
        password_hash = hash_password(password)
        user_data = {
            "id": 1,
            "password_hash": password_hash,
            "is_active": True,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = user_data
        mock_conn.execute.return_value = "UPDATE 1"  # last_login_at update
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await authenticate(
            mock_db_pool,
            email="test@example.com",
            password=password,
        )

        assert "access_token" in result
        assert "refresh_token" in result
        assert result["expires_in"] > 0
        # Tokens should be JWTs (contain two dots)
        assert result["access_token"].count(".") == 2
        assert result["refresh_token"].count(".") == 2

    @pytest.mark.asyncio
    async def test_authenticate_with_wrong_password_raises_error(self, mock_db_pool):
        """Authentication with wrong password should raise HTTPException."""
        password = "securepass123"
        password_hash = hash_password(password)
        user_data = {
            "id": 1,
            "password_hash": password_hash,
            "is_active": True,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = user_data
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await authenticate(
                mock_db_pool,
                email="test@example.com",
                password="wrongpassword",
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticate_nonexistent_user_raises_error(self, mock_db_pool):
        """Authentication with nonexistent user should raise HTTPException."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await authenticate(
                mock_db_pool,
                email="nonexistent@example.com",
                password="anypassword",
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticate_inactive_user_raises_error(self, mock_db_pool):
        """Authentication with inactive user should raise HTTPException."""
        password = "securepass123"
        password_hash = hash_password(password)
        user_data = {
            "id": 1,
            "password_hash": password_hash,
            "is_active": False,  # Inactive
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = user_data
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await authenticate(
                mock_db_pool,
                email="test@example.com",
                password=password,
            )
        assert exc_info.value.status_code == 403


# ────────────────────────────────────────────────────────────────────────────
# Token Refresh Tests
# ────────────────────────────────────────────────────────────────────────────

class TestTokenRefresh:
    """Test access token refresh."""

    @pytest.mark.asyncio
    async def test_refresh_token_with_valid_refresh_token(self):
        """Refreshing with valid refresh token should return new access token."""
        user_id = 123
        refresh_token, _ = _create_jwt(user_id=user_id, token_type="refresh")

        result = await refresh_access_token(refresh_token)

        assert "access_token" in result
        assert result["expires_in"] > 0
        assert result["access_token"].count(".") == 2

    @pytest.mark.asyncio
    async def test_refresh_token_with_invalid_token_raises_error(self):
        """Refreshing with invalid token should raise HTTPException."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await refresh_access_token("invalid.token.here")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_with_access_token_raises_error(self):
        """Refreshing with access token (not refresh token) should raise error."""
        user_id = 123
        access_token, _ = _create_jwt(user_id=user_id, token_type="access")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await refresh_access_token(access_token)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_returns_valid_access_token(self):
        """Returned access token from refresh should be valid."""
        user_id = 456
        refresh_token, _ = _create_jwt(user_id=user_id, token_type="refresh")

        result = await refresh_access_token(refresh_token)
        new_user_id = validate_token(result["access_token"])

        assert new_user_id == user_id


# ────────────────────────────────────────────────────────────────────────────
# API Key Management Tests
# ────────────────────────────────────────────────────────────────────────────

class TestAPIKeyGeneration:
    """Test API key generation and hashing."""

    def test_generate_api_key_returns_string(self):
        """Generated API key should be a non-empty string."""
        key = _generate_api_key()
        assert isinstance(key, str)
        assert len(key) > 20

    def test_generate_api_key_produces_different_keys(self):
        """Different calls should produce different keys."""
        key1 = _generate_api_key()
        key2 = _generate_api_key()
        assert key1 != key2

    def test_hash_api_key_returns_string(self):
        """Hashed API key should be a string."""
        key = _generate_api_key()
        hashed = _hash_api_key(key)
        assert isinstance(hashed, str)
        assert len(hashed) > 20

    def test_hash_api_key_is_one_way(self):
        """Hashed key should not be reversible."""
        key = _generate_api_key()
        hashed = _hash_api_key(key)
        assert hashed != key
        # Should not contain parts of original key
        assert key[:10] not in hashed


class TestAPIKeyCreation:
    """Test API key creation in database."""

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, mock_db_pool):
        """Creating API key should return key data with full key."""
        key_data = {
            "id": 1,
            "created_at": datetime.now(tz=timezone.utc),
            "expires_at": None,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = key_data
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await create_api_key(
            mock_db_pool,
            user_id=123,
            label="My API Key",
            permissions=["read", "write"],
        )

        assert result["id"] == 1
        assert result["label"] == "My API Key"
        assert result["permissions"] == ["read", "write"]
        assert "key" in result
        assert len(result["key"]) > 20
        assert result["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_api_key_with_expiry(self, mock_db_pool):
        """Creating API key with expiry should set expires_at."""
        expires_at = datetime.now(tz=timezone.utc) + timedelta(days=30)
        key_data = {
            "id": 1,
            "created_at": datetime.now(tz=timezone.utc),
            "expires_at": expires_at,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = key_data
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await create_api_key(
            mock_db_pool,
            user_id=123,
            label="Expiring Key",
            permissions=["read"],
            expires_days=30,
        )

        assert result["expires_at"] is not None


class TestAPIKeyValidation:
    """Test API key validation."""

    @pytest.mark.asyncio
    async def test_validate_api_key_with_valid_key(self, mock_db_pool):
        """Validating valid API key should return user_id and permissions."""
        key = _generate_api_key()
        key_hash = _hash_api_key(key)
        key_data = {
            "id": 1,
            "user_id": 123,
            "key_hash": key_hash,
            "permissions": ["read"],
            "expires_at": None,
            "last_used_at": None,
        }
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [key_data]
        mock_conn.execute.return_value = "UPDATE 1"  # last_used_at update
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await validate_api_key(mock_db_pool, key)

        assert result is not None
        assert result["user_id"] == 123
        assert result["permissions"] == ["read"]

    @pytest.mark.asyncio
    async def test_validate_api_key_with_invalid_key(self, mock_db_pool):
        """Validating invalid key should return None."""
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await validate_api_key(mock_db_pool, "invalid_key_here")

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_expired_api_key_returns_none(self, mock_db_pool):
        """Validating expired API key should return None."""
        key = _generate_api_key()
        key_hash = _hash_api_key(key)
        past_time = datetime.now(tz=timezone.utc) - timedelta(days=1)
        key_data = {
            "id": 1,
            "user_id": 123,
            "key_hash": key_hash,
            "permissions": ["read"],
            "expires_at": past_time,  # Expired
            "last_used_at": None,
        }
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [key_data]
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await validate_api_key(mock_db_pool, key)

        assert result is None


class TestAPIKeyRevocation:
    """Test API key revocation."""

    @pytest.mark.asyncio
    async def test_revoke_api_key_success(self, mock_db_pool):
        """Revoking own API key should succeed."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 123  # user_id from key
        mock_conn.execute.return_value = "UPDATE 1"
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await revoke_api_key(mock_db_pool, key_id=1, user_id=123)

        assert result is True

    @pytest.mark.asyncio
    async def test_revoke_api_key_unauthorized_fails(self, mock_db_pool):
        """Revoking someone else's key should fail."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 456  # Different user
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await revoke_api_key(mock_db_pool, key_id=1, user_id=123)

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_api_key_fails(self, mock_db_pool):
        """Revoking nonexistent key should fail."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = None
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await revoke_api_key(mock_db_pool, key_id=999, user_id=123)

        assert result is False


# ────────────────────────────────────────────────────────────────────────────
# User Profile Tests
# ────────────────────────────────────────────────────────────────────────────

class TestUserProfile:
    """Test user profile retrieval."""

    @pytest.mark.asyncio
    async def test_get_user_by_id_success(self, mock_db_pool):
        """Getting user by ID should return user data."""
        user_data = {
            "id": 1,
            "email": "test@example.com",
            "display_name": "Test User",
            "role": "user",
            "is_active": True,
            "created_at": datetime.now(tz=timezone.utc),
            "last_login_at": None,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = user_data
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await get_user_by_id(mock_db_pool, 1)

        assert result is not None
        assert result["id"] == 1
        assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_by_id_nonexistent(self, mock_db_pool):
        """Getting nonexistent user should return None."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await get_user_by_id(mock_db_pool, 999)

        assert result is None


# ────────────────────────────────────────────────────────────────────────────
# User Deactivation Tests
# ────────────────────────────────────────────────────────────────────────────

class TestUserDeactivation:
    """Test user account deactivation."""

    @pytest.mark.asyncio
    async def test_deactivate_user_success(self, mock_db_pool):
        """Deactivating user should return True."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "UPDATE 1"
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await deactivate_user(mock_db_pool, 1)

        assert result is True

    @pytest.mark.asyncio
    async def test_deactivate_nonexistent_user_fails(self, mock_db_pool):
        """Deactivating nonexistent user should return False."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "UPDATE 0"
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await deactivate_user(mock_db_pool, 999)

        assert result is False


# ────────────────────────────────────────────────────────────────────────────
# API Keys Listing Tests
# ────────────────────────────────────────────────────────────────────────────

class TestListAPIKeys:
    """Test listing user's API keys."""

    @pytest.mark.asyncio
    async def test_list_user_api_keys(self, mock_db_pool):
        """Listing API keys should return all user keys without full key."""
        keys = [
            {
                "id": 1,
                "label": "Key 1",
                "permissions": ["read"],
                "created_at": datetime.now(tz=timezone.utc),
                "expires_at": None,
                "last_used_at": None,
                "is_active": True,
            },
            {
                "id": 2,
                "label": "Key 2",
                "permissions": ["read", "write"],
                "created_at": datetime.now(tz=timezone.utc),
                "expires_at": None,
                "last_used_at": None,
                "is_active": True,
            },
        ]
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = keys
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await list_user_api_keys(mock_db_pool, 123)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        # Should not include full key
        assert "key" not in result[0]

    @pytest.mark.asyncio
    async def test_list_user_api_keys_empty(self, mock_db_pool):
        """Listing API keys for user without keys should return empty list."""
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await list_user_api_keys(mock_db_pool, 123)

        assert result == []


# ────────────────────────────────────────────────────────────────────────────
# FastAPI Dependency Tests
# ────────────────────────────────────────────────────────────────────────────

class TestFastAPIDependencies:
    """Test FastAPI dependencies for authentication."""

    @pytest.mark.asyncio
    async def test_get_current_user_with_valid_token(self, mock_db_pool):
        """get_current_user should extract user from valid JWT."""
        from fastapi.security import HTTPAuthorizationCredentials

        user_id = 123
        token, _ = _create_jwt(user_id=user_id, token_type="access")
        credentials = HTTPAuthorizationCredentials(scheme="bearer", credentials=token)

        user_data = {
            "id": user_id,
            "email": "test@example.com",
            "display_name": "Test User",
            "role": "user",
            "is_active": True,
            "created_at": datetime.now(tz=timezone.utc),
            "last_login_at": None,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = user_data
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await _get_current_user_impl(mock_db_pool, credentials)

        assert result["id"] == user_id
        assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_current_user_missing_credentials_raises_error(self, mock_db_pool):
        """get_current_user should raise error without credentials."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await _get_current_user_impl(mock_db_pool, credentials=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token_raises_error(self, mock_db_pool):
        """get_current_user should raise error with invalid token."""
        from fastapi.security import HTTPAuthorizationCredentials
        from fastapi import HTTPException

        credentials = HTTPAuthorizationCredentials(scheme="bearer", credentials="invalid.token.here")

        with pytest.raises(HTTPException) as exc_info:
            await _get_current_user_impl(mock_db_pool, credentials)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_inactive_user_raises_error(self, mock_db_pool):
        """get_current_user should raise error for inactive user."""
        from fastapi.security import HTTPAuthorizationCredentials
        from fastapi import HTTPException

        user_id = 123
        token, _ = _create_jwt(user_id=user_id, token_type="access")
        credentials = HTTPAuthorizationCredentials(scheme="bearer", credentials=token)

        user_data = {
            "id": user_id,
            "email": "test@example.com",
            "display_name": "Test User",
            "role": "user",
            "is_active": False,  # Inactive
            "created_at": datetime.now(tz=timezone.utc),
            "last_login_at": None,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = user_data
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with pytest.raises(HTTPException) as exc_info:
            await _get_current_user_impl(mock_db_pool, credentials)
        assert exc_info.value.status_code == 403

    def test_require_role_dependency_factory(self):
        """require_role should return a callable dependency."""
        dependency = require_role("admin")
        assert callable(dependency)


# ────────────────────────────────────────────────────────────────────────────
# Integration Tests with FastAPI
# ────────────────────────────────────────────────────────────────────────────

class TestAuthRoutes:
    """Test authentication routes integration."""

    def test_auth_routes_registered(self):
        """Authentication routes should be registered in the app."""
        from api.auth_routes import router
        assert router.prefix == "/api/v1/auth"
        assert "authentication" in router.tags


# ────────────────────────────────────────────────────────────────────────────
# Edge Cases and Error Handling
# ────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_hash_password_handles_special_characters(self):
        """Password hashing should handle special characters."""
        password = "p@$$w0rd!#%&*()[]{}|;:<>?,./"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_hash_password_handles_unicode(self):
        """Password hashing should handle unicode characters."""
        password = "pässwörd123!😀"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_api_key_hashing_handles_special_characters(self):
        """API key hashing should handle special characters in generated keys."""
        key = _generate_api_key()
        hashed = _hash_api_key(key)
        # Should be different
        assert hashed != key
        # Should be hashable
        assert isinstance(hashed, str)

    @pytest.mark.asyncio
    async def test_create_jwt_token_with_large_user_id(self):
        """JWT creation should handle large user IDs."""
        large_user_id = 9999999999
        token, _ = _create_jwt(user_id=large_user_id, token_type="access")
        validated_id = validate_token(token)
        assert validated_id == large_user_id

    @pytest.mark.asyncio
    async def test_register_user_email_case_sensitivity(self, mock_db_pool):
        """Email should be treated as-is (case sensitivity depends on DB)."""
        user_data = {
            "id": 1,
            "email": "Test@Example.com",
            "display_name": None,
            "role": "user",
            "is_active": True,
            "created_at": datetime.now(tz=timezone.utc),
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = user_data
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await register_user(
            mock_db_pool,
            email="Test@Example.com",
            password="securepass123",
        )

        assert result["email"] == "Test@Example.com"
