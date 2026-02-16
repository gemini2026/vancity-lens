"""
VanCity Lens — Political Risk API Routes

Endpoints for neighborhood-level political risk scores,
opposition themes, and parcel-level risk summaries.
"""

from fastapi import APIRouter

from ..db import db
from .political_risk import (
    get_all_risk_scores,
    get_neighborhood_risk,
    get_opposition_themes,
    get_parcel_political_risk,
    VANCOUVER_NEIGHBORHOODS,
)

router = APIRouter(prefix="/api/v1/political-risk", tags=["political-risk"])


@router.get("/neighborhoods")
async def list_neighborhood_risk():
    """Get political risk scores for all neighborhoods."""
    scores = await get_all_risk_scores(db.pool)
    return {
        "neighborhoods": scores,
        "count": len(scores),
        "total_neighborhoods": len(VANCOUVER_NEIGHBORHOODS),
    }


@router.get("/neighborhoods/{neighborhood}")
async def get_neighborhood_detail(neighborhood: str):
    """Get detailed political risk for a specific neighborhood."""
    risk = await get_neighborhood_risk(db.pool, neighborhood)
    if not risk:
        return {"error": f"No risk data for {neighborhood}", "neighborhood": neighborhood}

    themes, themes_status = await get_opposition_themes(db.pool, neighborhood)
    risk["themes"] = themes
    if themes_status:
        risk["themes_status"] = themes_status
    return risk


@router.get("/parcels/{pid}")
async def get_parcel_risk(pid: str):
    """Get political risk summary for a specific parcel."""
    result = await get_parcel_political_risk(db.pool, pid)
    if not result:
        return {"error": f"No risk data for parcel {pid}", "pid": pid}
    return result
