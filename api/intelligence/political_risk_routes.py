"""
VanCity Lens — Political Risk API Routes

Endpoints for neighborhood-level political risk scores,
opposition themes, and parcel-level risk summaries.
"""

from fastapi import APIRouter, Request

from .political_risk import (
    get_all_risk_scores,
    get_neighborhood_risk,
    get_opposition_themes,
    get_parcel_political_risk,
    VANCOUVER_NEIGHBORHOODS,
)

router = APIRouter(prefix="/api/v1/political-risk", tags=["political-risk"])


@router.get("/neighborhoods")
async def list_neighborhood_risk(request: Request):
    """Get political risk scores for all neighborhoods."""
    db_pool = request.app.state.db_pool
    scores = await get_all_risk_scores(db_pool)
    return {
        "neighborhoods": scores,
        "count": len(scores),
        "total_neighborhoods": len(VANCOUVER_NEIGHBORHOODS),
    }


@router.get("/neighborhoods/{neighborhood}")
async def get_neighborhood_detail(neighborhood: str, request: Request):
    """Get detailed political risk for a specific neighborhood."""
    db_pool = request.app.state.db_pool
    risk = await get_neighborhood_risk(db_pool, neighborhood)
    if not risk:
        return {"error": f"No risk data for {neighborhood}", "neighborhood": neighborhood}

    themes = await get_opposition_themes(db_pool, neighborhood)
    risk["themes"] = themes
    return risk


@router.get("/parcels/{pid}")
async def get_parcel_risk(pid: str, request: Request):
    """Get political risk summary for a specific parcel."""
    db_pool = request.app.state.db_pool
    result = await get_parcel_political_risk(db_pool, pid)
    if not result:
        return {"error": f"No risk data for parcel {pid}", "pid": pid}
    return result
