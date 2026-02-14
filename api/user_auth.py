"""
VanCity Lens — User Authentication & Accounts (VCL-74 / BIZ-001)

User authentication, JWT tokens, API keys, and role-based access control.
"""

import os
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from enum import Enum

import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncpg

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    """User roles for role-based access control."""
    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"


# Read from environment variables
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is required. "
        "Set it to a strong random string (>= 32 characters)."
    )
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token scheme
bearer_scheme = HTTPBearer(auto_error=False)


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ────────────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    """Request model for user registration."""
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)


class UserLogin(BaseModel):
    """Request model for user login."""
    email: str
    password: str


class UserResponse(BaseModel):
    """Response model for user data."""
    id: int
    email: str
    display_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """JWT token pair response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class APIKeyCreate(BaseModel):
    """Request model for creating an API key."""
    label: str = Field(..., max_length=255)
    permissions: List[str] = Field(default=["read"])
    expires_days: Optional[int] = Field(None, ge=1, le=3650)


class APIKeyResponse(BaseModel):
    """Response model for API key (with masked key)."""
    id: int
    label: str
    permissions: List[str]
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    is_active: bool
    # Note: full key is only returned on creation, not on subsequent reads


class APIKeyCreateResponse(APIKeyResponse):
    """Response model for newly created API key (includes full key)."""
    key: str  # Full key - only shown once


class RefreshTokenRequest(BaseModel):
    """Request model for refreshing access token."""
    refresh_token: str


# ────────────────────────────────────────────────────────────────────────────
# Password Hashing
# ────────────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a hash."""
    return pwd_context.verify(plain_password, password_hash)


# ────────────────────────────────────────────────────────────────────────────
# JWT Token Management
# ────────────────────────────────────────────────────────────────────────────

def _create_jwt(
    user_id: int,
    token_type: str,
    expires_in_minutes: Optional[int] = None,
) -> tuple[str, int]:
    """
    Create a JWT token.

    Args:
        user_id: The user ID to encode in the token
        token_type: Either "access" or "refresh"
        expires_in_minutes: Minutes until token expires (None uses defaults)

    Returns:
        Tuple of (token, expires_in_seconds)
    """
    now = datetime.now(tz=timezone.utc)

    if token_type == "access":
        expires_in = expires_in_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
        expires_at = now + timedelta(minutes=expires_in)
        expires_in_seconds = expires_in * 60
    elif token_type == "refresh":
        expires_in = REFRESH_TOKEN_EXPIRE_DAYS
        expires_at = now + timedelta(days=expires_in)
        expires_in_seconds = expires_in * 24 * 3600
    else:
        raise ValueError(f"Invalid token_type: {token_type}")

    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token, expires_in_seconds


def validate_token(token: str) -> Optional[int]:
    """
    Validate and decode a JWT token.

    Args:
        token: The JWT token string

    Returns:
        User ID if valid, None if invalid
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload.get("sub"))
        return user_id
    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None


# ────────────────────────────────────────────────────────────────────────────
# API Key Management
# ────────────────────────────────────────────────────────────────────────────

def _generate_api_key() -> str:
    """Generate a random API key."""
    return secrets.token_urlsafe(32)


def _hash_api_key(key: str) -> str:
    """Hash an API key using bcrypt."""
    return pwd_context.hash(key)


async def create_api_key(
    db_pool: asyncpg.Pool,
    user_id: int,
    label: str,
    permissions: List[str],
    expires_days: Optional[int] = None,
) -> Dict:
    """
    Create a new API key for a user.

    Args:
        db_pool: Database connection pool
        user_id: The user ID
        label: Human-readable label for the key
        permissions: List of permission strings
        expires_days: Days until key expires (None = no expiry)

    Returns:
        Dict with id, key, created_at, expires_at, permissions, label
    """
    key = _generate_api_key()
    key_hash = _hash_api_key(key)
    now = datetime.now(tz=timezone.utc)
    expires_at = None
    if expires_days:
        expires_at = now + timedelta(days=expires_days)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO api_keys (user_id, key_hash, label, permissions, created_at, expires_at, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, created_at, expires_at
            """,
            user_id,
            key_hash,
            label,
            permissions,
            now,
            expires_at,
        )

    return {
        "id": row["id"],
        "key": key,  # Only returned on creation
        "label": label,
        "permissions": permissions,
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "is_active": True,
    }


async def validate_api_key(db_pool: asyncpg.Pool, key: str) -> Optional[Dict]:
    """
    Validate an API key and return user_id and permissions.

    Args:
        db_pool: Database connection pool
        key: The API key string

    Returns:
        Dict with user_id and permissions if valid, None if invalid
    """
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, user_id, key_hash, permissions, expires_at, last_used_at
            FROM api_keys
            WHERE is_active = true
            """
        )

    # Find matching key by hashing comparison
    for row in rows:
        if pwd_context.verify(key, row["key_hash"]):
            # Check expiry
            if row["expires_at"] and row["expires_at"] < datetime.now(tz=timezone.utc):
                return None  # Expired

            # Update last_used_at asynchronously (non-blocking)
            try:
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE api_keys SET last_used_at = $1 WHERE id = $2",
                        datetime.now(tz=timezone.utc),
                        row["id"],
                    )
            except Exception as e:
                logger.warning(f"Failed to update last_used_at for api_key {row['id']}: {e}")

            return {
                "user_id": row["user_id"],
                "permissions": row["permissions"] or ["read"],
                "key_id": row["id"],
            }

    return None


async def revoke_api_key(db_pool: asyncpg.Pool, key_id: int, user_id: int) -> bool:
    """
    Revoke (deactivate) an API key.

    Args:
        db_pool: Database connection pool
        key_id: The API key ID
        user_id: The user ID (for authorization check)

    Returns:
        True if revoked, False if not found or unauthorized
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT user_id FROM api_keys WHERE id = $1",
            key_id,
        )

    if not row or row != user_id:
        return False

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE api_keys SET is_active = false WHERE id = $1",
            key_id,
        )

    return True


# ────────────────────────────────────────────────────────────────────────────
# User Management
# ────────────────────────────────────────────────────────────────────────────

async def register_user(
    db_pool: asyncpg.Pool,
    email: str,
    password: str,
    display_name: Optional[str] = None,
) -> Dict:
    """
    Register a new user.

    Args:
        db_pool: Database connection pool
        email: User email (must be unique)
        password: Plaintext password (will be hashed)
        display_name: Optional display name

    Returns:
        Dict with user data

    Raises:
        ValueError: If email already exists or password is weak
    """
    # Validate password strength (minimum 8 chars, checked in UserCreate model)
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    password_hash = hash_password(password)
    now = datetime.utcnow()

    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, display_name, role, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, email, display_name, role, is_active, created_at
                """,
                email,
                password_hash,
                display_name,
                UserRole.USER.value,
                now,
                now,
            )
    except asyncpg.UniqueViolationError:
        raise ValueError(f"User with email {email} already exists")

    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "is_active": row["is_active"],
        "created_at": row["created_at"],
        "last_login_at": None,
    }


async def authenticate(
    db_pool: asyncpg.Pool,
    email: str,
    password: str,
) -> Dict:
    """
    Authenticate a user with email and password.

    Args:
        db_pool: Database connection pool
        email: User email
        password: Plaintext password

    Returns:
        Dict with access_token, refresh_token, expires_in

    Raises:
        HTTPException: If credentials are invalid or user is inactive
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_hash, is_active FROM users WHERE email = $1",
            email,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    user_id = row["id"]

    # Update last_login_at
    now = datetime.now(tz=timezone.utc)
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET last_login_at = $1 WHERE id = $2",
                now,
                user_id,
            )
    except Exception as e:
        logger.warning(f"Failed to update last_login_at for user {user_id}: {e}")

    # Create tokens
    access_token, access_expires_in = _create_jwt(user_id, "access")
    refresh_token, _ = _create_jwt(user_id, "refresh")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": access_expires_in,
    }


async def refresh_access_token(refresh_token: str) -> Dict:
    """
    Refresh an access token using a refresh token.

    Args:
        refresh_token: The refresh token string

    Returns:
        Dict with new access_token and expires_in

    Raises:
        HTTPException: If refresh token is invalid
    """
    user_id = validate_token(refresh_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Verify it's actually a refresh token
    try:
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    access_token, access_expires_in = _create_jwt(user_id, "access")

    return {
        "access_token": access_token,
        "expires_in": access_expires_in,
    }


async def deactivate_user(db_pool: asyncpg.Pool, user_id: int) -> bool:
    """
    Deactivate a user account.

    Args:
        db_pool: Database connection pool
        user_id: The user ID to deactivate

    Returns:
        True if successful
    """
    async with db_pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET is_active = false WHERE id = $1",
            user_id,
        )

    return result == "UPDATE 1"


async def get_user_by_id(db_pool: asyncpg.Pool, user_id: int) -> Optional[Dict]:
    """
    Retrieve a user by ID.

    Args:
        db_pool: Database connection pool
        user_id: The user ID

    Returns:
        Dict with user data or None if not found
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, email, display_name, role, is_active, created_at, last_login_at
            FROM users
            WHERE id = $1
            """,
            user_id,
        )

    return dict(row) if row else None


async def list_user_api_keys(db_pool: asyncpg.Pool, user_id: int) -> List[Dict]:
    """
    List all API keys for a user.

    Args:
        db_pool: Database connection pool
        user_id: The user ID

    Returns:
        List of API key dicts (without the full key)
    """
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, label, permissions, created_at, expires_at, last_used_at, is_active
            FROM api_keys
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )

    return [dict(row) for row in rows]


# ────────────────────────────────────────────────────────────────────────────
# FastAPI Dependencies
# ────────────────────────────────────────────────────────────────────────────

async def _get_current_user_impl(
    db_pool: asyncpg.Pool,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Dict:
    """
    Extract and validate the current user from JWT Bearer token.

    Usage:
        @app.get("/api/v1/auth/me")
        async def get_profile(user: Dict = Depends(get_current_user)):
            return user

    Args:
        db_pool: Database connection pool (injected by FastAPI context)
        credentials: HTTP Bearer credentials from Authorization header

    Returns:
        Dict with user data

    Raises:
        HTTPException: If token is missing or invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    user_id = validate_token(token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_id(db_pool, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


def require_role(required_role: str):
    """
    Factory function to create a dependency that checks user role.

    Usage:
        @app.get("/admin")
        async def admin_endpoint(user: Dict = Depends(require_role("admin"))):
            return {"message": "admin only"}

    Args:
        required_role: The required role (e.g., "admin", "moderator")

    Returns:
        Async dependency function
    """

    async def _check_role(user: Dict = Depends(_get_current_user_impl)) -> Dict:
        if user["role"] != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role} role",
            )
        return user

    return _check_role


# Export the implementation for direct use in routes
def get_current_user(db_pool: asyncpg.Pool):
    """
    Factory function to create a dependency that extracts the current user.

    This must be used with the db_pool explicitly provided by the route handler.

    Usage:
        @app.get("/api/v1/auth/me")
        async def get_profile(user: Dict = Depends(get_current_user(db_pool))):
            return user

    Args:
        db_pool: The asyncpg database pool

    Returns:
        An async dependency function
    """
    async def _wrapper(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    ) -> Dict:
        return await _get_current_user_impl(db_pool, credentials)
    return _wrapper


async def get_current_user_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Dict:
    """
    Standalone dependency that extracts the current user, resolving db_pool
    from request.app.state.pool automatically.

    Usage in routes:
        from api.user_auth import get_current_user_from_request

        @router.get("/me")
        async def get_me(user: Dict = Depends(get_current_user_from_request)):
            return user
    """
    from .db import db as _db
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        pool = _db.pool
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available",
        )
    return await _get_current_user_impl(pool, credentials)


async def get_optional_user_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[Dict]:
    """
    Like get_current_user_from_request, but allows anonymous requests (returns None)
    when no Authorization header is provided.

    If credentials are present but invalid/expired, this still raises 401.
    """
    if not credentials:
        return None

    from .db import db as _db
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        pool = _db.pool
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available",
        )
    return await _get_current_user_impl(pool, credentials)
