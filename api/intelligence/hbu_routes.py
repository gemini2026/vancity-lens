"""HBU Engine API Routes.

Endpoints:
- GET  /parcels/{pid}/hbu  — Get cached HBU analysis (fast)
- POST /parcels/{pid}/hbu  — Run new HBU analysis (slow, LLM-powered)
"""

from fastapi import APIRouter, Query, Request

from .hbu_engine import analyze_hbu, get_cached_hbu

router = APIRouter(tags=["hbu"])


def _get_pool(request: Request):
    pool = getattr(request.app.state, "pool", None)
    if not pool:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Database connection not available")
    return pool


@router.get("/parcels/{pid}/hbu")
async def get_hbu_analysis(pid: str, request: Request):
    """Get cached HBU analysis for a parcel.

    Returns cached result if available and fresh (within 7-day TTL).
    Returns 404 if no cached analysis exists.
    """
    pool = _get_pool(request)
    cached = await get_cached_hbu(pool, pid)
    if cached:
        return cached
    return {"detail": "No cached HBU analysis. Use POST to run analysis.", "pid": pid}


@router.post("/parcels/{pid}/hbu")
async def run_hbu_analysis(
    pid: str,
    request: Request,
    force_refresh: bool = Query(False, description="Force re-analysis even if cached"),
):
    """Run HBU analysis for a parcel.

    Orchestrates entitlement engine + K2 retrieval + LLM synthesis.
    Result is cached for 7 days. Takes ~3-5 seconds.
    """
    pool = _get_pool(request)
    result = await analyze_hbu(pool, pid, force_refresh=force_refresh)
    return result
