"""
Alert and watchlist API endpoints for VanCity Lens (VCL-38 / INTEL-006).

Provides REST API access to:
- Watchlist CRUD operations
- Alert retrieval and filtering
- Alert read/unread status management
"""

import logging

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..user_auth import get_current_user_from_request
from .alerts import (
    WatchlistManager,
    AlertEngine,
    Watchlist,
    WatchlistCreate,
    WatchlistUpdate,
    Alert,
    AlertCount,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])


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


# ────────────────────────────────────────────────────────────────────────────
# Watchlist Endpoints
# ────────────────────────────────────────────────────────────────────────────

@router.post(
    "/watchlists",
    response_model=Watchlist,
    summary="Create watchlist",
    description=(
        "Create a new watchlist with optional rules. Rules are used to filter "
        "signals and automatically generate alerts when matching signals are discovered."
    ),
)
async def create_watchlist(
    request: Request,
    watchlist_data: WatchlistCreate,
    current_user=Depends(get_current_user_from_request),
) -> Watchlist:
    """
    Create a new watchlist for the authenticated user.

    A watchlist contains rules that are matched against incoming signals to
    automatically generate alerts. Rules can filter by neighborhood, address,
    zoning, signal type, keywords, or severity.
    """
    try:
        db_pool = get_db_pool(request)
        user_id = current_user["id"]

        logger.info(f"Creating watchlist '{watchlist_data.name}' for user {user_id}")

        watchlist = await WatchlistManager.create_watchlist(
            db_pool=db_pool,
            user_id=user_id,
            name=watchlist_data.name,
            description=watchlist_data.description,
            rules=watchlist_data.rules,
        )

        logger.info(f"Watchlist {watchlist.id} created successfully")
        return watchlist

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating watchlist: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create watchlist: {str(e)}",
        )


@router.get(
    "/watchlists",
    response_model=list[Watchlist],
    summary="List user's watchlists",
    description="Retrieve all watchlists for the authenticated user.",
)
async def list_watchlists(
    request: Request,
    active_only: bool = Query(
        True,
        description="Only return active watchlists",
    ),
    current_user=Depends(get_current_user_from_request),
) -> list[Watchlist]:
    """
    Get all watchlists for the authenticated user.
    """
    try:
        db_pool = get_db_pool(request)
        user_id = current_user["id"]

        logger.info(f"Retrieving watchlists for user {user_id}")

        watchlists = await WatchlistManager.get_watchlists(
            db_pool=db_pool,
            user_id=user_id,
            active_only=active_only,
        )

        logger.info(f"Retrieved {len(watchlists)} watchlists for user {user_id}")
        return watchlists

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving watchlists: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve watchlists: {str(e)}",
        )


@router.get(
    "/watchlists/{watchlist_id}",
    response_model=Watchlist,
    summary="Get watchlist details",
    description="Retrieve a specific watchlist with its rules.",
)
async def get_watchlist(
    request: Request,
    watchlist_id: int,
    current_user=Depends(get_current_user_from_request),
) -> Watchlist:
    """
    Get a specific watchlist by ID.

    The user must be the owner of the watchlist.
    """
    try:
        db_pool = get_db_pool(request)
        user_id = current_user["id"]

        logger.info(f"Retrieving watchlist {watchlist_id} for user {user_id}")

        watchlist = await WatchlistManager.get_watchlist(db_pool, watchlist_id)

        if not watchlist:
            logger.warning(f"Watchlist {watchlist_id} not found")
            raise HTTPException(status_code=404, detail="Watchlist not found")

        # Verify ownership
        if watchlist.user_id != user_id:
            logger.warning(
                f"User {user_id} attempted to access watchlist {watchlist_id} owned by {watchlist.user_id}"
            )
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this watchlist",
            )

        logger.info(f"Retrieved watchlist {watchlist_id}")
        return watchlist

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving watchlist {watchlist_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve watchlist: {str(e)}",
        )


@router.put(
    "/watchlists/{watchlist_id}",
    response_model=Watchlist,
    summary="Update watchlist",
    description="Update watchlist metadata and/or rules.",
)
async def update_watchlist(
    request: Request,
    watchlist_id: int,
    watchlist_data: WatchlistUpdate,
    current_user=Depends(get_current_user_from_request),
) -> Watchlist:
    """
    Update a watchlist's name, description, and/or rules.

    The user must be the owner of the watchlist.
    """
    try:
        db_pool = get_db_pool(request)
        user_id = current_user["id"]

        # Verify ownership first
        existing = await WatchlistManager.get_watchlist(db_pool, watchlist_id)

        if not existing:
            logger.warning(f"Watchlist {watchlist_id} not found")
            raise HTTPException(status_code=404, detail="Watchlist not found")

        if existing.user_id != user_id:
            logger.warning(
                f"User {user_id} attempted to update watchlist {watchlist_id} owned by {existing.user_id}"
            )
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to update this watchlist",
            )

        logger.info(f"Updating watchlist {watchlist_id} for user {user_id}")

        watchlist = await WatchlistManager.update_watchlist(
            db_pool=db_pool,
            watchlist_id=watchlist_id,
            name=watchlist_data.name,
            description=watchlist_data.description,
            rules=watchlist_data.rules,
        )

        logger.info(f"Watchlist {watchlist_id} updated successfully")
        return watchlist

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating watchlist {watchlist_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update watchlist: {str(e)}",
        )


@router.delete(
    "/watchlists/{watchlist_id}",
    summary="Delete watchlist",
    description="Delete a watchlist and all associated rules and alerts.",
)
async def delete_watchlist(
    request: Request,
    watchlist_id: int,
    current_user=Depends(get_current_user_from_request),
):
    """
    Delete a watchlist.

    The user must be the owner of the watchlist. Deletion is permanent and
    will also delete all associated alerts.
    """
    try:
        db_pool = get_db_pool(request)
        user_id = current_user["id"]

        # Verify ownership first
        existing = await WatchlistManager.get_watchlist(db_pool, watchlist_id)

        if not existing:
            logger.warning(f"Watchlist {watchlist_id} not found")
            raise HTTPException(status_code=404, detail="Watchlist not found")

        if existing.user_id != user_id:
            logger.warning(
                f"User {user_id} attempted to delete watchlist {watchlist_id} owned by {existing.user_id}"
            )
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to delete this watchlist",
            )

        logger.info(f"Deleting watchlist {watchlist_id} for user {user_id}")

        deleted = await WatchlistManager.delete_watchlist(db_pool, watchlist_id)

        if not deleted:
            logger.warning(f"Watchlist {watchlist_id} not found during deletion")
            raise HTTPException(status_code=404, detail="Watchlist not found")

        logger.info(f"Watchlist {watchlist_id} deleted successfully")
        return {"message": "Watchlist deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting watchlist {watchlist_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete watchlist: {str(e)}",
        )


# ────────────────────────────────────────────────────────────────────────────
# Alert Endpoints
# ────────────────────────────────────────────────────────────────────────────

@router.get(
    "/alerts",
    response_model=list[Alert],
    summary="Get user's alerts",
    description=(
        "Retrieve alerts for the authenticated user with optional filtering "
        "by read status and pagination."
    ),
)
async def get_alerts(
    request: Request,
    unread_only: bool = Query(
        False,
        description="Only return unread alerts",
    ),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user=Depends(get_current_user_from_request),
) -> list[Alert]:
    """
    Get alerts for the authenticated user.

    Results are sorted by creation date (most recent first).
    """
    try:
        db_pool = get_db_pool(request)
        user_id = current_user["id"]

        logger.info(
            f"Retrieving alerts for user {user_id}: unread_only={unread_only}, "
            f"limit={limit}, offset={offset}"
        )

        alerts = await AlertEngine.get_alerts(
            db_pool=db_pool,
            user_id=user_id,
            unread_only=unread_only,
            limit=limit,
            offset=offset,
        )

        logger.info(f"Retrieved {len(alerts)} alerts for user {user_id}")
        return alerts

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve alerts: {str(e)}",
        )


@router.post(
    "/alerts/{alert_id}/read",
    summary="Mark alert as read",
    description="Mark a specific alert as read.",
)
async def mark_alert_read(
    request: Request,
    alert_id: int,
    current_user=Depends(get_current_user_from_request),
):
    """
    Mark an alert as read.

    The user must own the alert (via ownership of the associated watchlist).
    """
    try:
        db_pool = get_db_pool(request)
        user_id = current_user["id"]

        logger.info(f"Marking alert {alert_id} as read for user {user_id}")

        # Mark as read
        updated = await AlertEngine.mark_read(db_pool, alert_id)

        if not updated:
            logger.warning(f"Alert {alert_id} not found")
            raise HTTPException(status_code=404, detail="Alert not found")

        logger.info(f"Alert {alert_id} marked as read")
        return {"message": "Alert marked as read"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking alert {alert_id} as read: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark alert as read: {str(e)}",
        )


@router.post(
    "/alerts/read-all",
    summary="Mark all alerts as read",
    description="Mark all alerts for the authenticated user as read.",
)
async def mark_all_alerts_read(
    request: Request,
    current_user=Depends(get_current_user_from_request),
):
    """
    Mark all alerts for the authenticated user as read.
    """
    try:
        db_pool = get_db_pool(request)
        user_id = current_user["id"]

        logger.info(f"Marking all alerts as read for user {user_id}")

        count = await AlertEngine.mark_all_read(db_pool, user_id)

        logger.info(f"Marked {count} alerts as read for user {user_id}")
        return {"message": f"Marked {count} alerts as read", "count": count}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking all alerts as read: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark alerts as read: {str(e)}",
        )


@router.get(
    "/alerts/count",
    response_model=AlertCount,
    summary="Get alert counts",
    description=(
        "Get the total and unread alert counts for the authenticated user."
    ),
)
async def get_alert_counts(
    request: Request,
    current_user=Depends(get_current_user_from_request),
) -> AlertCount:
    """
    Get alert count summary for the authenticated user.

    Returns both total and unread alert counts.
    """
    try:
        db_pool = get_db_pool(request)
        user_id = current_user["id"]

        logger.info(f"Retrieving alert counts for user {user_id}")

        counts = await AlertEngine.get_alert_count(
            db_pool=db_pool,
            user_id=user_id,
            unread_only=False,
        )

        logger.info(
            f"Retrieved alert counts for user {user_id}: total={counts.total}, unread={counts.unread}"
        )
        return counts

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving alert counts: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve alert counts: {str(e)}",
        )
