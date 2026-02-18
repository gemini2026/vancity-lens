"""HBU Engine — Automated Highest & Best Use Analysis.

Orchestrates:
1. Existing entitlement engine (Bill 47/44, community plans, setbacks)
2. K2 RAG retrieval (zoning bylaw, community plan, heritage chunks)
3. LLM synthesis (Gemini/Anthropic) with HBU-specific prompt
4. Result caching in hbu_analyses table

Usage:
    result = await analyze_hbu(db_pool, pid)
    cached = await get_cached_hbu(db_pool, pid)
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

from ..entitlement import compute_entitlement
from .hbu_prompts import HBU_SYSTEM_PROMPT, build_hbu_context
from .llm_backend import generate_chat
from .retrieval_backend import retrieve_document_chunks

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 7


async def get_cached_hbu(db_pool: asyncpg.Pool, pid: str) -> Optional[dict[str, Any]]:
    """Return cached HBU analysis if fresh, else None."""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT h.analysis, h.narrative, h.confidence_score, h.sources,
                       h.llm_model, h.created_at, h.expires_at,
                       p.civic_address, p.current_zoning
                FROM hbu_analyses h
                JOIN parcels p ON p.pid = h.pid
                WHERE h.pid = $1 AND h.expires_at > NOW()
                ORDER BY h.created_at DESC
                LIMIT 1
                """,
                pid,
            )
            if not row:
                return None

            # asyncpg returns JSONB as strings — must json.loads()
            analysis = row["analysis"]
            if isinstance(analysis, str):
                analysis = json.loads(analysis)

            sources = row["sources"]
            if isinstance(sources, str):
                sources = json.loads(sources)

            return {
                "pid": pid,
                "address": row["civic_address"] or "",
                "current_zoning": row["current_zoning"] or "",
                "highest_best_use": analysis,
                "confidence_score": float(row["confidence_score"])
                if row["confidence_score"]
                else None,
                "sources": sources or [],
                "llm_model": row["llm_model"],
                "analysis_duration_ms": 0,  # not tracked for cached results
                "cached_at": row["created_at"].isoformat()
                if row["created_at"]
                else None,
                "expires_at": row["expires_at"].isoformat()
                if row["expires_at"]
                else None,
            }
    except Exception as e:
        logger.warning("Failed to fetch cached HBU for %s: %s", pid, e)
        return None


async def analyze_hbu(
    db_pool: asyncpg.Pool,
    pid: str,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Run full HBU analysis for a parcel.

    Steps:
    1. Check cache (unless force_refresh)
    2. Compute entitlement via existing engine
    3. Retrieve regulatory document chunks from K2
    4. Send to LLM with HBU system prompt
    5. Parse structured response
    6. Cache result
    7. Return

    Args:
        db_pool: AsyncPG connection pool
        pid: Parcel ID
        force_refresh: Skip cache and re-analyze

    Returns:
        Dict with pid, address, current_zoning, highest_best_use, confidence_score, etc.
    """
    # 1. Check cache
    if not force_refresh:
        cached = await get_cached_hbu(db_pool, pid)
        if cached:
            logger.info("Returning cached HBU for %s", pid)
            return cached

    t0 = time.perf_counter()

    # 2. Compute entitlement
    async with db_pool.acquire() as conn:
        entitlement_response = await compute_entitlement(conn, pid)

    if hasattr(entitlement_response, "model_dump"):
        ent_data = entitlement_response.model_dump()
    else:
        ent_data = dict(entitlement_response)

    parcel_info = {
        "pid": ent_data.get("pid", pid),
        "address": ent_data.get("civic_address", ""),
        "zoning": ent_data.get("current_zoning", ""),
        "lot_area_sqm": None,
        "assessed_value": None,
    }
    ve = ent_data.get("value_estimate") or {}
    if ve:
        parcel_info["lot_area_sqm"] = ve.get("lot_area_sqm")
        parcel_info["assessed_value"] = ve.get("current_assessed")

    pro_forma_data = {}
    if ve:
        pro_forma_data = {
            "buildable_sqft": ve.get("buildable_sqft"),
            "estimated_land_value": ve.get("estimated_land_value"),
            "current_assessed": ve.get("current_assessed"),
            "value_delta": ve.get("value_delta"),
            "price_per_sqft_assumption": ve.get("price_per_sqft_assumption"),
        }

    # 3. Retrieve regulatory chunks from K2
    zoning = ent_data.get("current_zoning", "")
    address = ent_data.get("civic_address", "")

    queries = [
        f"Vancouver zoning bylaw {zoning} maximum height FSR setbacks",
        f"{address} community plan density bonus height allowance",
        f"{address} heritage designation view cone restrictions",
    ]

    all_chunks: list[dict] = []
    for q in queries:
        try:
            chunks = await retrieve_document_chunks(
                db_pool,
                query=q,
                search_mode="full",
            )
            all_chunks.extend(chunks)
        except Exception as e:
            logger.warning("K2 retrieval failed for query '%s': %s", q, e)

    # Deduplicate by chunk text prefix
    seen_texts: set[str] = set()
    unique_chunks: list[dict] = []
    for c in all_chunks:
        text = (c.get("chunk_text") or "")[:200]
        if text not in seen_texts:
            seen_texts.add(text)
            unique_chunks.append(c)

    # Cap at 15 chunks to stay within context limits
    regulatory_chunks = unique_chunks[:15]

    # 4. Build context and call LLM
    context = build_hbu_context(
        parcel_info=parcel_info,
        entitlement_data=ent_data,
        pro_forma_data=pro_forma_data,
        regulatory_chunks=regulatory_chunks,
    )

    try:
        answer_text, model_used, llm_latency = await generate_chat(
            system_prompt=HBU_SYSTEM_PROMPT,
            user_message=context,
            max_tokens=3000,
        )
    except Exception as e:
        logger.error(
            "LLM synthesis failed for HBU %s: %s: %s", pid, type(e).__name__, e
        )
        return _build_fallback_response(pid, ent_data, pro_forma_data)

    # 5. Parse LLM response
    hbu_analysis = _parse_llm_response(answer_text)
    narrative = hbu_analysis.get("narrative", "")
    confidence = _compute_confidence(ent_data, regulatory_chunks, hbu_analysis)

    # Build citation sources
    sources = [
        {
            "title": c.get("document_title", "Unknown"),
            "url": c.get("source_url", ""),
            "score": c.get("final_score", 0),
        }
        for c in regulatory_chunks[:5]
    ]

    total_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "HBU analysis for %s completed in %dms (model=%s)", pid, total_ms, model_used
    )

    # 6. Cache result
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO hbu_analyses (pid, analysis, narrative, confidence_score,
                    llm_model, llm_cost_cents, sources)
                VALUES ($1, $2::jsonb, $3, $4, $5, $6, $7::jsonb)
                """,
                pid,
                json.dumps(hbu_analysis),
                narrative,
                confidence,
                model_used,
                0,  # cost tracking placeholder
                json.dumps(sources),
            )
    except Exception as e:
        logger.warning("Failed to cache HBU result for %s: %s", pid, e)

    # 7. Return
    now = datetime.now(timezone.utc)
    return {
        "pid": pid,
        "address": parcel_info["address"],
        "current_zoning": parcel_info["zoning"],
        "highest_best_use": hbu_analysis,
        "confidence_score": confidence,
        "sources": sources,
        "llm_model": model_used,
        "analysis_duration_ms": total_ms,
        "cached_at": now.isoformat(),
        "expires_at": None,  # fresh result, not from cache
    }


def _parse_llm_response(answer_text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling markdown code fences.

    Always guarantees these keys exist in the result (frontend depends on them):
    - key_constraints: list
    - feasibility_verdict: str
    - recommended_use: str
    """
    import re

    text = answer_text.strip()

    # Strategy 1: Extract JSON from markdown code fences (```json ... ```)
    fence_match = re.search(r"```(?:json)?\s*\n([\s\S]*?)```", text)
    if fence_match:
        text = fence_match.group(1).strip()

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Strategy 2: Find the outermost JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    if not isinstance(parsed, dict):
        logger.warning("Could not parse LLM response as JSON, returning raw narrative")
        parsed = {
            "recommended_use": "Analysis available — see narrative",
            "narrative": answer_text,
        }

    # Guarantee required keys the frontend depends on
    parsed.setdefault("key_constraints", [])
    parsed.setdefault("feasibility_verdict", "unknown")
    parsed.setdefault("recommended_use", "See narrative")
    # Ensure key_constraints is always a list
    if not isinstance(parsed["key_constraints"], list):
        parsed["key_constraints"] = []

    return parsed


def _compute_confidence(ent_data: dict, chunks: list[dict], hbu: dict) -> float:
    """Compute confidence score (0.0-1.0) based on data quality."""
    score = 0.5  # baseline

    # Boost if in TOA with clear entitlement
    if ent_data.get("in_toa") and ent_data.get("best_entitlement"):
        score += 0.15

    # Boost if regulatory chunks found
    if len(chunks) >= 5:
        score += 0.15
    elif len(chunks) >= 2:
        score += 0.10

    # Boost if LLM returned structured fields
    if hbu.get("max_height_storeys") and hbu.get("max_fsr"):
        score += 0.10

    # Boost if feasibility verdict is definitive
    if hbu.get("feasibility_verdict") in ("pencils", "does_not_pencil"):
        score += 0.05

    # Penalty if zoning already exceeds (more uncertain)
    best = ent_data.get("best_entitlement") or {}
    if best.get("zoning_already_exceeds"):
        score -= 0.10

    return round(min(max(score, 0.1), 1.0), 2)


def _build_fallback_response(
    pid: str, ent_data: dict, pro_forma_data: dict
) -> dict[str, Any]:
    """Build rule-engine-only response when LLM is unavailable."""
    best = ent_data.get("best_entitlement") or {}
    return {
        "pid": pid,
        "address": ent_data.get("civic_address", ""),
        "current_zoning": ent_data.get("current_zoning", ""),
        "highest_best_use": {
            "recommended_use": f"Up to {best.get('max_storeys', '?')}-storey (rule-engine estimate)",
            "zoning_basis": f"Bill 47 Tier {best.get('tier', '?')} TOD",
            "max_height_storeys": best.get("max_storeys"),
            "max_fsr": best.get("max_fsr"),
            "estimated_units": None,
            "unit_mix": None,
            "buildable_sqft": pro_forma_data.get("buildable_sqft"),
            "key_constraints": [
                "AI analysis unavailable — showing rule-engine estimates only"
            ],
            "feasibility_verdict": "unknown",
            "narrative": None,
            "cited_sources": [],
        },
        "confidence_score": 0.4,
        "sources": [],
        "llm_model": None,
        "analysis_duration_ms": 0,
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": None,
    }
