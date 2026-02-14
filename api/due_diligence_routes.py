"""
Due Diligence Evidence Routes

Public endpoint that returns verifiable due diligence evidence + source links
so the frontend and PDF report can cite where facts came from.
"""

import logging

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from .db import db
from .due_diligence_evidence import DueDiligenceEvidenceResponse, build_due_diligence_evidence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["due_diligence"])


@router.get(
    "/parcels/{pid}/due-diligence/evidence",
    response_model=DueDiligenceEvidenceResponse,
    summary="Get due diligence evidence for a parcel",
    description="Returns utilities proximity, easements proxy, and policy excerpts with source links.",
)
async def get_due_diligence_evidence(
    pid: str,
    pool: asyncpg.Pool = Depends(lambda: db.pool),
) -> DueDiligenceEvidenceResponse:
    if not pool:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        async with pool.acquire() as conn:
            return await build_due_diligence_evidence(conn, pid)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Parcel {pid} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error building due diligence evidence for %s: %s", pid, e)
        raise HTTPException(status_code=500, detail="Failed to build due diligence evidence")

