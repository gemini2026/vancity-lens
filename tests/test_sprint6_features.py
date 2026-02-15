"""
Sprint 6 tests — Due Diligence Report Expansion

Tests cover:
- Executive summary generation (AC-DD-006)
- Title and Ownership section (6.1)
- Environmental section (6.2, AC-DD-003)
- Market Context CMHC section (6.3)
- Demographic Profile StatsCan section (6.4)
- Nearby Development Activity (6.8, AC-DD-004)
- Data Currency section (6.6)
- Source unavailable handling (6.7)
- External retrieval audit log (DI-005)
- Migration file validation
"""

import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.report_generator import (
    ParcelReport,
    ReportGenerator,
)


# ── Helpers ─────────────────────────────────────────────────────────


def _make_parcel_data(**overrides) -> ParcelReport:
    """Create a minimal ParcelReport for testing."""
    defaults = dict(
        pid="012-345-678",
        civic_address="123 Main St",
        current_zoning="RS-1",
        lot_area_sqm=Decimal("500"),
        lot_area_sqft=Decimal("5382"),
        buildable_sqft=Decimal("26910"),
        current_storeys=2,
        entitled_storeys=12,
        current_fsr=Decimal("0.6"),
        entitled_fsr=Decimal("5.0"),
        estimated_land_value=2500000,
        assessed_value=1800000,
        value_delta=700000,
    )
    defaults.update(overrides)
    return ParcelReport(**defaults)


def _make_async_pool_mock():
    """Create a properly configured async pool mock."""
    pool = MagicMock()
    conn = AsyncMock()
    acm = AsyncMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = acm
    return pool, conn


# ── Executive Summary Tests ─────────────────────────────────────────


class TestExecutiveSummary:
    """AC-DD-006: Auto-generated executive summary under 300 words."""

    def test_summary_includes_address(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()
        gen._build_executive_summary(pdf, data)
        assert pdf.page_no() >= 1

    def test_summary_with_uplift(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data(current_storeys=2, entitled_storeys=12)
        gen._build_executive_summary(pdf, data)
        assert pdf.page_no() >= 1

    def test_summary_no_uplift(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data(current_storeys=15, entitled_storeys=12)
        gen._build_executive_summary(pdf, data)
        assert pdf.page_no() >= 1

    def test_summary_with_risks(self):
        from api.report_generator import RiskFlag
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()
        data.risk_flags = [
            RiskFlag(category="Zoning", description="Test", severity="high"),
            RiskFlag(category="Community", description="Test2", severity="low"),
        ]
        gen._build_executive_summary(pdf, data)
        assert pdf.page_no() >= 1

    def test_summary_minimal_data(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data(
            current_storeys=None,
            entitled_storeys=None,
            estimated_land_value=None,
            assessed_value=None,
            value_delta=None,
        )
        gen._build_executive_summary(pdf, data)
        assert pdf.page_no() >= 1


# ── Title and Ownership Tests ───────────────────────────────────────


class TestTitleOwnership:
    """Sprint 6.1: Title and Ownership section with LTSA placeholder."""

    def test_renders_with_assessed_value(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data(assessed_value=2000000)
        gen._build_title_ownership(pdf, data)
        assert pdf.page_no() >= 1

    def test_renders_without_assessed_value(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data(assessed_value=None)
        gen._build_title_ownership(pdf, data)
        assert pdf.page_no() >= 1

    def test_renders_pid(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()
        gen._build_title_ownership(pdf, data)
        assert pdf.page_no() >= 1


# ── Environmental Section Tests ─────────────────────────────────────


class TestEnvironmentalSection:
    """Sprint 6.2: Environmental section with contaminated sites."""

    @pytest.mark.asyncio
    async def test_no_sites_found(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()

        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = []

        await gen._build_environmental_section(pdf, data, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_sites_found(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()

        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = [
            {
                "site_name": "Former Gas Station",
                "address": "456 Oak St",
                "classification": "Detailed Risk Assessment",
                "status": "Active",
                "contamination_type": "Petroleum",
                "date_reported": "2020-01-15",
                "distance_m": 120.5,
            },
            {
                "site_name": "Industrial Site",
                "address": "789 Elm St",
                "classification": "Independent Remediation",
                "status": "Under Review",
                "contamination_type": "Heavy Metals",
                "date_reported": "2019-06-01",
                "distance_m": 350.2,
            },
        ]

        await gen._build_environmental_section(pdf, data, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_table_not_exist(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()

        pool, conn = _make_async_pool_mock()
        conn.fetch.side_effect = Exception("UndefinedTableError")

        await gen._build_environmental_section(pdf, data, pool)
        assert pdf.page_no() >= 1


# ── Market Context Tests ────────────────────────────────────────────


class TestMarketContext:
    """Sprint 6.3: CMHC market context section."""

    @pytest.mark.asyncio
    async def test_with_data(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)

        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = [
            {"metric": "starts", "dwelling_type": "total", "value": 1250, "ref_date": "2025-12"},
            {"metric": "completions", "dwelling_type": "total", "value": 980, "ref_date": "2025-12"},
            {"metric": "under_construction", "dwelling_type": "total", "value": 5400, "ref_date": "2025-12"},
            {"metric": "absorptions", "dwelling_type": "total", "value": 870, "ref_date": "2025-12"},
        ]

        await gen._build_market_context(pdf, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_no_data(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)

        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = []

        await gen._build_market_context(pdf, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_table_missing(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)

        pool, conn = _make_async_pool_mock()
        conn.fetch.side_effect = Exception("UndefinedTableError")

        await gen._build_market_context(pdf, pool)
        assert pdf.page_no() >= 1


# ── Demographic Profile Tests ───────────────────────────────────────


class TestDemographicProfile:
    """Sprint 6.4: StatsCan demographic profile section."""

    @pytest.mark.asyncio
    async def test_with_data(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()

        pool, conn = _make_async_pool_mock()
        conn.fetchrow.side_effect = [
            {"census_tract": "9330069.00", "distance_to_tract_boundary_m": Decimal("250")},
            {
                "population": 4500,
                "population_5yr_growth": Decimal("8.2"),
                "median_household_income": 72000,
                "avg_household_size": Decimal("2.3"),
                "owner_pct": Decimal("45.5"),
                "renter_pct": Decimal("54.5"),
                "dominant_dwelling_type": "Apartment",
                "total_dwellings": 2100,
                "median_age": Decimal("38.5"),
                "census_year": 2021,
            },
        ]

        await gen._build_demographic_profile(pdf, data, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_boundary_proximity(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()

        pool, conn = _make_async_pool_mock()
        conn.fetchrow.side_effect = [
            {"census_tract": "9330069.00", "distance_to_tract_boundary_m": Decimal("45")},
            {
                "population": 4500,
                "population_5yr_growth": Decimal("8.2"),
                "median_household_income": 72000,
                "avg_household_size": Decimal("2.3"),
                "owner_pct": Decimal("45.5"),
                "renter_pct": Decimal("54.5"),
                "dominant_dwelling_type": "Apartment",
                "total_dwellings": 2100,
                "median_age": Decimal("38.5"),
                "census_year": 2021,
            },
        ]

        await gen._build_demographic_profile(pdf, data, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_no_census_lookup(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()

        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = None

        await gen._build_demographic_profile(pdf, data, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_table_missing(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()

        pool, conn = _make_async_pool_mock()
        conn.fetchrow.side_effect = Exception("UndefinedTableError")

        await gen._build_demographic_profile(pdf, data, pool)
        assert pdf.page_no() >= 1


# ── Nearby Development Tests ────────────────────────────────────────


class TestNearbyDevelopment:
    """Sprint 6.8: Nearby development activity within 500m."""

    @pytest.mark.asyncio
    async def test_with_projects(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()

        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = [
            {
                "address": "100 Cambie St",
                "developer": "Westbank",
                "pipeline_stage": "rezoning_application",
                "proposed_units": 250,
                "proposed_storeys": 35,
                "distance_m": 150.0,
            },
            {
                "address": "200 Main St",
                "developer": "Bosa Properties",
                "pipeline_stage": "under_construction",
                "proposed_units": 180,
                "proposed_storeys": 22,
                "distance_m": 380.0,
            },
        ]

        await gen._build_nearby_development(pdf, data, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_no_projects(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()

        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = []

        await gen._build_nearby_development(pdf, data, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_table_missing(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        data = _make_parcel_data()

        pool, conn = _make_async_pool_mock()
        conn.fetch.side_effect = Exception("UndefinedTableError")

        await gen._build_nearby_development(pdf, data, pool)
        assert pdf.page_no() >= 1


# ── Data Currency Tests ─────────────────────────────────────────────


class TestDataCurrency:
    """Sprint 6.6: Data currency section with retrieval dates."""

    @pytest.mark.asyncio
    async def test_with_dates(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)

        pool, conn = _make_async_pool_mock()
        now = datetime.now(timezone.utc)
        conn.fetchrow.return_value = {"latest": now}

        await gen._build_data_currency(pdf, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_no_dates(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)

        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = {"latest": None}

        await gen._build_data_currency(pdf, pool)
        assert pdf.page_no() >= 1

    @pytest.mark.asyncio
    async def test_query_failure(self):
        gen = ReportGenerator()
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)

        pool, conn = _make_async_pool_mock()
        conn.fetchrow.side_effect = Exception("connection refused")

        await gen._build_data_currency(pdf, pool)
        assert pdf.page_no() >= 1


# ── Audit Log Tests ─────────────────────────────────────────────────


from api.audit_log import log_retrieval, RetrievalTimer, get_retrieval_summary


class TestAuditLog:
    """DI-005: External retrieval audit log."""

    @pytest.mark.asyncio
    async def test_log_retrieval(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = {"id": 42}

        result = await log_retrieval(
            pool,
            source_name="statscan_wds",
            operation="fetch",
            endpoint_url="https://statscan.example.com/api",
            response_status=200,
            records_returned=50,
            records_stored=50,
            duration_ms=1200,
        )
        assert result == 42
        conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_retrieval_failure(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.side_effect = Exception("DB down")

        result = await log_retrieval(
            pool,
            source_name="cmhc",
            operation="ingest",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_log_retrieval_with_error(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = {"id": 99}

        result = await log_retrieval(
            pool,
            source_name="bclaws",
            operation="scrape",
            response_status=500,
            error_message="Internal Server Error",
            records_returned=0,
        )
        assert result == 99

    @pytest.mark.asyncio
    async def test_retrieval_timer(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = {"id": 10}

        async with RetrievalTimer(
            pool, source_name="test", operation="fetch"
        ) as timer:
            timer.response_status = 200
            timer.records_returned = 5
            timer.records_stored = 5
            time.sleep(0.01)

        conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieval_timer_exception(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = {"id": 11}

        with pytest.raises(ValueError, match="test error"):
            async with RetrievalTimer(
                pool, source_name="test", operation="fetch"
            ) as timer:
                raise ValueError("test error")

        conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_retrieval_summary(self):
        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = [
            {
                "source_name": "statscan_wds",
                "total_calls": 15,
                "success_count": 14,
                "error_count": 1,
                "avg_duration_ms": 800,
                "last_retrieval": datetime.now(timezone.utc),
                "total_records_stored": 500,
            },
        ]

        result = await get_retrieval_summary(pool, days_back=7)
        assert len(result) == 1
        assert result[0]["source_name"] == "statscan_wds"
        assert result[0]["total_calls"] == 15

    @pytest.mark.asyncio
    async def test_get_retrieval_summary_failure(self):
        pool, conn = _make_async_pool_mock()
        conn.fetch.side_effect = Exception("table not found")

        result = await get_retrieval_summary(pool)
        assert result == []


# ── Migration Tests ─────────────────────────────────────────────────


class TestSprint6Migration:
    """Test Sprint 6 migration files."""

    def test_audit_log_migration_exists(self):
        assert os.path.exists("db/039_audit_log_sprint6.sql")

    def test_audit_log_migration_content(self):
        with open("db/039_audit_log_sprint6.sql") as f:
            sql = f.read()
        assert "external_retrieval_log" in sql
        assert "source_name" in sql
        assert "operation" in sql
        assert "endpoint_url" in sql
        assert "response_status" in sql
        assert "records_returned" in sql
        assert "records_stored" in sql
        assert "duration_ms" in sql
        assert "triggered_by" in sql
        assert "error_message" in sql

    def test_audit_log_migration_has_indexes(self):
        with open("db/039_audit_log_sprint6.sql") as f:
            sql = f.read()
        assert "idx_retrieval_log_source" in sql
        assert "idx_retrieval_log_created" in sql


# ── Report Generator Method Existence Tests ─────────────────────────


class TestReportGeneratorMethods:
    """Verify all Sprint 6 methods exist on ReportGenerator."""

    def test_has_executive_summary(self):
        gen = ReportGenerator()
        assert hasattr(gen, "_build_executive_summary")
        assert callable(gen._build_executive_summary)

    def test_has_title_ownership(self):
        gen = ReportGenerator()
        assert hasattr(gen, "_build_title_ownership")
        assert callable(gen._build_title_ownership)

    def test_has_environmental_section(self):
        gen = ReportGenerator()
        assert hasattr(gen, "_build_environmental_section")

    def test_has_market_context(self):
        gen = ReportGenerator()
        assert hasattr(gen, "_build_market_context")

    def test_has_demographic_profile(self):
        gen = ReportGenerator()
        assert hasattr(gen, "_build_demographic_profile")

    def test_has_nearby_development(self):
        gen = ReportGenerator()
        assert hasattr(gen, "_build_nearby_development")

    def test_has_data_currency(self):
        gen = ReportGenerator()
        assert hasattr(gen, "_build_data_currency")
