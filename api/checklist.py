"""
Due Diligence Checklist Router
Handles CRUD operations for real estate due diligence checklists.
"""

from typing import Optional
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
import asyncpg

from .db import get_db_pool

router = APIRouter(prefix="/api/v1", tags=["checklist"])


class ChecklistItemRequest(BaseModel):
    """Request model for checklist item creation/update."""

    label: str = Field(..., min_length=1, max_length=255)
    category: str = Field(
        ...,
        description="Category: title_legal, zoning_planning, physical, financial, municipal",
    )
    checked: bool = False
    notes: Optional[str] = None


class ChecklistItemResponse(BaseModel):
    """Response model for checklist item."""

    id: str
    label: str
    category: str
    checked: bool
    notes: Optional[str] = None
    createdAt: str


class ChecklistResponse(BaseModel):
    """Response model for full checklist."""

    parcelId: str
    userId: str
    items: list[ChecklistItemResponse]
    updatedAt: str


class ChecklistBatchUpdate(BaseModel):
    """Request model for batch updating checklist items."""

    items: list[ChecklistItemRequest]


async def get_db():
    """Dependency: get database pool."""
    pool = await get_db_pool()
    return pool


@router.get("/parcels/{parcel_id}/checklist", response_model=ChecklistResponse)
async def get_checklist(
    parcel_id: str, user_id: str = "anonymous", db: asyncpg.Pool = Depends(get_db)
) -> ChecklistResponse:
    """
    Retrieve checklist for a parcel.
    Returns stored checklist or empty items array if none exists.
    """
    async with db.acquire() as conn:
        result = await conn.fetchval(
            """
            SELECT items FROM due_diligence_checklists
            WHERE parcel_id = $1 AND user_id = $2
            """,
            parcel_id,
            user_id,
        )

    items = []
    if result:
        items = [ChecklistItemResponse(**item) for item in result]

    return ChecklistResponse(
        parcelId=parcel_id,
        userId=user_id,
        items=items,
        updatedAt=datetime.utcnow().isoformat(),
    )


@router.put("/parcels/{parcel_id}/checklist", response_model=ChecklistResponse)
async def update_checklist(
    parcel_id: str,
    payload: ChecklistBatchUpdate,
    user_id: str = "anonymous",
    db: asyncpg.Pool = Depends(get_db),
) -> ChecklistResponse:
    """
    Save or update entire checklist for a parcel.
    """
    items_data = [item.model_dump() for item in payload.items]
    now = datetime.utcnow().isoformat()

    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO due_diligence_checklists (parcel_id, user_id, items, updated_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (parcel_id, user_id)
            DO UPDATE SET items = $3, updated_at = $4
            """,
            parcel_id,
            user_id,
            items_data,
            now,
        )

    return ChecklistResponse(
        parcelId=parcel_id,
        userId=user_id,
        items=[ChecklistItemResponse(**item) for item in items_data],
        updatedAt=now,
    )


@router.post(
    "/parcels/{parcel_id}/checklist/items", response_model=ChecklistItemResponse
)
async def add_checklist_item(
    parcel_id: str,
    item: ChecklistItemRequest,
    user_id: str = "anonymous",
    db: asyncpg.Pool = Depends(get_db),
) -> ChecklistItemResponse:
    """
    Add a single custom item to a parcel checklist.
    """
    item_id = str(uuid4())
    created_at = datetime.utcnow().isoformat()

    new_item = ChecklistItemResponse(
        id=item_id,
        label=item.label,
        category=item.category,
        checked=item.checked,
        notes=item.notes,
        createdAt=created_at,
    )

    async with db.acquire() as conn:
        current_items = await conn.fetchval(
            """
            SELECT items FROM due_diligence_checklists
            WHERE parcel_id = $1 AND user_id = $2
            """,
            parcel_id,
            user_id,
        )

        items_list = current_items or []
        items_list.append(new_item.model_dump())

        await conn.execute(
            """
            INSERT INTO due_diligence_checklists (parcel_id, user_id, items, updated_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (parcel_id, user_id)
            DO UPDATE SET items = $3, updated_at = $4
            """,
            parcel_id,
            user_id,
            items_list,
            created_at,
        )

    return new_item


@router.delete(
    "/parcels/{parcel_id}/checklist/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_checklist_item(
    parcel_id: str,
    item_id: str,
    user_id: str = "anonymous",
    db: asyncpg.Pool = Depends(get_db),
) -> None:
    """
    Remove an item from a parcel checklist.
    """
    async with db.acquire() as conn:
        current_items = await conn.fetchval(
            """
            SELECT items FROM due_diligence_checklists
            WHERE parcel_id = $1 AND user_id = $2
            """,
            parcel_id,
            user_id,
        )

        if not current_items:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Checklist not found"
            )

        updated_items = [item for item in current_items if item.get("id") != item_id]

        if len(updated_items) == len(current_items):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
            )

        await conn.execute(
            """
            UPDATE due_diligence_checklists
            SET items = $1, updated_at = $2
            WHERE parcel_id = $3 AND user_id = $4
            """,
            updated_items,
            datetime.utcnow().isoformat(),
            parcel_id,
            user_id,
        )
