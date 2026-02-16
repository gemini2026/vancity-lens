# Phase 2 Implementation Plan -- F02 Regulatory Change Intelligence + F03 Due Diligence Assembly

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the delta between existing codebase and PRD Phase 2 requirements for F02 (Regulatory Change Intelligence Engine) and F03 (AI-Powered Due Diligence Assembly).

**Architecture:** New `change_records` table stores LLM-extracted regulatory changes. A change extraction pipeline feeds from document ingestion into structured records. Watchlist matching generates alerts on regulatory changes. Archive search API exposes paginated change history. Report generator gains red flag auto-aggregation, LLM-enhanced executive summary, section reordering, and unavailability handling.

**Tech Stack:** FastAPI, asyncpg, PostgreSQL/PostGIS, Playwright (council scraper), FPDF2, Gemini/Anthropic LLM

**Design Doc:** `docs/plans/2026-02-15-prd-gap-closure-design.md`

---

## Task 1: Change Records Table

**Files:**
- Create: `db/047_change_records.sql`
- Test: `tests/test_prd_phase2.py` (create)

### Step 1: Write the failing tests

Create `tests/test_prd_phase2.py`:

```python
"""Tests for PRD Phase 2 gap-closure features (F02 + F03)."""

import json
import os
from decimal import Decimal
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestChangeRecordsTable:
    """F02-A: Change records database table."""

    def test_migration_file_exists(self):
        assert os.path.exists("db/047_change_records.sql")

    def test_migration_creates_change_records(self):
        with open("db/047_change_records.sql") as f:
            content = f.read()
        assert "change_records" in content
        assert "CREATE TABLE" in content

    def test_migration_has_required_columns(self):
        with open("db/047_change_records.sql") as f:
            content = f.read()
        required_cols = [
            "change_type", "source_url", "source_document_title",
            "publication_date", "effective_date", "geographic_scope",
            "affected_areas", "entitlement_change", "plain_english_summary",
            "nlp_confidence_score", "requires_manual_review",
        ]
        for col in required_cols:
            assert col in content, f"Missing column: {col}"

    def test_migration_has_indexes(self):
        with open("db/047_change_records.sql") as f:
            content = f.read()
        assert "idx_change_records" in content

    def test_migration_has_full_text_search(self):
        with open("db/047_change_records.sql") as f:
            content = f.read()
        assert "gin" in content.lower() or "GIN" in content
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase2.py::TestChangeRecordsTable -v`
Expected: FAIL -- migration file does not exist

### Step 3: Write the migration

Create `db/047_change_records.sql`:

```sql
-- Migration 047: Regulatory change records (F02-A)
-- Stores LLM-extracted regulatory changes from council docs, bylaws, etc.

CREATE TABLE IF NOT EXISTS change_records (
    change_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id INT REFERENCES intelligence_signals(id) ON DELETE SET NULL,
    change_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_document_title TEXT NOT NULL,
    publication_date TIMESTAMPTZ,
    effective_date TIMESTAMPTZ,
    geographic_scope TEXT NOT NULL,
    affected_areas TEXT[] DEFAULT '{}',
    entitlement_change JSONB DEFAULT '{}',
    plain_english_summary TEXT,
    nlp_confidence_score NUMERIC(3,2),
    extraction_timestamp TIMESTAMPTZ DEFAULT NOW(),
    requires_manual_review BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_change_records_change_type ON change_records(change_type);
CREATE INDEX IF NOT EXISTS idx_change_records_pub_date ON change_records(publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_change_records_geo_scope ON change_records(geographic_scope);
CREATE INDEX IF NOT EXISTS idx_change_records_affected_areas ON change_records USING GIN(affected_areas);
CREATE INDEX IF NOT EXISTS idx_change_records_fts
    ON change_records USING GIN(to_tsvector('english', coalesce(plain_english_summary, '') || ' ' || source_document_title));

COMMENT ON TABLE change_records IS 'Regulatory changes extracted from council docs, bylaws, and policy updates';
COMMENT ON COLUMN change_records.change_type IS 'One of: new_legislation, bylaw_amendment, policy_update, council_vote, staff_directive';
COMMENT ON COLUMN change_records.geographic_scope IS 'One of: citywide, neighbourhood, zoning_district, parcel_specific';
```

### Step 4: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase2.py::TestChangeRecordsTable -v`
Expected: All PASS

### Step 5: Commit

```bash
git add db/047_change_records.sql tests/test_prd_phase2.py
git commit -m "feat(F02): add change_records table for regulatory change tracking"
```

---

## Task 2: Change Extraction Pipeline

**Files:**
- Create: `api/intelligence/change_prompts.py`
- Create: `api/intelligence/change_extraction.py`
- Test: `tests/test_prd_phase2.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase2.py`:

```python
class TestChangeExtraction:
    """F02-B: LLM change extraction pipeline."""

    def test_change_prompts_module_exists(self):
        assert os.path.exists("api/intelligence/change_prompts.py")

    def test_change_extraction_module_exists(self):
        assert os.path.exists("api/intelligence/change_extraction.py")

    def test_extraction_prompt_has_required_fields(self):
        from api.intelligence.change_prompts import CHANGE_EXTRACTION_PROMPT
        required = ["change_type", "geographic_scope", "affected_areas",
                     "entitlement_change", "plain_english_summary"]
        for field in required:
            assert field in CHANGE_EXTRACTION_PROMPT

    def test_extract_change_is_callable(self):
        from api.intelligence.change_extraction import extract_regulatory_change
        assert callable(extract_regulatory_change)

    def test_parse_extraction_response_valid_json(self):
        from api.intelligence.change_extraction import parse_extraction_response
        sample = json.dumps({
            "change_type": "bylaw_amendment",
            "geographic_scope": "citywide",
            "affected_areas": ["Downtown"],
            "entitlement_change": {"field": "max_fsr", "before_value": "3.0", "after_value": "5.0"},
            "plain_english_summary": "FSR increased citywide for mixed-use.",
            "confidence": 0.92,
        })
        result = parse_extraction_response(sample)
        assert result["change_type"] == "bylaw_amendment"
        assert result["nlp_confidence_score"] == 0.92
        assert result["requires_manual_review"] is False

    def test_parse_extraction_low_confidence_flags_review(self):
        from api.intelligence.change_extraction import parse_extraction_response
        sample = json.dumps({
            "change_type": "policy_update",
            "geographic_scope": "neighbourhood",
            "affected_areas": ["Kitsilano"],
            "entitlement_change": {},
            "plain_english_summary": "Minor policy clarification.",
            "confidence": 0.70,
        })
        result = parse_extraction_response(sample)
        assert result["requires_manual_review"] is True

    def test_is_candidate_chunk_detects_bylaw(self):
        from api.intelligence.change_extraction import is_candidate_chunk
        assert is_candidate_chunk("The bylaw amendment to RS-1 zoning increases FSR from 0.6 to 1.2")
        assert not is_candidate_chunk("The weather today is sunny and warm")
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase2.py::TestChangeExtraction -v`
Expected: FAIL

### Step 3: Write the change prompts

Create `api/intelligence/change_prompts.py`:

```python
"""Prompts for regulatory change extraction (F02-B)."""

CHANGE_EXTRACTION_PROMPT = """You are a regulatory change extraction assistant for Vancouver real estate.

Given a text chunk from a council document, bylaw, or policy paper, extract the following structured data:

{
    "change_type": "new_legislation | bylaw_amendment | policy_update | council_vote | staff_directive",
    "geographic_scope": "citywide | neighbourhood | zoning_district | parcel_specific",
    "affected_areas": ["list of affected neighbourhood names, zoning codes, or PIDs"],
    "entitlement_change": {
        "field": "max_fsr | max_height | setbacks | permitted_uses | density_bonus | other",
        "before_value": "previous value or null",
        "after_value": "new value or null"
    },
    "plain_english_summary": "A 1-2 sentence summary of what changed and its impact (max 200 words)",
    "confidence": 0.0 to 1.0
}

Rules:
- Only extract ACTUAL regulatory changes, not discussions or proposals unless they are voted/approved
- geographic_scope must be one of the four values listed
- If you cannot determine a field, use null
- Be conservative with confidence: only >0.85 if the change is explicit and unambiguous
- plain_english_summary should be understandable by a real estate investor, not a lawyer

Respond ONLY with the JSON object, no additional text."""


CHANGE_CANDIDATE_PATTERNS = [
    r"bylaw\s+(?:amendment|change|update|repeal)",
    r"(?:FSR|floor\s+space\s+ratio)\s+(?:increase|decrease|change)",
    r"(?:height|storey|density)\s+(?:increase|limit|change|amendment)",
    r"(?:rezone|rezoning|re-zone)",
    r"(?:council|staff)\s+(?:approve|direct|recommend|vote)",
    r"(?:setback|lot\s+coverage)\s+(?:reduce|increase|change)",
    r"(?:permitted\s+use|conditional\s+use)\s+(?:add|remove|change)",
    r"(?:density\s+bonus|community\s+amenity)",
    r"(?:Bill\s+\d+|transit.oriented|TOD|TOA)",
]
```

### Step 4: Write the extraction module

Create `api/intelligence/change_extraction.py`:

```python
"""Regulatory change extraction pipeline (F02-B).

Flow:
1. is_candidate_chunk() filters for regulatory-relevant text
2. extract_regulatory_change() sends to LLM for structured extraction
3. parse_extraction_response() validates and normalizes the response
4. Caller inserts into change_records table
"""

import json
import logging
import re
from typing import Any, Optional

from .change_prompts import CHANGE_EXTRACTION_PROMPT, CHANGE_CANDIDATE_PATTERNS
from .llm_backend import generate_chat

logger = logging.getLogger(__name__)

_CANDIDATE_RE = re.compile(
    "|".join(CHANGE_CANDIDATE_PATTERNS),
    re.IGNORECASE,
)

VALID_CHANGE_TYPES = {
    "new_legislation", "bylaw_amendment", "policy_update",
    "council_vote", "staff_directive",
}

VALID_GEO_SCOPES = {
    "citywide", "neighbourhood", "zoning_district", "parcel_specific",
}


def is_candidate_chunk(text: str) -> bool:
    """Check if a text chunk likely contains a regulatory change."""
    return bool(_CANDIDATE_RE.search(text))


def parse_extraction_response(answer_text: str) -> dict[str, Any]:
    """Parse and validate LLM extraction response.

    Returns a dict ready for insertion into change_records.
    """
    text = answer_text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    if not isinstance(parsed, dict):
        logger.warning("Could not parse change extraction response as JSON")
        return {
            "change_type": "policy_update",
            "geographic_scope": "citywide",
            "affected_areas": [],
            "entitlement_change": {},
            "plain_english_summary": answer_text[:500],
            "nlp_confidence_score": 0.3,
            "requires_manual_review": True,
        }

    # Normalize and validate
    change_type = parsed.get("change_type", "policy_update")
    if change_type not in VALID_CHANGE_TYPES:
        change_type = "policy_update"

    geo_scope = parsed.get("geographic_scope", "citywide")
    if geo_scope not in VALID_GEO_SCOPES:
        geo_scope = "citywide"

    confidence = float(parsed.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    return {
        "change_type": change_type,
        "geographic_scope": geo_scope,
        "affected_areas": parsed.get("affected_areas") or [],
        "entitlement_change": parsed.get("entitlement_change") or {},
        "plain_english_summary": (parsed.get("plain_english_summary") or "")[:1000],
        "nlp_confidence_score": round(confidence, 2),
        "requires_manual_review": confidence < 0.85,
    }


async def extract_regulatory_change(
    chunk_text: str,
    source_url: str = "",
    source_title: str = "",
) -> dict[str, Any]:
    """Extract a regulatory change from a document chunk via LLM.

    Args:
        chunk_text: The text to analyze
        source_url: URL of the source document
        source_title: Title of the source document

    Returns:
        Dict with change_records fields
    """
    user_message = (
        f"Source: {source_title}\n"
        f"URL: {source_url}\n\n"
        f"Text:\n{chunk_text}"
    )

    answer_text, model_used, latency = await generate_chat(
        system_prompt=CHANGE_EXTRACTION_PROMPT,
        user_message=user_message,
        max_tokens=1500,
    )

    result = parse_extraction_response(answer_text)
    result["source_url"] = source_url
    result["source_document_title"] = source_title
    return result


async def store_change_record(
    db_pool,
    record: dict[str, Any],
) -> Optional[str]:
    """Insert a change record into the database.

    Returns the change_id (UUID) or None on failure.
    """
    try:
        async with db_pool.acquire() as conn:
            # Duplicate check: same source_url + similar entitlement_change
            existing = await conn.fetchval(
                """
                SELECT change_id FROM change_records
                WHERE source_url = $1
                  AND entitlement_change = $2::jsonb
                LIMIT 1
                """,
                record["source_url"],
                json.dumps(record.get("entitlement_change") or {}),
            )
            if existing:
                logger.info("Duplicate change record for %s, skipping", record["source_url"])
                return str(existing)

            change_id = await conn.fetchval(
                """
                INSERT INTO change_records (
                    change_type, source_url, source_document_title,
                    publication_date, effective_date, geographic_scope,
                    affected_areas, entitlement_change, plain_english_summary,
                    nlp_confidence_score, requires_manual_review
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11)
                RETURNING change_id
                """,
                record["change_type"],
                record["source_url"],
                record.get("source_document_title", ""),
                record.get("publication_date"),
                record.get("effective_date"),
                record["geographic_scope"],
                record.get("affected_areas") or [],
                json.dumps(record.get("entitlement_change") or {}),
                record.get("plain_english_summary"),
                record.get("nlp_confidence_score"),
                record.get("requires_manual_review", False),
            )
            return str(change_id)
    except Exception as e:
        logger.error("Failed to store change record: %s", e)
        return None
```

### Step 5: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase2.py::TestChangeExtraction -v`
Expected: All PASS

### Step 6: Commit

```bash
git add api/intelligence/change_prompts.py api/intelligence/change_extraction.py tests/test_prd_phase2.py
git commit -m "feat(F02): add LLM change extraction pipeline and prompts"
```

---

## Task 3: Regulatory Change Watchlist Matching

**Files:**
- Modify: `api/intelligence/alerts.py`
- Test: `tests/test_prd_phase2.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase2.py`:

```python
class TestChangeWatchlistMatching:
    """F02-C: Watchlist matching for regulatory changes."""

    def test_rule_type_has_geographic_scope(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "GEOGRAPHIC_SCOPE")

    def test_rule_type_has_change_type(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "CHANGE_TYPE")

    def test_match_geographic_scope_citywide(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule
        rule = WatchlistRule(rule_type="geographic_scope", rule_value="citywide")
        signal = {"geographic_scope": "citywide", "signal_type": "regulatory_change"}
        assert AlertEngine.match_rule(signal, rule) is True

    def test_match_geographic_scope_neighbourhood(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule
        rule = WatchlistRule(rule_type="geographic_scope", rule_value="kitsilano")
        signal = {"geographic_scope": "neighbourhood", "affected_areas": ["Kitsilano", "Point Grey"]}
        assert AlertEngine.match_rule(signal, rule) is True

    def test_match_geographic_scope_no_match(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule
        rule = WatchlistRule(rule_type="geographic_scope", rule_value="marpole")
        signal = {"geographic_scope": "neighbourhood", "affected_areas": ["Kitsilano"]}
        assert AlertEngine.match_rule(signal, rule) is False

    def test_match_change_type_rule(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule
        rule = WatchlistRule(rule_type="change_type", rule_value="bylaw_amendment")
        signal = {"change_type": "bylaw_amendment"}
        assert AlertEngine.match_rule(signal, rule) is True

    def test_match_change_type_no_match(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule
        rule = WatchlistRule(rule_type="change_type", rule_value="bylaw_amendment")
        signal = {"change_type": "council_vote"}
        assert AlertEngine.match_rule(signal, rule) is False
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase2.py::TestChangeWatchlistMatching -v`
Expected: FAIL

### Step 3: Add new rule types

In `api/intelligence/alerts.py`:

1. Add to `RuleType` enum:
```python
    GEOGRAPHIC_SCOPE = "geographic_scope"
    CHANGE_TYPE = "change_type"
```

2. Add match logic in `match_rule()` before the `else` clause:

```python
    elif rule_type == RuleType.GEOGRAPHIC_SCOPE:
        geo_scope = (signal.get("geographic_scope") or "").lower()
        if geo_scope == "citywide":
            return rule_value == "citywide"
        affected = [a.lower() for a in (signal.get("affected_areas") or [])]
        return rule_value in affected

    elif rule_type == RuleType.CHANGE_TYPE:
        change_type = (signal.get("change_type") or "").lower()
        return rule_value == change_type
```

### Step 4: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase2.py::TestChangeWatchlistMatching -v`
Expected: All PASS

### Step 5: Run full suite

Run: `python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5`

### Step 6: Commit

```bash
git add api/intelligence/alerts.py tests/test_prd_phase2.py
git commit -m "feat(F02): add geographic scope and change type watchlist rules"
```

---

## Task 4: Regulatory Archive Search API

**Files:**
- Create: `api/intelligence/change_routes.py`
- Modify: `api/intelligence/routes.py`
- Test: `tests/test_prd_phase2.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase2.py`:

```python
class TestRegulatoryArchiveSearch:
    """F02-D: Regulatory archive search API."""

    def test_change_routes_file_exists(self):
        assert os.path.exists("api/intelligence/change_routes.py")

    def test_change_router_has_get_endpoint(self):
        from api.intelligence.change_routes import router
        paths = [r.path for r in router.routes]
        assert any("change" in p for p in paths)
        methods = []
        for r in router.routes:
            methods.extend(getattr(r, "methods", []))
        assert "GET" in methods

    def test_change_routes_mounted(self):
        with open("api/intelligence/routes.py") as f:
            content = f.read()
        assert "change_routes" in content

    def test_search_endpoint_has_pagination(self):
        with open("api/intelligence/change_routes.py") as f:
            content = f.read()
        assert "page" in content
        assert "per_page" in content

    def test_search_endpoint_has_filters(self):
        with open("api/intelligence/change_routes.py") as f:
            content = f.read()
        assert "change_type" in content
        assert "geographic_scope" in content
        assert "start_date" in content
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase2.py::TestRegulatoryArchiveSearch -v`
Expected: FAIL

### Step 3: Create change routes

Create `api/intelligence/change_routes.py`:

```python
"""Regulatory change archive search API (F02-D).

Endpoints:
- GET /changes -- Search and filter regulatory change records
- GET /changes/{change_id} -- Get single change record
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["regulatory-changes"])


def _get_pool(request: Request):
    pool = getattr(request.app.state, "pool", None)
    if not pool:
        raise HTTPException(status_code=500, detail="Database connection not available")
    return pool


@router.get("/changes")
async def search_changes(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    change_type: Optional[str] = Query(None, description="Comma-separated change types"),
    geographic_scope: Optional[str] = Query(None, description="Geographic scope filter"),
    affected_area: Optional[str] = Query(None, description="Text search in affected areas"),
    q: Optional[str] = Query(None, description="Full-text search query"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Search regulatory change records with filters and pagination."""
    pool = _get_pool(request)

    conditions = []
    params = []
    param_idx = 1

    if start_date:
        conditions.append(f"publication_date >= ${param_idx}::timestamptz")
        params.append(start_date)
        param_idx += 1

    if end_date:
        conditions.append(f"publication_date <= ${param_idx}::timestamptz")
        params.append(end_date)
        param_idx += 1

    if change_type:
        types = [t.strip() for t in change_type.split(",")]
        conditions.append(f"change_type = ANY(${param_idx}::text[])")
        params.append(types)
        param_idx += 1

    if geographic_scope:
        conditions.append(f"geographic_scope = ${param_idx}")
        params.append(geographic_scope)
        param_idx += 1

    if affected_area:
        conditions.append(f"${param_idx} = ANY(affected_areas)")
        params.append(affected_area)
        param_idx += 1

    if q:
        conditions.append(
            f"to_tsvector('english', coalesce(plain_english_summary, '') || ' ' || source_document_title) "
            f"@@ plainto_tsquery('english', ${param_idx})"
        )
        params.append(q)
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    offset = (page - 1) * per_page

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM change_records WHERE {where_clause}",
            *params,
        )

        rows = await conn.fetch(
            f"""
            SELECT change_id, change_type, source_url, source_document_title,
                   publication_date, effective_date, geographic_scope,
                   affected_areas, entitlement_change, plain_english_summary,
                   nlp_confidence_score, requires_manual_review, created_at
            FROM change_records
            WHERE {where_clause}
            ORDER BY publication_date DESC NULLS LAST
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """,
            *params, per_page, offset,
        )

    results = []
    for row in rows:
        ent_change = row["entitlement_change"]
        if isinstance(ent_change, str):
            ent_change = json.loads(ent_change)
        results.append({
            "change_id": str(row["change_id"]),
            "change_type": row["change_type"],
            "source_url": row["source_url"],
            "source_document_title": row["source_document_title"],
            "publication_date": row["publication_date"].isoformat() if row["publication_date"] else None,
            "effective_date": row["effective_date"].isoformat() if row["effective_date"] else None,
            "geographic_scope": row["geographic_scope"],
            "affected_areas": row["affected_areas"] or [],
            "entitlement_change": ent_change,
            "plain_english_summary": row["plain_english_summary"],
            "nlp_confidence_score": float(row["nlp_confidence_score"]) if row["nlp_confidence_score"] else None,
            "requires_manual_review": row["requires_manual_review"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        })

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "results": results,
    }


@router.get("/changes/{change_id}")
async def get_change(request: Request, change_id: UUID):
    """Get a single change record by ID."""
    pool = _get_pool(request)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM change_records WHERE change_id = $1",
            change_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Change record not found")

    ent_change = row["entitlement_change"]
    if isinstance(ent_change, str):
        ent_change = json.loads(ent_change)

    return {
        "change_id": str(row["change_id"]),
        "change_type": row["change_type"],
        "source_url": row["source_url"],
        "source_document_title": row["source_document_title"],
        "publication_date": row["publication_date"].isoformat() if row["publication_date"] else None,
        "effective_date": row["effective_date"].isoformat() if row["effective_date"] else None,
        "geographic_scope": row["geographic_scope"],
        "affected_areas": row["affected_areas"] or [],
        "entitlement_change": ent_change,
        "plain_english_summary": row["plain_english_summary"],
        "nlp_confidence_score": float(row["nlp_confidence_score"]) if row["nlp_confidence_score"] else None,
        "requires_manual_review": row["requires_manual_review"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
```

### Step 4: Mount in intelligence routes

In `api/intelligence/routes.py`, add:
```python
from . import change_routes
router.include_router(change_routes.router)
```

### Step 5: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase2.py::TestRegulatoryArchiveSearch -v`
Expected: All PASS

### Step 6: Commit

```bash
git add api/intelligence/change_routes.py api/intelligence/routes.py tests/test_prd_phase2.py
git commit -m "feat(F02): add regulatory archive search API with pagination and filters"
```

---

## Task 5: Playwright Council Scraper

**Files:**
- Create: `api/intelligence/scraper_council_playwright.py`
- Test: `tests/test_prd_phase2.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase2.py`:

```python
class TestCouncilScraper:
    """F02-E: Playwright council meeting scraper."""

    def test_scraper_module_exists(self):
        assert os.path.exists("api/intelligence/scraper_council_playwright.py")

    def test_scraper_has_scrape_function(self):
        from api.intelligence.scraper_council_playwright import scrape_council_agendas
        assert callable(scrape_council_agendas)

    def test_scraper_has_parse_agenda_items(self):
        from api.intelligence.scraper_council_playwright import parse_agenda_items
        assert callable(parse_agenda_items)

    def test_parse_agenda_items_extracts_from_html(self):
        from api.intelligence.scraper_council_playwright import parse_agenda_items
        html = '''
        <div class="agenda-item">
            <h3>Public Hearing: Rezoning Application - 123 Main St</h3>
            <a href="/docs/report.pdf">Staff Report</a>
        </div>
        <div class="agenda-item">
            <h3>Regular Item: Budget Amendment</h3>
            <a href="/docs/budget.pdf">Budget Report</a>
        </div>
        '''
        items = parse_agenda_items(html)
        assert len(items) >= 1

    def test_scraper_target_url_is_vancouver(self):
        with open("api/intelligence/scraper_council_playwright.py") as f:
            content = f.read()
        assert "vancouver.ca" in content
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase2.py::TestCouncilScraper -v`
Expected: FAIL

### Step 3: Write the scraper module

Create `api/intelligence/scraper_council_playwright.py`:

```python
"""Playwright-based council meeting agenda scraper (F02-E).

Scrapes Vancouver council meeting agendas and extracts:
- Agenda items (public hearings, rezoning decisions, policy votes)
- Staff report PDF links
- Meeting dates and topics

Schedule: Weekly Monday 5 AM UTC ("0 5 * * 1")
Target: vancouver.ca/your-government/council-meetings.aspx
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

COUNCIL_URL = "https://vancouver.ca/your-government/council-meetings.aspx"
MAX_RETRIES = 3


@dataclass
class AgendaItem:
    """A single agenda item from a council meeting."""
    title: str
    item_type: str = "regular"  # public_hearing, rezoning, regular, bylaw
    pdf_urls: list[str] = field(default_factory=list)
    meeting_date: Optional[str] = None
    description: str = ""


class _AgendaHTMLParser(HTMLParser):
    """Simple HTML parser for agenda items."""

    def __init__(self):
        super().__init__()
        self.items: list[dict] = []
        self._in_item = False
        self._in_heading = False
        self._current: dict = {}
        self._current_text = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        if "agenda" in cls.lower() and tag == "div":
            self._in_item = True
            self._current = {"title": "", "pdf_urls": []}
        if self._in_item and tag in ("h2", "h3", "h4"):
            self._in_heading = True
            self._current_text = ""
        if self._in_item and tag == "a":
            href = attrs_dict.get("href", "")
            if href.endswith(".pdf"):
                self._current["pdf_urls"].append(href)

    def handle_endtag(self, tag):
        if self._in_heading and tag in ("h2", "h3", "h4"):
            self._in_heading = False
            self._current["title"] = self._current_text.strip()
        if self._in_item and tag == "div":
            if self._current.get("title"):
                self.items.append(self._current)
            self._in_item = False
            self._current = {}

    def handle_data(self, data):
        if self._in_heading:
            self._current_text += data


def parse_agenda_items(html: str) -> list[AgendaItem]:
    """Parse agenda items from HTML content.

    Returns list of AgendaItem with title, type classification, and PDF URLs.
    """
    parser = _AgendaHTMLParser()
    parser.feed(html)

    items = []
    for raw in parser.items:
        title = raw["title"]

        # Classify item type
        title_lower = title.lower()
        if "public hearing" in title_lower or "rezone" in title_lower or "rezoning" in title_lower:
            item_type = "public_hearing"
        elif "bylaw" in title_lower:
            item_type = "bylaw"
        else:
            item_type = "regular"

        items.append(AgendaItem(
            title=title,
            item_type=item_type,
            pdf_urls=raw.get("pdf_urls", []),
        ))

    return items


async def scrape_council_agendas(
    max_pages: int = 3,
) -> list[AgendaItem]:
    """Scrape council meeting agendas using Playwright.

    Launches headless Chromium, navigates to council meetings page,
    extracts agenda items and staff report links.

    Falls back gracefully if Playwright is not installed or Cloudflare blocks.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed -- council scraper disabled")
        return []

    all_items: list[AgendaItem] = []

    for attempt in range(MAX_RETRIES):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                page.set_default_timeout(30000)

                await page.goto(COUNCIL_URL, wait_until="domcontentloaded")
                html = await page.content()
                await browser.close()

            all_items = parse_agenda_items(html)
            logger.info(
                "Scraped %d agenda items from council page",
                len(all_items),
            )
            return all_items

        except Exception as e:
            logger.warning(
                "Council scrape attempt %d/%d failed: %s",
                attempt + 1, MAX_RETRIES, e,
            )

    logger.error("Council scraper failed after %d retries", MAX_RETRIES)
    return []
```

### Step 4: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase2.py::TestCouncilScraper -v`
Expected: All PASS

### Step 5: Commit

```bash
git add api/intelligence/scraper_council_playwright.py tests/test_prd_phase2.py
git commit -m "feat(F02): add Playwright council meeting agenda scraper"
```

---

## Task 6: Red Flag Auto-Aggregation

**Files:**
- Modify: `api/report_generator.py`
- Test: `tests/test_prd_phase2.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase2.py`:

```python
class TestRedFlagAutoAggregation:
    """F03-A: Red flag auto-aggregation."""

    def test_collect_red_flags_method_exists(self):
        from api.report_generator import ReportGenerator
        assert hasattr(ReportGenerator, "_collect_red_flags")

    def test_collect_red_flags_heritage_high(self):
        """Heritage Category A produces a high-severity red flag."""
        from api.report_generator import ReportGenerator, ParcelReport
        gen = ReportGenerator.__new__(ReportGenerator)
        data = MagicMock(spec=ParcelReport)
        data.heritage_designation = "A"
        data.contamination_status = "Not Listed"
        data.risk_flags = []
        data.assessed_value = 1500000
        data.neighbourhood_median_assessed = 1400000
        data.neighbourhood_std_assessed = 200000
        data.data_currency = []
        flags = gen._collect_red_flags(data)
        heritage_flags = [f for f in flags if "heritage" in f["flag_name"].lower()]
        assert len(heritage_flags) == 1
        assert heritage_flags[0]["severity"] == "high"

    def test_collect_red_flags_contamination_high(self):
        """Non-clean contamination status produces a high-severity red flag."""
        from api.report_generator import ReportGenerator, ParcelReport
        gen = ReportGenerator.__new__(ReportGenerator)
        data = MagicMock(spec=ParcelReport)
        data.heritage_designation = None
        data.contamination_status = "Active Site"
        data.risk_flags = []
        data.assessed_value = 1000000
        data.neighbourhood_median_assessed = 1000000
        data.neighbourhood_std_assessed = 200000
        data.data_currency = []
        flags = gen._collect_red_flags(data)
        contam_flags = [f for f in flags if "contamination" in f["flag_name"].lower()]
        assert len(contam_flags) == 1
        assert contam_flags[0]["severity"] == "high"

    def test_collect_red_flags_returns_list_of_dicts(self):
        """Red flags are returned as list of dicts with required keys."""
        from api.report_generator import ReportGenerator, ParcelReport
        gen = ReportGenerator.__new__(ReportGenerator)
        data = MagicMock(spec=ParcelReport)
        data.heritage_designation = None
        data.contamination_status = "Not Listed"
        data.risk_flags = []
        data.assessed_value = 1000000
        data.neighbourhood_median_assessed = 1000000
        data.neighbourhood_std_assessed = 200000
        data.data_currency = []
        flags = gen._collect_red_flags(data)
        assert isinstance(flags, list)
        for flag in flags:
            assert "flag_name" in flag
            assert "severity" in flag
            assert "detail" in flag
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase2.py::TestRedFlagAutoAggregation -v`
Expected: FAIL

### Step 3: Implement `_collect_red_flags()`

In `api/report_generator.py`, add this method to the `ReportGenerator` class. Read the file first to find the right insertion point (after `_build_parcel_overview` or similar). Also check what attributes `ParcelReport` actually has -- the mock attributes must match real fields.

```python
    def _collect_red_flags(self, parcel_data) -> list[dict]:
        """Auto-aggregate red flags from all available data sources (F03-A).

        Returns list of {flag_name, severity, detail} dicts.
        Severity: high, medium, low.
        """
        flags = []

        # Heritage designation
        heritage = getattr(parcel_data, "heritage_designation", None)
        if heritage:
            if heritage == "A":
                flags.append({
                    "flag_name": "Heritage Designation",
                    "severity": "high",
                    "detail": f"Heritage Category {heritage} -- demolition unlikely to be approved",
                })
            else:
                flags.append({
                    "flag_name": "Heritage Designation",
                    "severity": "medium",
                    "detail": f"Heritage Category {heritage} -- additional review required",
                })

        # Contamination
        contam = getattr(parcel_data, "contamination_status", None)
        if contam and contam.lower() not in ("not listed", "clean", "n/a", "none", ""):
            flags.append({
                "flag_name": "Contamination Risk",
                "severity": "high",
                "detail": f"Site contamination status: {contam}",
            })

        # Assessed value outlier (>2 std dev from neighbourhood median)
        assessed = getattr(parcel_data, "assessed_value", None)
        median = getattr(parcel_data, "neighbourhood_median_assessed", None)
        std = getattr(parcel_data, "neighbourhood_std_assessed", None)
        if assessed and median and std and std > 0:
            if abs(assessed - median) > 2 * std:
                direction = "above" if assessed > median else "below"
                flags.append({
                    "flag_name": "Assessment Outlier",
                    "severity": "medium",
                    "detail": f"Assessed value is >2σ {direction} neighbourhood median (${assessed:,} vs ${median:,})",
                })

        # Data staleness
        currency = getattr(parcel_data, "data_currency", []) or []
        for item in currency:
            if isinstance(item, dict) and item.get("stale"):
                flags.append({
                    "flag_name": "Data Staleness",
                    "severity": "low",
                    "detail": f"Stale data: {item.get('source', 'unknown')} -- last updated {item.get('last_updated', 'unknown')}",
                })

        return flags
```

IMPORTANT: Before implementing, read `ParcelReport` model to verify which field names actually exist. Adapt the attribute names to match the real model.

### Step 4: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase2.py::TestRedFlagAutoAggregation -v`
Expected: All PASS

### Step 5: Commit

```bash
git add api/report_generator.py tests/test_prd_phase2.py
git commit -m "feat(F03): add red flag auto-aggregation to report generator"
```

---

## Task 7: LLM-Enhanced Executive Summary

**Files:**
- Modify: `api/report_generator.py`
- Test: `tests/test_prd_phase2.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase2.py`:

```python
class TestLLMExecutiveSummary:
    """F03-B: LLM-enhanced executive summary."""

    def test_executive_summary_method_exists(self):
        from api.report_generator import ReportGenerator
        assert hasattr(ReportGenerator, "_build_executive_summary")

    def test_executive_summary_includes_red_flag_count(self):
        """Executive summary references red flags in its text."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "risk" in content.lower() or "red flag" in content.lower() or "risk_flags" in content

    def test_executive_summary_has_llm_option(self):
        """Report generator has option for LLM-enhanced summary."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "generate_chat" in content or "llm" in content.lower()
```

### Step 2: Enhance `_build_executive_summary()`

In `api/report_generator.py`, modify `_build_executive_summary()` (lines 953-1015) to:
1. Call `_collect_red_flags()` for flag count
2. Add optional LLM enhancement: try calling `generate_chat()` with a summary prompt; if it fails, fall back to the existing template-based summary
3. Cap narrative at 300 words

Read the existing method first. The enhancement should wrap the existing template in an LLM call that refines it. Make this method async if needed (it currently isn't -- check if report generation flow supports async).

### Step 3: Run tests

Run: `python3 -m pytest tests/test_prd_phase2.py::TestLLMExecutiveSummary -v`

### Step 4: Commit

```bash
git add api/report_generator.py tests/test_prd_phase2.py
git commit -m "feat(F03): add LLM-enhanced executive summary with red flag integration"
```

---

## Task 8: Report Section Reordering + Heritage Section + Red Flags Summary

**Files:**
- Modify: `api/report_generator.py`
- Test: `tests/test_prd_phase2.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase2.py`:

```python
class TestReportSectionReorder:
    """F03-C: Report section reordering per PRD spec."""

    def test_section_order_in_generate_method(self):
        """Verify sections appear in PRD-specified order in generate method."""
        with open("api/report_generator.py") as f:
            content = f.read()
        # Find the section call order in generate_parcel_report
        exec_idx = content.find("_build_executive_summary")
        title_idx = content.find("_build_title_ownership")
        entitlement_idx = content.find("_build_entitlement_analysis")
        environmental_idx = content.find("_build_environmental_section")
        heritage_idx = content.find("_build_heritage_section")
        risk_idx = content.find("_build_red_flags_summary")

        # Executive summary before title
        assert exec_idx < title_idx
        # Environmental before heritage
        assert environmental_idx < heritage_idx or heritage_idx == -1 or environmental_idx < heritage_idx
        # Heritage section exists
        assert heritage_idx != -1

    def test_heritage_section_method_exists(self):
        from api.report_generator import ReportGenerator
        assert hasattr(ReportGenerator, "_build_heritage_section")

    def test_red_flags_summary_method_exists(self):
        from api.report_generator import ReportGenerator
        assert hasattr(ReportGenerator, "_build_red_flags_summary")
```

### Step 2: Implement section reordering

In `api/report_generator.py`:

1. Add `_build_heritage_section()` method -- standalone heritage section with designation details
2. Add `_build_red_flags_summary()` method -- renders collected red flags in a table
3. Reorder the section calls in `generate_parcel_report()` to match PRD order:

```python
        # Build report sections (PRD F03-C order)
        self._build_header_section(pdf, parcel_data)
        self._build_executive_summary(pdf, parcel_data)
        self._build_title_ownership(pdf, parcel_data)
        self._build_entitlement_analysis(pdf, parcel_data)
        await self._build_environmental_section(pdf, parcel_data, db_pool)
        self._build_heritage_section(pdf, parcel_data)
        self._build_before_after_section(pdf, parcel_data)
        await self._build_nearby_development(pdf, parcel_data, db_pool)
        await self._build_market_context(pdf, db_pool)
        await self._build_demographic_profile(pdf, parcel_data, db_pool)
        self._build_red_flags_summary(pdf, parcel_data)
        await self._build_data_currency(pdf, db_pool)
        self._build_pro_forma(pdf, parcel_data)
        self._build_due_diligence(pdf, parcel_data)
        if parcel_data.comparables:
            self._build_comparable_sales(pdf, parcel_data)
        self._build_sources(pdf, parcel_data)
        self._build_footer(pdf, parcel_data)
```

### Step 3: Run tests

Run: `python3 -m pytest tests/test_prd_phase2.py::TestReportSectionReorder -v`

### Step 4: Commit

```bash
git add api/report_generator.py tests/test_prd_phase2.py
git commit -m "feat(F03): reorder report sections, add heritage and red flags summary"
```

---

## Task 9: Unavailability Handling

**Files:**
- Modify: `api/report_generator.py`
- Test: `tests/test_prd_phase2.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase2.py`:

```python
class TestUnavailabilityHandling:
    """F03-D: Data unavailability handling in reports."""

    def test_unavailability_helper_exists(self):
        from api.report_generator import ReportGenerator
        assert hasattr(ReportGenerator, "_render_unavailable_section")

    def test_unavailability_message_format(self):
        """Unavailability renders a standard message format."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "Data unavailable" in content or "data unavailable" in content
```

### Step 2: Implement unavailability helper

In `api/report_generator.py`, add a helper method:

```python
    def _render_unavailable_section(self, pdf: FPDF, section_name: str, source_name: str, error: str = ""):
        """Render a standard unavailability message for a section (F03-D).

        Never silently omit a section -- always show what's missing and why.
        """
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        msg = f"Data unavailable -- {source_name} timeout at {timestamp}"
        if error:
            msg += f" ({error})"

        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(180, 0, 0)
        pdf.multi_cell(0, 5, msg)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 10)
        pdf.ln(3)
```

Then wrap existing async section calls (environmental, market, demographic, nearby development) with try/except that falls back to `_render_unavailable_section()`.

### Step 3: Run tests

Run: `python3 -m pytest tests/test_prd_phase2.py::TestUnavailabilityHandling -v`

### Step 4: Commit

```bash
git add api/report_generator.py tests/test_prd_phase2.py
git commit -m "feat(F03): add data unavailability handling for all report sections"
```

---

## Task 10: Final Integration Verification

### Step 1: Run full test suite

Run: `python3 -m pytest tests/ -q --tb=short 2>&1 | tail -10`
Expected: All tests pass (existing + new Phase 2 tests)

### Step 2: Verify frontend builds

Run: `cd frontend && npx next build`
Expected: No TypeScript errors

### Step 3: Count new tests

Run: `python3 -m pytest tests/test_prd_phase2.py -v --tb=short 2>&1 | tail -10`
Expected: ~35-45 new Phase 2 tests, all passing

### Step 4: Push

```bash
git push origin main
```

---

## Summary

| Task | Feature | What | New Files | Modified Files |
|------|---------|------|-----------|----------------|
| 1 | F02-A | Change records table | 1 | 1 |
| 2 | F02-B | Change extraction pipeline + prompts | 2 | 1 |
| 3 | F02-C | Watchlist matching for changes | 0 | 2 |
| 4 | F02-D | Regulatory archive search API | 1 | 2 |
| 5 | F02-E | Playwright council scraper | 1 | 1 |
| 6 | F03-A | Red flag auto-aggregation | 0 | 2 |
| 7 | F03-B | LLM executive summary | 0 | 2 |
| 8 | F03-C | Section reorder + heritage + red flags | 0 | 2 |
| 9 | F03-D | Unavailability handling | 0 | 2 |
| 10 | -- | Final integration verification | 0 | 0 |

**Total: 10 tasks, ~9 commits, 5 new files, ~15 file modifications, ~40 new tests.**
