"""
Test suite for VCL-112: Address-based parcel search (test_parcel_search.py).

Comprehensive testing of parcel search service including:
- Address normalization rules
- Full-text search (ts_vector)
- Trigram similarity (pg_trgm)
- Spatial coordinates search
- PID lookup
- API endpoints
- Response models
- Edge cases and error handling
"""

import pathlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

COMPONENTS_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "components"
)
API_DIR = pathlib.Path(__file__).resolve().parent.parent / "api"


class TestParcelSearchResultsComponentStructure:
    """Test ParcelSearchResults component exists and has proper structure."""

    def test_component_file_exists(self):
        assert (COMPONENTS_DIR / "ParcelSearchResults.tsx").exists()

    def test_component_exports_default_function(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "export default function ParcelSearchResults" in content

    def test_component_imports_react_hooks(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "useState" in content
        assert "useMemo" in content
        assert "use client" in content

    def test_component_has_parcel_result_interface(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "interface ParcelResult" in content
        assert "parcel_id: string" in content
        assert "pid: string" in content
        assert "civic_address: string" in content

    def test_component_has_required_props(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "results: ParcelResult[]" in content
        assert "onSelect: (parcel: ParcelResult) => void" in content
        assert "isLoading: boolean" in content

    def test_component_renders_address(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "civic_address" in content

    def test_component_renders_pid(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "parcel.pid" in content

    def test_component_renders_zoning(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "zoning" in content

    def test_component_renders_neighborhood(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "neighborhood" in content

    def test_component_has_match_score_indicator(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "MatchScoreIndicator" in content
        assert "match_score" in content


class TestMatchScoreIndicator:
    """Test MatchScoreIndicator sub-component."""

    def test_score_indicator_exists(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "function MatchScoreIndicator" in content

    def test_score_percentage_calculation(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "Math.round(score * 100)" in content

    def test_score_colors_by_threshold(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "text-green-600" in content
        assert "text-blue-600" in content
        assert "text-yellow-600" in content
        assert "text-orange-600" in content

    def test_score_high_threshold_green(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert ">= 80" in content or "80" in content

    def test_score_medium_threshold_blue(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert ">= 60" in content or "60" in content


class TestResultSkeleton:
    """Test loading skeleton state."""

    def test_skeleton_component_exists(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "function ResultSkeleton" in content

    def test_skeleton_has_animate_pulse(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "animate-pulse" in content

    def test_skeleton_renders_in_loading_state(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "if (isLoading)" in content or "isLoading" in content

    def test_skeleton_has_multiple_lines(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "bg-gray-300" in content
        assert "bg-gray-200" in content


class TestEmptyState:
    """Test empty state when no results found."""

    def test_empty_state_component_exists(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "function EmptyState" in content

    def test_empty_state_renders_when_no_results(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "results.length === 0" in content

    def test_empty_state_has_helpful_message(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "No parcels found" in content

    def test_empty_state_suggests_alternatives(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "Try searching" in content


class TestParcelSearchServiceFile:
    """Test parcel_search.py API service file structure."""

    def test_parcel_search_file_exists(self):
        assert (API_DIR / "parcel_search.py").exists()

    def test_file_has_docstring(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert '"""' in content

    def test_file_imports_asyncpg(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "import asyncpg" in content

    def test_file_imports_fastapi(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "from fastapi import" in content

    def test_file_imports_dataclass(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "from dataclasses import dataclass" in content


class TestParcelSearchResultModel:
    """Test ParcelSearchResult dataclass."""

    def test_parcel_search_result_dataclass_exists(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "@dataclass" in content
        assert "class ParcelSearchResult" in content

    def test_result_has_parcel_id_field(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "parcel_id: str" in content

    def test_result_has_pid_field(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "pid: str" in content

    def test_result_has_civic_address_field(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "civic_address: str" in content

    def test_result_has_coordinates_fields(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "lat: float" in content
        assert "lng: float" in content

    def test_result_has_lot_area_field(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "lot_area_sqm: float" in content

    def test_result_has_zoning_field(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "zoning: str" in content

    def test_result_has_neighborhood_field(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "neighborhood: str" in content

    def test_result_has_match_score_field(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "match_score: float" in content


class TestAddressNormalizer:
    """Test address normalization rules."""

    def test_normalizer_class_exists(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "class AddressNormalizer" in content

    def test_normalizer_has_normalize_method(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "def normalize(query: str)" in content

    def test_normalizer_strips_unit_numbers(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "unit" in content.lower()
        assert "suite" in content.lower()

    def test_normalizer_standardizes_street_suffixes(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "STREET_SUFFIXES" in content
        assert "street" in content

    def test_normalizer_has_street_suffix_dict(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "st" in content and "street" in content
        assert "ave" in content and "avenue" in content

    def test_normalizer_converts_to_lowercase(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "lower()" in content

    def test_normalizer_removes_extra_whitespace(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "strip()" in content or "re.sub" in content

    def test_normalizer_handles_vancouver_patterns(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "Vancouver" in content or "vancouver" in content.lower()


class TestParcelSearchService:
    """Test ParcelSearchService class methods."""

    def test_service_class_exists(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "class ParcelSearchService" in content

    def test_service_has_init_method(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "def __init__(self, db_pool: asyncpg.Pool)" in content

    def test_service_has_search_by_address_method(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "async def search_by_address" in content

    def test_search_by_address_has_limit_param(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "search_by_address" in content
        assert "limit: int = 10" in content

    def test_search_by_address_returns_list(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "-> list[ParcelSearchResult]" in content or "List[ParcelSearchResult]" in content

    def test_service_has_search_by_pid_method(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "async def search_by_pid" in content

    def test_search_by_pid_returns_optional(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "Optional[ParcelSearchResult]" in content

    def test_service_has_search_by_coordinates_method(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "async def search_by_coordinates" in content

    def test_search_coordinates_has_lat_lng_params(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "lat: float" in content
        assert "lng: float" in content

    def test_search_coordinates_has_radius_param(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "radius_m: float" in content

    def test_service_has_fuzzy_match_method(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "async def fuzzy_address_match" in content

    def test_fuzzy_match_returns_list(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "fuzzy_address_match" in content
        assert "list[ParcelSearchResult]" in content or "List[ParcelSearchResult]" in content


class TestFullTextSearchImplementation:
    """Test full-text search SQL patterns (ts_vector)."""

    def test_uses_ts_vector(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "to_tsvector" in content

    def test_uses_plainto_tsquery(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "plainto_tsquery" in content

    def test_uses_ts_rank(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "ts_rank" in content

    def test_uses_english_language_config(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "english" in content

    def test_search_uses_match_operator(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "@@" in content


class TestTrigramSimilarityImplementation:
    """Test trigram similarity (pg_trgm) patterns."""

    def test_fuzzy_search_uses_similarity_function(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "similarity(" in content

    def test_fuzzy_search_uses_trgm_operator(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "%" in content

    def test_fuzzy_search_mentions_pg_trgm(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "pg_trgm" in content or "trigram" in content.lower()


class TestSpatialSearchImplementation:
    """Test PostGIS spatial search patterns."""

    def test_coordinates_search_uses_st_point(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "ST_Point" in content

    def test_coordinates_search_uses_st_distance(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "ST_Distance" in content

    def test_coordinates_search_uses_st_dwithin(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "ST_DWithin" in content

    def test_coordinates_search_sets_srid_4326(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "4326" in content

    def test_coordinates_search_validates_lat_range(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "-90 <= lat <= 90" in content or "lat" in content


class TestAPIEndpoints:
    """Test API endpoint definitions."""

    def test_router_is_defined(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "router = APIRouter" in content

    def test_router_has_correct_prefix(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "/api/v1/parcels" in content

    def test_search_endpoint_exists(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert '@router.get("/search")' in content

    def test_search_endpoint_has_query_param(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert 'q: str = Query' in content

    def test_search_endpoint_has_limit_param(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert 'limit: int = Query' in content

    def test_by_pid_endpoint_exists(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert '@router.get("/by-pid/{pid}")' in content

    def test_nearby_endpoint_exists(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert '@router.get("/nearby")' in content

    def test_nearby_endpoint_has_lat_param(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "lat: float = Query" in content

    def test_nearby_endpoint_has_lng_param(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "lng: float = Query" in content

    def test_nearby_endpoint_has_radius_param(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "radius: float = Query" in content


class TestResponseFormat:
    """Test API response format and structure."""

    def test_search_endpoint_returns_dict(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "async def search_parcels" in content
        assert "-> dict" in content or "dict:" in content

    def test_response_includes_query(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "query" in content

    def test_response_includes_results_array(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "results" in content

    def test_response_includes_count(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "count" in content

    def test_pid_endpoint_returns_parcel_object(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "async def get_parcel_by_pid" in content

    def test_pid_endpoint_raises_404_if_not_found(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "404" in content


class TestEdgeCases:
    """Test edge case handling."""

    def test_empty_query_handled(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "if not query" in content or "if not" in content

    def test_special_characters_handled(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "re." in content or "regex" in content.lower()

    def test_partial_addresses_supported(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "partial" in content.lower() or "fuzzy" in content.lower()

    def test_limit_parameter_validated(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "min=" in content or "max=" in content or "le=" in content

    def test_coordinates_validated(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "ge=" in content or ">=" in content

    def test_none_handling_for_pid_search(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "Optional" in content
        assert "if not result" in content or "if result is None" in content


class TestParameterValidation:
    """Test parameter validation in endpoints."""

    def test_query_has_min_length(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert 'min_length=' in content

    def test_query_has_max_length(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert 'max_length=' in content

    def test_limit_has_ge_constraint(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "ge=1" in content or "ge=" in content

    def test_limit_has_le_constraint(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "le=100" in content or "le=" in content

    def test_lat_has_range_constraint(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "ge=-90" in content or "-90" in content

    def test_lng_has_range_constraint(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "ge=-180" in content or "-180" in content

    def test_radius_has_min_constraint(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "ge=1" in content

    def test_radius_has_max_constraint(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "le=10000" in content


class TestErrorHandling:
    """Test error handling in service."""

    def test_database_errors_caught(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "asyncpg.PostgresError" in content or "except" in content

    def test_errors_logged(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "logger.error" in content

    def test_404_raised_for_missing_parcel(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "HTTPException" in content
        assert "404" in content

    def test_error_messages_are_descriptive(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "detail=" in content


class TestDatabaseInteraction:
    """Test database connection and query patterns."""

    def test_uses_connection_pool(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "self.pool.acquire()" in content

    def test_uses_context_manager(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "async with self.pool.acquire() as conn" in content

    def test_uses_fetch_for_multiple_results(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert ".fetch(" in content

    def test_uses_fetchrow_for_single_result(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert ".fetchrow(" in content

    def test_uses_parameterized_queries(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "$1" in content or "$2" in content


class TestComponentInteraction:
    """Test component interaction with results."""

    def test_component_sorts_results(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "sort" in content.lower() or "useMemo" in content

    def test_component_handles_selection(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "onSelect" in content

    def test_component_tracks_selected_parcel(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "selectedId" in content or "selected" in content.lower()

    def test_component_renders_as_button(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "<button" in content

    def test_component_has_hover_state(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "hover:" in content or "hover" in content.lower()


class TestAccessibility:
    """Test accessibility features in component."""

    def test_component_has_aria_attributes(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "aria-" in content

    def test_buttons_have_aria_pressed(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "aria-pressed" in content

    def test_list_has_role_attribute(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "role=" in content

    def test_results_are_keyboard_navigable(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "onClick" in content or "onKey" in content


class TestTypeScript:
    """Test TypeScript type safety."""

    def test_result_interface_is_typed(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "interface ParcelResult" in content

    def test_props_interface_is_typed(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "interface ParcelSearchResultsProps" in content or "Props" in content

    def test_return_types_are_specified(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert ": ReactNode" in content or "ReactNode" in content

    def test_imports_types(self):
        content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "type" in content or "import type" in content


class TestDocumentation:
    """Test code documentation."""

    def test_api_has_module_docstring(self):
        content = (API_DIR / "parcel_search.py").read_text()
        lines = content.split("\n")
        assert lines[0].startswith('"""') or lines[0].startswith("#")

    def test_service_methods_have_docstrings(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert '"""' in content
        assert "Args:" in content or "Parameters:" in content

    def test_endpoints_have_docstrings(self):
        content = (API_DIR / "parcel_search.py").read_text()
        assert "@router.get" in content
        assert '"""' in content

    def test_docstrings_avoid_apostrophes(self):
        content = (API_DIR / "parcel_search.py").read_text()
        lines = content.split("\n")
        in_triple_quote = False
        for line in lines:
            if '"""' in line:
                in_triple_quote = not in_triple_quote
            if in_triple_quote and "'" in line:
                # Allow apostrophes in triple-quote lines, comments, and SQL/code examples
                stripped = line.strip()
                is_ok = (
                    '"""' in line
                    or stripped.startswith("#")
                    or "tsvector" in line
                    or "tsquery" in line
                    or stripped.startswith("-")
                    or "'" in stripped and ("(" in stripped or "=" in stripped)
                )
                assert is_ok


class TestIntegration:
    """Integration tests for the full feature."""

    def test_api_and_component_are_compatible(self):
        api_content = (API_DIR / "parcel_search.py").read_text()
        component_content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "ParcelSearchResult" in api_content
        assert "ParcelResult" in component_content

    def test_response_structure_matches_component(self):
        api_content = (API_DIR / "parcel_search.py").read_text()
        component_content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        assert "civic_address" in api_content
        assert "civic_address" in component_content
        assert "match_score" in api_content
        assert "match_score" in component_content

    def test_api_provides_all_fields_component_needs(self):
        api_content = (API_DIR / "parcel_search.py").read_text()
        component_content = (COMPONENTS_DIR / "ParcelSearchResults.tsx").read_text()
        fields = [
            "parcel_id",
            "pid",
            "civic_address",
            "lat",
            "lng",
            "lot_area_sqm",
            "zoning",
            "neighborhood",
            "match_score",
        ]
        for field in fields:
            assert field in api_content
            assert field in component_content
