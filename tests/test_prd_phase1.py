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
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("600"),
            "assessed_value": 1500000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Kitsilano",
            "lat": Decimal("49.265"),
            "lng": Decimal("-123.165"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = {"name": "Smith House", "category": "A"}

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row, None])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
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
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Marpole",
            "lat": Decimal("49.210"),
            "lng": Decimal("-123.130"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = None

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row, None])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
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
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("550"),
            "assessed_value": 2000000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Strathcona",
            "lat": Decimal("49.275"),
            "lng": Decimal("-123.090"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = {"name": "Old Mill", "category": "A"}

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row, None])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-003")
        warning_msgs = [w.message for w in result.data_warnings]
        assert any("Heritage Category A" in m for m in warning_msgs)

    @pytest.mark.asyncio
    async def test_heritage_category_b_adds_warning(self):
        """Heritage Category B adds a medium-priority warning."""
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-004",
            "civic_address": "321 Heritage Ct",
            "current_zoning": "RS-1",
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1200000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Kitsilano",
            "lat": Decimal("49.265"),
            "lng": Decimal("-123.165"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = {"name": "Historic Building", "category": "B"}

        conn.fetchrow = AsyncMock(side_effect=[parcel_row, view_cone_row, heritage_row, None])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-004")
        assert result.heritage_site is True
        assert result.heritage_category == "B"
        warning_msgs = [w.message for w in result.data_warnings]
        assert any("Heritage Category B" in m and "Additional review" in m for m in warning_msgs)


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
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("600"),
            "assessed_value": 1500000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Kitsilano",
            "lat": Decimal("49.265"),
            "lng": Decimal("-123.165"),
        }
        entitlement_rows = [{
            "station_name": "Broadway-City Hall",
            "distance_m": Decimal("150"),
            "tier": 1,
            "max_storeys": 20,
            "max_fsr": Decimal("5.5"),
            "current_height": None,
            "current_fsr": None,
        }]
        view_cone_row = None
        heritage_row = None
        benchmark_row = {
            "revenue_per_sf": Decimal("1200"),
            "hard_cost_per_sf": Decimal("450"),
            "effective_date": "2025-01-01",
        }

        # Note: fetchrow order is: parcel, view_cone, heritage, benchmark
        conn.fetchrow = AsyncMock(side_effect=[
            parcel_row, view_cone_row, heritage_row, benchmark_row
        ])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
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
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Marpole",
            "lat": Decimal("49.210"),
            "lng": Decimal("-123.130"),
        }
        entitlement_rows = [{
            "station_name": "Marine Drive",
            "distance_m": Decimal("200"),
            "tier": 1,
            "max_storeys": 20,
            "max_fsr": Decimal("5.5"),
            "current_height": None,
            "current_fsr": None,
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

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-011")
        assert result.market_data_date == "2025-06-15"

    @pytest.mark.asyncio
    async def test_fallback_to_default_when_no_benchmark(self):
        """When no benchmark row found, falls back to $800/sqft."""
        from api.entitlement import compute_entitlement, MARKET_DATA_DATE

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-012",
            "civic_address": "300 Fallback Ln",
            "current_zoning": "RS-1",
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "UnknownNeighbourhood",
            "lat": Decimal("49.210"),
            "lng": Decimal("-123.130"),
        }
        entitlement_rows = [{
            "station_name": "Marine Drive",
            "distance_m": Decimal("200"),
            "tier": 1,
            "max_storeys": 20,
            "max_fsr": Decimal("5.5"),
            "current_height": None,
            "current_fsr": None,
        }]

        # benchmark returns None (no match)
        conn.fetchrow = AsyncMock(side_effect=[
            parcel_row, None, None, None
        ])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-012")
        assert result.value_estimate is not None
        assert result.value_estimate.price_per_sqft_assumption == Decimal("800")
        assert result.market_data_date == MARKET_DATA_DATE


class TestStalenessWarnings:
    """F01-D: Data staleness warnings in entitlement response."""

    @pytest.mark.asyncio
    async def test_stale_assessment_warning(self):
        """Parcels with BC Assessment data > 1 year old get a staleness warning."""
        from datetime import date
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        stale_year = date.today().year - 2
        parcel_row = {
            "pid": "100-001-020",
            "civic_address": "300 Stale Data Rd",
            "current_zoning": "RS-1",
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "assessed_year": stale_year,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
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

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
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
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "assessed_year": 2026,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Marpole",
            "lat": Decimal("49.210"),
            "lng": Decimal("-123.130"),
        }
        entitlement_rows = [{
            "station_name": "Marine Drive",
            "distance_m": Decimal("200"),
            "tier": 1,
            "max_storeys": 20,
            "max_fsr": Decimal("5.5"),
            "current_height": 2,
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

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-021")
        warning_msgs = [w.message for w in result.data_warnings]
        assert any("Cost data may be outdated" in m for m in warning_msgs)

    @pytest.mark.asyncio
    async def test_no_stale_assessment_when_current(self):
        """Parcels with current-year assessment data do NOT get a staleness warning."""
        from datetime import date
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        parcel_row = {
            "pid": "100-001-022",
            "civic_address": "500 Fresh Data Ave",
            "current_zoning": "RS-1",
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "assessed_year": date.today().year,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Kitsilano",
            "lat": Decimal("49.265"),
            "lng": Decimal("-123.165"),
        }
        entitlement_rows = []
        view_cone_row = None
        heritage_row = None
        benchmark_row = None

        conn.fetchrow = AsyncMock(side_effect=[
            parcel_row, view_cone_row, heritage_row, benchmark_row
        ])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-022")
        stale_codes = [w.code for w in result.data_warnings if w.code == "STALE_ASSESSMENT"]
        assert len(stale_codes) == 0

    @pytest.mark.asyncio
    async def test_no_stale_market_when_recent(self):
        """Market benchmarks less than 12 months old do NOT trigger staleness."""
        from datetime import date, timedelta
        from api.entitlement import compute_entitlement

        conn = AsyncMock()
        recent_date = (date.today() - timedelta(days=100)).isoformat()
        parcel_row = {
            "pid": "100-001-023",
            "civic_address": "600 Recent Mkt Blvd",
            "current_zoning": "RS-1",
            "current_height": None,
            "current_fsr": None,
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 1000000,
            "assessed_year": date.today().year,
            "asking_price": None,
            "land_value": None,
            "improvement_value": None,
            "year_built": None,
            "geo_local_area": "Marpole",
            "lat": Decimal("49.210"),
            "lng": Decimal("-123.130"),
        }
        entitlement_rows = [{
            "station_name": "Marine Drive",
            "distance_m": Decimal("200"),
            "tier": 1,
            "max_storeys": 20,
            "max_fsr": Decimal("5.5"),
            "current_height": 2,
            "current_fsr": Decimal("0.6"),
        }]
        view_cone_row = None
        heritage_row = None
        benchmark_row = {
            "revenue_per_sf": Decimal("800"),
            "hard_cost_per_sf": Decimal("350"),
            "effective_date": recent_date,
        }

        conn.fetchrow = AsyncMock(side_effect=[
            parcel_row, view_cone_row, heritage_row, benchmark_row
        ])
        conn.fetch = AsyncMock(return_value=entitlement_rows)

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):
            result = await compute_entitlement(conn, "100-001-023")
        stale_codes = [w.code for w in result.data_warnings if w.code == "STALE_MARKET_DATA"]
        assert len(stale_codes) == 0


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
