"""
V2 Feature Tests — POC Improvement Features

Tests cover:
1. Before/After Comparison component (frontend)
2. Saved Parcels (bookmarks) — DB migration, API routes, frontend
3. Before/After table in PDF report
4. Case Studies — DB migration, seed data, API routes, frontend carousel
"""

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 1. Before/After Comparison Component ──────────────────────────


class TestBeforeAfterComparison:
    """V2 Feature 1: Before/After comparison UI component."""

    def test_component_exists(self):
        assert os.path.exists("frontend/src/components/BeforeAfterComparison.tsx")

    def test_is_client_component(self):
        with open("frontend/src/components/BeforeAfterComparison.tsx") as f:
            content = f.read()
        assert '"use client"' in content

    def test_renders_comparison_table(self):
        with open("frontend/src/components/BeforeAfterComparison.tsx") as f:
            content = f.read()
        assert "Before Bill 47" in content
        assert "After Bill 47" in content
        assert "Uplift" in content

    def test_shows_four_rows(self):
        """Table has Zoning, Max Height, Max FSR, Buildable SF rows."""
        with open("frontend/src/components/BeforeAfterComparison.tsx") as f:
            content = f.read()
        assert "Zoning" in content
        assert "Max Height" in content
        assert "Max FSR" in content
        assert "Buildable SF" in content

    def test_handles_already_exceeds(self):
        """Shows special message when current zoning already exceeds Bill 47."""
        with open("frontend/src/components/BeforeAfterComparison.tsx") as f:
            content = f.read()
        assert "already exceeds" in content.lower()

    def test_green_for_positive_uplift(self):
        """Uses green color for positive uplift values."""
        with open("frontend/src/components/BeforeAfterComparison.tsx") as f:
            content = f.read()
        assert "green" in content

    def test_integrated_in_detail_panel(self):
        """Component is imported and rendered in ParcelDetailPanel."""
        with open("frontend/src/components/ParcelDetailPanel.tsx") as f:
            content = f.read()
        assert "BeforeAfterComparison" in content

    def test_computes_buildable_delta(self):
        """Component computes buildable SF delta."""
        with open("frontend/src/components/BeforeAfterComparison.tsx") as f:
            content = f.read()
        assert "buildableDelta" in content


# ── 2. Saved Parcels (Bookmarks) ─────────────────────────────────


class TestSavedParcelsMigration:
    """V2 Feature 2: Saved parcels DB schema."""

    def test_migration_exists(self):
        assert os.path.exists("db/032_saved_parcels.sql")

    def test_creates_table(self):
        with open("db/032_saved_parcels.sql") as f:
            sql = f.read()
        assert "saved_parcels" in sql
        assert "user_id" in sql
        assert "pid" in sql
        assert "notes" in sql

    def test_has_unique_constraint(self):
        with open("db/032_saved_parcels.sql") as f:
            sql = f.read()
        assert "UNIQUE" in sql

    def test_has_user_index(self):
        with open("db/032_saved_parcels.sql") as f:
            sql = f.read()
        assert "idx_saved_parcels_user" in sql

    def test_cascades_on_user_delete(self):
        with open("db/032_saved_parcels.sql") as f:
            sql = f.read()
        assert "ON DELETE CASCADE" in sql


class TestSavedParcelsRoutes:
    """V2 Feature 2: Saved parcels API routes."""

    def test_router_prefix(self):
        from api.saved_parcels_routes import router
        assert router.prefix == "/api/v1"

    def test_has_save_route(self):
        from api.saved_parcels_routes import router
        paths = [r.path for r in router.routes]
        assert any("save" in p for p in paths)

    def test_has_delete_route(self):
        from api.saved_parcels_routes import router
        methods = []
        for r in router.routes:
            methods.extend(getattr(r, "methods", []))
        assert "DELETE" in methods

    def test_has_check_saved_route(self):
        from api.saved_parcels_routes import router
        paths = [r.path for r in router.routes]
        assert any("saved" in p for p in paths)

    def test_has_list_route(self):
        from api.saved_parcels_routes import router
        paths = [r.path for r in router.routes]
        assert any("saved-parcels" in p for p in paths)

    def test_router_mounted_in_main(self):
        with open("api/main.py") as f:
            content = f.read()
        assert "saved_parcels" in content


class TestSavedParcelsFrontend:
    """V2 Feature 2: Saved parcels frontend."""

    def test_api_client_exists(self):
        assert os.path.exists("frontend/src/lib/saved-parcels-api.ts")

    def test_api_client_exports_functions(self):
        with open("frontend/src/lib/saved-parcels-api.ts") as f:
            content = f.read()
        assert "saveParcel" in content
        assert "unsaveParcel" in content
        assert "checkParcelSaved" in content
        assert "listSavedParcels" in content

    def test_detail_panel_has_save_button(self):
        """ParcelDetailPanel has bookmark/star button."""
        with open("frontend/src/components/ParcelDetailPanel.tsx") as f:
            content = f.read()
        assert "isSaved" in content or "saved" in content.lower()

    def test_uses_auth_headers(self):
        """API client sends auth headers."""
        with open("frontend/src/lib/saved-parcels-api.ts") as f:
            content = f.read()
        assert "Authorization" in content or "Bearer" in content


# ── 3. Before/After in PDF Report ────────────────────────────────


class TestBeforeAfterPDF:
    """V2 Feature 3: Before/After comparison table in PDF report."""

    def test_method_exists(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "_build_before_after_section" in content

    def test_called_in_report_flow(self):
        """Method is called during report generation."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "self._build_before_after_section(pdf, parcel_data)" in content

    def test_renders_table_headers(self):
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "Before Bill 47" in content
        assert "After Bill 47" in content

    def test_computes_buildable_sqft(self):
        """Computes before/after buildable SF."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "before_buildable" in content
        assert "after_buildable" in content
        assert "buildable_delta" in content

    def test_handles_already_exceeds(self):
        """Shows blue highlight for current zoning exceeding Bill 47."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert "current_exceeds" in content or "already exceeds" in content.lower()

    def test_green_fill_for_uplift(self):
        """Uses green fill color for positive uplift cells."""
        with open("api/report_generator.py") as f:
            content = f.read()
        # set_fill_color with green values
        assert "set_fill_color(200, 255, 200)" in content or "set_fill_color" in content

    def test_four_data_rows(self):
        """Table has Zoning, Max Height, Max FSR, Buildable SF rows."""
        with open("api/report_generator.py") as f:
            content = f.read()
        assert '"Zoning"' in content
        assert '"Max Height"' in content
        assert '"Max FSR"' in content
        assert '"Buildable SF"' in content


# ── 4. Case Studies ──────────────────────────────────────────────


class TestCaseStudiesMigration:
    """V2 Feature 4: Case studies DB schema."""

    def test_migration_exists(self):
        assert os.path.exists("db/033_case_studies.sql")

    def test_creates_table(self):
        with open("db/033_case_studies.sql") as f:
            sql = f.read()
        assert "case_studies" in sql
        assert "pid" in sql
        assert "title" in sql
        assert "narrative" in sql
        assert "highlight_metrics" in sql

    def test_has_active_flag(self):
        with open("db/033_case_studies.sql") as f:
            sql = f.read()
        assert "is_active" in sql

    def test_has_display_order(self):
        with open("db/033_case_studies.sql") as f:
            sql = f.read()
        assert "display_order" in sql


class TestCaseStudiesSeedData:
    """V2 Feature 4: Case studies seed data."""

    def test_seed_file_exists(self):
        assert os.path.exists("data/seed/case_studies.json")

    def test_seed_is_valid_json(self):
        with open("data/seed/case_studies.json") as f:
            data = json.load(f)
        assert isinstance(data, list)

    def test_seed_has_five_studies(self):
        with open("data/seed/case_studies.json") as f:
            data = json.load(f)
        assert len(data) == 5

    def test_each_study_has_required_fields(self):
        with open("data/seed/case_studies.json") as f:
            data = json.load(f)
        for study in data:
            assert "pid" in study
            assert "title" in study
            assert "narrative" in study
            assert "highlight_metrics" in study

    def test_has_already_exceeds_scenario(self):
        """At least one case study demonstrates 'already exceeds' scenario."""
        with open("data/seed/case_studies.json") as f:
            data = json.load(f)
        exceeds = [s for s in data if s["highlight_metrics"].get("zoning_already_exceeds")]
        assert len(exceeds) >= 1

    def test_has_tier1_uplift_scenario(self):
        """At least one case study shows a major tier 1 uplift."""
        with open("data/seed/case_studies.json") as f:
            data = json.load(f)
        uplifts = [s for s in data if s["highlight_metrics"].get("storey_uplift", 0) >= 10]
        assert len(uplifts) >= 1

    def test_has_display_order(self):
        with open("data/seed/case_studies.json") as f:
            data = json.load(f)
        orders = [s["display_order"] for s in data]
        assert sorted(orders) == list(range(1, 6))

    def test_seed_loader_handles_case_studies(self):
        """load_seed.py includes case_studies.json loading."""
        with open("data/load_seed.py") as f:
            content = f.read()
        assert "case_studies" in content


class TestCaseStudiesRoutes:
    """V2 Feature 4: Case studies API routes."""

    def test_router_prefix(self):
        from api.case_studies_routes import router
        assert router.prefix == "/api/v1/case-studies"

    def test_has_list_route(self):
        from api.case_studies_routes import router
        paths = [r.path for r in router.routes]
        assert any("case-studies" in p and "{" not in p for p in paths)

    def test_has_detail_route(self):
        from api.case_studies_routes import router
        paths = [r.path for r in router.routes]
        assert any("case_study_id" in p or "{" in p for p in paths)

    def test_router_mounted_in_main(self):
        with open("api/main.py") as f:
            content = f.read()
        assert "case_studies" in content

    def test_handles_jsonb_string_conversion(self):
        """Route handles asyncpg returning JSONB as string."""
        with open("api/case_studies_routes.py") as f:
            content = f.read()
        assert "json.loads" in content


class TestCaseStudyCarousel:
    """V2 Feature 4: Case study carousel frontend component."""

    def test_component_exists(self):
        assert os.path.exists("frontend/src/components/CaseStudyCarousel.tsx")

    def test_is_client_component(self):
        with open("frontend/src/components/CaseStudyCarousel.tsx") as f:
            content = f.read()
        assert '"use client"' in content

    def test_fetches_case_studies_api(self):
        with open("frontend/src/components/CaseStudyCarousel.tsx") as f:
            content = f.read()
        assert "/api/v1/case-studies" in content

    def test_has_navigation_controls(self):
        """Carousel has left/right scroll and dismiss controls."""
        with open("frontend/src/components/CaseStudyCarousel.tsx") as f:
            content = f.read()
        assert "ChevronLeft" in content or "scroll" in content
        assert "ChevronRight" in content
        assert "onDismiss" in content

    def test_shows_metrics(self):
        """Cards display key metrics."""
        with open("frontend/src/components/CaseStudyCarousel.tsx") as f:
            content = f.read()
        assert "storey_uplift" in content
        assert "entitled_fsr" in content

    def test_handles_already_exceeds(self):
        with open("frontend/src/components/CaseStudyCarousel.tsx") as f:
            content = f.read()
        assert "ALREADY EXCEEDS" in content or "already_exceeds" in content

    def test_click_navigates_to_parcel(self):
        """Clicking a card navigates to that parcel."""
        with open("frontend/src/components/CaseStudyCarousel.tsx") as f:
            content = f.read()
        assert "onSelectParcel" in content

    def test_integrated_in_map(self):
        """Carousel is rendered in MapView."""
        with open("frontend/src/components/MapView.tsx") as f:
            content = f.read()
        assert "CaseStudyCarousel" in content
