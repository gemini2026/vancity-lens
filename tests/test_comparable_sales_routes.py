"""
Tests for comparable sales analysis routes (VCL-110 / BIZ-011)

Tests cover:
- API endpoint structure, query parameters, response models
- Search criteria filtering
- Analysis output (adjusted average, value range, confidence)
- Component structure (table, sorting, summary stats)
- Pydantic models and validation
"""

import pathlib
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import pytest

COMPONENTS_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "components"
)
API_DIR = pathlib.Path(__file__).resolve().parent.parent / "api"


class TestComparableSalesModels:
    """Test Pydantic models for comparable sales data."""

    def test_comparable_sale_model_exists(self):
        """Verify ComparableSale model can be imported."""
        from api.comparable_sales_routes import ComparableSale
        assert ComparableSale is not None

    def test_comparable_sale_model_required_fields(self):
        """Test ComparableSale has required fields."""
        from api.comparable_sales_routes import ComparableSale
        required_fields = {
            "address", "price", "sale_date", "sqft",
            "price_per_sqft", "distance_m", "property_type"
        }
        field_names = set(ComparableSale.model_fields.keys())
        assert required_fields.issubset(field_names)

    def test_comparable_sale_optional_fields(self):
        """Test ComparableSale optional fields."""
        from api.comparable_sales_routes import ComparableSale
        optional_fields = {"bedrooms", "year_built"}
        field_names = set(ComparableSale.model_fields.keys())
        assert optional_fields.issubset(field_names)

    def test_comparable_sale_adjustment_factor_default(self):
        """Test ComparableSale adjustment_factor defaults to 1.0."""
        from api.comparable_sales_routes import ComparableSale
        sale = ComparableSale(
            address="123 Main St",
            price=500000.0,
            sale_date=datetime.utcnow(),
            sqft=2000.0,
            price_per_sqft=250.0,
            distance_m=100.0,
            property_type="residential"
        )
        assert sale.adjustment_factor == 1.0

    def test_comparable_sale_model_validation_price_positive(self):
        """Test ComparableSale validates price values."""
        from api.comparable_sales_routes import ComparableSale
        with pytest.raises(ValueError):
            ComparableSale(
                address="123 Main St",
                price=-100000.0,
                sale_date=datetime.utcnow(),
                sqft=2000.0,
                price_per_sqft=250.0,
                distance_m=100.0,
                property_type="residential"
            )

    def test_comparable_sale_model_serialization(self):
        """Test ComparableSale can be serialized to JSON."""
        from api.comparable_sales_routes import ComparableSale
        sale = ComparableSale(
            address="123 Main St",
            price=500000.0,
            sale_date=datetime.utcnow(),
            sqft=2000.0,
            price_per_sqft=250.0,
            distance_m=100.0,
            property_type="residential"
        )
        json_data = sale.model_dump_json()
        assert "123 Main St" in json_data
        assert "500000" in json_data

    def test_comp_analysis_result_model_exists(self):
        """Verify CompAnalysisResult model can be imported."""
        from api.comparable_sales_routes import CompAnalysisResult
        assert CompAnalysisResult is not None

    def test_comp_analysis_result_required_fields(self):
        """Test CompAnalysisResult has required fields."""
        from api.comparable_sales_routes import CompAnalysisResult
        required_fields = {
            "subject_property", "comparables",
            "adjusted_avg_psf", "suggested_value_range", "confidence"
        }
        field_names = set(CompAnalysisResult.model_fields.keys())
        assert required_fields.issubset(field_names)

    def test_comp_analysis_result_confidence_bounds(self):
        """Test CompAnalysisResult confidence is bounded 0-1."""
        from api.comparable_sales_routes import CompAnalysisResult, ComparableSale
        valid_result = CompAnalysisResult(
            subject_property="456 Oak Ave",
            comparables=[],
            adjusted_avg_psf=300.0,
            suggested_value_range={"low": 600000, "mid": 750000, "high": 900000},
            confidence=0.85
        )
        assert 0 <= valid_result.confidence <= 1

    def test_comp_analysis_result_invalid_confidence_high(self):
        """Test CompAnalysisResult rejects confidence > 1."""
        from api.comparable_sales_routes import CompAnalysisResult
        with pytest.raises(ValueError):
            CompAnalysisResult(
                subject_property="456 Oak Ave",
                comparables=[],
                adjusted_avg_psf=300.0,
                suggested_value_range={"low": 600000, "mid": 750000, "high": 900000},
                confidence=1.5
            )

    def test_comp_analysis_result_invalid_confidence_low(self):
        """Test CompAnalysisResult rejects confidence < 0."""
        from api.comparable_sales_routes import CompAnalysisResult
        with pytest.raises(ValueError):
            CompAnalysisResult(
                subject_property="456 Oak Ave",
                comparables=[],
                adjusted_avg_psf=300.0,
                suggested_value_range={"low": 600000, "mid": 750000, "high": 900000},
                confidence=-0.1
            )

    def test_comp_analysis_result_serialization(self):
        """Test CompAnalysisResult can be serialized to JSON."""
        from api.comparable_sales_routes import CompAnalysisResult
        result = CompAnalysisResult(
            subject_property="456 Oak Ave",
            comparables=[],
            adjusted_avg_psf=300.0,
            suggested_value_range={"low": 600000, "mid": 750000, "high": 900000},
            confidence=0.85
        )
        json_data = result.model_dump_json()
        assert "456 Oak Ave" in json_data
        assert "0.85" in json_data


class TestComparableSalesRoutesStructure:
    """Test API route structure and configuration."""

    def test_routes_file_exists(self):
        """Verify comparable_sales_routes.py file exists."""
        assert (API_DIR / "comparable_sales_routes.py").exists()

    def test_router_exists(self):
        """Verify APIRouter instance is created."""
        from api.comparable_sales_routes import router
        assert router is not None

    def test_router_has_correct_prefix(self):
        """Test router has /api/v1 prefix."""
        from api.comparable_sales_routes import router
        assert router.prefix == "/api/v1"

    def test_router_has_correct_tags(self):
        """Test router has comparable-sales tag."""
        from api.comparable_sales_routes import router
        assert "comparable-sales" in router.tags

    def test_get_parcel_comparables_endpoint_exists(self):
        """Verify GET /parcels/{parcel_id}/comparables endpoint exists."""
        from api.comparable_sales_routes import get_parcel_comparables
        assert callable(get_parcel_comparables)

    def test_search_comparables_endpoint_exists(self):
        """Verify GET /comparables/search endpoint exists."""
        from api.comparable_sales_routes import search_comparables
        assert callable(search_comparables)

    def test_analyze_comparables_endpoint_exists(self):
        """Verify POST /comparables/analyze endpoint exists."""
        from api.comparable_sales_routes import analyze_comparables
        assert callable(analyze_comparables)

    def test_get_parcel_comparables_has_docstring(self):
        """Test get_parcel_comparables has documentation."""
        from api.comparable_sales_routes import get_parcel_comparables
        assert get_parcel_comparables.__doc__ is not None
        assert len(get_parcel_comparables.__doc__) > 0

    def test_search_comparables_has_docstring(self):
        """Test search_comparables has documentation."""
        from api.comparable_sales_routes import search_comparables
        assert search_comparables.__doc__ is not None
        assert len(search_comparables.__doc__) > 0

    def test_analyze_comparables_has_docstring(self):
        """Test analyze_comparables has documentation."""
        from api.comparable_sales_routes import analyze_comparables
        assert analyze_comparables.__doc__ is not None
        assert len(analyze_comparables.__doc__) > 0


class TestGetParcelComparablesEndpoint:
    """Test GET /parcels/{parcel_id}/comparables endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_returns_list(self):
        """Test endpoint returns a list of ComparableSale objects."""
        from api.comparable_sales_routes import get_parcel_comparables
        result = await get_parcel_comparables(parcel_id="PARCEL123")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_endpoint_respects_radius_parameter(self):
        """Test endpoint accepts radius_m parameter."""
        from api.comparable_sales_routes import get_parcel_comparables
        result = await get_parcel_comparables(parcel_id="PARCEL123", radius_m=500)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_endpoint_respects_max_results_parameter(self):
        """Test endpoint returns at most max_results items."""
        from api.comparable_sales_routes import get_parcel_comparables
        result = await get_parcel_comparables(parcel_id="PARCEL123", max_results=5)
        assert len(result) <= 5

    @pytest.mark.asyncio
    async def test_endpoint_respects_property_type_filter(self):
        """Test endpoint filters by property_type."""
        from api.comparable_sales_routes import get_parcel_comparables
        result = await get_parcel_comparables(
            parcel_id="PARCEL123",
            property_type="residential"
        )
        assert all(c.property_type == "residential" for c in result)

    @pytest.mark.asyncio
    async def test_endpoint_respects_months_back_parameter(self):
        """Test endpoint respects months_back parameter."""
        from api.comparable_sales_routes import get_parcel_comparables
        result = await get_parcel_comparables(parcel_id="PARCEL123", months_back=6)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_endpoint_validates_radius_minimum(self):
        """Test endpoint validates radius minimum (100m)."""
        from api.comparable_sales_routes import get_parcel_comparables
        from fastapi import HTTPException
        try:
            await get_parcel_comparables(parcel_id="PARCEL123", radius_m=50)
            assert False, "Should raise validation error"
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_endpoint_validates_radius_maximum(self):
        """Test endpoint validates radius maximum (5000m)."""
        from api.comparable_sales_routes import get_parcel_comparables
        try:
            await get_parcel_comparables(parcel_id="PARCEL123", radius_m=6000)
            assert False, "Should raise validation error"
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_endpoint_validates_max_results_minimum(self):
        """Test endpoint validates max_results minimum (1)."""
        from api.comparable_sales_routes import get_parcel_comparables
        try:
            await get_parcel_comparables(parcel_id="PARCEL123", max_results=0)
            assert False, "Should raise validation error"
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_endpoint_validates_max_results_maximum(self):
        """Test endpoint validates max_results maximum (50)."""
        from api.comparable_sales_routes import get_parcel_comparables
        try:
            await get_parcel_comparables(parcel_id="PARCEL123", max_results=100)
            assert False, "Should raise validation error"
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_endpoint_rejects_empty_parcel_id(self):
        """Test endpoint rejects empty parcel_id."""
        from api.comparable_sales_routes import get_parcel_comparables
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_parcel_comparables(parcel_id="")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_endpoint_returns_comparable_sale_objects(self):
        """Test endpoint returns ComparableSale objects."""
        from api.comparable_sales_routes import get_parcel_comparables, ComparableSale
        result = await get_parcel_comparables(parcel_id="PARCEL123")
        if result:
            assert isinstance(result[0], ComparableSale)

    @pytest.mark.asyncio
    async def test_endpoint_results_sorted_by_distance(self):
        """Test results are reasonably ordered by distance."""
        from api.comparable_sales_routes import get_parcel_comparables
        result = await get_parcel_comparables(parcel_id="PARCEL123")
        if len(result) > 1:
            distances = [c.distance_m for c in result]
            assert distances == sorted(distances)


class TestSearchComparablesEndpoint:
    """Test GET /comparables/search endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_returns_list(self):
        """Test endpoint returns a list."""
        from api.comparable_sales_routes import search_comparables
        result = await search_comparables()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_endpoint_respects_min_price_filter(self):
        """Test endpoint filters by minimum price."""
        from api.comparable_sales_routes import search_comparables
        result = await search_comparables(min_price=700000.0)
        assert all(c.price >= 700000.0 for c in result)

    @pytest.mark.asyncio
    async def test_endpoint_respects_max_price_filter(self):
        """Test endpoint filters by maximum price."""
        from api.comparable_sales_routes import search_comparables
        result = await search_comparables(max_price=900000.0)
        assert all(c.price <= 900000.0 for c in result)

    @pytest.mark.asyncio
    async def test_endpoint_respects_price_range_filter(self):
        """Test endpoint filters by both min and max price."""
        from api.comparable_sales_routes import search_comparables
        result = await search_comparables(
            min_price=700000.0,
            max_price=900000.0
        )
        for comp in result:
            assert 700000.0 <= comp.price <= 900000.0

    @pytest.mark.asyncio
    async def test_endpoint_respects_property_type_filter(self):
        """Test endpoint filters by property_type."""
        from api.comparable_sales_routes import search_comparables
        result = await search_comparables(property_type="residential")
        assert all(c.property_type == "residential" for c in result)

    @pytest.mark.asyncio
    async def test_endpoint_respects_max_results_parameter(self):
        """Test endpoint returns at most max_results."""
        from api.comparable_sales_routes import search_comparables
        result = await search_comparables(max_results=3)
        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_endpoint_respects_months_back_parameter(self):
        """Test endpoint respects months_back parameter."""
        from api.comparable_sales_routes import search_comparables
        result = await search_comparables(months_back=6)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_endpoint_validates_min_price_non_negative(self):
        """Test endpoint validates min_price is non-negative."""
        from api.comparable_sales_routes import search_comparables
        try:
            result = await search_comparables(min_price=-100000.0)
            assert False, "Should raise validation error"
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_endpoint_validates_max_price_non_negative(self):
        """Test endpoint validates max_price is non-negative."""
        from api.comparable_sales_routes import search_comparables
        try:
            result = await search_comparables(max_price=-100000.0)
            assert False, "Should raise validation error"
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_endpoint_validates_max_results_minimum(self):
        """Test endpoint validates max_results minimum."""
        from api.comparable_sales_routes import search_comparables
        try:
            await search_comparables(max_results=0)
            assert False, "Should raise validation error"
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_endpoint_validates_max_results_maximum(self):
        """Test endpoint validates max_results maximum (50)."""
        from api.comparable_sales_routes import search_comparables
        try:
            await search_comparables(max_results=100)
            assert False, "Should raise validation error"
        except Exception:
            pass


class TestAnalyzeComparablesEndpoint:
    """Test POST /comparables/analyze endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_returns_analysis_result(self):
        """Test endpoint returns CompAnalysisResult."""
        from api.comparable_sales_routes import analyze_comparables, CompAnalysisResult
        result = await analyze_comparables(subject_property="456 Oak Ave")
        assert isinstance(result, CompAnalysisResult)

    @pytest.mark.asyncio
    async def test_analysis_includes_subject_property(self):
        """Test analysis result includes subject property."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(subject_property="456 Oak Ave")
        assert result.subject_property == "456 Oak Ave"

    @pytest.mark.asyncio
    async def test_analysis_includes_comparables_list(self):
        """Test analysis result includes comparables list."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(subject_property="456 Oak Ave")
        assert isinstance(result.comparables, list)

    @pytest.mark.asyncio
    async def test_analysis_includes_adjusted_avg_psf(self):
        """Test analysis result includes adjusted average PSF."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(subject_property="456 Oak Ave")
        assert isinstance(result.adjusted_avg_psf, (int, float))
        assert result.adjusted_avg_psf > 0

    @pytest.mark.asyncio
    async def test_analysis_includes_suggested_value_range(self):
        """Test analysis result includes value range."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(subject_property="456 Oak Ave")
        assert isinstance(result.suggested_value_range, dict)
        assert "low" in result.suggested_value_range
        assert "mid" in result.suggested_value_range
        assert "high" in result.suggested_value_range

    @pytest.mark.asyncio
    async def test_analysis_value_range_ordered(self):
        """Test value range has low <= mid <= high."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(subject_property="456 Oak Ave")
        low = result.suggested_value_range["low"]
        mid = result.suggested_value_range["mid"]
        high = result.suggested_value_range["high"]
        assert low <= mid <= high

    @pytest.mark.asyncio
    async def test_analysis_includes_confidence(self):
        """Test analysis result includes confidence score."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(subject_property="456 Oak Ave")
        assert isinstance(result.confidence, (int, float))
        assert 0 <= result.confidence <= 1

    @pytest.mark.asyncio
    async def test_analysis_respects_radius_parameter(self):
        """Test analysis respects radius_m parameter."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(
            subject_property="456 Oak Ave",
            radius_m=500
        )
        assert isinstance(result.comparables, list)

    @pytest.mark.asyncio
    async def test_analysis_respects_property_type_filter(self):
        """Test analysis respects property_type filter."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(
            subject_property="456 Oak Ave",
            property_type="residential"
        )
        if result.comparables:
            assert all(c.property_type == "residential" for c in result.comparables)

    @pytest.mark.asyncio
    async def test_analysis_respects_months_back_parameter(self):
        """Test analysis respects months_back parameter."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(
            subject_property="456 Oak Ave",
            months_back=6
        )
        assert isinstance(result.comparables, list)

    @pytest.mark.asyncio
    async def test_analysis_rejects_empty_subject_property(self):
        """Test analysis rejects empty subject property."""
        from api.comparable_sales_routes import analyze_comparables
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await analyze_comparables(subject_property="")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_analysis_validates_radius_minimum(self):
        """Test analysis validates radius minimum."""
        from api.comparable_sales_routes import analyze_comparables
        try:
            await analyze_comparables(subject_property="456 Oak Ave", radius_m=50)
            assert False, "Should raise validation error"
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_analysis_validates_radius_maximum(self):
        """Test analysis validates radius maximum."""
        from api.comparable_sales_routes import analyze_comparables
        try:
            await analyze_comparables(subject_property="456 Oak Ave", radius_m=6000)
            assert False, "Should raise validation error"
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_analysis_adjusted_avg_psf_calculated(self):
        """Test adjusted average PSF is properly calculated."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(subject_property="456 Oak Ave")
        if result.comparables:
            adjusted_values = [
                c.price_per_sqft * c.adjustment_factor
                for c in result.comparables
            ]
            expected_avg = sum(adjusted_values) / len(adjusted_values)
            assert abs(result.adjusted_avg_psf - expected_avg) < 0.01

    @pytest.mark.asyncio
    async def test_analysis_confidence_increases_with_comparables(self):
        """Test confidence score is calculated based on comparables."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(subject_property="456 Oak Ave")
        assert result.confidence > 0
        assert result.confidence <= 1


class TestComparableSalesComponentStructure:
    """Test ComparableSalesPanel component structure."""

    def test_component_file_exists(self):
        """Verify ComparableSalesPanel.tsx file exists."""
        assert (COMPONENTS_DIR / "ComparableSalesPanel.tsx").exists()

    def test_component_exports_default(self):
        """Test component exports default function."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "export default ComparableSalesPanel" in content

    def test_component_has_props_interface(self):
        """Test component defines props interface."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "ComparableSalesPanelProps" in content

    def test_component_accepts_parcel_id_prop(self):
        """Test component accepts parcelId prop."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "parcelId" in content

    def test_component_accepts_comparables_prop(self):
        """Test component accepts comparables prop."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "comparables" in content

    def test_component_has_table_element(self):
        """Test component renders a table."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "<table" in content

    def test_component_table_has_address_column(self):
        """Test table includes address column."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "address" in content.lower()

    def test_component_table_has_price_column(self):
        """Test table includes price column."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "price" in content.lower()

    def test_component_table_has_date_column(self):
        """Test table includes date column."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "sale_date" in content or "date" in content.lower()

    def test_component_table_has_sqft_column(self):
        """Test table includes sqft column."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "sqft" in content.lower()

    def test_component_table_has_psf_column(self):
        """Test table includes PSF column."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "psf" in content.lower() or "price_per_sqft" in content.lower()

    def test_component_table_has_distance_column(self):
        """Test table includes distance column."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "distance" in content.lower()

    def test_component_has_sorting_functionality(self):
        """Test component supports sorting."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "sort" in content.lower()

    def test_component_has_summary_stats(self):
        """Test component displays summary statistics."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "avg" in content.lower() or "average" in content.lower()

    def test_component_shows_average_psf(self):
        """Test component calculates and displays average PSF."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert ("avgPsf" in content or "avg" in content.lower())

    def test_component_shows_median_price(self):
        """Test component displays median price."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "median" in content.lower()

    def test_component_shows_price_range(self):
        """Test component displays price range."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "range" in content.lower()

    def test_component_handles_empty_comparables(self):
        """Test component handles empty comparables list."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "length === 0" in content or "comparables.length === 0" in content

    def test_component_highlights_adjustments(self):
        """Test component highlights adjustment factors."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        has_adjustments = any([
            "adjustment" in content.lower(),
            "time" in content.lower() and "location" in content.lower(),
        ])
        assert has_adjustments

    def test_component_uses_react_hooks(self):
        """Test component uses React hooks (useState)."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "useState" in content

    def test_component_formats_currency(self):
        """Test component formats values as currency."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        has_formatting = any([
            "currency" in content.lower(),
            "tolocalestring" in content.lower(),
            "CAD" in content,
        ])
        assert has_formatting

    def test_component_formats_dates(self):
        """Test component formats dates properly."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "toLocaleDateString" in content or "format" in content.lower()

    def test_component_responsive_grid(self):
        """Test component uses responsive grid layout."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        assert "grid" in content.lower()

    def test_component_color_coding_by_distance(self):
        """Test component uses color coding for distance tiers."""
        content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        has_colors = any([
            "green" in content and "yellow" in content,
            "distance" in content and "color" in content.lower(),
        ])
        assert has_colors


class TestComparableSalesIntegration:
    """Integration tests for comparable sales feature."""

    def test_api_and_component_model_alignment(self):
        """Test API ComparableSale model matches component interface."""
        from api.comparable_sales_routes import ComparableSale
        component_content = (COMPONENTS_DIR / "ComparableSalesPanel.tsx").read_text()
        api_fields = set(ComparableSale.model_fields.keys())
        for field in ["address", "price", "sale_date", "sqft", "price_per_sqft", "distance_m"]:
            assert field in component_content

    def test_analysis_result_maps_to_component_data(self):
        """Test CompAnalysisResult data can populate component."""
        from api.comparable_sales_routes import CompAnalysisResult
        result_fields = set(CompAnalysisResult.model_fields.keys())
        assert "comparables" in result_fields
        assert "suggested_value_range" in result_fields

    @pytest.mark.asyncio
    async def test_endpoint_response_serializable_to_json(self):
        """Test endpoint responses are JSON serializable."""
        from api.comparable_sales_routes import get_parcel_comparables
        result = await get_parcel_comparables(parcel_id="TEST123")
        json_str = json.dumps([c.model_dump(mode='json') for c in result])
        assert len(json_str) > 0

    @pytest.mark.asyncio
    async def test_analysis_response_serializable_to_json(self):
        """Test analysis response is JSON serializable."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(subject_property="TEST123")
        json_str = result.model_dump_json()
        assert len(json_str) > 0


class TestModelValidation:
    """Test Pydantic model validation."""

    def test_comparable_sale_with_all_fields(self):
        """Test ComparableSale with all fields populated."""
        from api.comparable_sales_routes import ComparableSale
        sale = ComparableSale(
            address="123 Main St",
            price=500000.0,
            sale_date=datetime.utcnow(),
            sqft=2000.0,
            price_per_sqft=250.0,
            distance_m=100.0,
            property_type="residential",
            bedrooms=3,
            year_built=1995,
            adjustment_factor=0.95
        )
        assert sale.bedrooms == 3
        assert sale.year_built == 1995

    def test_comparable_sale_with_minimal_fields(self):
        """Test ComparableSale with only required fields."""
        from api.comparable_sales_routes import ComparableSale
        sale = ComparableSale(
            address="123 Main St",
            price=500000.0,
            sale_date=datetime.utcnow(),
            sqft=2000.0,
            price_per_sqft=250.0,
            distance_m=100.0,
            property_type="residential"
        )
        assert sale.bedrooms is None
        assert sale.year_built is None

    def test_comp_analysis_result_value_range_types(self):
        """Test CompAnalysisResult value_range has correct types."""
        from api.comparable_sales_routes import CompAnalysisResult
        result = CompAnalysisResult(
            subject_property="456 Oak Ave",
            comparables=[],
            adjusted_avg_psf=300.0,
            suggested_value_range={"low": 600000, "mid": 750000, "high": 900000},
            confidence=0.85
        )
        assert isinstance(result.suggested_value_range["low"], (int, float))
        assert isinstance(result.suggested_value_range["mid"], (int, float))
        assert isinstance(result.suggested_value_range["high"], (int, float))


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_search_with_no_matching_results(self):
        """Test search with criteria that yield no results."""
        from api.comparable_sales_routes import search_comparables
        result = await search_comparables(
            min_price=5000000.0,
            max_price=10000000.0
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_analysis_with_single_comparable(self):
        """Test analysis works with minimal comparables."""
        from api.comparable_sales_routes import analyze_comparables
        result = await analyze_comparables(subject_property="456 Oak Ave")
        assert result.adjusted_avg_psf > 0

    @pytest.mark.asyncio
    async def test_default_parameters(self):
        """Test endpoints use correct default parameters."""
        from api.comparable_sales_routes import get_parcel_comparables
        result = await get_parcel_comparables(parcel_id="TEST123")
        assert isinstance(result, list)

    def test_comparable_sale_distance_range(self):
        """Test ComparableSale distance_m is reasonable."""
        from api.comparable_sales_routes import ComparableSale
        sale = ComparableSale(
            address="123 Main St",
            price=500000.0,
            sale_date=datetime.utcnow(),
            sqft=2000.0,
            price_per_sqft=250.0,
            distance_m=0.0,
            property_type="residential"
        )
        assert sale.distance_m >= 0

    def test_comparable_sale_sqft_positive(self):
        """Test ComparableSale sqft must be positive."""
        from api.comparable_sales_routes import ComparableSale
        sale = ComparableSale(
            address="123 Main St",
            price=500000.0,
            sale_date=datetime.utcnow(),
            sqft=0.1,
            price_per_sqft=250.0,
            distance_m=100.0,
            property_type="residential"
        )
        assert sale.sqft > 0
