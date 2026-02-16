# HBU Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an automated Highest & Best Use analysis engine that combines the existing entitlement engine + K2 RAG retrieval + LLM synthesis to deliver per-parcel development recommendations with regulatory citations.

**Architecture:** New HBU orchestration module calls existing `entitlement.py` for hard numbers, `retrieval_backend.py` for K2 document chunks (zoning bylaws, community plans), and `llm_backend.py` for narrative synthesis. Results cached in a new `hbu_analyses` DB table. Frontend component + PDF section + standalone PDF report.

**Tech Stack:** FastAPI, asyncpg, K2 RAG (existing), Gemini/Anthropic LLM (existing), React 19, FPDF2

**Design Doc:** `docs/plans/2026-02-15-hbu-engine-design.md`

---

## Epic 1: Backend — HBU Engine Core

### Task 1: Database Migration

**Files:**
- Create: `db/034_hbu_analyses.sql`

**Step 1: Write the migration file**

```sql
-- Migration 034: HBU Analyses cache table
-- Caches LLM-powered Highest & Best Use analysis results per parcel.

CREATE TABLE IF NOT EXISTS hbu_analyses (
    id SERIAL PRIMARY KEY,
    pid TEXT NOT NULL REFERENCES parcels(pid),
    analysis JSONB NOT NULL,
    narrative TEXT,
    confidence_score NUMERIC(3,2),
    llm_model TEXT,
    llm_cost_cents INTEGER DEFAULT 0,
    sources JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
);

CREATE INDEX IF NOT EXISTS idx_hbu_analyses_pid ON hbu_analyses(pid);
CREATE INDEX IF NOT EXISTS idx_hbu_analyses_expires ON hbu_analyses(expires_at);
```

**Step 2: Commit**

```bash
git add db/034_hbu_analyses.sql
git commit -m "feat(db): add hbu_analyses cache table (migration 034)"
```

---

### Task 2: HBU System Prompts

**Files:**
- Create: `api/intelligence/hbu_prompts.py`

**Step 1: Write the failing test**

Create `tests/test_hbu_engine.py`:

```python
"""Tests for HBU Engine — Automated Highest & Best Use Analysis."""

import json
import os

import pytest


class TestHBUPrompts:
    """HBU prompt module exists and exports required constants."""

    def test_module_exists(self):
        assert os.path.exists("api/intelligence/hbu_prompts.py")

    def test_exports_system_prompt(self):
        from api.intelligence.hbu_prompts import HBU_SYSTEM_PROMPT
        assert "highest and best use" in HBU_SYSTEM_PROMPT.lower()
        assert "zoning" in HBU_SYSTEM_PROMPT.lower()

    def test_exports_context_template(self):
        from api.intelligence.hbu_prompts import build_hbu_context
        assert callable(build_hbu_context)

    def test_context_template_includes_parcel_data(self):
        from api.intelligence.hbu_prompts import build_hbu_context
        context = build_hbu_context(
            parcel_info={"pid": "123", "address": "Test St", "zoning": "RS-1", "lot_area_sqm": 600},
            entitlement_data={"best_entitlement": {"tier": 1, "max_storeys": 20, "max_fsr": 5.5}},
            pro_forma_data={"land_value_estimate": 1000000},
            regulatory_chunks=[{"chunk_text": "Section 4.7 allows...", "document_title": "Zoning Bylaw"}],
        )
        assert "123" in context
        assert "RS-1" in context
        assert "Zoning Bylaw" in context

    def test_system_prompt_requests_json(self):
        from api.intelligence.hbu_prompts import HBU_SYSTEM_PROMPT
        assert "JSON" in HBU_SYSTEM_PROMPT
```

**Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_hbu_engine.py::TestHBUPrompts -v
```

Expected: FAIL — module not found.

**Step 3: Write the implementation**

Create `api/intelligence/hbu_prompts.py`:

```python
"""HBU Engine — System prompts and context builders for LLM synthesis."""

from typing import Any


HBU_SYSTEM_PROMPT = """You are a Vancouver real estate development analyst specializing in \
highest and best use (HBU) analysis. Given a parcel's location, current zoning, entitlement \
data, pro forma estimates, and relevant regulatory document excerpts, determine the highest \
and best use for the site.

You MUST:
1. Identify the maximum legally buildable envelope (height, FSR, unit count, setbacks)
2. Consider ALL applicable regulations: base zoning district, Bill 47 TOD overlay, \
Bill 44 multiplex eligibility, community plan density bonuses, view cone hard caps, \
heritage restrictions, and setback rules
3. Recommend the most profitable use type consistent with entitlements \
(e.g., "20-storey mixed-use residential" or "6-storey wood-frame rental")
4. Provide a feasibility verdict: "pencils" (viable), "marginal", or "does not pencil"
5. Flag any constraints, red flags, or risk factors
6. Cite specific bylaw sections and plan policies from the provided regulatory excerpts

Return your analysis as JSON with exactly these fields:
{
  "recommended_use": "string — e.g., '12-storey mixed-use residential'",
  "zoning_basis": "string — regulatory basis, e.g., 'Bill 47 Tier 1 TOD + RS-1 base zoning'",
  "max_height_storeys": number,
  "max_fsr": number,
  "estimated_units": number,
  "unit_mix": {"studio": n, "1br": n, "2br": n, "3br": n},
  "buildable_sqft": number,
  "key_constraints": ["string — each constraint or red flag"],
  "feasibility_verdict": "pencils | marginal | does_not_pencil",
  "narrative": "string — 2-4 paragraph analysis with citations like [Source: Document Title]",
  "cited_sources": [{"title": "string", "section": "string", "relevance": "string"}]
}

PROHIBITED:
- Do not invent regulations not in the provided excerpts
- Do not provide investment advice beyond feasibility assessment
- Do not speculate about future regulatory changes"""


def build_hbu_context(
    *,
    parcel_info: dict[str, Any],
    entitlement_data: dict[str, Any],
    pro_forma_data: dict[str, Any],
    regulatory_chunks: list[dict[str, Any]],
) -> str:
    """Build the user-message context for HBU LLM synthesis.

    Combines parcel facts, entitlement calculations, pro forma estimates,
    and retrieved regulatory document chunks into a structured prompt.
    """
    sections = []

    # Parcel info
    sections.append("## PARCEL INFORMATION")
    sections.append(f"PID: {parcel_info.get('pid', 'N/A')}")
    sections.append(f"Address: {parcel_info.get('address', 'N/A')}")
    sections.append(f"Current Zoning: {parcel_info.get('zoning', 'N/A')}")
    lot_sqm = parcel_info.get("lot_area_sqm", 0)
    lot_sqft = round(float(lot_sqm) * 10.764, 0) if lot_sqm else "N/A"
    sections.append(f"Lot Area: {lot_sqm} sqm ({lot_sqft} sqft)")
    if parcel_info.get("assessed_value"):
        sections.append(f"BC Assessment Value: ${parcel_info['assessed_value']:,.0f}")
    sections.append("")

    # Entitlement data
    sections.append("## ENTITLEMENT ANALYSIS (Rule Engine Output)")
    best = entitlement_data.get("best_entitlement")
    if best:
        sections.append(f"Nearest Station: {best.get('station_name', 'N/A')} ({best.get('distance_m', '?')}m)")
        sections.append(f"TOD Tier: {best.get('tier', 'N/A')}")
        sections.append(f"Bill 47 Max Storeys: {best.get('max_storeys', 'N/A')}")
        sections.append(f"Bill 47 Max FSR: {best.get('max_fsr', 'N/A')}")
        sections.append(f"Current Storeys: {best.get('current_storeys', 'N/A')}")
        sections.append(f"Current FSR: {best.get('current_fsr', 'N/A')}")
        sections.append(f"Storey Uplift: +{best.get('storey_uplift', 0)}")
        sections.append(f"FSR Uplift: +{best.get('fsr_uplift', 0)}")
        sections.append(f"Zoning Already Exceeds: {best.get('zoning_already_exceeds', False)}")
    else:
        sections.append("Parcel is NOT in a Transit-Oriented Area (TOA).")

    if entitlement_data.get("bill44"):
        b44 = entitlement_data["bill44"]
        sections.append(f"Bill 44 Eligible: {b44.get('is_eligible', False)}")
        if b44.get("max_units"):
            sections.append(f"Bill 44 Max Units: {b44['max_units']}")

    if entitlement_data.get("community_plan") and entitlement_data["community_plan"].get("has_bonus"):
        cp = entitlement_data["community_plan"]
        sections.append(f"Community Plan Bonus: {cp.get('plan_name', 'N/A')} — +{cp.get('best_bonus', {}).get('fsr_bonus', 0)} FSR")

    if entitlement_data.get("setbacks"):
        sb = entitlement_data["setbacks"]
        sections.append(f"Setbacks: front={sb.get('front_m', '?')}m, rear={sb.get('rear_m', '?')}m, side={sb.get('side_m', '?')}m")
    sections.append("")

    # Pro forma data
    sections.append("## PRO FORMA ESTIMATES")
    if pro_forma_data:
        for k, v in pro_forma_data.items():
            if isinstance(v, (int, float)) and v > 1000:
                sections.append(f"{k}: ${v:,.0f}")
            else:
                sections.append(f"{k}: {v}")
    sections.append("")

    # Regulatory document chunks
    sections.append("## REGULATORY DOCUMENT EXCERPTS")
    sections.append("(Retrieved from K2 knowledge base — use these as your primary regulatory source)")
    sections.append("")
    for i, chunk in enumerate(regulatory_chunks, 1):
        title = chunk.get("document_title", "Unknown Document")
        text = chunk.get("chunk_text", "")
        sections.append(f"### Excerpt {i}: {title}")
        sections.append(text[:2000])  # cap each chunk
        sections.append("")

    return "\n".join(sections)
```

**Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_hbu_engine.py::TestHBUPrompts -v
```

Expected: 5 PASS.

**Step 5: Commit**

```bash
git add api/intelligence/hbu_prompts.py tests/test_hbu_engine.py
git commit -m "feat: add HBU system prompts and context builder"
```

---

### Task 3: HBU Engine Orchestrator

**Files:**
- Create: `api/intelligence/hbu_engine.py`
- Test: `tests/test_hbu_engine.py` (append)

**Step 1: Write the failing tests**

Append to `tests/test_hbu_engine.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal


class TestHBUEngine:
    """HBU Engine orchestrator tests."""

    def test_module_exists(self):
        assert os.path.exists("api/intelligence/hbu_engine.py")

    def test_exports_analyze_function(self):
        from api.intelligence.hbu_engine import analyze_hbu
        assert callable(analyze_hbu)

    def test_exports_get_cached_function(self):
        from api.intelligence.hbu_engine import get_cached_hbu
        assert callable(get_cached_hbu)

    @pytest.mark.asyncio
    async def test_get_cached_returns_none_when_empty(self):
        from api.intelligence.hbu_engine import get_cached_hbu

        mock_pool = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        conn.fetchrow = AsyncMock(return_value=None)

        result = await get_cached_hbu(mock_pool, "999-999-999")
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_hbu_returns_structured_response(self):
        """analyze_hbu returns dict with required keys."""
        from api.intelligence.hbu_engine import analyze_hbu

        mock_pool = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock: no cached result
        conn.fetchrow = AsyncMock(return_value=None)
        conn.execute = AsyncMock()

        # Mock entitlement
        mock_entitlement = {
            "pid": "100-001-006",
            "civic_address": "3838 Cambie Street",
            "current_zoning": "RS-1",
            "in_toa": True,
            "best_entitlement": {
                "station_name": "King Edward",
                "tier": 1,
                "max_storeys": 20,
                "max_fsr": 5.5,
                "distance_m": 165.2,
                "current_storeys": 10,
                "current_fsr": 0.6,
                "storey_uplift": 10,
                "fsr_uplift": 4.9,
                "zoning_already_exceeds": False,
            },
            "value_estimate": {
                "lot_area_sqm": 600,
                "buildable_sqft": 35521,
                "estimated_land_value": 28416696,
            },
        }

        # Mock K2 retrieval
        mock_chunks = [
            {"chunk_text": "RS-1 zoning allows max 0.6 FSR...", "document_title": "Zoning Bylaw"},
        ]

        # Mock LLM response
        mock_llm_response = json.dumps({
            "recommended_use": "20-storey mixed-use",
            "zoning_basis": "Bill 47 Tier 1 TOD",
            "max_height_storeys": 20,
            "max_fsr": 5.5,
            "estimated_units": 85,
            "unit_mix": {"studio": 15, "1br": 35, "2br": 25, "3br": 10},
            "buildable_sqft": 35521,
            "key_constraints": [],
            "feasibility_verdict": "pencils",
            "narrative": "This RS-1 lot qualifies for Tier 1 TOD...",
            "cited_sources": [{"title": "Zoning Bylaw", "section": "4.7", "relevance": "base zoning"}],
        })

        with patch("api.intelligence.hbu_engine.compute_entitlement") as mock_ent, \
             patch("api.intelligence.hbu_engine.retrieve_document_chunks") as mock_ret, \
             patch("api.intelligence.hbu_engine.generate_chat") as mock_llm:
            mock_ent.return_value = MagicMock()
            mock_ent.return_value.__class__.__name__ = "ParcelEntitlementResponse"
            # Make it dict-serializable
            mock_ent.return_value.model_dump = MagicMock(return_value=mock_entitlement)

            mock_ret.return_value = mock_chunks
            mock_llm.return_value = (mock_llm_response, "gemini-2.0-flash", 1.5)

            result = await analyze_hbu(mock_pool, "100-001-006")

        assert result is not None
        assert result["pid"] == "100-001-006"
        assert "highest_best_use" in result
        hbu = result["highest_best_use"]
        assert hbu["recommended_use"] == "20-storey mixed-use"
        assert hbu["max_height_storeys"] == 20
        assert "confidence_score" in result
```

**Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_hbu_engine.py::TestHBUEngine -v
```

Expected: FAIL — `hbu_engine` module not found.

**Step 3: Write the implementation**

Create `api/intelligence/hbu_engine.py`:

```python
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


async def get_cached_hbu(
    db_pool: asyncpg.Pool, pid: str
) -> Optional[dict[str, Any]]:
    """Return cached HBU analysis if fresh, else None."""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT analysis, narrative, confidence_score, sources,
                       llm_model, created_at, expires_at
                FROM hbu_analyses
                WHERE pid = $1 AND expires_at > NOW()
                ORDER BY created_at DESC
                LIMIT 1
                """,
                pid,
            )
            if not row:
                return None

            analysis = row["analysis"]
            if isinstance(analysis, str):
                analysis = json.loads(analysis)

            sources = row["sources"]
            if isinstance(sources, str):
                sources = json.loads(sources)

            return {
                "pid": pid,
                "highest_best_use": analysis,
                "narrative": row["narrative"],
                "confidence_score": float(row["confidence_score"]) if row["confidence_score"] else None,
                "sources": sources,
                "llm_model": row["llm_model"],
                "cached_at": row["created_at"].isoformat() if row["created_at"] else None,
                "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
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

    ent_data = entitlement_response.model_dump() if hasattr(entitlement_response, "model_dump") else dict(entitlement_response)

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
                db_pool, query=q, search_mode="full",
            )
            all_chunks.extend(chunks)
        except Exception as e:
            logger.warning("K2 retrieval failed for query '%s': %s", q, e)

    # Deduplicate by chunk text
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
        logger.error("LLM synthesis failed for HBU %s: %s", pid, e)
        # Fallback: rule-engine-only result
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
    logger.info("HBU analysis for %s completed in %dms (model=%s)", pid, total_ms, model_used)

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
    """Extract JSON from LLM response, handling markdown code fences."""
    text = answer_text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    logger.warning("Could not parse LLM response as JSON, returning raw narrative")
    return {
        "recommended_use": "Analysis available — see narrative",
        "narrative": answer_text,
        "key_constraints": [],
        "feasibility_verdict": "unknown",
    }


def _compute_confidence(
    ent_data: dict, chunks: list[dict], hbu: dict
) -> float:
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
            "key_constraints": ["AI analysis unavailable — showing rule-engine estimates only"],
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
```

**Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_hbu_engine.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add api/intelligence/hbu_engine.py tests/test_hbu_engine.py
git commit -m "feat: add HBU engine orchestrator with K2 retrieval + LLM synthesis"
```

---

### Task 4: HBU API Routes

**Files:**
- Create: `api/intelligence/hbu_routes.py`
- Modify: `api/intelligence/routes.py` — mount the HBU router
- Test: `tests/test_hbu_engine.py` (append)

**Step 1: Write the failing tests**

Append to `tests/test_hbu_engine.py`:

```python
class TestHBURoutes:
    """HBU API route registration tests."""

    def test_routes_file_exists(self):
        assert os.path.exists("api/intelligence/hbu_routes.py")

    def test_router_has_analyze_endpoint(self):
        from api.intelligence.hbu_routes import router
        paths = [r.path for r in router.routes]
        assert any("hbu" in p for p in paths)

    def test_router_has_get_endpoint(self):
        from api.intelligence.hbu_routes import router
        methods = []
        for r in router.routes:
            methods.extend(getattr(r, "methods", []))
        assert "GET" in methods

    def test_router_has_post_endpoint(self):
        from api.intelligence.hbu_routes import router
        methods = []
        for r in router.routes:
            methods.extend(getattr(r, "methods", []))
        assert "POST" in methods

    def test_hbu_routes_mounted_in_intelligence(self):
        with open("api/intelligence/routes.py") as f:
            content = f.read()
        assert "hbu_routes" in content
```

**Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_hbu_engine.py::TestHBURoutes -v
```

Expected: FAIL — module not found.

**Step 3: Write the routes**

Create `api/intelligence/hbu_routes.py`:

```python
"""HBU Engine API Routes.

Endpoints:
- GET  /parcels/{pid}/hbu  — Get cached HBU analysis (fast)
- POST /parcels/{pid}/hbu  — Run new HBU analysis (slow, LLM-powered)
"""

from fastapi import APIRouter, Query

from ..db import db
from .hbu_engine import analyze_hbu, get_cached_hbu

router = APIRouter(tags=["hbu"])


@router.get("/parcels/{pid}/hbu")
async def get_hbu_analysis(pid: str):
    """Get cached HBU analysis for a parcel.

    Returns cached result if available and fresh (within 7-day TTL).
    Returns 404 if no cached analysis exists.
    """
    cached = await get_cached_hbu(db.pool, pid)
    if cached:
        return cached
    return {"detail": "No cached HBU analysis. Use POST to run analysis.", "pid": pid}


@router.post("/parcels/{pid}/hbu")
async def run_hbu_analysis(
    pid: str,
    force_refresh: bool = Query(False, description="Force re-analysis even if cached"),
):
    """Run HBU analysis for a parcel.

    Orchestrates entitlement engine + K2 retrieval + LLM synthesis.
    Result is cached for 7 days. Takes ~3-5 seconds.
    """
    result = await analyze_hbu(db.pool, pid, force_refresh=force_refresh)
    return result
```

**Step 4: Mount the router**

In `api/intelligence/routes.py`, add after the existing router imports:

```python
from . import hbu_routes
```

And after the existing `router.include_router()` calls:

```python
router.include_router(hbu_routes.router)
```

**Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_hbu_engine.py::TestHBURoutes -v
```

Expected: All PASS.

**Step 6: Run full test suite to verify no regressions**

```bash
python3 -m pytest tests/ -q --ignore=tests/test_mobile_responsive.py
```

Expected: All existing tests still pass.

**Step 7: Commit**

```bash
git add api/intelligence/hbu_routes.py api/intelligence/routes.py tests/test_hbu_engine.py
git commit -m "feat: add HBU API routes and mount in intelligence router"
```

---

## Epic 2: Document Ingestion

### Task 5: Add New Sources to K2 Pipeline

**Files:**
- Modify: `pipeline/sources.yaml` — add 9 new document sources

**Step 1: Add the community plan document library sources**

Append these entries to `pipeline/sources.yaml` in the `sources:` array, after the existing Rupert/Renfrew entry:

```yaml
  - id: syc_marpole_plan_documents
    enabled: true
    priority: p1
    cadence: weekly
    name: "Shape Your City Vancouver — Marpole Community Plan (Documents)"
    discover:
      type: syc_document_library_page
      page_url: "https://www.shapeyourcity.ca/marpole-community-plan/documents"
      ingest_page: true
      store:
        page_source_type: "syc_plan_page"
        document_source_type: "syc_plan_document"

  - id: syc_west_end_plan_documents
    enabled: true
    priority: p1
    cadence: weekly
    name: "Shape Your City Vancouver — West End Community Plan (Documents)"
    discover:
      type: syc_document_library_page
      page_url: "https://www.shapeyourcity.ca/west-end-community-plan/documents"
      ingest_page: true
      store:
        page_source_type: "syc_plan_page"
        document_source_type: "syc_plan_document"

  - id: syc_mount_pleasant_plan_documents
    enabled: true
    priority: p1
    cadence: weekly
    name: "Shape Your City Vancouver — Mount Pleasant Community Plan (Documents)"
    discover:
      type: syc_document_library_page
      page_url: "https://www.shapeyourcity.ca/mount-pleasant-community-plan/documents"
      ingest_page: true
      store:
        page_source_type: "syc_plan_page"
        document_source_type: "syc_plan_document"

  - id: syc_norquay_plan_documents
    enabled: true
    priority: p1
    cadence: weekly
    name: "Shape Your City Vancouver — Norquay Village Neighbourhood Centre Plan (Documents)"
    discover:
      type: syc_document_library_page
      page_url: "https://www.shapeyourcity.ca/norquay-village-neighbourhood-centre-plan/documents"
      ingest_page: true
      store:
        page_source_type: "syc_plan_page"
        document_source_type: "syc_plan_document"

  - id: syc_cambie_corridor_plan_documents
    enabled: true
    priority: p1
    cadence: weekly
    name: "Shape Your City Vancouver — Cambie Corridor Plan (Documents)"
    discover:
      type: syc_document_library_page
      page_url: "https://www.shapeyourcity.ca/cambie-corridor-plan/documents"
      ingest_page: true
      store:
        page_source_type: "syc_plan_page"
        document_source_type: "syc_plan_document"

  - id: syc_grandview_woodland_plan_documents
    enabled: true
    priority: p1
    cadence: weekly
    name: "Shape Your City Vancouver — Grandview-Woodland Community Plan (Documents)"
    discover:
      type: syc_document_library_page
      page_url: "https://www.shapeyourcity.ca/grandview-woodland-community-plan/documents"
      ingest_page: true
      store:
        page_source_type: "syc_plan_page"
        document_source_type: "syc_plan_document"

  - id: vancouver_zoning_bylaw
    enabled: true
    priority: p0
    cadence: monthly
    name: "Vancouver Zoning & Development Bylaw"
    discover:
      type: static_urls
      store:
        source_type: "municipal_bylaw"
      urls:
        - "https://bylaws.vancouver.ca/zoning/zoning-and-development-by-law-3575.pdf"

  - id: vancouver_heritage_register
    enabled: true
    priority: p1
    cadence: monthly
    name: "Vancouver Heritage Register"
    discover:
      type: static_urls
      store:
        source_type: "heritage_register"
      urls:
        - "https://opendata.vancouver.ca/explore/dataset/heritage-register/information/"

  - id: vancouver_view_cones
    enabled: true
    priority: p1
    cadence: monthly
    name: "Vancouver Protected View Cones"
    discover:
      type: static_urls
      store:
        source_type: "view_protection"
      urls:
        - "https://opendata.vancouver.ca/explore/dataset/view-protection-guidelines/information/"
```

**Step 2: Commit**

```bash
git add pipeline/sources.yaml
git commit -m "feat: add 9 new K2 document sources for HBU analysis"
```

**Step 3: Run K2 ingestion (manual, requires K2 credentials)**

```bash
K2_API_KEY=... K2_CORPUS_ID=vancity python3 migration/k2_ingest_sources.py --dry-run
```

Then remove `--dry-run` when ready:

```bash
K2_API_KEY=... K2_CORPUS_ID=vancity python3 migration/k2_ingest_sources.py --wait --build-indexes
```

---

## Epic 3: Frontend

### Task 6: HBU API Client

**Files:**
- Create: `frontend/src/lib/hbu-api.ts`

**Step 1: Write the API client**

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

function getAuthHeaders(): HeadersInit {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("token") : null;
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export interface HBUAnalysis {
  pid: string;
  address: string;
  current_zoning: string;
  highest_best_use: {
    recommended_use: string;
    zoning_basis: string;
    max_height_storeys: number | null;
    max_fsr: number | null;
    estimated_units: number | null;
    unit_mix: Record<string, number> | null;
    buildable_sqft: number | null;
    key_constraints: string[];
    feasibility_verdict: string;
    narrative: string | null;
    cited_sources: Array<{ title: string; section: string; relevance: string }>;
  };
  confidence_score: number | null;
  sources: Array<{ title: string; url: string; score: number }>;
  llm_model: string | null;
  analysis_duration_ms: number;
  cached_at: string | null;
  expires_at: string | null;
}

export async function getHBUAnalysis(pid: string): Promise<HBUAnalysis | null> {
  const res = await fetch(`${API_BASE}/api/v1/intel/parcels/${pid}/hbu`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) return null;
  const data = await res.json();
  if (data.detail) return null; // no cached result
  return data;
}

export async function runHBUAnalysis(
  pid: string,
  forceRefresh = false
): Promise<HBUAnalysis> {
  const url = `${API_BASE}/api/v1/intel/parcels/${pid}/hbu${forceRefresh ? "?force_refresh=true" : ""}`;
  const res = await fetch(url, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`HBU analysis failed: ${res.status}`);
  return res.json();
}
```

**Step 2: Commit**

```bash
git add frontend/src/lib/hbu-api.ts
git commit -m "feat: add HBU analysis API client"
```

---

### Task 7: HBU Frontend Component

**Files:**
- Create: `frontend/src/components/HBUAnalysis.tsx`
- Modify: `frontend/src/components/ParcelDetailPanel.tsx` — add the component

**Step 1: Write the component**

Create `frontend/src/components/HBUAnalysis.tsx`:

```tsx
"use client";

import { useState } from "react";
import { type HBUAnalysis, getHBUAnalysis, runHBUAnalysis } from "../lib/hbu-api";

interface Props {
  pid: string;
}

export default function HBUAnalysisPanel({ pid }: Props) {
  const [data, setData] = useState<HBUAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showNarrative, setShowNarrative] = useState(false);
  const [showConstraints, setShowConstraints] = useState(false);

  async function handleAnalyze(forceRefresh = false) {
    setLoading(true);
    setError(null);
    try {
      // Try cached first
      if (!forceRefresh) {
        const cached = await getHBUAnalysis(pid);
        if (cached) {
          setData(cached);
          setLoading(false);
          return;
        }
      }
      // Run fresh analysis
      const result = await runHBUAnalysis(pid, forceRefresh);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  if (!data && !loading && !error) {
    return (
      <div className="mt-2">
        <button
          onClick={() => handleAnalyze()}
          className="w-full py-2 px-3 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition-colors"
        >
          Analyze Highest &amp; Best Use
        </button>
        <p className="text-[10px] text-gray-500 mt-1 text-center">
          AI-powered analysis using zoning bylaws &amp; community plans
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mt-2 space-y-2 animate-pulse">
        <div className="h-4 bg-white/[0.06] rounded w-3/4" />
        <div className="h-3 bg-white/[0.06] rounded w-1/2" />
        <div className="h-16 bg-white/[0.06] rounded" />
        <p className="text-[10px] text-gray-500 text-center">
          Analyzing zoning bylaws &amp; community plans...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-2 p-2 rounded bg-red-500/10 border border-red-500/20">
        <p className="text-xs text-red-400">{error}</p>
        <button
          onClick={() => handleAnalyze(true)}
          className="text-[10px] text-red-300 underline mt-1"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const hbu = data.highest_best_use;
  const verdictColor =
    hbu.feasibility_verdict === "pencils"
      ? "text-green-400"
      : hbu.feasibility_verdict === "marginal"
        ? "text-yellow-400"
        : "text-red-400";
  const verdictLabel =
    hbu.feasibility_verdict === "pencils"
      ? "Pencils"
      : hbu.feasibility_verdict === "marginal"
        ? "Marginal"
        : hbu.feasibility_verdict === "does_not_pencil"
          ? "Does Not Pencil"
          : "Unknown";

  const cachedAgo = data.cached_at
    ? Math.round((Date.now() - new Date(data.cached_at).getTime()) / 3600000)
    : null;

  return (
    <div className="mt-2 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-indigo-300">
          {hbu.recommended_use}
        </span>
        <button
          onClick={() => handleAnalyze(true)}
          className="text-[10px] text-gray-500 hover:text-gray-300"
          title="Re-analyze"
        >
          ⟳
        </button>
      </div>

      <p className="text-[10px] text-gray-400">{hbu.zoning_basis}</p>

      {/* Key Metrics */}
      <div className="grid grid-cols-3 gap-2 text-center">
        {hbu.max_height_storeys != null && (
          <div className="bg-white/[0.04] rounded p-1.5">
            <div className="text-sm font-bold text-white">{hbu.max_height_storeys} st</div>
            <div className="text-[9px] text-gray-500">Height</div>
          </div>
        )}
        {hbu.max_fsr != null && (
          <div className="bg-white/[0.04] rounded p-1.5">
            <div className="text-sm font-bold text-white">{hbu.max_fsr}</div>
            <div className="text-[9px] text-gray-500">FSR</div>
          </div>
        )}
        {hbu.estimated_units != null && (
          <div className="bg-white/[0.04] rounded p-1.5">
            <div className="text-sm font-bold text-white">~{hbu.estimated_units}</div>
            <div className="text-[9px] text-gray-500">Units</div>
          </div>
        )}
      </div>

      {/* Buildable + Feasibility */}
      {hbu.buildable_sqft && (
        <div className="flex justify-between text-xs">
          <span className="text-gray-400">Buildable</span>
          <span className="text-white font-medium">
            {Number(hbu.buildable_sqft).toLocaleString()} SF
          </span>
        </div>
      )}
      <div className="flex justify-between text-xs">
        <span className="text-gray-400">Feasibility</span>
        <span className={`font-semibold ${verdictColor}`}>{verdictLabel}</span>
      </div>

      {/* Constraints */}
      {hbu.key_constraints.length > 0 && (
        <div>
          <button
            onClick={() => setShowConstraints(!showConstraints)}
            className="bg-transparent border-none text-gray-400 cursor-pointer flex items-center gap-1 p-0 text-[11px]"
          >
            <span className="text-[9px]">{showConstraints ? "▼" : "▶"}</span>
            Constraints ({hbu.key_constraints.length})
          </button>
          {showConstraints && (
            <ul className="mt-1 space-y-0.5">
              {hbu.key_constraints.map((c, i) => (
                <li key={i} className="text-[10px] text-yellow-400/80 pl-3">
                  • {c}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* AI Narrative */}
      {hbu.narrative && (
        <div>
          <button
            onClick={() => setShowNarrative(!showNarrative)}
            className="bg-transparent border-none text-gray-400 cursor-pointer flex items-center gap-1 p-0 text-[11px]"
          >
            <span className="text-[9px]">{showNarrative ? "▼" : "▶"}</span>
            AI Analysis
          </button>
          {showNarrative && (
            <div className="mt-1 text-[10px] text-gray-300 leading-relaxed whitespace-pre-line">
              {hbu.narrative}
            </div>
          )}
        </div>
      )}

      {/* Sources */}
      {data.sources.length > 0 && (
        <div className="text-[9px] text-gray-600">
          Sources: {data.sources.map((s) => s.title).join(", ")}
        </div>
      )}

      {/* Cache indicator */}
      {cachedAgo != null && cachedAgo > 0 && (
        <div className="text-[9px] text-gray-600 text-center">
          Cached {cachedAgo}h ago
        </div>
      )}

      {/* Confidence */}
      {data.confidence_score != null && (
        <div className="flex items-center gap-1 justify-center">
          <div className="h-1 flex-1 bg-white/[0.06] rounded overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded"
              style={{ width: `${data.confidence_score * 100}%` }}
            />
          </div>
          <span className="text-[9px] text-gray-500">
            {Math.round(data.confidence_score * 100)}% confidence
          </span>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Integrate into ParcelDetailPanel**

In `frontend/src/components/ParcelDetailPanel.tsx`:

1. Add import at the top:
   ```typescript
   import HBUAnalysisPanel from "./HBUAnalysis";
   ```

2. Add a new `CollapsibleSection` after the BeforeAfterComparison section (after the closing `</CollapsibleSection>` for "Before / After Bill 47"):
   ```tsx
   <CollapsibleSection title="Highest & Best Use" defaultOpen>
     <HBUAnalysisPanel pid={data.pid} />
   </CollapsibleSection>
   ```

**Step 3: Write the test**

Append to `tests/test_hbu_engine.py`:

```python
class TestHBUFrontend:
    """HBU frontend component tests."""

    def test_component_exists(self):
        assert os.path.exists("frontend/src/components/HBUAnalysis.tsx")

    def test_is_client_component(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert '"use client"' in content

    def test_api_client_exists(self):
        assert os.path.exists("frontend/src/lib/hbu-api.ts")

    def test_api_client_exports_functions(self):
        with open("frontend/src/lib/hbu-api.ts") as f:
            content = f.read()
        assert "getHBUAnalysis" in content
        assert "runHBUAnalysis" in content

    def test_component_shows_key_metrics(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "max_height_storeys" in content
        assert "max_fsr" in content
        assert "estimated_units" in content
        assert "buildable_sqft" in content

    def test_component_shows_feasibility(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "feasibility_verdict" in content
        assert "pencils" in content.lower()

    def test_component_has_analyze_button(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "Analyze" in content
        assert "handleAnalyze" in content

    def test_component_shows_narrative(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "narrative" in content
        assert "AI Analysis" in content

    def test_component_shows_constraints(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "key_constraints" in content
        assert "Constraints" in content

    def test_component_shows_confidence(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "confidence_score" in content
        assert "confidence" in content.lower()

    def test_integrated_in_detail_panel(self):
        with open("frontend/src/components/ParcelDetailPanel.tsx") as f:
            content = f.read()
        assert "HBUAnalysis" in content

    def test_component_has_loading_state(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "loading" in content.lower()
        assert "animate-pulse" in content

    def test_component_has_error_state(self):
        with open("frontend/src/components/HBUAnalysis.tsx") as f:
            content = f.read()
        assert "error" in content
        assert "Retry" in content
```

**Step 4: Run tests**

```bash
python3 -m pytest tests/test_hbu_engine.py::TestHBUFrontend -v
```

Expected: All PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/HBUAnalysis.tsx frontend/src/lib/hbu-api.ts frontend/src/components/ParcelDetailPanel.tsx tests/test_hbu_engine.py
git commit -m "feat: add HBU Analysis frontend component with on-demand LLM analysis"
```

---

## Epic 4: PDF Integration

### Task 8: HBU Section in Existing PDF Report

**Files:**
- Modify: `api/report_generator.py` — add `_build_hbu_section()` method

**Step 1: Write the test**

Append to `tests/test_hbu_engine.py`:

```python
class TestHBUPDFSection:
    """HBU section in PDF report."""

    def test_report_has_hbu_method(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "_build_hbu_section" in content

    def test_hbu_method_called_in_generate(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "self._build_hbu_section" in content

    def test_hbu_section_has_header(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "Highest & Best Use" in content

    def test_hbu_section_shows_recommendation(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "recommended_use" in content

    def test_hbu_section_shows_feasibility(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "feasibility_verdict" in content or "Feasibility" in content
```

**Step 2: Write the implementation**

In `api/report_generator.py`:

1. Add a new method `_build_hbu_section(self, pdf, parcel_data)` following the same pattern as `_build_before_after_section`:

```python
def _build_hbu_section(self, pdf, parcel_data):
    """Build Highest & Best Use analysis section."""
    hbu = getattr(parcel_data, "hbu_analysis", None)
    if not hbu:
        return

    analysis = hbu.get("highest_best_use", {})
    if not analysis.get("recommended_use"):
        return

    # Section header
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Highest & Best Use Analysis", ln=True)
    pdf.set_draw_color(100, 100, 100)
    pdf.line(self.left_margin, pdf.get_y(), self.page_width - self.right_margin, pdf.get_y())
    pdf.ln(4)

    # Recommendation
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(230, 230, 255)
    pdf.cell(0, 7, f"  Recommended: {analysis['recommended_use']}", fill=True, ln=True)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 5, f"  Basis: {analysis.get('zoning_basis', 'N/A')}", ln=True)
    pdf.ln(3)

    # Key metrics table
    col_widths = [45, 45, 45, 45]
    headers = ["Height", "FSR", "Est. Units", "Buildable SF"]
    values = [
        f"{analysis.get('max_height_storeys', '?')} storeys",
        f"{analysis.get('max_fsr', '?')}",
        f"~{analysis.get('estimated_units', '?')}",
        f"{int(analysis.get('buildable_sqft', 0)):,}" if analysis.get("buildable_sqft") else "?",
    ]

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(240, 240, 240)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 6, h, border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for i, v in enumerate(values):
        pdf.cell(col_widths[i], 6, v, border=1)
    pdf.ln(4)

    # Feasibility verdict
    verdict = analysis.get("feasibility_verdict", "unknown")
    verdict_label = {"pencils": "Pencils", "marginal": "Marginal", "does_not_pencil": "Does Not Pencil"}.get(verdict, verdict)
    if verdict == "pencils":
        pdf.set_fill_color(200, 255, 200)
    elif verdict == "marginal":
        pdf.set_fill_color(255, 255, 200)
    else:
        pdf.set_fill_color(255, 220, 220)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, f"  Feasibility: {verdict_label}", fill=True, ln=True)
    pdf.ln(3)

    # Constraints
    constraints = analysis.get("key_constraints", [])
    if constraints:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Constraints:", ln=True)
        pdf.set_font("Helvetica", "", 8)
        for c in constraints[:5]:
            pdf.cell(0, 4, f"  • {c}", ln=True)
        pdf.ln(2)

    # Narrative (truncated for in-report version)
    narrative = analysis.get("narrative", "")
    if narrative:
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 4, narrative[:800])
        pdf.ln(2)

    # Sources
    sources = hbu.get("sources", [])
    if sources:
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(120, 120, 120)
        source_text = "Sources: " + ", ".join(s.get("title", "") for s in sources[:5])
        pdf.cell(0, 4, source_text, ln=True)
        pdf.set_text_color(0, 0, 0)

    pdf.ln(4)
```

2. Call it in `generate_parcel_report()` after `self._build_before_after_section(pdf, parcel_data)`:

```python
self._build_hbu_section(pdf, parcel_data)
```

**Step 3: Run tests**

```bash
python3 -m pytest tests/test_hbu_engine.py::TestHBUPDFSection -v
```

Expected: All PASS.

**Step 4: Run full test suite**

```bash
python3 -m pytest tests/ -q --ignore=tests/test_mobile_responsive.py
```

Expected: All existing tests still pass.

**Step 5: Commit**

```bash
git add api/report_generator.py tests/test_hbu_engine.py
git commit -m "feat: add HBU analysis section to PDF report"
```

---

## Epic 5: Final Integration & Verification

### Task 9: Full Integration Test

**Step 1: Run the full test suite**

```bash
python3 -m pytest tests/ -q --ignore=tests/test_mobile_responsive.py
```

Expected: All 4923+ tests pass (original + new HBU tests).

**Step 2: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: No TypeScript errors.

**Step 3: Commit any remaining changes and push**

```bash
git add -A
git status
git commit -m "feat: complete HBU Engine — AI-powered Highest & Best Use analysis"
git push origin main
```

---

## Summary

| Task | What | Files | Commits |
|------|------|-------|---------|
| 1 | DB migration | `db/034_hbu_analyses.sql` | 1 |
| 2 | System prompts | `api/intelligence/hbu_prompts.py` | 1 |
| 3 | Engine orchestrator | `api/intelligence/hbu_engine.py` | 1 |
| 4 | API routes | `api/intelligence/hbu_routes.py`, `routes.py` | 1 |
| 5 | K2 document sources | `pipeline/sources.yaml` | 1 |
| 6 | Frontend API client | `frontend/src/lib/hbu-api.ts` | 1 |
| 7 | Frontend component | `HBUAnalysis.tsx`, `ParcelDetailPanel.tsx` | 1 |
| 8 | PDF integration | `api/report_generator.py` | 1 |
| 9 | Final verification | — | 1 |

**Total: 9 tasks, ~9 commits, estimated 7 new files + 3 modified files.**
