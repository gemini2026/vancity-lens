"""
VanCity Lens — API Key Management (VCL-108 / BIZ-010)

Third-party integration API keys with secure hashing, scopes, and rate limiting.
"""

import logging
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, List, NamedTuple

import asyncpg

logger = logging.getLogger(__name__)


class APIKey(NamedTuple):
    """Generated API key with metadata."""

    key: str
    key_prefix: str
    expires_at: Optional[datetime]


class APIKeyInfo(NamedTuple):
    """API key information for display."""

    id: int
    user_id: int
    name: str
    key_prefix: str
    scopes: List[str]
    rate_limit: int
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]


# Valid scopes for third-party integrations
VALID_SCOPES = {
    "read:parcels",
    "read:entitlements",
    "read:signals",
    "read:neighborhoods",
    "write:webhooks",
}

# Default rate limit: 100 requests per minute
DEFAULT_RATE_LIMIT = 100


class APIKeyManager:
    """Manages API keys for third-party integrations."""

    @staticmethod
    def generate_api_key(
        user_id: int,
        name: str,
        scopes: List[str],
        rate_limit: int = DEFAULT_RATE_LIMIT,
        expires_days: Optional[int] = None,
    ) -> APIKey:
        """
        Generate a new API key for a user.

        Args:
            user_id: The user ID
            name: Name/label for the key
            scopes: List of scopes (read:parcels, read:entitlements, etc.)
            rate_limit: Requests per minute (default: 100)
            expires_days: Days until key expires (None = never)

        Returns:
            APIKey with raw key (for one-time return to user)
        """
        # Validate scopes
        invalid_scopes = set(scopes) - VALID_SCOPES
        if invalid_scopes:
            raise ValueError(f"Invalid scopes: {invalid_scopes}")

        # Generate random key: "vcl_" + 32 hex chars
        random_bytes = secrets.token_bytes(16)  # 16 bytes = 32 hex chars
        raw_key = "vcl_" + random_bytes.hex()

        # Calculate expiration
        expires_at = None
        if expires_days:
            expires_at = datetime.now(tz=timezone.utc) + timedelta(days=expires_days)

        return APIKey(
            key=raw_key,
            key_prefix=raw_key[:12],  # "vcl_" + 8 hex chars
            expires_at=expires_at,
        )

    @staticmethod
    def hash_api_key(key: str) -> str:
        """
        Hash an API key using SHA-256.

        Args:
            key: The raw API key

        Returns:
            SHA-256 hash of the key
        """
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    async def validate_api_key(pool: asyncpg.Pool, key: str) -> Optional[APIKeyInfo]:
        """
        Validate and retrieve API key information.

        Args:
            pool: Database connection pool
            key: The API key to validate

        Returns:
            APIKeyInfo if valid and not expired/revoked, None otherwise
        """
        key_hash = APIKeyManager.hash_api_key(key)
        key_prefix = key[:12]

        async with pool.acquire() as conn:
            record = await conn.fetchrow(
                """
                SELECT
                    id, user_id, name, key_prefix, scopes, rate_limit,
                    created_at, expires_at, last_used_at, revoked_at
                FROM api_keys
                WHERE key_hash = $1 AND key_prefix = $2
                """,
                key_hash,
                key_prefix,
            )

        if not record:
            return None

        # Check if revoked
        if record["revoked_at"] is not None:
            return None

        # Check if expired
        now = datetime.now(tz=timezone.utc)
        if record["expires_at"] and record["expires_at"] < now:
            return None

        return APIKeyInfo(
            id=record["id"],
            user_id=record["user_id"],
            name=record["name"],
            key_prefix=record["key_prefix"],
            scopes=record["scopes"],
            rate_limit=record["rate_limit"],
            created_at=record["created_at"],
            expires_at=record["expires_at"],
            last_used_at=record["last_used_at"],
            revoked_at=record["revoked_at"],
        )

    @staticmethod
    async def revoke_api_key(pool: asyncpg.Pool, key_id: int, user_id: int) -> bool:
        """
        Revoke an API key.

        Args:
            pool: Database connection pool
            key_id: The API key ID
            user_id: The user ID (must own the key)

        Returns:
            True if revoked, False if not found or not owned by user
        """
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE api_keys
                SET revoked_at = $1
                WHERE id = $2 AND user_id = $3 AND revoked_at IS NULL
                """,
                datetime.now(tz=timezone.utc),
                key_id,
                user_id,
            )

        return result == "UPDATE 1"

    @staticmethod
    async def list_api_keys(pool: asyncpg.Pool, user_id: int) -> List[APIKeyInfo]:
        """
        List all API keys for a user.

        Args:
            pool: Database connection pool
            user_id: The user ID

        Returns:
            List of APIKeyInfo (never returns raw keys)
        """
        async with pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT
                    id, user_id, name, key_prefix, scopes, rate_limit,
                    created_at, expires_at, last_used_at, revoked_at
                FROM api_keys
                WHERE user_id = $1
                ORDER BY created_at DESC
                """,
                user_id,
            )

        return [
            APIKeyInfo(
                id=r["id"],
                user_id=r["user_id"],
                name=r["name"],
                key_prefix=r["key_prefix"],
                scopes=r["scopes"],
                rate_limit=r["rate_limit"],
                created_at=r["created_at"],
                expires_at=r["expires_at"],
                last_used_at=r["last_used_at"],
                revoked_at=r["revoked_at"],
            )
            for r in records
        ]

    @staticmethod
    async def rotate_api_key(
        pool: asyncpg.Pool, key_id: int, user_id: int
    ) -> Optional[APIKey]:
        """
        Rotate an API key (create new, revoke old).

        Args:
            pool: Database connection pool
            key_id: The API key ID to rotate
            user_id: The user ID (must own the key)

        Returns:
            New APIKey if successful, None otherwise
        """
        async with pool.acquire() as conn:
            # Get old key info
            old_key = await conn.fetchrow(
                """
                SELECT name, scopes, rate_limit, expires_at
                FROM api_keys
                WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL
                """,
                key_id,
                user_id,
            )

            if not old_key:
                return None

            # Calculate days until expiration for the new key
            expires_days = None
            if old_key["expires_at"]:
                now = datetime.now(tz=timezone.utc)
                expires_days = (old_key["expires_at"] - now).days

            # Generate new key
            new_key = APIKeyManager.generate_api_key(
                user_id=user_id,
                name=old_key["name"],
                scopes=old_key["scopes"],
                rate_limit=old_key["rate_limit"],
                expires_days=expires_days,
            )

            # Insert new key and revoke old one in transaction
            key_hash = APIKeyManager.hash_api_key(new_key.key)

            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO api_keys
                    (user_id, name, key_hash, key_prefix, scopes, rate_limit, created_at, expires_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    user_id,
                    old_key["name"],
                    key_hash,
                    new_key.key_prefix,
                    old_key["scopes"],
                    old_key["rate_limit"],
                    datetime.now(tz=timezone.utc),
                    new_key.expires_at,
                )

                await conn.execute(
                    """
                    UPDATE api_keys
                    SET revoked_at = $1
                    WHERE id = $2
                    """,
                    datetime.now(tz=timezone.utc),
                    key_id,
                )

            return new_key

    @staticmethod
    async def update_last_used(pool: asyncpg.Pool, key_id: int) -> None:
        """
        Update the last_used_at timestamp for an API key.

        Args:
            pool: Database connection pool
            key_id: The API key ID
        """
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE api_keys
                SET last_used_at = $1
                WHERE id = $2
                """,
                datetime.now(tz=timezone.utc),
                key_id,
            )
