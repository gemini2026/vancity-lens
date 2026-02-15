"""
VanCity Lens — Signal Review Queue (DV-REG-002)

Signals extracted with confidence < 85% are flagged for manual review.
This module provides the review queue management functions.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


async def get_pending_reviews(
    db_pool: asyncpg.Pool,
    limit: int = 50,
    offset: int = 0,
    signal_type: Optional[str] = None,
) -> List[dict]:
    """Get signals pending manual review, ordered by confidence (lowest first)."""
    where_clauses = ["review_status = 'pending_review'"]
    params = []
    idx = 1

    if signal_type:
        where_clauses.append(f"signal_type = ${idx}")
        params.append(signal_type)
        idx += 1

    where = " AND ".join(where_clauses)
    params.extend([limit, offset])

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT id, document_id, signal_type, summary, headline,
                   neighborhood, severity, confidence, event_date,
                   review_status, created_at
            FROM intelligence_signals
            WHERE {where}
            ORDER BY confidence ASC, created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
        """, *params)

        count_row = await conn.fetchrow(f"""
            SELECT count(*) as total FROM intelligence_signals WHERE {where}
        """, *(params[:-2] if signal_type else []))

        return {
            "items": [dict(r) for r in rows],
            "total": count_row["total"] if count_row else 0,
            "page_size": limit,
        }


async def review_signal(
    db_pool: asyncpg.Pool,
    signal_id: int,
    action: str,  # 'approve' or 'reject'
    reviewer_id: int,
    notes: Optional[str] = None,
) -> Optional[dict]:
    """Approve or reject a signal in the review queue."""
    if action not in ("approve", "reject"):
        raise ValueError(f"Invalid action: {action}. Must be 'approve' or 'reject'.")

    review_status = "approved" if action == "approve" else "rejected"

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE intelligence_signals
            SET review_status = $1,
                reviewed_by = $2,
                reviewed_at = $3,
                review_notes = $4
            WHERE id = $5
            RETURNING id, signal_type, summary, confidence, review_status
        """,
            review_status,
            reviewer_id,
            datetime.now(timezone.utc),
            notes,
            signal_id,
        )

        if not row:
            return None
        return dict(row)


async def bulk_review(
    db_pool: asyncpg.Pool,
    signal_ids: List[int],
    action: str,
    reviewer_id: int,
    notes: Optional[str] = None,
) -> Dict[str, int]:
    """Bulk approve or reject signals."""
    if action not in ("approve", "reject"):
        raise ValueError(f"Invalid action: {action}")

    review_status = "approved" if action == "approve" else "rejected"

    async with db_pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE intelligence_signals
            SET review_status = $1,
                reviewed_by = $2,
                reviewed_at = $3,
                review_notes = $4
            WHERE id = ANY($5)
              AND review_status = 'pending_review'
        """,
            review_status,
            reviewer_id,
            datetime.now(timezone.utc),
            notes,
            signal_ids,
        )

        # Parse "UPDATE N" to get count
        count = int(result.split()[-1]) if result else 0
        return {"updated": count, "action": action}


async def get_review_stats(db_pool: asyncpg.Pool) -> dict:
    """Get review queue statistics."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                count(*) FILTER (WHERE review_status = 'pending_review') AS pending,
                count(*) FILTER (WHERE review_status = 'approved') AS approved,
                count(*) FILTER (WHERE review_status = 'rejected') AS rejected,
                count(*) FILTER (WHERE review_status = 'auto_approved') AS auto_approved,
                avg(confidence) FILTER (WHERE review_status = 'pending_review') AS avg_pending_confidence
            FROM intelligence_signals
        """)
        return dict(row) if row else {}
