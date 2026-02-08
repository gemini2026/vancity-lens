"""
VanCity Lens — Authentication Routes (VCL-74 / BIZ-001)

User registration, login, token refresh, and API key management endpoints.
"""

import logging
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg

from .db import db
from .user_auth import (
    UserCreate,
    UserLogin,
    UserResponse,
    TokenResponse,
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyResponse,
    RefreshTokenRequest,
    register_user,
    authenticate,
    refresh_access_token,
    deactivate_user,
    get_user_by_id,
    validate_api_key,
    create_api_key,
    revoke_api_key,
    list_user_api_keys,
    get_current_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


# ────────────────────────────────────────────────────────────────────────────
# User Registration & Login
# ────────────────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account with email and password.",
)
async def register(request: UserCreate) -> UserResponse:
    """
    Register a new user.

    Returns HTTP 201 on success, HTTP 400 if email already exists.
    """
    try:
        user = await register_user(
            db.pool,
            email=request.email,
            password=request.password,
            display_name=request.display_name,
        )
        return UserResponse(**user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and get tokens",
    description="Login with email and password to get access and refresh tokens.",
)
async def login(request: UserLogin) -> TokenResponse:
    """
    Authenticate a user and return JWT token pair.

    Returns HTTP 200 with tokens on success, HTTP 401 if credentials are invalid.
    """
    result = await authenticate(db.pool, request.email, request.password)
    return TokenResponse(**result)


@router.post(
    "/refresh",
    response_model=Dict,
    summary="Refresh access token",
    description="Use a refresh token to get a new access token.",
)
async def refresh(request: RefreshTokenRequest) -> Dict:
    """
    Refresh an expired access token using a valid refresh token.

    Returns new access token and expiry time.
    """
    result = await refresh_access_token(request.refresh_token)
    return result


# ────────────────────────────────────────────────────────────────────────────
# User Profile
# ────────────────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Retrieve the authenticated user's profile information.",
)
async def get_profile(user: Dict = Depends(get_current_user(db.pool))) -> UserResponse:
    """
    Get the current authenticated user's profile.

    Requires valid JWT in Authorization header.
    """
    return UserResponse(**user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout (invalidate user)",
    description="Deactivate the current user account.",
)
async def logout(user: Dict = Depends(get_current_user(db.pool))):
    """
    Logout by deactivating the user account.

    Note: In a real system, you might track session tokens instead.
    This endpoint is mainly for user-initiated account deactivation.
    """
    await deactivate_user(db.pool, user["id"])
    return None


# ────────────────────────────────────────────────────────────────────────────
# API Key Management
# ────────────────────────────────────────────────────────────────────────────

@router.post(
    "/api-keys",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description="Generate a new API key for the authenticated user.",
)
async def create_api_key_endpoint(
    request: APIKeyCreate,
    user: Dict = Depends(get_current_user(db.pool)),
) -> APIKeyCreateResponse:
    """
    Create a new API key for the current user.

    The full key is only returned on creation. Store it securely.
    Returns HTTP 201 on success.
    """
    key_data = await create_api_key(
        db.pool,
        user_id=user["id"],
        label=request.label,
        permissions=request.permissions,
        expires_days=request.expires_days,
    )
    return APIKeyCreateResponse(**key_data)


@router.get(
    "/api-keys",
    response_model=List[APIKeyResponse],
    summary="List user's API keys",
    description="Get all API keys for the authenticated user (without full key values).",
)
async def list_api_keys(user: Dict = Depends(get_current_user(db.pool))) -> List[APIKeyResponse]:
    """
    List all API keys for the current user.

    Full key values are not included for security (only shown on creation).
    """
    keys = await list_user_api_keys(db.pool, user["id"])
    return [APIKeyResponse(**key) for key in keys]


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
    description="Deactivate an API key for the authenticated user.",
)
async def delete_api_key(
    key_id: int,
    user: Dict = Depends(get_current_user(db.pool)),
):
    """
    Revoke (deactivate) an API key.

    Only the owner can revoke their own keys. Returns HTTP 204 on success.
    """
    success = await revoke_api_key(db.pool, key_id, user["id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or you are not authorized to revoke it",
        )

    return None
