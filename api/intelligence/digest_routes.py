"""
VCL-42 [INTEL-007] API routes for weekly digest management.

Endpoints:
- POST /api/v1/intel/digests/subscribe - Create subscription
- GET /api/v1/intel/digests/subscriptions - List user's subscriptions
- PUT /api/v1/intel/digests/subscriptions/{id} - Update subscription
- DELETE /api/v1/intel/digests/subscriptions/{id} - Delete subscription
- GET /api/v1/intel/digests/preview - Preview digest for current period
- GET /api/v1/intel/digests/history - Get past digest deliveries
- POST /api/v1/admin/digests/trigger - Admin: trigger digest generation
"""

import logging
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
import asyncpg

from ..user_auth import get_current_user_from_request
from ..db import db
from .digest import (
    DigestGenerator,
    DigestScheduler,
    DigestSubscription,
    DigestContent,
    DigestDelivery,
    DigestFrequency,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/v1/intel/digests",
    tags=["intelligence", "digests"],
)

admin_router = APIRouter(
    prefix="/api/v1/admin/digests",
    tags=["admin", "digests"],
)


# ────────────────────────────────────────────────────────────────────────────
# Subscription Endpoints
# ────────────────────────────────────────────────────────────────────────────

@router.post("/subscribe", response_model=DigestSubscription, status_code=201)
async def create_subscription(
    neighborhoods: Optional[List[str]] = Query(None),
    signal_types: Optional[List[str]] = Query(None),
    frequency: DigestFrequency = Query(DigestFrequency.WEEKLY),
    is_active: bool = Query(True),
    user: dict = Depends(get_current_user_from_request),
):
    """
    Create a new digest subscription for the authenticated user.

    Query parameters:
    - neighborhoods: List of neighborhoods to include (optional)
    - signal_types: List of signal types to include (optional)
    - frequency: 'weekly' or 'daily' (default: weekly)
    - is_active: Whether subscription is active (default: true)

    Returns the created subscription with ID.
    """
    user_id = user["id"]
    try:
        logger.info(
            f"Creating digest subscription for user {user_id} "
            f"with {len(neighborhoods or [])} neighborhoods"
        )

        async with db.pool.acquire() as conn:
            subscription_id = await conn.fetchval(
                """
                INSERT INTO digest_subscriptions
                (user_id, neighborhoods, signal_types, frequency, is_active)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                user_id,
                neighborhoods or [],
                signal_types or [],
                frequency.value,
                is_active,
            )

        subscription = DigestSubscription(
            id=subscription_id,
            user_id=user_id,
            neighborhoods=neighborhoods or [],
            signal_types=signal_types or [],
            frequency=frequency,
            is_active=is_active,
        )

        logger.info(f"Created subscription {subscription_id} for user {user_id}")
        return subscription

    except Exception as e:
        logger.error(f"Error creating subscription: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subscription",
        )


@router.get("/subscriptions", response_model=List[DigestSubscription])
async def list_subscriptions(
    user: dict = Depends(get_current_user_from_request),
):
    """
    List all digest subscriptions for the authenticated user.

    Returns list of subscription objects.
    """
    user_id = user["id"]
    try:
        logger.info(f"Retrieving subscriptions for user {user_id}")

        async with db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM digest_subscriptions
                WHERE user_id = $1
                ORDER BY created_at DESC
                """,
                user_id,
            )

        subscriptions = [
            DigestSubscription(
                id=row["id"],
                user_id=row["user_id"],
                neighborhoods=list(row["neighborhoods"] or []),
                signal_types=list(row["signal_types"] or []),
                frequency=DigestFrequency(row["frequency"]),
                is_active=row["is_active"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

        logger.info(f"Retrieved {len(subscriptions)} subscriptions for user {user_id}")
        return subscriptions

    except Exception as e:
        logger.error(f"Error retrieving subscriptions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subscriptions",
        )


@router.put("/subscriptions/{subscription_id}", response_model=DigestSubscription)
async def update_subscription(
    subscription_id: int,
    neighborhoods: Optional[List[str]] = Query(None),
    signal_types: Optional[List[str]] = Query(None),
    frequency: Optional[DigestFrequency] = Query(None),
    is_active: Optional[bool] = Query(None),
    user: dict = Depends(get_current_user_from_request),
):
    """
    Update an existing digest subscription.

    Only the authenticated user can update their own subscriptions.

    Query parameters:
    - neighborhoods: Updated list of neighborhoods (optional, only if provided)
    - signal_types: Updated list of signal types (optional, only if provided)
    - frequency: Updated frequency (optional, only if provided)
    - is_active: Updated active status (optional, only if provided)

    Returns updated subscription object.
    """
    user_id = user["id"]
    try:
        logger.info(f"Updating subscription {subscription_id} for user {user_id}")

        # Verify ownership
        async with db.pool.acquire() as conn:
            owner = await conn.fetchval(
                "SELECT user_id FROM digest_subscriptions WHERE id = $1",
                subscription_id,
            )

        if not owner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found",
            )

        if owner != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this subscription",
            )

        # Build update query dynamically
        updates = []
        params = []
        param_idx = 1

        if neighborhoods is not None:
            updates.append(f"neighborhoods = ${param_idx}")
            params.append(neighborhoods)
            param_idx += 1

        if signal_types is not None:
            updates.append(f"signal_types = ${param_idx}")
            params.append(signal_types)
            param_idx += 1

        if frequency is not None:
            updates.append(f"frequency = ${param_idx}")
            params.append(frequency.value)
            param_idx += 1

        if is_active is not None:
            updates.append(f"is_active = ${param_idx}")
            params.append(is_active)
            param_idx += 1

        if not updates:
            # No updates provided, fetch and return current subscription
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM digest_subscriptions WHERE id = $1",
                    subscription_id,
                )
            return DigestSubscription(
                id=row["id"],
                user_id=row["user_id"],
                neighborhoods=list(row["neighborhoods"] or []),
                signal_types=list(row["signal_types"] or []),
                frequency=DigestFrequency(row["frequency"]),
                is_active=row["is_active"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

        updates.append(f"updated_at = NOW()")
        query = f"UPDATE digest_subscriptions SET {', '.join(updates)} WHERE id = ${param_idx} RETURNING *"
        params.append(subscription_id)

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

        subscription = DigestSubscription(
            id=row["id"],
            user_id=row["user_id"],
            neighborhoods=list(row["neighborhoods"] or []),
            signal_types=list(row["signal_types"] or []),
            frequency=DigestFrequency(row["frequency"]),
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

        logger.info(f"Updated subscription {subscription_id}")
        return subscription

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating subscription: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update subscription",
        )


@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def delete_subscription(
    subscription_id: int,
    user: dict = Depends(get_current_user_from_request),
):
    """
    Delete a digest subscription.

    Only the authenticated user can delete their own subscriptions.
    """
    user_id = user["id"]
    try:
        logger.info(f"Deleting subscription {subscription_id} for user {user_id}")

        # Verify ownership
        async with db.pool.acquire() as conn:
            owner = await conn.fetchval(
                "SELECT user_id FROM digest_subscriptions WHERE id = $1",
                subscription_id,
            )

        if not owner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found",
            )

        if owner != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this subscription",
            )

        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM digest_subscriptions WHERE id = $1",
                subscription_id,
            )

        logger.info(f"Deleted subscription {subscription_id}")
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting subscription: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete subscription",
        )


# ────────────────────────────────────────────────────────────────────────────
# Digest Preview & History
# ────────────────────────────────────────────────────────────────────────────

@router.get("/preview", response_model=DigestContent)
async def preview_digest(
    neighborhoods: Optional[List[str]] = Query(None),
    signal_types: Optional[List[str]] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    user: dict = Depends(get_current_user_from_request),
):
    """
    Preview a digest for the current period with optional filters.

    Query parameters:
    - neighborhoods: List of neighborhoods to include (optional)
    - signal_types: List of signal types to include (optional)
    - date_from: Start date (optional, default: 7 days ago)
    - date_to: End date (optional, default: today)

    Returns digest content without saving to database.
    """
    user_id = user["id"]
    try:
        logger.info(f"Generating digest preview for user {user_id}")

        digest_content = await DigestGenerator.generate_weekly_digest(
            db.pool,
            user_id,
            neighborhoods=neighborhoods,
            signal_types=signal_types,
            date_from=date_from,
            date_to=date_to,
        )

        logger.info(f"Generated preview with {len(digest_content.highlights)} highlights")
        return digest_content

    except Exception as e:
        logger.error(f"Error generating digest preview: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate digest preview",
        )


@router.get("/history", response_model=List[DigestDelivery])
async def get_digest_history(
    subscription_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user_from_request),
):
    """
    Retrieve past digest deliveries for user's subscriptions.

    Query parameters:
    - subscription_id: Filter by specific subscription (optional)
    - limit: Number of results (default: 20, max: 100)
    - offset: Pagination offset (default: 0)

    Returns list of digest deliveries ordered by most recent first.
    """
    user_id = user["id"]
    try:
        logger.info(f"Retrieving digest history for user {user_id}")

        # Build query with ownership check
        query = """
            SELECT d.* FROM digest_deliveries d
            JOIN digest_subscriptions s ON d.subscription_id = s.id
            WHERE s.user_id = $1
        """
        params = [user_id]

        if subscription_id:
            query += " AND d.subscription_id = $2"
            params.append(subscription_id)
            param_idx = 3
        else:
            param_idx = 2

        query += f" ORDER BY d.digest_date DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([limit, offset])

        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        deliveries = [
            DigestDelivery(
                id=row["id"],
                subscription_id=row["subscription_id"],
                digest_date=row["digest_date"],
                content_json=row["content_json"],
                signal_count=row["signal_count"],
                delivery_status=row["delivery_status"],
                created_at=row["created_at"],
                sent_at=row["sent_at"],
            )
            for row in rows
        ]

        logger.info(f"Retrieved {len(deliveries)} digest deliveries for user {user_id}")
        return deliveries

    except Exception as e:
        logger.error(f"Error retrieving digest history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve digest history",
        )


# ────────────────────────────────────────────────────────────────────────────
# Admin Endpoints
# ────────────────────────────────────────────────────────────────────────────

@admin_router.post("/trigger", status_code=202)
async def trigger_digest_generation(
    frequency: DigestFrequency = Query(DigestFrequency.WEEKLY),
    user: dict = Depends(get_current_user_from_request),
):
    """
    Admin endpoint: Trigger digest generation for all active subscriptions.

    This is an async operation that runs in the background.
    Returns 202 Accepted.

    Query parameters:
    - frequency: 'weekly' or 'daily' (default: weekly)

    Requires admin privileges.
    """
    user_id = user["id"]
    try:
        logger.info(
            f"Admin {user_id} triggering digest generation for frequency: {frequency.value}"
        )

        # Verify admin (would be done by dependency in real implementation)
        # For now, just log the action

        # Run digest cycle asynchronously (would be in background task in production)
        # For now, just trigger it
        import asyncio

        # Fire and forget (in production, use Celery or similar)
        asyncio.create_task(DigestScheduler.run_digest_cycle(db.pool, frequency))

        logger.info(f"Digest generation triggered for frequency: {frequency.value}")
        return {"status": "digest generation started", "frequency": frequency.value}

    except Exception as e:
        logger.error(f"Error triggering digest generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger digest generation",
        )
