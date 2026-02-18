"""
FastAPI routes for VCL-50 [INTEL-009] Proactive opportunity alerts.

Provides REST API for:
- Creating and managing opportunity profiles
- Triggering opportunity scans
- Retrieving and dismissing matches
- Admin operations
"""

import logging
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..user_auth import get_current_user_from_request
from ..auth import require_admin
from .opportunity_alerts import (
    OpportunityAlertEngine,
    OpportunityProfileCreate,
    OpportunityProfileUpdate,
    OpportunityProfileResponse,
    OpportunityMatchResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


# ────────────────────────────────────────────────────────────────────────────
# Dependency Injection
# ────────────────────────────────────────────────────────────────────────────


def get_db_pool(request: Request) -> asyncpg.Pool:
    """Get database pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if not pool:
        logger.error("Database pool not initialized")
        raise HTTPException(
            status_code=500,
            detail="Database connection not available",
        )
    return pool


async def get_current_user_id(
    user: dict = Depends(get_current_user_from_request),
) -> int:
    """
    Extract user_id from the current authenticated user.
    """
    return user["id"]


# ────────────────────────────────────────────────────────────────────────────
# Profile Endpoints
# ────────────────────────────────────────────────────────────────────────────


@router.post("/profiles", response_model=OpportunityProfileResponse)
async def create_profile(
    profile: OpportunityProfileCreate,
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    user_id: int = Depends(get_current_user_id),
) -> OpportunityProfileResponse:
    """
    Create a new opportunity search profile.

    The profile defines criteria for finding development opportunities:
    - Minimum lot size
    - Maximum price
    - Target neighborhoods/zoning
    - Minimum storey/FSR uplift
    - Maximum distance from transit

    Returns the created profile with ID.
    """
    try:
        created = await OpportunityAlertEngine.create_profile(
            db_pool,
            user_id,
            profile,
        )
        return created
    except Exception as e:
        logger.error(f"Error creating profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to create profile")


@router.get("/profiles", response_model=list[OpportunityProfileResponse])
async def list_profiles(
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    user_id: int = Depends(get_current_user_id),
    include_inactive: bool = Query(False),
) -> list[OpportunityProfileResponse]:
    """
    List all opportunity profiles for the current user.

    Query Parameters:
    - include_inactive: Include deactivated profiles (default: false)
    """
    try:
        profiles = await OpportunityAlertEngine.get_profiles(
            db_pool,
            user_id,
            include_inactive=include_inactive,
        )
        return profiles
    except Exception as e:
        logger.error(f"Error listing profiles: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve profiles")


@router.get("/profiles/{profile_id}", response_model=OpportunityProfileResponse)
async def get_profile(
    profile_id: int,
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    user_id: int = Depends(get_current_user_id),
) -> OpportunityProfileResponse:
    """
    Get a specific opportunity profile by ID.

    Requires that the requesting user owns the profile.
    """
    try:
        profile = await OpportunityAlertEngine.get_profile(db_pool, profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        # Authorization check
        if profile.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve profile")


@router.put("/profiles/{profile_id}", response_model=OpportunityProfileResponse)
async def update_profile(
    profile_id: int,
    updates: OpportunityProfileUpdate,
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    user_id: int = Depends(get_current_user_id),
) -> OpportunityProfileResponse:
    """
    Update an opportunity profile.

    Only the current user can update their own profiles.
    All fields are optional - only provided fields are updated.
    """
    try:
        # Check ownership
        owner_id = await OpportunityAlertEngine.get_profile_owner(db_pool, profile_id)
        if owner_id is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        updated = await OpportunityAlertEngine.update_profile(
            db_pool,
            profile_id,
            updates,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Profile not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile")


@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: int,
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """
    Delete an opportunity profile.

    Only the current user can delete their own profiles.
    Deletes the profile and all associated matches.
    """
    try:
        # Check ownership
        owner_id = await OpportunityAlertEngine.get_profile_owner(db_pool, profile_id)
        if owner_id is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        deleted = await OpportunityAlertEngine.delete_profile(db_pool, profile_id)
        if not deleted:
            raise HTTPException(status_code=500, detail="Failed to delete profile")

        return {"deleted": True, "profile_id": profile_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete profile")


# ────────────────────────────────────────────────────────────────────────────
# Scan Endpoints
# ────────────────────────────────────────────────────────────────────────────


@router.post(
    "/profiles/{profile_id}/scan", response_model=list[OpportunityMatchResponse]
)
async def scan_profile(
    profile_id: int,
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    user_id: int = Depends(get_current_user_id),
) -> list[OpportunityMatchResponse]:
    """
    Trigger an opportunity scan for a specific profile.

    Queries the database for parcels matching the profile criteria and
    calculates match scores based on development potential and proximity.

    Returns newly found matches (may include existing matches with updated scores).
    """
    try:
        # Check ownership
        owner_id = await OpportunityAlertEngine.get_profile_owner(db_pool, profile_id)
        if owner_id is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        matches = await OpportunityAlertEngine.scan_opportunities(db_pool, profile_id)
        return matches
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scanning profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to scan opportunities")


# ────────────────────────────────────────────────────────────────────────────
# Match Endpoints
# ────────────────────────────────────────────────────────────────────────────


@router.get("/matches", response_model=list[OpportunityMatchResponse])
async def get_matches(
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    user_id: int = Depends(get_current_user_id),
    profile_id: Optional[int] = Query(None),
    include_dismissed: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[OpportunityMatchResponse]:
    """
    Get matches for a profile (or across all user profiles if profile_id not specified).

    Query Parameters:
    - profile_id: Filter by specific profile (required - must own the profile)
    - include_dismissed: Include dismissed matches (default: false)
    - limit: Result limit (default: 50, max: 200)
    - offset: Result offset (default: 0)
    """
    if profile_id is None:
        raise HTTPException(
            status_code=400,
            detail="profile_id query parameter is required",
        )

    try:
        # Check ownership
        owner_id = await OpportunityAlertEngine.get_profile_owner(db_pool, profile_id)
        if owner_id is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        matches = await OpportunityAlertEngine.get_matches(
            db_pool,
            profile_id,
            include_dismissed=include_dismissed,
            limit=limit,
            offset=offset,
        )
        return matches
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving matches: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve matches")


@router.get("/top", response_model=list[OpportunityMatchResponse])
async def get_top_matches(
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    user_id: int = Depends(get_current_user_id),
    limit: int = Query(10, ge=1, le=100),
) -> list[OpportunityMatchResponse]:
    """
    Get top opportunity matches across all active user profiles.

    Returns the highest-scoring matches from all user's active profiles.

    Query Parameters:
    - limit: Number of top matches to return (default: 10, max: 100)
    """
    try:
        matches = await OpportunityAlertEngine.get_top_matches(
            db_pool,
            user_id,
            limit=limit,
        )
        return matches
    except Exception as e:
        logger.error(f"Error retrieving top matches: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve matches")


@router.post("/matches/{match_id}/dismiss")
async def dismiss_match(
    match_id: int,
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """
    Dismiss (hide) an opportunity match.

    The match will no longer appear in future queries unless explicitly included.
    """
    try:
        # Authorization: verify user owns the profile associated with this match
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT m.id, op.user_id
                FROM opportunity_matches m
                INNER JOIN opportunity_profiles op ON m.profile_id = op.id
                WHERE m.id = $1
                """,
                match_id,
            )
            if not result:
                raise HTTPException(status_code=404, detail="Match not found")
            if result["user_id"] != user_id:
                raise HTTPException(status_code=403, detail="Forbidden")

        dismissed = await OpportunityAlertEngine.dismiss_match(db_pool, match_id)
        if not dismissed:
            raise HTTPException(status_code=500, detail="Failed to dismiss match")

        return {"dismissed": True, "match_id": match_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error dismissing match: {e}")
        raise HTTPException(status_code=500, detail="Failed to dismiss match")


# ────────────────────────────────────────────────────────────────────────────
# Admin Endpoints
# ────────────────────────────────────────────────────────────────────────────


@router.post("/admin/scan-all", dependencies=[Depends(require_admin)])
async def scan_all_profiles(
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    """
    Admin-only endpoint: Scan opportunities for all active profiles.

    Typically called by a scheduled background job.
    Requires admin privileges (X-Admin-Key header).

    Returns summary of scan results including count of scanned profiles and errors.
    """
    try:
        results = await OpportunityAlertEngine.run_scan_all(db_pool)
        return results
    except Exception as e:
        logger.error(f"Error in scan_all: {e}")
        raise HTTPException(status_code=500, detail="Failed to scan all profiles")
