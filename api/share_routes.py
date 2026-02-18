"""Share link endpoints for public parcel report access."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone

from .db import db
from .user_auth import get_current_user_from_request
from .entitlement import compute_entitlement

router = APIRouter(prefix="/api/v1/share", tags=["share"])


class ShareLinkCreate(BaseModel):
    pid: str
    label: Optional[str] = None
    expires_days: int = 30


class ShareLinkResponse(BaseModel):
    token: str
    pid: str
    label: Optional[str]
    expires_at: str
    url: str


@router.post("", response_model=ShareLinkResponse)
async def create_share_link(body: ShareLinkCreate, request: Request):
    """Create a shareable link for a parcel report."""
    user = await get_current_user_from_request(request)
    pool = await db.get_pool()
    row = await pool.fetchrow(
        """INSERT INTO share_links (pid, user_id, label, expires_at)
           VALUES ($1, $2, $3, NOW() + make_interval(days => $4))
           RETURNING token, pid, label, expires_at""",
        body.pid,
        user["id"] if user else None,
        body.label,
        body.expires_days,
    )
    base_url = str(request.base_url).rstrip("/")
    return ShareLinkResponse(
        token=row["token"],
        pid=row["pid"],
        label=row["label"],
        expires_at=row["expires_at"].isoformat(),
        url=f"{base_url}/api/v1/share/{row['token']}",
    )


@router.get("/{token}")
async def get_shared_report(token: str):
    """Access a shared parcel report (no auth required)."""
    pool = await db.get_pool()
    row = await pool.fetchrow(
        "SELECT pid, expires_at FROM share_links WHERE token = $1", token
    )
    if not row:
        raise HTTPException(404, "Share link not found")
    if row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(410, "Share link has expired")
    # Increment view count
    await pool.execute(
        "UPDATE share_links SET view_count = view_count + 1 WHERE token = $1", token
    )
    # Return full entitlement data
    data = await compute_entitlement(row["pid"])
    return data
