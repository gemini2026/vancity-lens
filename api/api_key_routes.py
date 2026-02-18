"""
VanCity Lens — API Key Routes (VCL-108 / BIZ-010)

REST endpoints for API key management and third-party integration access.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field

from .api_keys import APIKeyManager, VALID_SCOPES, DEFAULT_RATE_LIMIT
from .db import db
from .user_auth import get_current_user_from_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ────────────────────────────────────────────────────────────────────────────


class APIKeyCreateRequest(BaseModel):
    """Request to create a new API key."""

    name: str = Field(..., min_length=1, max_length=255)
    scopes: List[str] = Field(default=["read:parcels"])
    rate_limit: int = Field(default=DEFAULT_RATE_LIMIT, ge=1, le=1000)
    expires_days: Optional[int] = Field(None, ge=1, le=3650)


class APIKeyCreateResponse(BaseModel):
    """Response when creating an API key (includes full key)."""

    id: int
    name: str
    key_prefix: str
    key: str  # Full key only shown once
    scopes: List[str]
    rate_limit: int
    created_at: datetime
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


class APIKeyListResponse(BaseModel):
    """Response for listing API keys (masked, no full key)."""

    id: int
    name: str
    key_prefix: str
    scopes: List[str]
    rate_limit: int
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]

    class Config:
        from_attributes = True


class APIKeyUsageResponse(BaseModel):
    """Usage statistics for an API key."""

    id: int
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime]
    requests_count: int
    rate_limit: int
    requests_this_minute: int


class APIKeyRotateResponse(BaseModel):
    """Response when rotating an API key."""

    id: int
    name: str
    key_prefix: str
    key: str  # New full key only shown once
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


# ────────────────────────────────────────────────────────────────────────────
# API Key Authentication Middleware
# ────────────────────────────────────────────────────────────────────────────


async def get_api_key_user(
    x_api_key: Optional[str] = Header(None),
) -> Dict:
    """
    Extract and validate API key from X-API-Key header.

    Returns user information if valid, raises 401 otherwise.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    key_info = await APIKeyManager.validate_api_key(db.pool, x_api_key)

    if not key_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    # Update last used timestamp
    await APIKeyManager.update_last_used(db.pool, key_info.id)

    return {
        "id": key_info.id,
        "user_id": key_info.user_id,
        "key_prefix": key_info.key_prefix,
        "scopes": key_info.scopes,
    }


# ────────────────────────────────────────────────────────────────────────────
# API Key Endpoints
# ────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
)
async def create_api_key(
    request: APIKeyCreateRequest,
    user: Dict = Depends(get_current_user_from_request),
) -> APIKeyCreateResponse:
    """
    Generate a new API key for third-party integrations.

    The full key is only returned once. Store it securely.
    Scopes control what data the key can access.
    """
    # Validate scopes
    invalid_scopes = set(request.scopes) - VALID_SCOPES
    if invalid_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scopes: {invalid_scopes}",
        )

    try:
        # Generate key
        api_key = APIKeyManager.generate_api_key(
            user_id=user["id"],
            name=request.name,
            scopes=request.scopes,
            rate_limit=request.rate_limit,
            expires_days=request.expires_days,
        )

        # Store in database
        key_hash = APIKeyManager.hash_api_key(api_key.key)

        async with db.pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO api_keys
                (user_id, name, key_hash, key_prefix, scopes, rate_limit, created_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, created_at
                """,
                user["id"],
                request.name,
                key_hash,
                api_key.key_prefix,
                request.scopes,
                request.rate_limit,
                datetime.now(tz=None),
                api_key.expires_at,
            )

        return APIKeyCreateResponse(
            id=result["id"],
            name=request.name,
            key_prefix=api_key.key_prefix,
            key=api_key.key,
            scopes=request.scopes,
            rate_limit=request.rate_limit,
            created_at=result["created_at"],
            expires_at=api_key.expires_at,
        )
    except Exception as e:
        logger.error(f"Error creating API key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create API key",
        )


@router.get(
    "",
    response_model=List[APIKeyListResponse],
    summary="List user's API keys",
)
async def list_api_keys(
    user: Dict = Depends(get_current_user_from_request),
) -> List[APIKeyListResponse]:
    """
    List all API keys for the authenticated user.

    Full key values are masked for security (only shown on creation).
    """
    keys = await APIKeyManager.list_api_keys(db.pool, user["id"])

    return [
        APIKeyListResponse(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            scopes=k.scopes,
            rate_limit=k.rate_limit,
            created_at=k.created_at,
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
            revoked_at=k.revoked_at,
        )
        for k in keys
    ]


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: int,
    user: Dict = Depends(get_current_user_from_request),
):
    """Revoke (deactivate) an API key for the authenticated user."""
    success = await APIKeyManager.revoke_api_key(db.pool, key_id, user["id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or not authorized to revoke",
        )


@router.post(
    "/{key_id}/rotate",
    response_model=APIKeyRotateResponse,
    summary="Rotate an API key",
)
async def rotate_api_key(
    key_id: int,
    user: Dict = Depends(get_current_user_from_request),
) -> APIKeyRotateResponse:
    """
    Rotate an API key (create new key, revoke old).

    Returns a new key that should be stored securely.
    """
    new_key = await APIKeyManager.rotate_api_key(db.pool, key_id, user["id"])

    if not new_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or not authorized to rotate",
        )

    return APIKeyRotateResponse(
        id=key_id,
        name="Rotated key",
        key_prefix=new_key.key_prefix,
        key=new_key.key,
        expires_at=new_key.expires_at,
    )


@router.get(
    "/{key_id}/usage",
    response_model=APIKeyUsageResponse,
    summary="Get API key usage statistics",
)
async def get_api_key_usage(
    key_id: int,
    user: Dict = Depends(get_current_user_from_request),
) -> APIKeyUsageResponse:
    """
    Get usage statistics for an API key.

    Shows request counts and rate limit information.
    """
    async with db.pool.acquire() as conn:
        key_info = await conn.fetchrow(
            """
            SELECT id, name, key_prefix, created_at, last_used_at, rate_limit
            FROM api_keys
            WHERE id = $1 AND user_id = $2
            """,
            key_id,
            user["id"],
        )

    if not key_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    # Placeholder for actual usage statistics
    # In a real implementation, this would query from a metrics table
    return APIKeyUsageResponse(
        id=key_info["id"],
        name=key_info["name"],
        key_prefix=key_info["key_prefix"],
        created_at=key_info["created_at"],
        last_used_at=key_info["last_used_at"],
        requests_count=0,
        rate_limit=key_info["rate_limit"],
        requests_this_minute=0,
    )
