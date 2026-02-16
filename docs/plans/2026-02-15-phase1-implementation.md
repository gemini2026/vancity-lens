# Phase 1 Implementation Plan -- F01 HBU + F04 Pipeline Gap Closure

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the delta between existing codebase and PRD Phase 1 requirements for F01 (HBU Engine) and F04 (Development Pipeline Intelligence).

**Architecture:** Extend existing entitlement engine with heritage lookups and DB-driven market benchmarks. Enhance supply pipeline schema with application tracking and entity resolution. Add clustering API + frontend visualization. Extend watchlist alert system with new pipeline-specific rule types.

**Tech Stack:** FastAPI, asyncpg, PostgreSQL/PostGIS, pg_trgm, Next.js 15 / React 19, Mapbox GL JS

**Design Doc:** `docs/plans/2026-02-15-prd-gap-closure-design.md`

---

## Task 1: Heritage Integration into Entitlement Engine

**Files:**
- Modify: `api/entitlement.py:151-357`
- Modify: `api/models.py:123-161`
- Test: `tests/test_prd_phase1.py` (create)

### Step 1: Write the failing tests

Create `tests/test_prd_phase1.py`:

```python
"""Tests for PRD Phase 1 gap-closure features."""

import json
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestHeritageIntegration:
    """F01-A: Heritage designation in entitlement response."""

    def test_model_has_heritage_fields(self):
        from api.models import ParcelEntitlementResponse
        fields = ParcelEntitlementResponse.model_fields
        assert "heritage_site" in fields
        assert "heritage_category" in fields

    @pytest.mark.asyncio
    async def test_heritage_site_detected(self):
        """Parcel near a heritage site gets heritage_designation set."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-001",
            "civic_address": "123 Heritage St",
            "current_zoning": "RS-1",
            "lot_area_sqm": Decimal("600"),
            "assessed_value": 1500000,
            "asking_price": None,
            "geo_local_area": "Kitsilano",
            "lat": Decimal("49.265"),
            "lng": Decimal("-123.165"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = {"name": "Smith House", "category": "A"}

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        result = await compute_entitlement(conn, "100-001-001")
        assert result.heritage_site is True
        assert result.heritage_category == "A"

    @pytest.mark.asyncio
    async def test_no_heritage_site(self):
        """Parcel not near any heritage site gets heritage_site=False."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-002",
            "civic_address": "456 Normal Ave",
            "current_zoning": "RS-1",
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "asking_price": None,
            "geo_local_area": "Marpole",
            "lat": Decimal("49.210"),
            "lng": Decimal("-123.130"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = None

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        result = await compute_entitlement(conn, "100-001-002")
        assert result.heritage_site is False
        assert result.heritage_category is None

    @pytest.mark.asyncio
    async def test_heritage_category_a_adds_constraint(self):
        """Heritage Category A adds constraint to data_warnings."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-003",
            "civic_address": "789 Heritage Blvd",
            "current_zoning": "RS-1",
            "lot_area_sqm": Decimal("550"),
            "assessed_value": 2000000,
            "asking_price": None,
            "geo_local_area": "Strathcona",
            "lat": Decimal("49.275"),
            "lng": Decimal("-123.090"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = {"name": "Old Mill", "category": "A"}

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        result = await compute_entitlement(conn, "100-001-003")
        warning_msgs = [w.message for w in result.data_warnings]
        assert any("Heritage Category A" in m for m in warning_msgs)
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase1.py::TestHeritageIntegration -v`
Expected: FAIL -- `heritage_site` not in model fields

### Step 3: Add heritage fields to model

In `api/models.py`, add two fields to `ParcelEntitlementResponse` (after line 161, before any `@computed_field`):

```python
    heritage_site: bool = Field(default=False, description="Is parcel a designated heritage site")
    heritage_category: Optional[str] = Field(None, description="Heritage category: A, B, or C")
```

### Step 4: Add heritage query to entitlement engine

In `api/entitlement.py`:

1. Add SQL constant after `SQL_VIEW_CONE_CAP` (around line 50):

```python
SQL_HERITAGE_CHECK = """
    SELECT name, category
    FROM heritage_sites
    WHERE ST_DWithin(
        geom,
        (SELECT ST_Centroid(geom) FROM parcels WHERE pid = $1),
        0.0003
    )
    ORDER BY ST_Distance(
        geom,
        (SELECT ST_Centroid(geom) FROM parcels WHERE pid = $1)
    )
    LIMIT 1
"""
```

2. After the view cone query (after line 213), add:

```python
    # Heritage site check
    heritage_row = await conn.fetchrow(SQL_HERITAGE_CHECK, pid)
    heritage_site = False
    heritage_category = None
    heritage_warnings: list[DataQualityWarning] = []
    if heritage_row:
        heritage_site = True
        heritage_category = heritage_row["category"]
        cat = heritage_category or "Unknown"
        if cat == "A":
            heritage_warnings.append(DataQualityWarning(
                field="heritage",
                message="Heritage Category A -- demolition unlikely to be approved",
                severity="high",
            ))
        else:
            heritage_warnings.append(DataQualityWarning(
                field="heritage",
                message=f"Heritage Category {cat} -- additional review required",
                severity="medium",
            ))
```

3. In the return statement (around line 342), add the heritage fields:

```python
    heritage_site=heritage_site,
    heritage_category=heritage_category,
```

4. Include `heritage_warnings` in the `data_warnings` list:

```python
    data_warnings=warnings + heritage_warnings,
```

### Step 5: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase1.py::TestHeritageIntegration -v`
Expected: All PASS

### Step 6: Run full test suite for regression

Run: `python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5`
Expected: All existing tests still pass

### Step 7: Commit

```bash
git add api/entitlement.py api/models.py tests/test_prd_phase1.py
git commit -m "feat(F01): integrate heritage site check into entitlement engine"
```

---

## Task 2: Market Benchmarks Database Table

**Files:**
- Create: `db/042_market_benchmarks.sql`
- Create: `data/seed/market_benchmarks.json`
- Modify: `data/load_seed.py`
- Test: `tests/test_prd_phase1.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase1.py`:

```python
class TestMarketBenchmarks:
    """F01-B: Market benchmarks DB table and seed data."""

    def test_migration_file_exists(self):
        assert os.path.exists("db/042_market_benchmarks.sql")

    def test_seed_file_exists(self):
        assert os.path.exists("data/seed/market_benchmarks.json")

    def test_seed_data_has_required_fields(self):
        with open("data/seed/market_benchmarks.json") as f:
            data = json.load(f)
        assert len(data) > 0
        first = data[0]
        required = ["neighbourhood", "product_type", "revenue_per_sf",
                     "hard_cost_per_sf", "source", "effective_date"]
        for field in required:
            assert field in first, f"Missing field: {field}"

    def test_seed_data_covers_all_neighborhoods(self):
        with open("data/seed/market_benchmarks.json") as f:
            data = json.load(f)
        neighborhoods = {d["neighbourhood"] for d in data}
        assert len(neighborhoods) >= 20

    def test_seed_data_has_four_product_types(self):
        with open("data/seed/market_benchmarks.json") as f:
            data = json.load(f)
        product_types = {d["product_type"] for d in data}
        assert "condo" in product_types
        assert "rental" in product_types
        assert "commercial" in product_types
        assert "townhouse" in product_types

    def test_revenue_per_sf_is_positive(self):
        with open("data/seed/market_benchmarks.json") as f:
            data = json.load(f)
        for row in data:
            assert row["revenue_per_sf"] > 0

    def test_hard_cost_per_sf_is_positive(self):
        with open("data/seed/market_benchmarks.json") as f:
            data = json.load(f)
        for row in data:
            assert row["hard_cost_per_sf"] > 0
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase1.py::TestMarketBenchmarks -v`
Expected: FAIL -- migration file does not exist

### Step 3: Write the migration

Create `db/042_market_benchmarks.sql`:

```sql
-- Migration 042: Market benchmarks table
-- Replaces hardcoded REVENUE_PSF_BY_NEIGHBORHOOD with DB-driven values.

CREATE TABLE IF NOT EXISTS market_benchmarks (
    id SERIAL PRIMARY KEY,
    neighbourhood TEXT NOT NULL,
    product_type TEXT NOT NULL,
    revenue_per_sf NUMERIC(10,2) NOT NULL,
    hard_cost_per_sf NUMERIC(10,2) NOT NULL,
    source TEXT NOT NULL DEFAULT 'seed',
    effective_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(neighbourhood, product_type)
);

CREATE INDEX IF NOT EXISTS idx_market_benchmarks_neighbourhood
    ON market_benchmarks(neighbourhood);
CREATE INDEX IF NOT EXISTS idx_market_benchmarks_product_type
    ON market_benchmarks(product_type);
```

### Step 4: Generate seed data from hardcoded values

Create `data/seed/market_benchmarks.json` by extracting the 26 neighbourhoods x 4 product types from `api/neighborhood_revenue.py` REVENUE_PSF_BY_NEIGHBORHOOD dict. Each entry:
- `neighbourhood`: exact match to `geo_local_area` values in parcels table
- `product_type`: "condo", "rental", "commercial", or "townhouse"
- `revenue_per_sf`: from existing dict
- `hard_cost_per_sf`: defaults by building type (highrise condo: 450, midrise rental: 350, commercial: 300, townhouse: 280)
- `source`: "REBGV_seed_2025"
- `effective_date`: "2025-01-01"

Read the exact values from `api/neighborhood_revenue.py` lines 44-207 and convert to JSON array.

### Step 5: Add to seed loader

In `data/load_seed.py`, add market_benchmarks to the loading sequence:

```python
async def load_market_benchmarks(conn, data_dir):
    """Load market benchmark data."""
    path = os.path.join(data_dir, "market_benchmarks.json")
    if not os.path.exists(path):
        logger.info("No market_benchmarks.json found, skipping")
        return
    with open(path) as f:
        data = json.load(f)
    for row in data:
        await conn.execute(
            """
            INSERT INTO market_benchmarks (neighbourhood, product_type, revenue_per_sf,
                hard_cost_per_sf, source, effective_date)
            VALUES ($1, $2, $3, $4, $5, $6::date)
            ON CONFLICT (neighbourhood, product_type)
            DO UPDATE SET revenue_per_sf = EXCLUDED.revenue_per_sf,
                hard_cost_per_sf = EXCLUDED.hard_cost_per_sf,
                source = EXCLUDED.source,
                effective_date = EXCLUDED.effective_date
            """,
            row["neighbourhood"],
            row["product_type"],
            row["revenue_per_sf"],
            row["hard_cost_per_sf"],
            row["source"],
            row["effective_date"],
        )
    logger.info("Loaded %d market benchmark rows", len(data))
```

### Step 6: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase1.py::TestMarketBenchmarks -v`
Expected: All PASS

### Step 7: Commit

```bash
git add db/042_market_benchmarks.sql data/seed/market_benchmarks.json data/load_seed.py tests/test_prd_phase1.py
git commit -m "feat(F01): add market_benchmarks table and seed data"
```

---

## Task 3: Wire Market Benchmarks into Entitlement Value Estimation

**Files:**
- Modify: `api/entitlement.py:277-310`
- Test: `tests/test_prd_phase1.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase1.py`:

```python
class TestMarketBenchmarksIntegration:
    """F01-B: Entitlement engine uses DB market benchmarks."""

    @pytest.mark.asyncio
    async def test_value_estimate_uses_neighborhood_revenue(self):
        """Value estimate uses neighbourhood-specific revenue, not static $800."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-010",
            "civic_address": "100 Benchmark Dr",
            "current_zoning": "RS-1",
            "lot_area_sqm": Decimal("600"),
            "assessed_value": 1500000,
            "asking_price": None,
            "geo_local_area": "Kitsilano",
            "lat": Decimal("49.265"),
            "lng": Decimal("-123.165"),
        }
        entitlement_rows = [{
            "station_name": "Broadway-City Hall",
            "distance_m": Decimal("150"),
            "tier": 1,
            "bill47_storeys": 20,
            "bill47_fsr": Decimal("5.5"),
            "current_storeys": 2,
            "current_fsr": Decimal("0.6"),
        }]
        view_cone_row = None
        heritage_row = None
        benchmark_row = {
            "revenue_per_sf": Decimal("1200"),
            "hard_cost_per_sf": Decimal("450"),
            "effective_date": "2025-01-01",
        }

        conn.fetchrow = AsyncMock(side_effect=[
            parcel_row, view_cone_row, heritage_row, benchmark_row
        ])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        result = await compute_entitlement(conn, "100-001-010")
        assert result.value_estimate is not None
        assert result.value_estimate.price_per_sqft_assumption == Decimal("1200")

    @pytest.mark.asyncio
    async def test_market_data_timestamp_in_response(self):
        """Response includes market_data_date from benchmark effective_date."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-011",
            "civic_address": "200 Timestamp St",
            "current_zoning": "RS-1",
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "asking_price": None,
            "geo_local_area": "Marpole",
            "lat": Decimal("49.210"),
            "lng": Decimal("-123.130"),
        }
        entitlement_rows = [{
            "station_name": "Marine Drive",
            "distance_m": Decimal("200"),
            "tier": 1,
            "bill47_storeys": 20,
            "bill47_fsr": Decimal("5.5"),
            "current_storeys": 2,
            "current_fsr": Decimal("0.6"),
        }]
        view_cone_row = None
        heritage_row = None
        benchmark_row = {
            "revenue_per_sf": Decimal("800"),
            "hard_cost_per_sf": Decimal("350"),
            "effective_date": "2025-06-15",
        }

        conn.fetchrow = AsyncMock(side_effect=[
            parcel_row, view_cone_row, heritage_row, benchmark_row
        ])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        result = await compute_entitlement(conn, "100-001-011")
        assert result.market_data_date == "2025-06-15"
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase1.py::TestMarketBenchmarksIntegration -v`
Expected: FAIL -- entitlement still uses static $800

### Step 3: Modify entitlement engine to query market_benchmarks

In `api/entitlement.py`:

1. Add SQL constant:

```python
SQL_MARKET_BENCHMARK = """
    SELECT revenue_per_sf, hard_cost_per_sf, effective_date::text
    FROM market_benchmarks
    WHERE neighbourhood = $1 AND product_type = 'condo'
    LIMIT 1
"""
```

2. After the heritage check, add:

```python
    # Market benchmark lookup
    neighbourhood = parcel.get("geo_local_area", "")
    benchmark_row = await conn.fetchrow(SQL_MARKET_BENCHMARK, neighbourhood)
    if benchmark_row:
        price_per_sqft = Decimal(str(benchmark_row["revenue_per_sf"]))
        market_data_date = benchmark_row["effective_date"]
    else:
        price_per_sqft = Decimal("800")
        market_data_date = None
```

3. Remove the `price_per_sqft: Decimal = Decimal("800")` parameter from the function signature (line 154). Use the DB lookup value instead.

4. Set `market_data_date` in the return statement.

### Step 4: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase1.py::TestMarketBenchmarksIntegration -v`
Expected: All PASS

### Step 5: Run full test suite

Run: `python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5`
Expected: All pass (fix any callers of compute_entitlement that passed price_per_sqft)

### Step 6: Commit

```bash
git add api/entitlement.py tests/test_prd_phase1.py
git commit -m "feat(F01): wire market benchmarks into entitlement value estimation"
```

---

## Task 4: Staleness Warnings

**Files:**
- Modify: `api/entitlement.py`
- Test: `tests/test_prd_phase1.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase1.py`:

```python
from datetime import date


class TestStalenessWarnings:
    """F01-D: Data staleness warnings in entitlement response."""

    @pytest.mark.asyncio
    async def test_stale_assessment_warning(self):
        """Parcels with BC Assessment data > 1 year old get a staleness warning."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        stale_year = date.today().year - 2
        parcel_row = {
            "pid": "100-001-020",
            "civic_address": "300 Stale Data Rd",
            "current_zoning": "RS-1",
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "assessed_year": stale_year,
            "asking_price": None,
            "geo_local_area": "Dunbar-Southlands",
            "lat": Decimal("49.240"),
            "lng": Decimal("-123.190"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = None
        benchmark_row = None

        conn.fetchrow = AsyncMock(side_effect=[
            parcel_row, view_cone_row, heritage_row, benchmark_row
        ])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        result = await compute_entitlement(conn, "100-001-020")
        warning_msgs = [w.message for w in result.data_warnings]
        assert any(str(stale_year) in m for m in warning_msgs)

    @pytest.mark.asyncio
    async def test_stale_market_data_warning(self):
        """Market benchmarks older than 12 months trigger a staleness warning."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-021",
            "civic_address": "400 Old Market Ln",
            "current_zoning": "RS-1",
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "assessed_year": date.today().year,
            "asking_price": None,
            "geo_local_area": "Marpole",
            "lat": Decimal("49.210"),
            "lng": Decimal("-123.130"),
        }
        entitlement_rows = [{
            "station_name": "Marine Drive",
            "distance_m": Decimal("200"),
            "tier": 1,
            "bill47_storeys": 20,
            "bill47_fsr": Decimal("5.5"),
            "current_storeys": 2,
            "current_fsr": Decimal("0.6"),
        }]
        view_cone_row = None
        heritage_row = None
        benchmark_row = {
            "revenue_per_sf": Decimal("800"),
            "hard_cost_per_sf": Decimal("350"),
            "effective_date": "2024-01-01",
        }

        conn.fetchrow = AsyncMock(side_effect=[
            parcel_row, view_cone_row, heritage_row, benchmark_row
        ])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        result = await compute_entitlement(conn, "100-001-021")
        warning_msgs = [w.message for w in result.data_warnings]
        assert any("Cost data may be outdated" in m for m in warning_msgs)
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase1.py::TestStalenessWarnings -v`
Expected: FAIL

### Step 3: Add staleness checks

In `api/entitlement.py`, before the return statement, add:

```python
    # Staleness warnings (DV-F01-006, DV-F01-007)
    from datetime import date as date_cls
    current_year = date_cls.today().year
    assessed_year = parcel.get("assessed_year")
    if assessed_year and assessed_year < current_year - 1:
        warnings.append(DataQualityWarning(
            field="assessed_value",
            message=f"Assessment data is from {assessed_year} -- may not reflect current values",
            severity="medium",
        ))

    if market_data_date:
        md = date_cls.fromisoformat(market_data_date) if isinstance(market_data_date, str) else market_data_date
        if (date_cls.today() - md).days > 365:
            warnings.append(DataQualityWarning(
                field="market_data",
                message=f"Cost data may be outdated -- last updated {market_data_date}",
                severity="low",
            ))
```

Ensure `SQL_PARCEL_INFO` includes `assessed_year` in SELECT. If not, add it.

### Step 4: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase1.py::TestStalenessWarnings -v`
Expected: All PASS

### Step 5: Commit

```bash
git add api/entitlement.py tests/test_prd_phase1.py
git commit -m "feat(F01): add assessment and market data staleness warnings"
```

---

## Task 5: Input Disambiguation Endpoint

**Files:**
- Modify: `api/parcel_search.py:365-401`
- Test: `tests/test_prd_phase1.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase1.py`:

```python
class TestInputDisambiguation:
    """F01-C: Parcel search returns disambiguation list or error."""

    def test_search_endpoint_exists(self):
        with open("api/parcel_search.py") as f:
            content = f.read()
        assert "/parcels/search" in content

    def test_search_result_has_required_fields(self):
        from api.parcel_search import ParcelSearchResult
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(ParcelSearchResult)]
        assert "pid" in field_names
        assert "civic_address" in field_names
        assert "zoning" in field_names
        assert "lot_area_sqm" in field_names

    def test_error_message_for_no_match(self):
        """Search endpoint returns PRD-compliant error for no matches."""
        with open("api/parcel_search.py") as f:
            content = f.read()
        assert "could not be resolved" in content.lower() or "not found" in content.lower()
```

### Step 2: Run tests to verify current state

Run: `python3 -m pytest tests/test_prd_phase1.py::TestInputDisambiguation -v`
Note: Some may pass. Focus on ensuring the PRD error message exists.

### Step 3: Enhance search endpoint

In `api/parcel_search.py`, modify the search endpoint to return a structured disambiguation response:

1. Return format: `{"count": N, "results": [...], "disambiguation": true/false}`
2. Zero results: return 404 with `{"detail": "Address could not be resolved to a valid Vancouver parcel. Please verify the address and try again."}`
3. PID format detection: if input matches `NNN-NNN-NNN`, do direct PID lookup first

### Step 4: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase1.py::TestInputDisambiguation -v`
Expected: All PASS

### Step 5: Commit

```bash
git add api/parcel_search.py tests/test_prd_phase1.py
git commit -m "feat(F01): enhance parcel search with disambiguation and error messages"
```

---

## Task 6: Pipeline Schema Enhancement

**Files:**
- Create: `db/043_pipeline_schema_v2.sql`
- Modify: `api/intelligence/supply_pipeline.py:32-40`
- Test: `tests/test_prd_phase1.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase1.py`:

```python
class TestPipelineSchemaEnhancement:
    """F04-A: Enhanced supply_pipeline schema."""

    def test_migration_file_exists(self):
        assert os.path.exists("db/043_pipeline_schema_v2.sql")

    def test_migration_adds_application_id(self):
        with open("db/043_pipeline_schema_v2.sql") as f:
            content = f.read()
        assert "application_id" in content

    def test_migration_adds_application_type(self):
        with open("db/043_pipeline_schema_v2.sql") as f:
            content = f.read()
        assert "application_type" in content

    def test_pipeline_stage_enum_has_nine_stages(self):
        from api.intelligence.supply_pipeline import PipelineStage
        assert len(PipelineStage) == 9

    def test_pipeline_stage_has_enquiry(self):
        from api.intelligence.supply_pipeline import PipelineStage
        assert hasattr(PipelineStage, "ENQUIRY")

    def test_pipeline_stage_has_withdrawn(self):
        from api.intelligence.supply_pipeline import PipelineStage
        assert hasattr(PipelineStage, "WITHDRAWN")

    def test_pipeline_stage_has_refused(self):
        from api.intelligence.supply_pipeline import PipelineStage
        assert hasattr(PipelineStage, "REFUSED")
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase1.py::TestPipelineSchemaEnhancement -v`
Expected: FAIL

### Step 3: Write the migration

Create `db/043_pipeline_schema_v2.sql`:

```sql
-- Migration 043: Pipeline schema enhancement for PRD F04

ALTER TABLE supply_pipeline
    ADD COLUMN IF NOT EXISTS application_id TEXT,
    ADD COLUMN IF NOT EXISTS application_type TEXT;

CREATE INDEX IF NOT EXISTS idx_supply_pipeline_application_id
    ON supply_pipeline(application_id);
CREATE INDEX IF NOT EXISTS idx_supply_pipeline_application_type
    ON supply_pipeline(application_type);

COMMENT ON COLUMN supply_pipeline.pipeline_stage IS
    'One of: enquiry, application_submitted, under_staff_review, '
    'referred_to_public_hearing, approved, under_construction, '
    'completed, refused, withdrawn';

COMMENT ON COLUMN supply_pipeline.application_type IS
    'One of: rezoning, development_permit, building_permit';
```

### Step 4: Update PipelineStage enum

In `api/intelligence/supply_pipeline.py`, replace the PipelineStage enum (lines 32-40):

```python
class PipelineStage(str, Enum):
    ENQUIRY = "enquiry"
    APPLICATION_SUBMITTED = "application_submitted"
    UNDER_STAFF_REVIEW = "under_staff_review"
    REFERRED_TO_PUBLIC_HEARING = "referred_to_public_hearing"
    APPROVED = "approved"
    UNDER_CONSTRUCTION = "under_construction"
    COMPLETED = "completed"
    REFUSED = "refused"
    WITHDRAWN = "withdrawn"


STAGE_MIGRATION_MAP = {
    "rezoning_application": PipelineStage.APPLICATION_SUBMITTED,
    "public_hearing": PipelineStage.REFERRED_TO_PUBLIC_HEARING,
    "council_decision": PipelineStage.APPROVED,
    "development_permit": PipelineStage.UNDER_STAFF_REVIEW,
    "building_permit": PipelineStage.APPLICATION_SUBMITTED,
    "under_construction": PipelineStage.UNDER_CONSTRUCTION,
    "completed": PipelineStage.COMPLETED,
}
```

### Step 5: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase1.py::TestPipelineSchemaEnhancement -v`
Expected: All PASS

### Step 6: Fix any regressions in existing pipeline tests

Run: `python3 -m pytest tests/test_supply_pipeline.py -v --tb=short 2>&1 | tail -20`
Fix any failures from renamed enum values.

### Step 7: Commit

```bash
git add db/043_pipeline_schema_v2.sql api/intelligence/supply_pipeline.py tests/test_prd_phase1.py
git commit -m "feat(F04): enhance pipeline schema with application tracking and 9-stage enum"
```

---

## Task 7: Entity Resolution Pipeline

**Files:**
- Create: `db/044_enable_pg_trgm.sql`
- Modify: `api/intelligence/supply_pipeline.py`
- Test: `tests/test_prd_phase1.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase1.py`:

```python
class TestEntityResolution:
    """F04-B: Developer name normalization and fuzzy matching."""

    def test_normalize_developer_name(self):
        from api.intelligence.supply_pipeline import normalize_developer_name
        assert normalize_developer_name("Westbank Projects Corp") == "westbank projects"
        assert normalize_developer_name("Westbank Corp.") == "westbank"
        assert normalize_developer_name("  Concert Properties Ltd  ") == "concert properties"

    def test_normalize_strips_common_suffixes(self):
        from api.intelligence.supply_pipeline import normalize_developer_name
        assert normalize_developer_name("Polygon Homes Ltd.") == "polygon homes"
        assert normalize_developer_name("Ledingham McAllister Inc") == "ledingham mcallister"

    def test_pg_trgm_migration_exists(self):
        assert os.path.exists("db/044_enable_pg_trgm.sql")

    @pytest.mark.asyncio
    async def test_resolve_developer_exact_match(self):
        from api.intelligence.supply_pipeline import resolve_developer_entity
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"id": 1, "canonical_name": "Westbank"},
        ])
        entity_id = await resolve_developer_entity(conn, "Westbank Projects Corp")
        assert entity_id == 1

    @pytest.mark.asyncio
    async def test_resolve_developer_no_match_creates_new(self):
        from api.intelligence.supply_pipeline import resolve_developer_entity
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[None, None])
        conn.fetchval = AsyncMock(return_value=42)
        conn.execute = AsyncMock()
        entity_id = await resolve_developer_entity(conn, "Brand New Developer Corp")
        assert entity_id == 42
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase1.py::TestEntityResolution -v`
Expected: FAIL

### Step 3: Write pg_trgm migration

Create `db/044_enable_pg_trgm.sql`:

```sql
-- Migration 044: Enable pg_trgm for fuzzy developer name matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_developer_entities_trgm
    ON developer_entities USING gin (canonical_name gin_trgm_ops);
```

### Step 4: Implement entity resolution functions

In `api/intelligence/supply_pipeline.py`, add after imports:

```python
import re

DEVELOPER_SUFFIXES = re.compile(
    r"\b(corp\.?|corporation|ltd\.?|limited|inc\.?|incorporated|"
    r"projects?|holdings?|developments?|group|llc)\b",
    re.IGNORECASE,
)


def normalize_developer_name(name: str) -> str:
    """Normalize developer name for matching."""
    name = name.strip().lower()
    name = DEVELOPER_SUFFIXES.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(".")
    return name


async def resolve_developer_entity(conn, developer_name: str) -> int:
    """Resolve developer name to developer_entities.id.

    1. Normalize name
    2. Exact match against aliases or canonical_name
    3. Fuzzy match via pg_trgm (threshold 0.6)
    4. No match: create new entity
    """
    normalized = normalize_developer_name(developer_name)

    row = await conn.fetchrow(
        "SELECT id, canonical_name FROM developer_entities "
        "WHERE $1 = ANY(aliases) OR lower(canonical_name) = $1",
        normalized,
    )
    if row:
        return row["id"]

    row = await conn.fetchrow(
        "SELECT id, canonical_name, similarity(lower(canonical_name), $1) AS sim "
        "FROM developer_entities "
        "WHERE similarity(lower(canonical_name), $1) > 0.6 "
        "ORDER BY sim DESC LIMIT 1",
        normalized,
    )
    if row:
        await conn.execute(
            "UPDATE developer_entities "
            "SET aliases = array_append(aliases, $1) WHERE id = $2",
            normalized, row["id"],
        )
        return row["id"]

    new_id = await conn.fetchval(
        "INSERT INTO developer_entities (canonical_name, aliases) "
        "VALUES ($1, $2) RETURNING id",
        normalized, [normalized],
    )
    return new_id
```

### Step 5: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase1.py::TestEntityResolution -v`
Expected: All PASS

### Step 6: Commit

```bash
git add db/044_enable_pg_trgm.sql api/intelligence/supply_pipeline.py tests/test_prd_phase1.py
git commit -m "feat(F04): add developer entity resolution with fuzzy matching"
```

---

## Task 8: Clustering API Endpoint + Frontend

**Files:**
- Create: `api/intelligence/cluster_routes.py`
- Modify: `api/intelligence/routes.py`
- Modify: `frontend/src/components/MapView.tsx`
- Test: `tests/test_prd_phase1.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase1.py`:

```python
class TestClusteringAPI:
    """F04-C: Clustering detection API endpoint."""

    def test_cluster_routes_file_exists(self):
        assert os.path.exists("api/intelligence/cluster_routes.py")

    def test_cluster_router_has_get_endpoint(self):
        from api.intelligence.cluster_routes import router
        paths = [r.path for r in router.routes]
        assert any("cluster" in p for p in paths)
        methods = []
        for r in router.routes:
            methods.extend(getattr(r, "methods", []))
        assert "GET" in methods

    def test_cluster_routes_mounted(self):
        with open("api/intelligence/routes.py") as f:
            content = f.read()
        assert "cluster_routes" in content
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase1.py::TestClusteringAPI -v`
Expected: FAIL

### Step 3: Create cluster routes

Create `api/intelligence/cluster_routes.py`:

```python
"""Development Clustering API Routes.

Endpoint:
- GET /clusters -- Detect and return active development clusters
"""

from fastapi import APIRouter, Query, Request

from .clustering import detect_clusters

router = APIRouter(tags=["clustering"])


def _get_pool(request: Request):
    pool = getattr(request.app.state, "pool", None)
    if not pool:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Database connection not available")
    return pool


@router.get("/clusters")
async def get_clusters(
    request: Request,
    radius_m: int = Query(500, ge=100, le=2000),
    window_days: int = Query(90, ge=30, le=365),
    min_apps: int = Query(3, ge=2, le=10),
):
    """Detect development application clusters.

    Returns clusters where 3+ applications were filed within the specified
    radius and time window. Uses geodesic distance.
    """
    pool = _get_pool(request)
    clusters = await detect_clusters(
        pool,
        radius_m=radius_m,
        window_days=window_days,
        min_apps=min_apps,
    )
    return {
        "count": len(clusters),
        "clusters": [c.model_dump() for c in clusters],
        "params": {
            "radius_m": radius_m,
            "window_days": window_days,
            "min_apps": min_apps,
        },
    }
```

### Step 4: Mount in intelligence routes

In `api/intelligence/routes.py`, add:

```python
from . import cluster_routes
```

And after existing `router.include_router()` calls:

```python
router.include_router(cluster_routes.router)
```

### Step 5: Add cluster visualization to MapView

In `frontend/src/components/MapView.tsx`:
- Add state: `const [clusters, setClusters] = useState<any[]>([]);`
- Fetch on load: `GET /api/v1/intel/clusters`
- Render pulsing circles at each cluster centroid using Mapbox marker overlays

### Step 6: Run tests + frontend build

Run: `python3 -m pytest tests/test_prd_phase1.py::TestClusteringAPI -v`
Run: `cd frontend && npm run build`
Expected: All pass, no TS errors

### Step 7: Commit

```bash
git add api/intelligence/cluster_routes.py api/intelligence/routes.py frontend/src/components/MapView.tsx tests/test_prd_phase1.py
git commit -m "feat(F04): add clustering API endpoint and map visualization"
```

---

## Task 9: Saved Pipeline Filter Alerts

**Files:**
- Modify: `api/intelligence/alerts.py:27-35` (RuleType enum)
- Modify: `api/intelligence/alerts.py:542-589` (match_rule function)
- Test: `tests/test_prd_phase1.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase1.py`:

```python
class TestPipelineFilterAlerts:
    """F04-D: Watchlist rules for pipeline filtering."""

    def test_rule_type_has_pipeline_stage(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "PIPELINE_STAGE")

    def test_rule_type_has_application_type(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "APPLICATION_TYPE")

    def test_rule_type_has_height_range(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "HEIGHT_RANGE")

    def test_rule_type_has_unit_range(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "UNIT_RANGE")

    def test_match_pipeline_stage_rule(self):
        from api.intelligence.alerts import match_rule, WatchlistRule
        rule = WatchlistRule(rule_type="pipeline_stage", rule_value="approved")
        signal = {"signal_type": "stage_transition", "pipeline_stage": "approved"}
        assert match_rule(signal, rule) is True

    def test_match_pipeline_stage_no_match(self):
        from api.intelligence.alerts import match_rule, WatchlistRule
        rule = WatchlistRule(rule_type="pipeline_stage", rule_value="approved")
        signal = {"signal_type": "stage_transition", "pipeline_stage": "under_construction"}
        assert match_rule(signal, rule) is False

    def test_match_height_range_rule(self):
        from api.intelligence.alerts import match_rule, WatchlistRule
        rule = WatchlistRule(rule_type="height_range", rule_value="10-30")
        signal = {"proposed_storeys": 20}
        assert match_rule(signal, rule) is True

    def test_match_height_range_out_of_range(self):
        from api.intelligence.alerts import match_rule, WatchlistRule
        rule = WatchlistRule(rule_type="height_range", rule_value="10-30")
        signal = {"proposed_storeys": 5}
        assert match_rule(signal, rule) is False
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase1.py::TestPipelineFilterAlerts -v`
Expected: FAIL

### Step 3: Add new rule types to enum

In `api/intelligence/alerts.py`, extend RuleType enum:

```python
class RuleType(str, Enum):
    NEIGHBORHOOD = "neighborhood"
    ADDRESS = "address"
    ZONING = "zoning"
    SIGNAL_TYPE = "signal_type"
    KEYWORD = "keyword"
    SEVERITY = "severity"
    PIPELINE_STAGE = "pipeline_stage"
    APPLICATION_TYPE = "application_type"
    HEIGHT_RANGE = "height_range"
    UNIT_RANGE = "unit_range"
```

### Step 4: Add match logic

In `match_rule()`, add before the else clause:

```python
    elif rule_type == RuleType.PIPELINE_STAGE:
        pipeline_stage = (signal.get("pipeline_stage") or "").lower()
        return rule_value == pipeline_stage

    elif rule_type == RuleType.APPLICATION_TYPE:
        app_type = (signal.get("application_type") or "").lower()
        return rule_value == app_type

    elif rule_type == RuleType.HEIGHT_RANGE:
        try:
            parts = rule_value.split("-")
            range_min, range_max = int(parts[0]), int(parts[1])
            storeys = signal.get("proposed_storeys") or signal.get("height_after")
            if storeys is None:
                return False
            return range_min <= int(storeys) <= range_max
        except (ValueError, IndexError):
            return False

    elif rule_type == RuleType.UNIT_RANGE:
        try:
            parts = rule_value.split("-")
            range_min, range_max = int(parts[0]), int(parts[1])
            units = signal.get("unit_count") or signal.get("proposed_units")
            if units is None:
                return False
            return range_min <= int(units) <= range_max
        except (ValueError, IndexError):
            return False
```

### Step 5: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase1.py::TestPipelineFilterAlerts -v`
Expected: All PASS

### Step 6: Commit

```bash
git add api/intelligence/alerts.py tests/test_prd_phase1.py
git commit -m "feat(F04): add pipeline stage, type, and range-based alert rules"
```

---

## Task 10: Cross-Cutting -- Retrieval Audit Log

**Files:**
- Create: `db/045_retrieval_log.sql`
- Create: `db/046_data_freshness.sql`
- Create: `api/retrieval_logging.py`
- Test: `tests/test_prd_phase1.py` (append)

### Step 1: Write the failing tests

Append to `tests/test_prd_phase1.py`:

```python
class TestRetrievalAuditLog:
    """DI-005: Retrieval audit logging."""

    def test_retrieval_log_migration_exists(self):
        assert os.path.exists("db/045_retrieval_log.sql")

    def test_freshness_migration_exists(self):
        assert os.path.exists("db/046_data_freshness.sql")

    def test_logging_module_exists(self):
        assert os.path.exists("api/retrieval_logging.py")

    def test_log_retrieval_is_callable(self):
        from api.retrieval_logging import log_retrieval
        assert callable(log_retrieval)

    def test_retrieval_tracker_exists(self):
        from api.retrieval_logging import RetrievalTracker
        tracker = RetrievalTracker("DS-001", {"q": "test"})
        tracker.set_status(200)
        tracker.set_record_count(10)
        assert tracker.http_status == 200
        assert tracker.record_count == 10
        assert tracker.duration_ms >= 0
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_prd_phase1.py::TestRetrievalAuditLog -v`
Expected: FAIL

### Step 3: Write the migrations

Create `db/045_retrieval_log.sql`:

```sql
-- Migration 045: Retrieval audit log (DI-005)

CREATE TABLE IF NOT EXISTS retrieval_log (
    id SERIAL PRIMARY KEY,
    source_id TEXT NOT NULL,
    query_params JSONB,
    retrieval_timestamp TIMESTAMPTZ DEFAULT NOW(),
    http_status INT,
    record_count INT,
    duration_ms INT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_retrieval_log_source
    ON retrieval_log(source_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_log_timestamp
    ON retrieval_log(retrieval_timestamp DESC);
```

Create `db/046_data_freshness.sql`:

```sql
-- Migration 046: Data source freshness monitoring (DI-006)

CREATE TABLE IF NOT EXISTS data_source_freshness (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    expected_cadence_hours INT NOT NULL,
    last_successful_retrieval TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO data_source_freshness (source_id, source_name, expected_cadence_hours)
VALUES
    ('DS-001', 'City of Vancouver Open Data', 24),
    ('DS-002', 'BC Assessment', 2160),
    ('DS-004', 'TransLink GTFS', 2160),
    ('DS-005', 'BC Laws', 168),
    ('DS-006', 'Vancouver Council Agendas', 168),
    ('DS-007', 'BC Contaminated Sites Registry', 720),
    ('DS-008', 'StatsCan Web Data Service', 24),
    ('DS-009', 'CMHC Housing Data', 720),
    ('DS-010', 'Vancouver Heritage Register', 8760),
    ('DS-011', 'Vancouver View Cones', 8760),
    ('DS-012', 'Vancouver Neighbourhood Plans', 8760),
    ('DS-013', 'Local News Sources', 24),
    ('DS-014', 'BC Gazette', 168)
ON CONFLICT (source_id) DO NOTHING;
```

### Step 4: Write the logging module

Create `api/retrieval_logging.py`:

```python
"""Retrieval audit logging (DI-005) and data freshness monitoring (DI-006)."""

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RetrievalTracker:
    """Tracks a single external data retrieval for audit logging."""

    def __init__(self, source_id: str, query_params: Optional[dict] = None):
        self.source_id = source_id
        self.query_params = query_params or {}
        self.http_status: Optional[int] = None
        self.record_count: Optional[int] = None
        self.error_message: Optional[str] = None
        self._start = time.perf_counter()

    def set_status(self, status: int) -> None:
        self.http_status = status

    def set_record_count(self, count: int) -> None:
        self.record_count = count

    def set_error(self, message: str) -> None:
        self.error_message = message

    @property
    def duration_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)


@asynccontextmanager
async def log_retrieval(db_pool, source_id: str, query_params: Optional[dict] = None):
    """Context manager that logs a retrieval to the audit table.

    Usage:
        async with log_retrieval(pool, "DS-001", {"q": "permits"}) as tracker:
            resp = await client.get(url)
            tracker.set_status(resp.status_code)
            tracker.set_record_count(10)
    """
    tracker = RetrievalTracker(source_id, query_params)
    try:
        yield tracker
    except Exception as e:
        tracker.set_error(str(e))
        raise
    finally:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO retrieval_log
                        (source_id, query_params, http_status,
                         record_count, duration_ms, error_message)
                    VALUES ($1, $2::jsonb, $3, $4, $5, $6)
                    """,
                    tracker.source_id,
                    json.dumps(tracker.query_params),
                    tracker.http_status,
                    tracker.record_count,
                    tracker.duration_ms,
                    tracker.error_message,
                )
                if tracker.http_status and 200 <= tracker.http_status < 300:
                    await conn.execute(
                        """
                        UPDATE data_source_freshness
                        SET last_successful_retrieval = NOW(),
                            updated_at = NOW()
                        WHERE source_id = $1
                        """,
                        tracker.source_id,
                    )
        except Exception as log_err:
            logger.warning(
                "Failed to log retrieval for %s: %s",
                source_id, log_err,
            )
```

### Step 5: Run tests to verify they pass

Run: `python3 -m pytest tests/test_prd_phase1.py::TestRetrievalAuditLog -v`
Expected: All PASS

### Step 6: Commit

```bash
git add db/045_retrieval_log.sql db/046_data_freshness.sql api/retrieval_logging.py tests/test_prd_phase1.py
git commit -m "feat(DI): add retrieval audit logging and data freshness monitoring"
```

---

## Task 11: Final Integration Verification

### Step 1: Run full test suite

Run: `python3 -m pytest tests/ -q --tb=short 2>&1 | tail -10`
Expected: All tests pass (existing + new Phase 1 tests)

### Step 2: Verify frontend builds

Run: `cd frontend && npm run build`
Expected: No TypeScript errors

### Step 3: Count new tests

Run: `python3 -m pytest tests/test_prd_phase1.py -v --tb=short 2>&1 | tail -5`
Expected: ~35-40 new Phase 1 tests, all passing

### Step 4: Push

```bash
git push origin main
```

---

## Summary

| Task | Feature | What | New Files | Modified Files |
|------|---------|------|-----------|----------------|
| 1 | F01-A | Heritage integration | 0 | 3 |
| 2 | F01-B | Market benchmarks table + seed | 3 | 1 |
| 3 | F01-B | Wire benchmarks into entitlement | 0 | 2 |
| 4 | F01-D | Staleness warnings | 0 | 2 |
| 5 | F01-C | Input disambiguation | 0 | 2 |
| 6 | F04-A | Pipeline schema v2 | 1 | 2 |
| 7 | F04-B | Entity resolution | 1 | 2 |
| 8 | F04-C | Clustering API + map UI | 1 | 3 |
| 9 | F04-D | Pipeline filter alerts | 0 | 2 |
| 10 | DI | Retrieval logging + freshness | 3 | 1 |
| 11 | -- | Final integration verification | 0 | 0 |

**Total: 11 tasks, ~11 commits, 9 new files, ~20 file modifications, ~40 new tests.**
