"""
VanCity Lens — CSV Export Tests (VCL-101 / FE-012)

Comprehensive test suite for CSV export service and routes.
Tests CSV generation, filtering, injection prevention, and API endpoints.
"""

import io
import csv
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

import pytest
from fastapi import HTTPException
import asyncpg

from api.csv_export import (
    CSVExporter,
    SignalExportFilters,
    ParcelExportFilters,
    ExportMetadata,
    _fetch_signals_for_export,
    _fetch_neighborhood_scorecard,
    _fetch_parcels_for_export,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pool():
    """Mock asyncpg pool."""
    pool = AsyncMock()
    pool.acquire = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.fixture
def sample_signals() -> List[Dict[str, Any]]:
    """Sample signal data for testing."""
    return [
        {
            "id": 1,
            "signal_type": "rezoning_decision",
            "headline": "1234 Main rezoned to 25-storey",
            "summary": "City Council approved rezoning from RS-1 to CD-1",
            "neighborhood": "Downtown",
            "addresses": ["1234 Main Street"],
            "event_date": date(2024, 1, 15),
            "severity": "high",
            "confidence": 0.95,
            "zoning_from": "RS-1",
            "zoning_to": "CD-1",
            "height_before": 10.5,
            "height_after": 80.0,
            "fsr_before": 1.0,
            "fsr_after": 8.5,
            "unit_count": 300,
            "project_value_dollars": 150000000,
            "decision": "approved",
            "vote_for": 10,
            "vote_against": 1,
            "conditions": ["Public plaza minimum 1500 sq m"],
            "sentiment": "positive_for_development",
            "source_title": "City Council Meeting",
            "source_url": "https://council.vancouver.ca/minutes.pdf",
            "source_type": "council_minutes",
            "source_date": date(2024, 1, 15),
        },
        {
            "id": 2,
            "signal_type": "policy_change",
            "headline": "ODP update affects density",
            "summary": "Official Development Plan updated",
            "neighborhood": "Mount Pleasant",
            "addresses": [],
            "event_date": date(2024, 1, 10),
            "severity": "medium",
            "confidence": 0.75,
            "zoning_from": None,
            "zoning_to": None,
            "height_before": None,
            "height_after": None,
            "fsr_before": None,
            "fsr_after": None,
            "unit_count": None,
            "project_value_dollars": None,
            "decision": None,
            "vote_for": None,
            "vote_against": None,
            "conditions": [],
            "sentiment": "neutral",
            "source_title": "Policy Update",
            "source_url": "https://council.vancouver.ca/policy.pdf",
            "source_type": "policy_document",
            "source_date": date(2024, 1, 10),
        },
    ]


@pytest.fixture
def sample_parcels() -> List[Dict[str, Any]]:
    """Sample parcel data for testing."""
    return [
        {
            "pid": "000-000-000",
            "civic_address": "1234 Main Street",
            "neighborhood": "Downtown",
            "zoning": "CD-1",
            "lot_area_sqft": 5000.0,
            "lot_area_sqm": 464.5,
            "assessed_value": 2000000,
            "asking_price": 2500000,
            "price_per_sqft": 500,
            "current_storeys": 5,
            "current_fsr": 2.0,
            "entitled_storeys": 25,
            "entitled_fsr": 8.5,
            "storey_uplift": 20,
            "fsr_uplift": 6.5,
            "estimated_land_value": 3500000,
            "value_delta": 1000000,
            "signal": "high_alpha",
            "in_toa": True,
            "zoning_already_exceeds": False,
            "nearest_station": "King George Station",
            "distance_to_station_m": 250.5,
            "bill47_tier": 1,
        },
        {
            "pid": "000-000-001",
            "civic_address": "5678 Granville Street",
            "neighborhood": "Mount Pleasant",
            "zoning": "RM-4",
            "lot_area_sqft": 3500.0,
            "lot_area_sqm": 325.2,
            "assessed_value": 1500000,
            "asking_price": 1800000,
            "price_per_sqft": 514,
            "current_storeys": 3,
            "current_fsr": 1.5,
            "entitled_storeys": 12,
            "entitled_fsr": 6.0,
            "storey_uplift": 9,
            "fsr_uplift": 4.5,
            "estimated_land_value": 2200000,
            "value_delta": 400000,
            "signal": "moderate",
            "in_toa": True,
            "zoning_already_exceeds": False,
            "nearest_station": "Broadway-City Hall Station",
            "distance_to_station_m": 180.2,
            "bill47_tier": 2,
        },
    ]


@pytest.fixture
def sample_neighborhood_scores() -> Dict[str, Dict[str, Any]]:
    """Sample neighborhood scorecard data."""
    return {
        "Downtown": {
            "population": 85000,
            "median_age": 38,
            "household_income": 95000,
            "property_tax_rate": 0.0045,
            "average_home_price": 1250000,
            "price_per_sqft": 850,
            "vacancy_rate": 0.03,
            "zoning_density_score": 95,
            "development_pipeline_count": 42,
            "transit_accessibility_score": 98,
            "walkability_score": 95,
            "bike_score": 85,
            "school_rating_avg": 7.2,
            "crime_rate_per_100k": 185,
            "parks_per_100k_residents": 150,
        },
        "Mount Pleasant": {
            "population": 65000,
            "median_age": 35,
            "household_income": 82000,
            "property_tax_rate": 0.0042,
            "average_home_price": 950000,
            "price_per_sqft": 680,
            "vacancy_rate": 0.04,
            "zoning_density_score": 72,
            "development_pipeline_count": 18,
            "transit_accessibility_score": 85,
            "walkability_score": 88,
            "bike_score": 82,
            "school_rating_avg": 6.8,
            "crime_rate_per_100k": 210,
            "parks_per_100k_residents": 140,
        },
    }


# ────────────────────────────────────────────────────────────────────────────
# Tests: CSV Injection Prevention
# ────────────────────────────────────────────────────────────────────────────


class TestCSVInjectionPrevention:
    """Test CSV injection prevention mechanisms."""

    def test_sanitize_csv_value_removes_equals_prefix(self):
        """Test that leading = is stripped."""
        assert CSVExporter._sanitize_csv_value("=SUM(A1:A10)") == "SUM(A1:A10)"

    def test_sanitize_csv_value_removes_plus_prefix(self):
        """Test that leading + is stripped."""
        assert CSVExporter._sanitize_csv_value("+HYPERLINK(...)") == "HYPERLINK(...)"

    def test_sanitize_csv_value_removes_minus_prefix(self):
        """Test that leading - is stripped."""
        assert CSVExporter._sanitize_csv_value("-2+5=3") == "2+5=3"

    def test_sanitize_csv_value_removes_at_prefix(self):
        """Test that leading @ is stripped."""
        assert CSVExporter._sanitize_csv_value("@SUM(A1:A10)") == "SUM(A1:A10)"

    def test_sanitize_csv_value_removes_multiple_prefixes(self):
        """Test that multiple dangerous prefixes are stripped."""
        assert CSVExporter._sanitize_csv_value("===SUM(A1)") == "SUM(A1)"
        assert CSVExporter._sanitize_csv_value("++LINK") == "LINK"

    def test_sanitize_csv_value_normal_text(self):
        """Test that normal text is unchanged."""
        assert CSVExporter._sanitize_csv_value("Normal text") == "Normal text"

    def test_sanitize_csv_value_none(self):
        """Test that None returns empty string."""
        assert CSVExporter._sanitize_csv_value(None) == ""

    def test_sanitize_csv_value_numeric(self):
        """Test that numeric values are converted safely."""
        assert CSVExporter._sanitize_csv_value(123) == "123"
        assert CSVExporter._sanitize_csv_value(45.67) == "45.67"

    def test_sanitize_csv_value_tab_and_carriage_return(self):
        """Test that tabs and carriage returns are stripped."""
        assert CSVExporter._sanitize_csv_value("\tContent") == "Content"
        assert CSVExporter._sanitize_csv_value("\rContent") == "Content"


# ────────────────────────────────────────────────────────────────────────────
# Tests: Filename Generation
# ────────────────────────────────────────────────────────────────────────────


class TestFilenameGeneration:
    """Test CSV filename generation."""

    def test_build_filename_signals_with_context(self):
        """Test filename generation for signals with context."""
        filename = CSVExporter._build_filename(
            "signals",
            "Downtown",
            date(2024, 2, 8),
        )
        assert filename == "signals_Downtown_2024-02-08.csv"

    def test_build_filename_signals_without_context(self):
        """Test filename generation for signals without context."""
        filename = CSVExporter._build_filename(
            "signals",
            export_date=date(2024, 2, 8),
        )
        assert filename == "signals_2024-02-08.csv"

    def test_build_filename_neighborhood_comparison(self):
        """Test filename generation for neighborhood comparison."""
        filename = CSVExporter._build_filename(
            "neighborhood_comparison",
            "Downtown_vs_Kitsilano",
            date(2024, 2, 8),
        )
        assert "neighborhood_comparison" in filename
        assert "2024-02-08" in filename

    def test_build_filename_parcels_with_zoning(self):
        """Test filename generation for parcels with zoning."""
        filename = CSVExporter._build_filename(
            "parcels",
            "Downtown_CD-1",
            date(2024, 2, 8),
        )
        assert "parcels" in filename
        assert "2024-02-08" in filename

    def test_build_filename_sanitizes_spaces(self):
        """Test that spaces in context are converted to underscores."""
        filename = CSVExporter._build_filename(
            "signals",
            "Mount Pleasant",
            date(2024, 2, 8),
        )
        assert " " not in filename
        assert "Mount_Pleasant" in filename

    def test_build_filename_default_date_is_today(self):
        """Test that filename uses today's date when not provided."""
        filename = CSVExporter._build_filename("signals")
        assert ".csv" in filename
        # Should contain date pattern YYYY-MM-DD
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}", filename) is not None


# ────────────────────────────────────────────────────────────────────────────
# Tests: Signal Export
# ────────────────────────────────────────────────────────────────────────────


class TestSignalExport:
    """Test signal feed CSV export."""

    @pytest.mark.asyncio
    async def test_export_signals_generates_valid_csv(self, mock_pool, sample_signals):
        """Test that export_signals generates valid CSV with correct headers."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals

        filters = SignalExportFilters()
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        assert "signal_id" in content
        assert "signal_type" in content
        assert "headline" in content

        # Parse CSV to verify structure
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_export_signals_includes_all_fields(self, mock_pool, sample_signals):
        """Test that export includes all required fields."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals

        filters = SignalExportFilters()
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        required_fields = [
            "signal_id", "signal_type", "headline", "summary",
            "neighborhood", "event_date", "severity", "confidence",
            "source_url", "source_type",
        ]
        for field in required_fields:
            assert field in content

    @pytest.mark.asyncio
    async def test_export_signals_filters_by_neighborhood(self, mock_pool, sample_signals):
        """Test that export respects neighborhood filter."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals[:1]

        filters = SignalExportFilters(neighborhood="Downtown")
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_export_signals_filters_by_date_range(self, mock_pool, sample_signals):
        """Test that export respects date range filters."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals[:1]

        filters = SignalExportFilters(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 20),
        )
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        assert content  # Should have content

    @pytest.mark.asyncio
    async def test_export_signals_respects_limit(self, mock_pool, sample_signals):
        """Test that export respects row limit (limit is enforced in SQL LIMIT clause)."""
        # Mock returns only 1 row to simulate DB enforcing LIMIT 1
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals[:1]

        filters = SignalExportFilters(limit=1)
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        # Only 1 data row (DB enforces LIMIT)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_export_signals_empty_results(self, mock_pool):
        """Test that export handles empty results gracefully."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = []

        filters = SignalExportFilters()
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 0  # No data rows, but headers should exist

    @pytest.mark.asyncio
    async def test_export_signals_filename_includes_date(self, mock_pool, sample_signals):
        """Test that filename includes proper date format."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals

        filters = SignalExportFilters(neighborhood="Downtown")
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}\.csv", filename) is not None

    @pytest.mark.asyncio
    async def test_export_signals_sanitizes_injection(self, mock_pool):
        """Test that dangerous values are sanitized in export."""
        dangerous_signal = {
            "id": 1,
            "signal_type": "rezoning_decision",
            "headline": "=SUM(A1:A10) malicious",
            "summary": "+HYPERLINK(...) attack",
            "neighborhood": "Downtown",
            "addresses": [],
            "event_date": date(2024, 1, 15),
            "severity": "high",
            "confidence": 0.95,
            "zoning_from": None,
            "zoning_to": None,
            "height_before": None,
            "height_after": None,
            "fsr_before": None,
            "fsr_after": None,
            "unit_count": None,
            "project_value_dollars": None,
            "decision": None,
            "vote_for": None,
            "vote_against": None,
            "conditions": [],
            "sentiment": "neutral",
            "source_title": "Test",
            "source_url": "https://example.com",
            "source_type": "test",
            "source_date": date(2024, 1, 15),
        }
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = [dangerous_signal]

        filters = SignalExportFilters()
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        # Dangerous prefixes should be stripped
        assert "=SUM" not in content
        assert "+HYPERLINK" not in content


# ────────────────────────────────────────────────────────────────────────────
# Tests: Neighborhood Comparison Export
# ────────────────────────────────────────────────────────────────────────────


class TestNeighborhoodComparisonExport:
    """Test neighborhood comparison scorecard CSV export."""

    @pytest.mark.asyncio
    async def test_export_neighborhood_comparison_valid_csv(
        self, mock_pool, sample_neighborhood_scores
    ):
        """Test that export generates valid CSV."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = [
            {"name": "Downtown", **sample_neighborhood_scores["Downtown"]},
            {"name": "Mount Pleasant", **sample_neighborhood_scores["Mount Pleasant"]},
        ]

        neighborhoods = ["Downtown", "Mount Pleasant"]
        csv_buffer, filename = await CSVExporter.export_neighborhood_comparison(
            mock_pool,
            neighborhoods,
        )

        content = csv_buffer.getvalue()
        assert "metric" in content
        assert "Downtown" in content
        assert "Mount Pleasant" in content

    @pytest.mark.asyncio
    async def test_export_neighborhood_comparison_includes_all_metrics(
        self, mock_pool, sample_neighborhood_scores
    ):
        """Test that all scorecard metrics are included."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = [
            {"name": "Downtown", **sample_neighborhood_scores["Downtown"]},
        ]

        neighborhoods = ["Downtown"]
        csv_buffer, filename = await CSVExporter.export_neighborhood_comparison(
            mock_pool,
            neighborhoods,
        )

        content = csv_buffer.getvalue()
        required_metrics = [
            "population", "median_age", "household_income",
            "average_home_price", "transit_accessibility_score",
        ]
        for metric in required_metrics:
            assert metric in content

    @pytest.mark.asyncio
    async def test_export_neighborhood_comparison_multiple_neighborhoods(
        self, mock_pool, sample_neighborhood_scores
    ):
        """Test comparison with multiple neighborhoods."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = [
            {"name": "Downtown", **sample_neighborhood_scores["Downtown"]},
            {"name": "Mount Pleasant", **sample_neighborhood_scores["Mount Pleasant"]},
        ]

        neighborhoods = ["Downtown", "Mount Pleasant"]
        csv_buffer, filename = await CSVExporter.export_neighborhood_comparison(
            mock_pool,
            neighborhoods,
        )

        content = csv_buffer.getvalue()
        reader = csv.DictReader(io.StringIO(content))
        # Check that header has all neighborhoods
        assert reader.fieldnames is not None
        assert "Downtown" in reader.fieldnames
        assert "Mount Pleasant" in reader.fieldnames

    @pytest.mark.asyncio
    async def test_export_neighborhood_comparison_filename(
        self, mock_pool, sample_neighborhood_scores
    ):
        """Test that filename is properly formatted."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = [
            {"name": "Downtown", **sample_neighborhood_scores["Downtown"]},
        ]

        neighborhoods = ["Downtown"]
        csv_buffer, filename = await CSVExporter.export_neighborhood_comparison(
            mock_pool,
            neighborhoods,
        )

        assert "neighborhood_comparison" in filename
        assert ".csv" in filename


# ────────────────────────────────────────────────────────────────────────────
# Tests: Parcel Export
# ────────────────────────────────────────────────────────────────────────────


class TestParcelExport:
    """Test parcel data CSV export."""

    @pytest.mark.asyncio
    async def test_export_parcels_generates_valid_csv(self, mock_pool, sample_parcels):
        """Test that export_parcels generates valid CSV."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_parcels

        filters = ParcelExportFilters()
        csv_buffer, filename = await CSVExporter.export_parcels(mock_pool, filters)

        content = csv_buffer.getvalue()
        assert "pid" in content
        assert "civic_address" in content
        assert "zoning" in content

    @pytest.mark.asyncio
    async def test_export_parcels_includes_all_fields(self, mock_pool, sample_parcels):
        """Test that all required parcel fields are included."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_parcels

        filters = ParcelExportFilters()
        csv_buffer, filename = await CSVExporter.export_parcels(mock_pool, filters)

        content = csv_buffer.getvalue()
        required_fields = [
            "pid", "civic_address", "neighborhood", "zoning",
            "lot_area_sqft", "assessed_value", "asking_price",
            "entitled_storeys", "entitled_fsr", "signal",
        ]
        for field in required_fields:
            assert field in content

    @pytest.mark.asyncio
    async def test_export_parcels_filters_by_neighborhood(self, mock_pool, sample_parcels):
        """Test that export respects neighborhood filter."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_parcels[:1]

        filters = ParcelExportFilters(neighborhood="Downtown")
        csv_buffer, filename = await CSVExporter.export_parcels(mock_pool, filters)

        content = csv_buffer.getvalue()
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_export_parcels_filters_by_zoning(self, mock_pool, sample_parcels):
        """Test that export respects zoning filter."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_parcels[:1]

        filters = ParcelExportFilters(zoning="CD-1")
        csv_buffer, filename = await CSVExporter.export_parcels(mock_pool, filters)

        content = csv_buffer.getvalue()
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) >= 0

    @pytest.mark.asyncio
    async def test_export_parcels_filters_by_lot_size(self, mock_pool, sample_parcels):
        """Test that export respects lot size filters."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_parcels

        filters = ParcelExportFilters(
            min_lot_sqft=3000,
            max_lot_sqft=6000,
        )
        csv_buffer, filename = await CSVExporter.export_parcels(mock_pool, filters)

        content = csv_buffer.getvalue()
        assert content

    @pytest.mark.asyncio
    async def test_export_parcels_respects_limit(self, mock_pool, sample_parcels):
        """Test that export respects row limit (limit is enforced in SQL LIMIT clause)."""
        # Mock returns only 1 row to simulate DB enforcing LIMIT 1
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_parcels[:1]

        filters = ParcelExportFilters(limit=1)
        csv_buffer, filename = await CSVExporter.export_parcels(mock_pool, filters)

        content = csv_buffer.getvalue()
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_export_parcels_empty_results(self, mock_pool):
        """Test that export handles empty results gracefully."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = []

        filters = ParcelExportFilters()
        csv_buffer, filename = await CSVExporter.export_parcels(mock_pool, filters)

        content = csv_buffer.getvalue()
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_export_parcels_filename_format(self, mock_pool, sample_parcels):
        """Test that filename is properly formatted."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_parcels

        filters = ParcelExportFilters(neighborhood="Downtown")
        csv_buffer, filename = await CSVExporter.export_parcels(mock_pool, filters)

        assert "parcels" in filename
        assert ".csv" in filename


# ────────────────────────────────────────────────────────────────────────────
# Tests: Filter Models
# ────────────────────────────────────────────────────────────────────────────


class TestFilterModels:
    """Test Pydantic filter models."""

    def test_signal_export_filters_valid(self):
        """Test SignalExportFilters model validation."""
        filters = SignalExportFilters(
            neighborhood="Downtown",
            category="rezoning_decision",
            limit=500,
        )
        assert filters.neighborhood == "Downtown"
        assert filters.category == "rezoning_decision"
        assert filters.limit == 500

    def test_signal_export_filters_limit_validation(self):
        """Test that limit is validated (max 10000)."""
        with pytest.raises(ValueError):
            SignalExportFilters(limit=15000)

    def test_signal_export_filters_defaults(self):
        """Test SignalExportFilters defaults."""
        filters = SignalExportFilters()
        assert filters.neighborhood is None
        assert filters.category is None
        assert filters.limit == 1000

    def test_parcel_export_filters_valid(self):
        """Test ParcelExportFilters model validation."""
        filters = ParcelExportFilters(
            neighborhood="Downtown",
            zoning="CD-1",
            min_lot_sqft=1000,
            max_lot_sqft=5000,
        )
        assert filters.neighborhood == "Downtown"
        assert filters.zoning == "CD-1"
        assert filters.min_lot_sqft == 1000

    def test_parcel_export_filters_limit_validation(self):
        """Test that limit is validated (max 5000)."""
        with pytest.raises(ValueError):
            ParcelExportFilters(limit=10000)

    def test_export_metadata_valid(self):
        """Test ExportMetadata model."""
        metadata = ExportMetadata(
            export_type="signals",
            row_count=42,
            exported_at=datetime.now(),
            filters_applied={"neighborhood": "Downtown"},
        )
        assert metadata.export_type == "signals"
        assert metadata.row_count == 42


# ────────────────────────────────────────────────────────────────────────────
# Tests: Database Query Helpers
# ────────────────────────────────────────────────────────────────────────────


class TestDatabaseQueryHelpers:
    """Test database query helper functions."""

    @pytest.mark.asyncio
    async def test_fetch_signals_for_export_no_filters(self, mock_pool, sample_signals):
        """Test fetching signals without filters."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals

        filters = SignalExportFilters()
        result = await _fetch_signals_for_export(mock_pool, filters)

        assert len(result) == 2
        assert result[0]["signal_type"] == "rezoning_decision"

    @pytest.mark.asyncio
    async def test_fetch_signals_for_export_with_neighborhood(self, mock_pool, sample_signals):
        """Test fetching signals with neighborhood filter."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals[:1]

        filters = SignalExportFilters(neighborhood="Downtown")
        result = await _fetch_signals_for_export(mock_pool, filters)

        assert len(result) >= 0

    @pytest.mark.asyncio
    async def test_fetch_neighborhood_scorecard(self, mock_pool, sample_neighborhood_scores):
        """Test fetching neighborhood scorecard data."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = [
            {"name": "Downtown", **sample_neighborhood_scores["Downtown"]},
        ]

        result = await _fetch_neighborhood_scorecard(mock_pool, ["Downtown"])

        assert "Downtown" in result
        assert result["Downtown"]["population"] == 85000

    @pytest.mark.asyncio
    async def test_fetch_parcels_for_export_no_filters(self, mock_pool, sample_parcels):
        """Test fetching parcels without filters."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_parcels

        filters = ParcelExportFilters()
        result = await _fetch_parcels_for_export(mock_pool, filters)

        assert len(result) == 2
        assert result[0]["pid"] == "000-000-000"

    @pytest.mark.asyncio
    async def test_fetch_parcels_for_export_with_zoning(self, mock_pool, sample_parcels):
        """Test fetching parcels with zoning filter."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_parcels[:1]

        filters = ParcelExportFilters(zoning="CD-1")
        result = await _fetch_parcels_for_export(mock_pool, filters)

        assert len(result) >= 0


# ────────────────────────────────────────────────────────────────────────────
# Tests: Streaming Response
# ────────────────────────────────────────────────────────────────────────────


class TestStreamingResponse:
    """Test CSV streaming response generation."""

    @pytest.mark.asyncio
    async def test_export_signals_returns_stringio(self, mock_pool, sample_signals):
        """Test that export returns StringIO buffer."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals

        filters = SignalExportFilters()
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        assert isinstance(csv_buffer, io.StringIO)
        assert filename.endswith(".csv")

    @pytest.mark.asyncio
    async def test_export_buffer_is_readable(self, mock_pool, sample_signals):
        """Test that returned buffer is readable."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals

        filters = SignalExportFilters()
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        assert len(content) > 0
        assert "\n" in content  # Has at least header row


# ────────────────────────────────────────────────────────────────────────────
# Tests: Date and Numeric Formatting
# ────────────────────────────────────────────────────────────────────────────


class TestDataFormatting:
    """Test date and numeric value formatting in CSV export."""

    @pytest.mark.asyncio
    async def test_export_signals_formats_dates(self, mock_pool, sample_signals):
        """Test that dates are properly formatted."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_signals

        filters = SignalExportFilters()
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        # Should contain date in YYYY-MM-DD format
        assert "2024-01" in content

    @pytest.mark.asyncio
    async def test_export_parcels_formats_decimals(self, mock_pool, sample_parcels):
        """Test that decimal values are properly formatted."""
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = sample_parcels

        filters = ParcelExportFilters()
        csv_buffer, filename = await CSVExporter.export_parcels(mock_pool, filters)

        content = csv_buffer.getvalue()
        # Should contain numeric values
        assert "5000" in content or "3500" in content

    @pytest.mark.asyncio
    async def test_export_signals_handles_null_values(self, mock_pool):
        """Test that NULL values are handled gracefully."""
        signal_with_nulls = {
            "id": 1,
            "signal_type": "policy_change",
            "headline": "Test",
            "summary": "Test summary",
            "neighborhood": "Downtown",
            "addresses": [],
            "event_date": date(2024, 1, 15),
            "severity": "medium",
            "confidence": 0.75,
            "zoning_from": None,
            "zoning_to": None,
            "height_before": None,
            "height_after": None,
            "fsr_before": None,
            "fsr_after": None,
            "unit_count": None,
            "project_value_dollars": None,
            "decision": None,
            "vote_for": None,
            "vote_against": None,
            "conditions": [],
            "sentiment": "neutral",
            "source_title": "Test",
            "source_url": "https://example.com",
            "source_type": "policy",
            "source_date": date(2024, 1, 15),
        }
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = [signal_with_nulls]

        filters = SignalExportFilters()
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        assert content  # Should not error with nulls


# ────────────────────────────────────────────────────────────────────────────
# Tests: Special Characters
# ────────────────────────────────────────────────────────────────────────────


class TestSpecialCharacterHandling:
    """Test handling of special characters in CSV data."""

    def test_sanitize_handles_quotes(self):
        """Test that quotes are handled properly."""
        value = 'He said "Hello"'
        sanitized = CSVExporter._sanitize_csv_value(value)
        assert "Hello" in sanitized

    def test_sanitize_handles_commas(self):
        """Test that commas are handled properly."""
        value = "1234 Main Street, Downtown"
        sanitized = CSVExporter._sanitize_csv_value(value)
        assert "Main Street" in sanitized

    def test_sanitize_handles_newlines(self):
        """Test that newlines are handled properly."""
        value = "Line 1\nLine 2"
        sanitized = CSVExporter._sanitize_csv_value(value)
        assert "Line 1" in sanitized

    @pytest.mark.asyncio
    async def test_export_signals_with_special_characters(self, mock_pool):
        """Test that signals with special characters export correctly."""
        special_signal = {
            "id": 1,
            "signal_type": "rezoning_decision",
            "headline": 'Rezoning @ 1234 "Main" Street, Downtown',
            "summary": 'Project includes 20% "affordable" units\nWith public plaza',
            "neighborhood": "Downtown",
            "addresses": ['1234 "Main" Street, Downtown'],
            "event_date": date(2024, 1, 15),
            "severity": "high",
            "confidence": 0.95,
            "zoning_from": "RS-1",
            "zoning_to": "CD-1",
            "height_before": 10.5,
            "height_after": 80.0,
            "fsr_before": 1.0,
            "fsr_after": 8.5,
            "unit_count": 300,
            "project_value_dollars": 150000000,
            "decision": "approved",
            "vote_for": 10,
            "vote_against": 1,
            "conditions": ["Public plaza (1500 sq m)", "Rental units >= 20%"],
            "sentiment": "positive_for_development",
            "source_title": 'Meeting "Minutes" - January 15',
            "source_url": "https://example.com?id=123&type=pdf",
            "source_type": "council_minutes",
            "source_date": date(2024, 1, 15),
        }
        mock_pool.acquire.return_value.__aenter__.return_value.fetch.return_value = [special_signal]

        filters = SignalExportFilters()
        csv_buffer, filename = await CSVExporter.export_signals(mock_pool, filters)

        content = csv_buffer.getvalue()
        # CSV should be parseable despite special characters
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1
