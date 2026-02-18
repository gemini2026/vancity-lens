"""
VanCity Lens -- Case Studies (Preloaded Showcase Parcels)

Curated parcels with narrative descriptions to help new users understand
Bill 47 opportunities through concrete examples.
"""

import json
import logging

from fastapi import APIRouter, HTTPException

from .db import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/case-studies", tags=["case-studies"])


@router.get("")
async def list_case_studies():
    """List all active case studies. No auth required."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                cs.id, cs.pid, cs.title, cs.narrative,
                cs.highlight_metrics, cs.display_order,
                p.civic_address, p.current_zoning, p.lot_area_sqm, p.assessed_value,
                ST_X(ST_Centroid(p.geom)) AS lng,
                ST_Y(ST_Centroid(p.geom)) AS lat
            FROM case_studies cs
            LEFT JOIN parcels p ON p.pid = cs.pid
            WHERE cs.is_active = true
            ORDER BY cs.display_order, cs.id
            """
        )
    results = []
    for r in rows:
        metrics = r["highlight_metrics"]
        if isinstance(metrics, str):
            metrics = json.loads(metrics)
        results.append(
            {
                "id": r["id"],
                "pid": r["pid"],
                "title": r["title"],
                "narrative": r["narrative"],
                "highlight_metrics": metrics,
                "display_order": r["display_order"],
                "civic_address": r["civic_address"],
                "current_zoning": r["current_zoning"],
                "lot_area_sqm": float(r["lot_area_sqm"]) if r["lot_area_sqm"] else None,
                "assessed_value": r["assessed_value"],
                "lng": float(r["lng"]) if r["lng"] else None,
                "lat": float(r["lat"]) if r["lat"] else None,
            }
        )
    return results


@router.get("/{case_study_id}")
async def get_case_study(case_study_id: int):
    """Get a single case study with full details. No auth required."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                cs.id, cs.pid, cs.title, cs.narrative,
                cs.highlight_metrics, cs.display_order,
                p.civic_address, p.current_zoning, p.lot_area_sqm, p.assessed_value,
                ST_X(ST_Centroid(p.geom)) AS lng,
                ST_Y(ST_Centroid(p.geom)) AS lat
            FROM case_studies cs
            LEFT JOIN parcels p ON p.pid = cs.pid
            WHERE cs.id = $1 AND cs.is_active = true
            """,
            case_study_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Case study not found")

    metrics = row["highlight_metrics"]
    if isinstance(metrics, str):
        metrics = json.loads(metrics)

    return {
        "id": row["id"],
        "pid": row["pid"],
        "title": row["title"],
        "narrative": row["narrative"],
        "highlight_metrics": metrics,
        "display_order": row["display_order"],
        "civic_address": row["civic_address"],
        "current_zoning": row["current_zoning"],
        "lot_area_sqm": float(row["lot_area_sqm"]) if row["lot_area_sqm"] else None,
        "assessed_value": row["assessed_value"],
        "lng": float(row["lng"]) if row["lng"] else None,
        "lat": float(row["lat"]) if row["lat"] else None,
    }
