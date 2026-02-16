"""
VanCity Lens — Undervalued Parcel Alert Routes

Endpoints for opportunity alerts and undervaluation scores.
Includes admin endpoint for triggering weekly email digests (F06-002).
"""

import logging
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_admin
from ..db import db
from .undervalued_scoring import (
    get_top_opportunities,
    get_parcel_undervaluation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])


@router.get("")
async def list_opportunities(
    top: int = 20,
    tod_tier: Optional[str] = Query(None, description="Filter by TOD tier (e.g., 'Tier 1')"),
    neighborhood: Optional[str] = Query(None, description="Filter by neighborhood name"),
):
    """Get top undervalued parcel opportunities."""
    try:
        opportunities = await get_top_opportunities(
            db.pool,
            top_n=min(top, 50),
            tod_tier=tod_tier,
            neighborhood=neighborhood,
        )
    except asyncpg.UndefinedTableError:
        raise HTTPException(
            status_code=503,
            detail="Undervalued scores data not yet available. Run scoring first.",
        )
    except asyncpg.PostgresError as e:
        logger.error("Failed to fetch opportunities: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch undervalued opportunities.",
        )
    return {
        "opportunities": opportunities,
        "count": len(opportunities),
    }


@router.get("/parcels/{pid}")
async def get_parcel_opportunity(pid: str):
    """Get undervaluation score for a specific parcel."""
    try:
        result = await get_parcel_undervaluation(db.pool, pid)
    except asyncpg.UndefinedTableError:
        raise HTTPException(
            status_code=503,
            detail="Undervalued scores data not yet available. Run scoring first.",
        )
    except asyncpg.PostgresError as e:
        logger.error("Failed to fetch undervaluation for %s: %s", pid, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch undervaluation data.",
        )
    if not result:
        return {"error": f"No undervaluation data for {pid}", "pid": pid}
    return result


# ── F06-002: Weekly Undervalued Alert Email Delivery ─────────────────


async def send_weekly_undervalued_digest(db_pool: asyncpg.Pool) -> dict:
    """
    Fetch subscribers with email_alerts=true, generate top-20 parcels,
    and send personalised email digests.

    Returns stats dict with keys: subscribers_found, emails_sent, emails_failed.
    """
    from ..email_service import send_undervalued_alert

    stats = {"subscribers_found": 0, "emails_sent": 0, "emails_failed": 0}

    try:
        # 1. Fetch top 20 undervalued parcels (shared across all subscribers)
        parcels = await get_top_opportunities(db_pool, top_n=20)
        if not parcels:
            logger.info("No undervalued parcels to include in weekly digest.")
            return stats

        # 2. Fetch subscribers (users with email_alerts enabled)
        async with db_pool.acquire() as conn:
            subscribers = await conn.fetch("""
                SELECT id, email, alert_email
                FROM users
                WHERE email_alerts = true
                  AND is_active = true
            """)

        stats["subscribers_found"] = len(subscribers)
        if not subscribers:
            logger.info("No subscribers opted in for undervalued alerts.")
            return stats

        # 3. Send to each subscriber
        for sub in subscribers:
            # Use alert_email if set, otherwise fall back to account email
            to_addr = sub["alert_email"] or sub["email"]
            if not to_addr:
                logger.warning("Subscriber id=%s has no usable email address.", sub["id"])
                stats["emails_failed"] += 1
                continue

            try:
                success = await send_undervalued_alert(to_addr, parcels)
                if success:
                    stats["emails_sent"] += 1
                else:
                    stats["emails_failed"] += 1
            except Exception as e:
                logger.error(
                    "Error sending undervalued alert to %s: %s",
                    to_addr,
                    e,
                    exc_info=True,
                )
                stats["emails_failed"] += 1

    except asyncpg.UndefinedTableError:
        logger.error(
            "Cannot send weekly digest: undervalued_scores table not available."
        )
    except asyncpg.UndefinedColumnError:
        logger.error(
            "Cannot send weekly digest: email_alerts column not yet migrated. "
            "Run db/048_email_preferences.sql first."
        )
    except Exception as e:
        logger.error("Weekly undervalued digest failed: %s", e, exc_info=True)

    logger.info("Weekly undervalued digest complete: %s", stats)
    return stats


@router.post(
    "/alerts/send",
    summary="Admin: send weekly undervalued parcel email digest",
    dependencies=[Depends(require_admin)],
    description=(
        "Trigger sending the weekly undervalued parcel email digest to all "
        "subscribed users (email_alerts=true). Returns delivery statistics."
    ),
)
async def admin_send_undervalued_alerts():
    """
    Send the weekly undervalued parcel alert emails (F06-002).

    Fetches users where email_alerts=true, generates the top-20 undervalued
    parcels list, and sends HTML email digests to each subscriber.
    """
    try:
        stats = await send_weekly_undervalued_digest(db.pool)
        return {
            "status": "completed",
            **stats,
        }
    except Exception as e:
        logger.error("Admin send undervalued alerts failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send undervalued alerts: {str(e)}",
        )
