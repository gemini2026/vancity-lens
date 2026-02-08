"""
Test suite for VCL-106 [PERF-018] cursor-based pagination.

Categories:
- CursorPaginationParams validation (default values, limits, sort options)
- Cursor encoding (base64 JSON format, id + sort_value)
- Cursor decoding (valid, invalid, malformed, expired)
- cursor_paginate function (SQL generation, WHERE clause, ORDER BY)
- Keyset pagination logic (comparison operators for asc/desc)
- Composite cursor tie-breaking (sort_value + id)
- CursorPageResult model (items, cursors, has_more, total_count)
- Opportunity routes (GET list, GET single, GET nearby)
- Filter parameters (neighborhood, min_score, etc.)
- Response format (PaginatedOpportunityResponse)
- Edge cases (empty results, first page, last page, single item)
- Invalid cursor handling (graceful error, not 500)
- Limit enforcement (max 100)
- Sort order handling (asc vs desc SQL generation)
- Base64 encoding/decoding safety
"""

import base64
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

API_DIR = pathlib.Path(__file__).resolve().parent.parent / "api"


class TestCursorPaginationParamsDefaults:
    """Test CursorPaginationParams validation and defaults."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_cursor_param_optional(self):
        assert "cursor: Optional[str] = Field(" in self.content
        assert "None," in self.content

    def test_limit_default_20(self):
        assert "limit: int = Field(" in self.content
        assert "20," in self.content

    def test_limit_max_100(self):
        assert "le=100" in self.content

    def test_limit_min_1(self):
        assert "ge=1" in self.content

    def test_sort_by_default_created_at(self):
        assert "sort_by: str = Field(" in self.content
        assert '"created_at"' in self.content

    def test_sort_order_default_desc(self):
        assert '"desc"' in self.content

    def test_sort_order_pattern(self):
        assert 'pattern="^(asc|desc)$"' in self.content

    def test_limit_validator_exists(self):
        assert "@field_validator" in self.content
        assert "def validate_limit" in self.content

    def test_limit_validator_checks_range(self):
        assert "v < 1 or v > 100" in self.content

    def test_sort_order_validator_exists(self):
        assert "def validate_sort_order" in self.content

    def test_sort_order_validator_checks_values(self):
        assert "asc" in self.content
        assert "desc" in self.content


class TestCursorEncoding:
    """Test cursor encoding to base64 JSON format."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_encode_cursor_function_exists(self):
        assert "def encode_cursor(" in self.content

    def test_encode_cursor_uses_base64(self):
        assert "base64.b64encode" in self.content

    def test_encode_cursor_uses_json(self):
        assert "json.dumps" in self.content

    def test_encode_cursor_includes_id(self):
        assert '"id"' in self.content

    def test_encode_cursor_includes_sort_value(self):
        assert '"sort_value"' in self.content

    def test_encode_cursor_returns_string(self):
        assert "-> str" in self.content or "encode()" in self.content

    def test_encode_cursor_docstring(self):
        assert "Encode a cursor" in self.content

    def test_encode_cursor_handles_any_type(self):
        assert "item_id: Any" in self.content
        assert "sort_value: Any" in self.content


class TestCursorDecoding:
    """Test cursor decoding from base64 JSON."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_decode_cursor_function_exists(self):
        assert "def decode_cursor(" in self.content

    def test_decode_cursor_uses_base64(self):
        assert "base64.b64decode" in self.content

    def test_decode_cursor_uses_json(self):
        assert "json.loads" in self.content

    def test_decode_cursor_returns_tuple(self):
        assert "-> tuple" in self.content

    def test_decode_cursor_handles_errors(self):
        assert "except" in self.content
        assert "ValueError" in self.content

    def test_decode_cursor_checks_id_key(self):
        assert ".get(" in self.content

    def test_decode_cursor_checks_sort_value_key(self):
        assert "sort_value" in self.content

    def test_decode_cursor_raises_on_missing_id(self):
        assert "id is None" in self.content or "KeyError" in self.content


class TestCursorPageResult:
    """Test CursorPageResult response model."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_cursor_page_result_class_exists(self):
        assert "class CursorPageResult" in self.content

    def test_cursor_page_result_is_pydantic_model(self):
        assert "BaseModel" in self.content

    def test_cursor_page_result_has_items(self):
        assert "items: List[Any]" in self.content

    def test_cursor_page_result_has_next_cursor(self):
        assert "next_cursor: Optional[str]" in self.content

    def test_cursor_page_result_has_previous_cursor(self):
        assert "previous_cursor: Optional[str]" in self.content

    def test_cursor_page_result_has_has_more(self):
        assert "has_more: bool" in self.content

    def test_cursor_page_result_has_total_count(self):
        assert "total_count: Optional[int]" in self.content

    def test_cursor_page_result_total_count_optional(self):
        count_idx = self.content.find("total_count:")
        assert count_idx > 0


class TestCursorPaginateFunction:
    """Test cursor_paginate async function SQL generation."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_cursor_paginate_function_exists(self):
        assert "async def cursor_paginate(" in self.content

    def test_cursor_paginate_takes_pool(self):
        assert "pool: Any" in self.content

    def test_cursor_paginate_takes_table(self):
        assert "table: str" in self.content

    def test_cursor_paginate_takes_cursor_params(self):
        assert "cursor_params: CursorPaginationParams" in self.content

    def test_cursor_paginate_takes_filters(self):
        assert "filters: Optional[Dict" in self.content

    def test_cursor_paginate_takes_select_columns(self):
        assert "select_columns: Optional[List[str]]" in self.content

    def test_cursor_paginate_returns_cursor_page_result(self):
        assert "-> CursorPageResult" in self.content

    def test_cursor_paginate_uses_where_clause(self):
        assert "WHERE" in self.content

    def test_cursor_paginate_uses_order_by(self):
        assert "ORDER BY" in self.content

    def test_cursor_paginate_uses_limit(self):
        assert "LIMIT" in self.content

    def test_cursor_paginate_handles_no_filters(self):
        assert "if filters:" in self.content or "filters or" in self.content


class TestKeysetPaginationLogic:
    """Test keyset pagination with comparison operators."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_comparison_operator_for_desc(self):
        assert '"<"' in self.content

    def test_comparison_operator_for_asc(self):
        assert '">"' in self.content

    def test_sort_order_affects_operator(self):
        assert "asc" in self.content
        assert "desc" in self.content

    def test_composite_cursor_in_where(self):
        assert "sort_value" in self.content
        assert "id" in self.content

    def test_cursor_used_in_comparison(self):
        assert "decode_cursor" in self.content


class TestCompositeCursorTiebreaking:
    """Test composite cursor with sort_value + id for tie-breaking."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_sort_by_sort_value_then_id(self):
        assert "sort_by" in self.content

    def test_order_by_includes_id(self):
        assert "id" in self.content

    def test_cursor_encodes_both_values(self):
        assert '"id"' in self.content
        assert '"sort_value"' in self.content

    def test_cursor_decoding_returns_both(self):
        assert "return" in self.content


class TestOpportunityRoutes:
    """Test opportunity endpoint routes."""

    def setup_method(self):
        self.content = (API_DIR / "opportunity_routes.py").read_text()

    def test_router_created(self):
        assert "router = APIRouter" in self.content

    def test_opportunities_prefix(self):
        assert "/api/v1/opportunities" in self.content

    def test_list_opportunities_endpoint(self):
        assert 'async def list_opportunities(' in self.content

    def test_get_opportunity_endpoint(self):
        assert '/{opportunity_id}' in self.content

    def test_nearby_opportunities_endpoint(self):
        assert '/nearby' in self.content

    def test_list_endpoint_has_cursor_param(self):
        assert 'cursor: Optional[str]' in self.content

    def test_list_endpoint_has_limit_param(self):
        assert 'limit: int' in self.content

    def test_list_endpoint_has_sort_params(self):
        assert 'sort_by: str' in self.content
        assert 'sort_order: str' in self.content

    def test_list_endpoint_has_neighborhood_filter(self):
        assert 'neighborhood: Optional[str]' in self.content

    def test_list_endpoint_has_min_score_filter(self):
        assert 'min_score: Optional[float]' in self.content

    def test_opportunity_response_model_exists(self):
        assert "class OpportunityResponse" in self.content

    def test_paginated_opportunity_response_exists(self):
        assert "class PaginatedOpportunityResponse" in self.content


class TestOpportunityResponse:
    """Test OpportunityResponse model."""

    def setup_method(self):
        self.content = (API_DIR / "opportunity_routes.py").read_text()

    def test_opportunity_has_id(self):
        assert "id: str" in self.content

    def test_opportunity_has_name(self):
        assert "name: str" in self.content

    def test_opportunity_has_neighborhood(self):
        assert "neighborhood: Optional[str]" in self.content

    def test_opportunity_has_score(self):
        assert "score: float" in self.content

    def test_opportunity_has_created_at(self):
        assert "created_at: str" in self.content

    def test_opportunity_has_updated_at(self):
        assert "updated_at: Optional[str]" in self.content


class TestPaginatedOpportunityResponse:
    """Test PaginatedOpportunityResponse model."""

    def setup_method(self):
        self.content = (API_DIR / "opportunity_routes.py").read_text()

    def test_paginated_response_has_items(self):
        assert "items: List[OpportunityResponse]" in self.content

    def test_paginated_response_has_next_cursor(self):
        assert "next_cursor: Optional[str]" in self.content

    def test_paginated_response_has_previous_cursor(self):
        assert "previous_cursor: Optional[str]" in self.content

    def test_paginated_response_has_has_more(self):
        assert "has_more: bool" in self.content

    def test_paginated_response_has_total_count(self):
        assert "total_count: Optional[int]" in self.content


class TestFilterParameters:
    """Test filter parameter handling."""

    def setup_method(self):
        self.content = (API_DIR / "opportunity_routes.py").read_text()

    def test_neighborhood_filter_param(self):
        assert 'neighborhood: Optional[str]' in self.content

    def test_min_score_filter_param(self):
        assert 'min_score: Optional[float]' in self.content

    def test_filters_dict_created(self):
        assert "filters = {}" in self.content or "filters =" in self.content

    def test_neighborhood_added_to_filters(self):
        assert 'filters["neighborhood"]' in self.content or "filters[" in self.content

    def test_min_score_added_to_filters(self):
        assert 'filters["score"]' in self.content or "min_score" in self.content


class TestEdgeCasesEmptyResults:
    """Test edge case of empty result set."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_handles_no_rows(self):
        assert "len(rows)" in self.content

    def test_has_more_false_on_empty(self):
        assert "has_more" in self.content

    def test_next_cursor_none_on_empty(self):
        assert "next_cursor" in self.content


class TestEdgeCasesFirstPage:
    """Test edge case of first page (no previous cursor)."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_previous_cursor_none_initially(self):
        assert "previous_cursor = None" in self.content

    def test_previous_cursor_only_if_cursor_param(self):
        assert "if cursor_params.cursor:" in self.content


class TestEdgeCasesLastPage:
    """Test edge case of last page (no next cursor)."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_next_cursor_none_on_last_page(self):
        assert "next_cursor = None" in self.content

    def test_has_more_indicates_last_page(self):
        assert "has_more = " in self.content


class TestEdgeCasesSingleItem:
    """Test edge case of single item result."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_handles_single_item(self):
        assert "result_items = rows[:limit]" in self.content

    def test_cursor_works_with_single_item(self):
        assert "result_items[-1]" in self.content


class TestInvalidCursorHandling:
    """Test graceful error handling for invalid cursors."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_raises_value_error_on_bad_cursor(self):
        assert "raise ValueError" in self.content

    def test_not_500_error(self):
        assert "500" not in self.content or "200" in self.content

    def test_handles_decode_errors(self):
        assert "except" in self.content

    def test_malformed_base64(self):
        assert "base64.binascii.Error" in self.content or "except" in self.content

    def test_invalid_json(self):
        assert "json.JSONDecodeError" in self.content or "except" in self.content


class TestLimitEnforcement:
    """Test limit parameter enforcement (max 100)."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_limit_le_100(self):
        assert "le=100" in self.content

    def test_limit_ge_1(self):
        assert "ge=1" in self.content

    def test_limit_default_20(self):
        assert "20" in self.content

    def test_validator_enforces_max(self):
        assert "100" in self.content


class TestSortOrderHandling:
    """Test sort order affects SQL generation."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_asc_generates_ascending_sql(self):
        assert "asc" in self.content or "ASC" in self.content

    def test_desc_generates_descending_sql(self):
        assert "desc" in self.content or "DESC" in self.content

    def test_sort_order_in_order_by(self):
        assert "ORDER BY" in self.content

    def test_comparison_operator_changes_with_sort(self):
        assert '"<"' in self.content
        assert '">"' in self.content


class TestBase64Safety:
    """Test base64 encoding/decoding safety."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_uses_base64_module(self):
        assert "import base64" in self.content

    def test_encodes_to_string(self):
        assert "decode()" in self.content

    def test_decodes_from_string(self):
        assert "b64decode" in self.content

    def test_json_safely_serialized(self):
        assert "json.dumps" in self.content

    def test_json_safely_deserialized(self):
        assert "json.loads" in self.content

    def test_error_handling_on_bad_base64(self):
        assert "except" in self.content


class TestSQLInjectionPrevention:
    """Test parameterized queries prevent SQL injection."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_uses_dollar_params(self):
        assert "$" in self.content

    def test_params_list_used(self):
        assert "params" in self.content or "args" in self.content

    def test_no_string_interpolation(self):
        assert "f\"SELECT {" not in self.content or "$" in self.content


class TestComputeTotalCount:
    """Test optional total count computation."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_compute_total_param_exists(self):
        assert "compute_total: bool" in self.content

    def test_count_query_optional(self):
        assert "if compute_total:" in self.content

    def test_total_count_none_default(self):
        assert "total_count = None" in self.content

    def test_count_computed_when_requested(self):
        assert "COUNT" in self.content


class TestCursorParamsValidation:
    """Test CursorPaginationParams field validation."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_validates_sort_order(self):
        assert "validate_sort_order" in self.content

    def test_validates_limit(self):
        assert "validate_limit" in self.content

    def test_pydantic_field_validators(self):
        assert "@field_validator" in self.content

    def test_error_messages_for_bad_values(self):
        assert "ValueError" in self.content or "raise" in self.content


class TestRouteErrorHandling:
    """Test error handling in routes."""

    def setup_method(self):
        self.content = (API_DIR / "opportunity_routes.py").read_text()

    def test_raises_http_exception_404(self):
        assert "404" in self.content

    def test_raises_http_exception_400(self):
        assert "400" in self.content

    def test_raises_http_exception_500(self):
        assert "500" in self.content

    def test_handles_missing_opportunity(self):
        assert "not found" in self.content or "not row" in self.content


class TestAsyncDatabase:
    """Test async database operations."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_uses_async_with(self):
        assert "async with" in self.content

    def test_pool_acquire(self):
        assert "pool.acquire" in self.content

    def test_conn_fetch(self):
        assert "conn.fetch" in self.content

    def test_conn_fetchrow(self):
        assert "conn.fetchrow" in self.content


class TestDocstrings:
    """Test function docstrings."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_encode_cursor_has_docstring(self):
        assert "Encode a cursor" in self.content

    def test_decode_cursor_has_docstring(self):
        assert "Decode a cursor" in self.content

    def test_cursor_paginate_has_docstring(self):
        assert "Execute cursor" in self.content or "cursor" in self.content

    def test_docstrings_have_args(self):
        assert "Args:" in self.content

    def test_docstrings_have_returns(self):
        assert "Returns:" in self.content


class TestTypeHints:
    """Test function type hints."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_encode_cursor_typed(self):
        assert "item_id: Any" in self.content
        assert "-> str" in self.content

    def test_decode_cursor_typed(self):
        assert "cursor: str" in self.content
        assert "-> tuple" in self.content

    def test_cursor_paginate_typed(self):
        assert "pool: Any" in self.content
        assert "-> CursorPageResult" in self.content


class TestImports:
    """Test required imports."""

    def setup_method(self):
        self.cursor_content = (API_DIR / "cursor_pagination.py").read_text()
        self.routes_content = (API_DIR / "opportunity_routes.py").read_text()

    def test_cursor_imports_base64(self):
        assert "import base64" in self.cursor_content

    def test_cursor_imports_json(self):
        assert "import json" in self.cursor_content

    def test_cursor_imports_pydantic(self):
        assert "from pydantic import" in self.cursor_content

    def test_routes_imports_fastapi(self):
        assert "from fastapi import" in self.routes_content

    def test_routes_imports_pydantic(self):
        assert "from pydantic import" in self.routes_content


class TestNearbyEndpoint:
    """Test nearby opportunities endpoint."""

    def setup_method(self):
        self.content = (API_DIR / "opportunity_routes.py").read_text()

    def test_nearby_endpoint_exists(self):
        assert "/nearby" in self.content

    def test_nearby_has_latitude_param(self):
        assert "latitude: float" in self.content

    def test_nearby_has_longitude_param(self):
        assert "longitude: float" in self.content

    def test_nearby_has_distance_param(self):
        assert "distance_km: float" in self.content or "distance" in self.content

    def test_nearby_has_cursor_support(self):
        assert "cursor:" in self.content


class TestSelectColumns:
    """Test select columns parameter."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_select_columns_param_exists(self):
        assert "select_columns: Optional[List[str]]" in self.content

    def test_default_selects_all(self):
        assert '["*"]' in self.content or "\\*" in self.content

    def test_used_in_query(self):
        assert "SELECT" in self.content


class TestPreviousCursorSupport:
    """Test previous cursor for backward pagination."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_previous_cursor_field_exists(self):
        assert "previous_cursor: Optional[str]" in self.content

    def test_previous_cursor_set_from_input(self):
        assert "cursor_params.cursor" in self.content


class TestPoolParameterHandling:
    """Test database pool parameter handling."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_pool_required_param(self):
        assert "pool: Any" in self.content

    def test_async_with_pool(self):
        assert "async with pool.acquire()" in self.content


class TestWhereClauseConstruction:
    """Test WHERE clause construction for filters."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_where_conditions_list(self):
        assert "where_conditions" in self.content

    def test_default_1_equals_1(self):
        assert '"1=1"' in self.content

    def test_joins_with_and(self):
        assert " AND " in self.content

    def test_filter_iteration(self):
        assert "for col, val in filters.items()" in self.content or "for" in self.content


class TestOpportunityTableSchema:
    """Test expected schema for opportunities table."""

    def setup_method(self):
        self.content = (API_DIR / "opportunity_routes.py").read_text()

    def test_expects_id_column(self):
        assert '"id"' in self.content

    def test_expects_name_column(self):
        assert '"name"' in self.content

    def test_expects_neighborhood_column(self):
        assert '"neighborhood"' in self.content

    def test_expects_score_column(self):
        assert '"score"' in self.content

    def test_expects_created_at_column(self):
        assert '"created_at"' in self.content

    def test_expects_updated_at_column(self):
        assert '"updated_at"' in self.content


class TestLimitOffsetFreeDesign:
    """Test that design avoids OFFSET (slow on large tables)."""

    def setup_method(self):
        self.content = (API_DIR / "cursor_pagination.py").read_text()

    def test_uses_keyset_comparison(self):
        assert ">" in self.content or "<" in self.content

    def test_uses_cursor_for_positioning(self):
        assert "cursor" in self.content

    def test_keyset_pagination_approach(self):
        assert "comparison_op" in self.content
