"""
VanCity Lens — Undervalued Parcel Alert Routes

Endpoints for opportunity alerts and undervaluation scores.
"""

import logging

import asyncpg
from fastapi import APIRouter, HTTPException

from ..db import db
from .undervalued_scoring import (
    get_top_opportunities,
    get_parcel_undervaluation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])


@router.get("")
async def list_opportunities(top: int = 20):
    """Get top undervalued parcel opportunities."""
    try:
        opportunities = await get_top_opportunities(db.pool, top_n=min(top, 50))
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
