"""
VanCity Lens -- Saved Parcels (Bookmarks)

Simple one-click save/unsave for parcels. Complements the rule-based watchlist.
"""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .db import db
from .user_auth import get_current_user_from_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["saved-parcels"])


class SaveParcelRequest(BaseModel):
    notes: Optional[str] = ""


class SavedParcelResponse(BaseModel):
    saved: bool


class SavedParcelItem(BaseModel):
    id: int
    pid: str
    notes: str
    created_at: str
    civic_address: Optional[str] = None
    current_zoning: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────


@router.post("/parcels/{pid}/save", response_model=SavedParcelResponse)
async def save_parcel(
    pid: str,
    body: SaveParcelRequest = SaveParcelRequest(),
    user: Dict = Depends(get_current_user_from_request),
):
    """Save (bookmark) a parcel for the current user."""
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO saved_parcels (user_id, pid, notes)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, pid) DO UPDATE SET notes = $3
            """,
            user["id"],
            pid,
            body.notes or "",
        )
    return {"saved": True}


@router.delete("/parcels/{pid}/save", response_model=SavedParcelResponse)
async def unsave_parcel(
    pid: str,
    user: Dict = Depends(get_current_user_from_request),
):
    """Remove a saved parcel for the current user."""
    async with db.acquire() as conn:
        await conn.execute(
            "DELETE FROM saved_parcels WHERE user_id = $1 AND pid = $2",
            user["id"],
            pid,
        )
    return {"saved": False}


@router.get("/parcels/{pid}/saved", response_model=SavedParcelResponse)
async def check_saved(
    pid: str,
    user: Dict = Depends(get_current_user_from_request),
):
    """Check if a parcel is saved by the current user."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM saved_parcels WHERE user_id = $1 AND pid = $2",
            user["id"],
            pid,
        )
    return {"saved": row is not None}


@router.get("/saved-parcels")
async def list_saved_parcels(
    user: Dict = Depends(get_current_user_from_request),
):
    """List all parcels saved by the current user, with parcel details."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                sp.id, sp.pid, sp.notes, sp.created_at,
                p.civic_address, p.current_zoning
            FROM saved_parcels sp
            LEFT JOIN parcels p ON p.pid = sp.pid
            WHERE sp.user_id = $1
            ORDER BY sp.created_at DESC
            """,
            user["id"],
        )
    return [
        {
            "id": r["id"],
            "pid": r["pid"],
            "notes": r["notes"] or "",
            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
            "civic_address": r["civic_address"],
            "current_zoning": r["current_zoning"],
        }
        for r in rows
    ]
