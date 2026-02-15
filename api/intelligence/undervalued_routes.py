"""
VanCity Lens — Undervalued Parcel Alert Routes

Endpoints for opportunity alerts and undervaluation scores.
"""

from fastapi import APIRouter, Request

from .undervalued_scoring import (
    get_top_opportunities,
    get_parcel_undervaluation,
)

router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])


@router.get("")
async def list_opportunities(request: Request, top: int = 20):
    """Get top undervalued parcel opportunities."""
    db_pool = request.app.state.db_pool
    opportunities = await get_top_opportunities(db_pool, top_n=min(top, 50))
    return {
        "opportunities": opportunities,
        "count": len(opportunities),
    }


@router.get("/parcels/{pid}")
async def get_parcel_opportunity(pid: str, request: Request):
    """Get undervaluation score for a specific parcel."""
    db_pool = request.app.state.db_pool
    result = await get_parcel_undervaluation(db_pool, pid)
    if not result:
        return {"error": f"No undervaluation data for {pid}", "pid": pid}
    return result
