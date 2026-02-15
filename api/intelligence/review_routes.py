"""
VanCity Lens — Review Queue API Routes

Admin endpoints for managing the signal review queue (DV-REG-002).
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .review_queue import (
    bulk_review,
    get_pending_reviews,
    get_review_stats,
    review_signal,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/review-queue", tags=["review-queue"])


class ReviewAction(BaseModel):
    action: str  # 'approve' or 'reject'
    notes: Optional[str] = None


class BulkReviewAction(BaseModel):
    signal_ids: List[int]
    action: str  # 'approve' or 'reject'
    notes: Optional[str] = None


@router.get("", summary="List signals pending review")
async def list_pending_reviews(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    signal_type: Optional[str] = Query(None),
):
    """Get signals flagged for manual review (confidence < threshold)."""
    pool = request.app.state.pool
    return await get_pending_reviews(pool, limit=limit, offset=offset, signal_type=signal_type)


@router.get("/stats", summary="Review queue statistics")
async def review_queue_stats(request: Request):
    """Get summary statistics for the review queue."""
    pool = request.app.state.pool
    return await get_review_stats(pool)


@router.post("/{signal_id}/review", summary="Review a single signal")
async def review_single_signal(
    signal_id: int,
    body: ReviewAction,
    request: Request,
):
    """Approve or reject a signal."""
    pool = request.app.state.pool
    # In production, get reviewer_id from auth token
    reviewer_id = 1  # placeholder

    result = await review_signal(
        pool, signal_id, body.action, reviewer_id, body.notes
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    return result


@router.post("/bulk-review", summary="Bulk review signals")
async def bulk_review_signals(
    body: BulkReviewAction,
    request: Request,
):
    """Approve or reject multiple signals at once."""
    pool = request.app.state.pool
    reviewer_id = 1  # placeholder

    result = await bulk_review(
        pool, body.signal_ids, body.action, reviewer_id, body.notes
    )
    return result
