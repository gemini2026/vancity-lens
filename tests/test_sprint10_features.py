"""
Sprint 10 tests — Cross-Feature Requirements

Tests cover:
- Data freshness admin dashboard (10.1)
- Multi-source conflict precedence (10.2)
- Pacific Time display utility (10.3)
- Sources & methodology in reports (10.4)
"""

import os
from datetime import datetime, timezone, timedelta

import pytest

from api.entitlement import (
    SOURCE_PRECEDENCE,
    resolve_source_conflict,
)


# ── 10.1: Data Freshness Admin Dashboard ─────────────────────────


class TestDataFreshnessDashboard:
    """Sprint 10.1: Data freshness admin endpoint and frontend."""

    def test_admin_freshness_endpoint_exists(self):
        """The /api/v1/admin/data-freshness route is registered."""
        from api.admin import router
        paths = [r.path for r in router.routes]
        assert any("data-freshness" in p for p in paths)

    def test_dashboard_component_exists(self):
        """DataFreshnessDashboard.tsx exists."""
        assert os.path.exists("frontend/src/components/DataFreshnessDashboard.tsx")

    def test_dashboard_is_client_component(self):
        """DataFreshnessDashboard uses 'use client' directive."""
        with open("frontend/src/components/DataFreshnessDashboard.tsx") as f:
            content = f.read()
        assert '"use client"' in content

    def test_dashboard_fetches_admin_api(self):
        """Dashboard fetches from the admin freshness endpoint."""
        with open("frontend/src/components/DataFreshnessDashboard.tsx") as f:
            content = f.read()
        assert "/api/v1/admin/data-freshness" in content

    def test_dashboard_shows_staleness_levels(self):
        """Dashboard displays fresh/aging/stale indicators."""
        with open("frontend/src/components/DataFreshnessDashboard.tsx") as f:
            content = f.read()
        assert "fresh" in content.lower()
        assert "aging" in content.lower()
        assert "stale" in content.lower()

    def test_dashboard_uses_pacific_time(self):
        """Dashboard imports Pacific Time formatting."""
        with open("frontend/src/components/DataFreshnessDashboard.tsx") as f:
            content = f.read()
        assert "format-date" in content


# ── 10.2: Multi-Source Conflict Precedence ────────────────────────


class TestSourcePrecedence:
    """Sprint 10.2: Source conflict resolution."""

    def test_bca_higher_than_cov(self):
        """BC Assessment Authority has higher precedence than City of Vancouver."""
        assert SOURCE_PRECEDENCE["BC Assessment Authority"] > SOURCE_PRECEDENCE["City of Vancouver Open Data"]

    def test_bca_via_cov_higher_than_cov(self):
        """BCA via CoV portal has higher precedence than plain CoV."""
        assert SOURCE_PRECEDENCE["BC Assessment via Vancouver Open Data"] > SOURCE_PRECEDENCE["City of Vancouver Open Data"]

    def test_legislation_higher_than_cov(self):
        """Bill 47 legislation has higher precedence than CoV Open Data."""
        bca_key = "Bill 47 — Housing Statutes (TOA) Amendment Act, 2023"
        assert SOURCE_PRECEDENCE[bca_key] > SOURCE_PRECEDENCE["City of Vancouver Open Data"]

    def test_translink_higher_than_cov(self):
        """TransLink GTFS has higher precedence than CoV Open Data."""
        assert SOURCE_PRECEDENCE["TransLink GTFS"] > SOURCE_PRECEDENCE["City of Vancouver Open Data"]

    def test_rew_lower_than_bca(self):
        """REW.ca listings have lower precedence than BC Assessment."""
        assert SOURCE_PRECEDENCE["REW.ca Listings"] < SOURCE_PRECEDENCE["BC Assessment Authority"]

    def test_model_lowest(self):
        """VanCity Lens Model has lowest precedence."""
        model_prec = SOURCE_PRECEDENCE["VanCity Lens Model"]
        for origin, prec in SOURCE_PRECEDENCE.items():
            if origin != "VanCity Lens Model":
                assert prec > model_prec, f"{origin} should be higher than VanCity Lens Model"

    def test_resolve_single_value(self):
        """Single-source resolution returns that value."""
        values = [{"value": 1000000, "origin": "BC Assessment Authority", "confidence": "verified"}]
        result = resolve_source_conflict("assessed_value", values)
        assert result["value"] == 1000000

    def test_resolve_empty(self):
        """Empty values returns empty dict."""
        assert resolve_source_conflict("field", []) == {}

    def test_resolve_bca_wins_over_cov(self):
        """BCA data wins over CoV data in conflict."""
        values = [
            {"value": 1500000, "origin": "City of Vancouver Open Data", "confidence": "verified"},
            {"value": 2000000, "origin": "BC Assessment Authority", "confidence": "verified"},
        ]
        result = resolve_source_conflict("assessed_value", values)
        assert result["value"] == 2000000
        assert "conflict_note" in result

    def test_resolve_no_conflict_note_when_same(self):
        """No conflict note when values agree."""
        values = [
            {"value": 1000000, "origin": "City of Vancouver Open Data", "confidence": "verified"},
            {"value": 1000000, "origin": "BC Assessment Authority", "confidence": "verified"},
        ]
        result = resolve_source_conflict("assessed_value", values)
        assert result["value"] == 1000000
        assert "conflict_note" not in result

    def test_resolve_unknown_origin_gets_zero_precedence(self):
        """Unknown origin defaults to zero precedence."""
        values = [
            {"value": 500, "origin": "Unknown Source XYZ", "confidence": "estimated"},
            {"value": 1000, "origin": "REW.ca Listings", "confidence": "estimated"},
        ]
        result = resolve_source_conflict("price", values)
        assert result["value"] == 1000  # REW.ca (40) beats unknown (0)


# ── 10.3: Pacific Time Display ────────────────────────────────────


class TestPacificTimeDisplay:
    """Sprint 10.3: Pacific Time formatting utility."""

    def test_format_date_utility_exists(self):
        """format-date.ts exists in frontend/src/lib/."""
        assert os.path.exists("frontend/src/lib/format-date.ts")

    def test_exports_format_functions(self):
        """Utility exports formatDatePT, formatDateTimePT, formatRelativeTimePT."""
        with open("frontend/src/lib/format-date.ts") as f:
            content = f.read()
        assert "export function formatDatePT" in content
        assert "export function formatDateTimePT" in content
        assert "export function formatRelativeTimePT" in content

    def test_uses_vancouver_timezone(self):
        """Utility uses America/Vancouver timezone."""
        with open("frontend/src/lib/format-date.ts") as f:
            content = f.read()
        assert "America/Vancouver" in content

    def test_handles_null_input(self):
        """Utility handles null/undefined input."""
        with open("frontend/src/lib/format-date.ts") as f:
            content = f.read()
        # Should have null/undefined guards
        assert "null" in content
        assert "undefined" in content


# ── 10.4: Sources & Methodology in Reports ────────────────────────


class TestSourcesMethodology:
    """Sprint 10.4: Enhanced sources & methodology section in PDF reports."""

    def test_report_has_methodology_section(self):
        """Report generator includes methodology text."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "Methodology" in content
        assert "Sources & Methodology" in content

    def test_methodology_mentions_precedence(self):
        """Methodology section explains data precedence rules."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "precedence" in content.lower()
        assert "BC Assessment" in content

    def test_methodology_mentions_spatial(self):
        """Methodology section explains spatial analysis method."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "PostGIS" in content or "spatial" in content.lower()

    def test_methodology_mentions_scenarios(self):
        """Methodology section explains three-scenario analysis."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "bull" in content.lower() or "bear" in content.lower() or "scenario" in content.lower()

    def test_sources_table_in_report(self):
        """Report generator builds a data sources table."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "standard_sources" in content
        assert "Parcel Boundaries" in content
        assert "Assessed Values" in content

    def test_verification_links_section(self):
        """Report includes verification links section."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "Verification Links" in content
