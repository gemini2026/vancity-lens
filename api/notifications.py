"""
VCL-93 [FE-010] Alert notification badge for VanCity Lens.

FastAPI router for user notifications system with badge display,
dropdown panel, and full notification management interface.

Features:
- List notifications with pagination and filtering
- Mark individual notifications as read
- Mark all notifications as read
- Dismiss/delete notifications
- Unread count endpoint
- Notification types: info, warning, alert, success
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from fastapi import APIRouter
import asyncpg
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class NotificationType(str, Enum):
    """Notification types for filtering and categorization."""

    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    SUCCESS = "success"


class NotificationModel(BaseModel):
    """Single notification response model."""

    id: str
    type: NotificationType
    title: str
    message: str
    created_at: str
    read_at: Optional[str] = None
    parcel_id: Optional[str] = None
    link: Optional[str] = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Response for notification list endpoint."""

    notifications: List[NotificationModel]
    total: int
    limit: int
    offset: int


class UnreadCountResponse(BaseModel):
    """Response for unread count endpoint."""

    unread_count: int


class CreateNotificationRequest(BaseModel):
    """Request model for creating notifications."""

    type: NotificationType
    title: str
    message: str
    parcel_id: Optional[str] = None
    link: Optional[str] = None


async def get_notifications(
    db_pool: asyncpg.Pool,
    user_id: int,
    notification_type: Optional[NotificationType] = None,
    unread_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> NotificationListResponse:
    """
    Fetch notifications for a user with optional filtering.

    Args:
        db_pool: Database connection pool
        user_id: User ID to fetch notifications for
        notification_type: Optional filter by notification type
        unread_only: Only return unread notifications
        limit: Number of results per page
        offset: Pagination offset
    """
    async with db_pool.acquire() as conn:
        query = "SELECT * FROM notifications WHERE user_id = $1"
        params: list = [user_id]
        param_idx = 2

        if notification_type:
            query += f" AND type = ${param_idx}"
            params.append(notification_type.value)
            param_idx += 1

        if unread_only:
            query += " AND read_at IS NULL"

        total_query = query.replace("SELECT *", "SELECT COUNT(*)")
        total_count = await conn.fetchval(total_query, *params)

        query += " ORDER BY created_at DESC LIMIT $" + str(param_idx)
        params.append(limit)
        query += " OFFSET $" + str(param_idx + 1)
        params.append(offset)

        rows = await conn.fetch(query, *params)

    notifications = [
        NotificationModel(
            id=str(row["id"]),
            type=row["type"],
            title=row["title"],
            message=row["message"],
            created_at=row["created_at"].isoformat(),
            read_at=row["read_at"].isoformat() if row["read_at"] else None,
            parcel_id=row["parcel_id"],
            link=row["link"],
        )
        for row in rows
    ]

    return NotificationListResponse(
        notifications=notifications,
        total=total_count or 0,
        limit=limit,
        offset=offset,
    )


async def get_unread_count(
    db_pool: asyncpg.Pool,
    user_id: int,
) -> UnreadCountResponse:
    """
    Get count of unread notifications for a user.

    Args:
        db_pool: Database connection pool
        user_id: User ID to count unread for
    """
    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE user_id = $1 AND read_at IS NULL",
            user_id,
        )

    return UnreadCountResponse(unread_count=count or 0)


async def mark_notification_read(
    db_pool: asyncpg.Pool,
    user_id: int,
    notification_id: str,
) -> Optional[NotificationModel]:
    """
    Mark a single notification as read.

    Args:
        db_pool: Database connection pool
        user_id: User ID (for validation)
        notification_id: Notification ID to mark as read
    """
    now = datetime.now(tz=timezone.utc)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE notifications
            SET read_at = $1
            WHERE id = $2 AND user_id = $3
            RETURNING *
            """,
            now,
            notification_id,
            user_id,
        )

    if not row:
        return None

    return NotificationModel(
        id=str(row["id"]),
        type=row["type"],
        title=row["title"],
        message=row["message"],
        created_at=row["created_at"].isoformat(),
        read_at=row["read_at"].isoformat() if row["read_at"] else None,
        parcel_id=row["parcel_id"],
        link=row["link"],
    )


async def mark_all_read(
    db_pool: asyncpg.Pool,
    user_id: int,
) -> int:
    """
    Mark all unread notifications as read for a user.

    Args:
        db_pool: Database connection pool
        user_id: User ID

    Returns:
        Number of notifications marked as read
    """
    now = datetime.now(tz=timezone.utc)

    async with db_pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE notifications
            SET read_at = $1
            WHERE user_id = $2 AND read_at IS NULL
            """,
            now,
            user_id,
        )

    rows_updated = int(result.split()[-1]) if result else 0
    return rows_updated


async def dismiss_notification(
    db_pool: asyncpg.Pool,
    user_id: int,
    notification_id: str,
) -> bool:
    """
    Delete/dismiss a notification.

    Args:
        db_pool: Database connection pool
        user_id: User ID (for validation)
        notification_id: Notification ID to delete

    Returns:
        True if deleted, False if not found
    """
    async with db_pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM notifications WHERE id = $1 AND user_id = $2",
            notification_id,
            user_id,
        )

    return result != "DELETE 0"


async def create_notification(
    db_pool: asyncpg.Pool,
    user_id: int,
    notification_type: NotificationType,
    title: str,
    message: str,
    parcel_id: Optional[str] = None,
    link: Optional[str] = None,
) -> NotificationModel:
    """
    Create a new notification for a user.

    Args:
        db_pool: Database connection pool
        user_id: User ID
        notification_type: Type of notification
        title: Notification title
        message: Notification message
        parcel_id: Optional parcel ID reference
        link: Optional link to view details

    Returns:
        Created notification
    """
    now = datetime.now(tz=timezone.utc)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO notifications
            (user_id, type, title, message, created_at, parcel_id, link)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            user_id,
            notification_type.value,
            title,
            message,
            now,
            parcel_id,
            link,
        )

    return NotificationModel(
        id=str(row["id"]),
        type=row["type"],
        title=row["title"],
        message=row["message"],
        created_at=row["created_at"].isoformat(),
        read_at=None,
        parcel_id=row["parcel_id"],
        link=row["link"],
    )
