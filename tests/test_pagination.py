"""
Comprehensive tests for VCL-83 [PERF-012] pagination module.

Tests cover:
- PaginationParams: validation, defaults, offset calculation
- PaginatedResponse: metadata computation, edge cases
- paginate() helper: various data sizes
- CursorPagination: encoding/decoding, stable ordering
- MaxPageSizeMiddleware: enforcement, configuration
- Endpoint integration: backward compatibility
"""

import pytest
import json
import base64
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.testclient import TestClient

from api.pagination import (
    PaginationParams,
    PaginatedResponse,
    paginate,
    MaxPageSizeMiddleware,
    CursorPagination,
    CursorPaginationParams,
    CursorPaginationResponse,
)


# ──────────────────────────────────────────────────────────────────────────
# Test PaginationParams Class
# ──────────────────────────────────────────────────────────────────────────

class TestPaginationParams:
    """Tests for PaginationParams validation and defaults."""

    def test_default_values_in_endpoint(self):
        """Test that default values are sensible when used in an endpoint."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(params: PaginationParams = Depends()):
            return {
                "page": params.page,
                "page_size": params.page_size,
                "sort_by": params.sort_by,
                "sort_order": params.sort_order,
            }

        client = TestClient(app)
        response = client.get("/test")
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["sort_by"] is None
        assert data["sort_order"] == "desc"

    def test_custom_values_in_endpoint(self):
        """Test initialization with custom values in endpoint."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(params: PaginationParams = Depends()):
            return {
                "page": params.page,
                "page_size": params.page_size,
                "sort_by": params.sort_by,
                "sort_order": params.sort_order,
            }

        client = TestClient(app)
        response = client.get("/test?page=2&page_size=50&sort_by=name&sort_order=asc")
        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 50
        assert data["sort_by"] == "name"
        assert data["sort_order"] == "asc"

    def test_offset_calculation(self):
        """Test that offset is computed correctly from page and page_size."""
        params = PaginationParams(page=1, page_size=20)
        assert params.offset == 0

        params = PaginationParams(page=2, page_size=20)
        assert params.offset == 20

        params = PaginationParams(page=5, page_size=10)
        assert params.offset == 40

    def test_limit_alias(self):
        """Test that limit property returns page_size."""
        params = PaginationParams(page_size=50)
        assert params.limit == 50

    def test_page_minimum_validation_endpoint(self):
        """Test that page=0 or negative is rejected via endpoint."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(params: PaginationParams = Depends()):
            return {"page": params.page}

        client = TestClient(app)
        # Page 0 should fail validation
        response = client.get("/test?page=0")
        assert response.status_code == 422

        # Negative page should fail
        response = client.get("/test?page=-1")
        assert response.status_code == 422

    def test_page_size_minimum_validation_endpoint(self):
        """Test that page_size=0 is rejected via endpoint."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(params: PaginationParams = Depends()):
            return {"page_size": params.page_size}

        client = TestClient(app)
        response = client.get("/test?page_size=0")
        assert response.status_code == 422

    def test_page_size_maximum_validation_endpoint(self):
        """Test that page_size>100 is rejected via endpoint."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(params: PaginationParams = Depends()):
            return {"page_size": params.page_size}

        client = TestClient(app)
        response = client.get("/test?page_size=101")
        assert response.status_code == 422

    def test_sort_order_validation_endpoint(self):
        """Test that sort_order must be asc or desc via endpoint."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(params: PaginationParams = Depends()):
            return {"sort_order": params.sort_order}

        client = TestClient(app)
        response = client.get("/test?sort_order=asc")
        assert response.status_code == 200

        response = client.get("/test?sort_order=invalid")
        assert response.status_code == 422

    def test_sort_by_optional(self):
        """Test that sort_by is optional."""
        params = PaginationParams(sort_by=None)
        assert params.sort_by is None

        params = PaginationParams(sort_by="created_at")
        assert params.sort_by == "created_at"


# ──────────────────────────────────────────────────────────────────────────
# Test PaginatedResponse Class
# ──────────────────────────────────────────────────────────────────────────

class TestPaginatedResponse:
    """Tests for PaginatedResponse metadata computation."""

    def test_single_page(self):
        """Test response when all items fit on one page."""
        response = PaginatedResponse.create(
            items=[1, 2, 3],
            total=3,
            page=1,
            page_size=20,
        )
        assert response.total == 3
        assert response.page == 1
        assert response.page_size == 20
        assert response.total_pages == 1
        assert response.has_next is False
        assert response.has_prev is False
        assert response.next_page is None
        assert response.prev_page is None

    def test_first_page_with_more_pages(self):
        """Test first page when there are more pages."""
        response = PaginatedResponse.create(
            items=[1, 2, 3],
            total=100,
            page=1,
            page_size=20,
        )
        assert response.total_pages == 5
        assert response.has_next is True
        assert response.has_prev is False
        assert response.next_page == 2
        assert response.prev_page is None

    def test_middle_page(self):
        """Test middle page has both next and prev."""
        response = PaginatedResponse.create(
            items=list(range(20)),
            total=100,
            page=3,
            page_size=20,
        )
        assert response.total_pages == 5
        assert response.has_next is True
        assert response.has_prev is True
        assert response.next_page == 4
        assert response.prev_page == 2

    def test_last_page(self):
        """Test last page has no next."""
        response = PaginatedResponse.create(
            items=[1],
            total=41,
            page=3,
            page_size=20,
        )
        assert response.total_pages == 3
        assert response.has_next is False
        assert response.has_prev is True
        assert response.next_page is None
        assert response.prev_page == 2

    def test_total_pages_calculation(self):
        """Test total_pages is correctly calculated."""
        # Exact multiple
        response = PaginatedResponse.create([], 100, 1, 20)
        assert response.total_pages == 5

        # With remainder (rounds up)
        response = PaginatedResponse.create([], 99, 1, 20)
        assert response.total_pages == 5

        # Single item
        response = PaginatedResponse.create([], 1, 1, 20)
        assert response.total_pages == 1

        # Empty
        response = PaginatedResponse.create([], 0, 1, 20)
        assert response.total_pages == 0

    def test_empty_results(self):
        """Test response with no items."""
        response = PaginatedResponse.create(
            items=[],
            total=0,
            page=1,
            page_size=20,
        )
        assert response.total == 0
        assert response.total_pages == 0
        assert response.has_next is False
        assert response.has_prev is False


# ──────────────────────────────────────────────────────────────────────────
# Test paginate() Helper Function
# ──────────────────────────────────────────────────────────────────────────

class TestPaginateHelper:
    """Tests for the paginate() helper function."""

    def test_paginate_with_items(self):
        """Test paginate creates correct response."""
        items = [{"id": i} for i in range(10)]
        response = paginate(items, total=100, page=2, page_size=10)

        assert response.items == items
        assert response.total == 100
        assert response.page == 2
        assert response.page_size == 10
        assert response.total_pages == 10
        assert response.next_page == 3
        assert response.prev_page == 1

    def test_paginate_empty(self):
        """Test paginate with no items."""
        response = paginate([], total=0, page=1, page_size=20)
        assert response.items == []
        assert response.total == 0
        assert response.total_pages == 0

    def test_paginate_single_page(self):
        """Test paginate when all items fit on one page."""
        items = list(range(5))
        response = paginate(items, total=5, page=1, page_size=20)

        assert len(response.items) == 5
        assert response.has_next is False
        assert response.has_prev is False


# ──────────────────────────────────────────────────────────────────────────
# Test CursorPagination Encoding/Decoding
# ──────────────────────────────────────────────────────────────────────────

class TestCursorPagination:
    """Tests for cursor-based pagination."""

    def test_encode_cursor(self):
        """Test cursor encoding."""
        cursor = CursorPagination.encode_cursor(last_id=42, last_sort_value="2024-01-15")
        assert isinstance(cursor, str)
        assert len(cursor) > 0
        # Should be valid base64
        try:
            base64.b64decode(cursor)
        except Exception:
            pytest.fail("Cursor is not valid base64")

    def test_encode_decode_roundtrip(self):
        """Test encoding and decoding returns original values."""
        original_id = 42
        original_sort = "2024-01-15T10:30:00"

        cursor = CursorPagination.encode_cursor(original_id, original_sort)
        decoded_id, decoded_sort = CursorPagination.decode_cursor(cursor)

        assert decoded_id == str(original_id)
        assert decoded_sort == original_sort

    def test_decode_invalid_cursor(self):
        """Test that invalid cursors raise ValueError."""
        with pytest.raises(ValueError):
            CursorPagination.decode_cursor("invalid-cursor")

        with pytest.raises(ValueError):
            CursorPagination.decode_cursor(base64.b64encode(b"{}").decode())

    def test_cursor_with_numeric_id(self):
        """Test cursor works with numeric IDs."""
        cursor = CursorPagination.encode_cursor(123456, "high")
        last_id, last_value = CursorPagination.decode_cursor(cursor)
        assert last_id == "123456"
        assert last_value == "high"

    def test_create_response_with_next(self):
        """Test create_response indicates next page when items > page_size."""
        class Item:
            def __init__(self, id, created_at):
                self.id = id
                self.created_at = created_at

        items = [Item(i, f"2024-01-{i:02d}") for i in range(1, 22)]  # 21 items
        response = CursorPagination.create_response(items, page_size=20, sort_order="desc")

        assert response.count == 20
        assert response.has_next is True
        assert response.cursor is not None
        assert len(response.items) == 20

    def test_create_response_no_next(self):
        """Test create_response indicates no next page when items <= page_size."""
        class Item:
            def __init__(self, id, created_at):
                self.id = id
                self.created_at = created_at

        items = [Item(i, f"2024-01-{i:02d}") for i in range(1, 11)]  # 10 items
        response = CursorPagination.create_response(items, page_size=20, sort_order="desc")

        assert response.count == 10
        assert response.has_next is False
        assert response.cursor is None

    def test_create_response_empty(self):
        """Test create_response with no items."""
        response = CursorPagination.create_response([], page_size=20, sort_order="desc")
        assert response.count == 0
        assert response.has_next is False
        assert response.cursor is None


# ──────────────────────────────────────────────────────────────────────────
# Test CursorPaginationParams Validation
# ──────────────────────────────────────────────────────────────────────────

class TestCursorPaginationParams:
    """Tests for CursorPaginationParams validation."""

    def test_default_values(self):
        """Test default parameter values."""
        params = CursorPaginationParams()
        assert params.cursor is None
        assert params.page_size == 20
        assert params.sort_order == "desc"

    def test_with_cursor(self):
        """Test providing a cursor."""
        cursor = "test-cursor-value"
        params = CursorPaginationParams(cursor=cursor)
        assert params.cursor == cursor

    def test_page_size_validation_min(self):
        """Test page_size must be >= 1."""
        with pytest.raises(ValueError):
            CursorPaginationParams(page_size=0)

    def test_page_size_validation_max(self):
        """Test page_size must be <= 100."""
        with pytest.raises(ValueError):
            CursorPaginationParams(page_size=101)

    def test_sort_order_validation(self):
        """Test sort_order must be asc or desc."""
        CursorPaginationParams(sort_order="asc")
        CursorPaginationParams(sort_order="desc")
        with pytest.raises(ValueError):
            CursorPaginationParams(sort_order="random")


# ──────────────────────────────────────────────────────────────────────────
# Test MaxPageSizeMiddleware
# ──────────────────────────────────────────────────────────────────────────

class TestMaxPageSizeMiddleware:
    """Tests for MaxPageSizeMiddleware enforcement."""

    def test_middleware_default_max(self):
        """Test middleware uses default max of 100."""
        app = FastAPI()

        @app.get("/items")
        async def get_items(page_size: int = Query(20)):
            return {"page_size": page_size}

        app.add_middleware(MaxPageSizeMiddleware, max_page_size=100)
        client = TestClient(app)

        # Under limit
        response = client.get("/items?page_size=50")
        assert response.status_code == 200
        assert response.json()["page_size"] == 50

        # At limit
        response = client.get("/items?page_size=100")
        assert response.status_code == 200

        # Over limit - middleware should reject
        response = client.get("/items?page_size=101")
        assert response.status_code == 400
        assert "exceeds maximum" in response.json()["detail"]

    def test_middleware_custom_max(self):
        """Test middleware with custom max page size."""
        app = FastAPI()

        @app.get("/items")
        async def get_items(page_size: int = Query(20)):
            return {"page_size": page_size}

        app.add_middleware(MaxPageSizeMiddleware, max_page_size=50)
        client = TestClient(app)

        # Just under custom limit
        response = client.get("/items?page_size=49")
        assert response.status_code == 200

        # Over custom limit
        response = client.get("/items?page_size=51")
        assert response.status_code == 400

    def test_middleware_no_page_size_param(self):
        """Test middleware allows requests without page_size."""
        app = FastAPI()
        app.add_middleware(MaxPageSizeMiddleware, max_page_size=100)

        @app.get("/items")
        async def get_items():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/items")
        assert response.status_code == 200

    def test_middleware_invalid_page_size_format(self):
        """Test middleware ignores invalid page_size formats."""
        app = FastAPI()
        app.add_middleware(MaxPageSizeMiddleware, max_page_size=100)

        @app.get("/items")
        async def get_items(page_size: int = Query(20)):
            return {"page_size": page_size}

        client = TestClient(app)
        # Invalid format - middleware allows it, FastAPI validation fails
        response = client.get("/items?page_size=abc")
        assert response.status_code == 422  # FastAPI validation error


# ──────────────────────────────────────────────────────────────────────────
# Integration Tests - Endpoint Usage
# ──────────────────────────────────────────────────────────────────────────

class TestEndpointIntegration:
    """Tests for pagination in actual FastAPI endpoints."""

    def test_paginated_endpoint(self):
        """Test endpoint using PaginationParams."""
        app = FastAPI()

        @app.get("/items")
        async def list_items(params: PaginationParams = Depends()):
            # Simulate database query results
            all_items = list(range(1, 101))  # 100 items
            page_items = all_items[params.offset:params.offset + params.limit]

            return paginate(
                items=page_items,
                total=len(all_items),
                page=params.page,
                page_size=params.page_size,
            )

        client = TestClient(app)

        # First page
        response = client.get("/items?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["total_pages"] == 10
        assert data["has_next"] is True
        assert data["next_page"] == 2

        # Last page
        response = client.get("/items?page=10&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 10
        assert data["has_prev"] is True
        assert data["has_next"] is False

    def test_default_pagination(self):
        """Test endpoint with default pagination parameters."""
        app = FastAPI()

        @app.get("/items")
        async def list_items(params: PaginationParams = Depends()):
            all_items = list(range(1, 51))
            page_items = all_items[params.offset:params.offset + params.limit]
            return paginate(page_items, len(all_items), params.page, params.page_size)

        client = TestClient(app)

        # Use all defaults
        response = client.get("/items")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["items"]) == 20

    def test_invalid_page(self):
        """Test endpoint with invalid page values."""
        app = FastAPI()

        @app.get("/items")
        async def list_items(params: PaginationParams = Depends()):
            return {"page": params.page}

        client = TestClient(app)

        # Page 0 should fail validation
        response = client.get("/items?page=0")
        assert response.status_code == 422

        # Negative page should fail
        response = client.get("/items?page=-1")
        assert response.status_code == 422

    def test_backward_compatibility_limit_offset(self):
        """
        Test that endpoints can still support legacy limit/offset params.
        This tests backward compatibility pattern.
        """
        app = FastAPI()

        @app.get("/items")
        async def list_items(
            limit: int = Query(20, ge=1, le=100),
            offset: int = Query(0, ge=0),
        ):
            all_items = list(range(1, 101))
            page_items = all_items[offset:offset + limit]

            # Convert to page-based response for compatibility
            page = (offset // limit) + 1 if limit > 0 else 1
            return paginate(page_items, len(all_items), page, limit)

        client = TestClient(app)

        # Legacy limit/offset params should work
        response = client.get("/items?limit=25&offset=50")
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 25
        assert len(data["items"]) == 25


# ──────────────────────────────────────────────────────────────────────────
# Edge Cases
# ──────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_single_item_dataset(self):
        """Test pagination with exactly one item."""
        response = PaginatedResponse.create(
            items=[1],
            total=1,
            page=1,
            page_size=20,
        )
        assert response.total_pages == 1
        assert response.has_next is False
        assert response.has_prev is False

    def test_very_large_page_size_relative_to_total(self):
        """Test when page_size is much larger than total items."""
        response = PaginatedResponse.create(
            items=list(range(5)),
            total=5,
            page=1,
            page_size=1000,
        )
        assert response.total_pages == 1
        assert response.has_next is False

    def test_exact_page_boundary(self):
        """Test when total is exact multiple of page_size."""
        response = PaginatedResponse.create(
            items=list(range(20)),
            total=100,
            page=5,
            page_size=20,
        )
        assert response.total_pages == 5
        assert response.has_next is False
        assert response.page == 5

    def test_last_page_with_partial_items(self):
        """Test last page with fewer items than page_size."""
        response = PaginatedResponse.create(
            items=[1],
            total=41,
            page=3,
            page_size=20,
        )
        assert response.total_pages == 3
        assert response.has_next is False
        assert len(response.items) == 1

    def test_sort_by_with_reserved_field_names(self):
        """Test sort_by with potentially problematic field names."""
        params = PaginationParams(sort_by="from")
        assert params.sort_by == "from"

        params = PaginationParams(sort_by="class")
        assert params.sort_by == "class"

    def test_cursor_with_special_characters(self):
        """Test cursor encoding with special characters in values."""
        cursor = CursorPagination.encode_cursor(
            last_id="abc-123_456",
            last_sort_value="2024-01-15 10:30:45.123456+00:00"
        )
        decoded_id, decoded_sort = CursorPagination.decode_cursor(cursor)
        assert decoded_id == "abc-123_456"
        assert "10:30:45" in decoded_sort

    def test_very_high_page_number(self):
        """Test requesting a very high page number beyond dataset."""
        params = PaginationParams(page=999999, page_size=20)
        # (999999 - 1) * 20 = 19999960
        assert params.offset == 19999960
        # Response logic should handle this gracefully (return empty)

    def test_offset_overflow_on_high_page(self):
        """Test that offset calculation doesn't overflow on extreme page numbers."""
        params = PaginationParams(page=2147483647, page_size=1)
        # Should not raise, offset will be large but valid
        assert params.offset > 0


# ──────────────────────────────────────────────────────────────────────────
# Response Serialization Tests
# ──────────────────────────────────────────────────────────────────────────

class TestResponseSerialization:
    """Tests for response JSON serialization."""

    def test_paginated_response_serializes_to_json(self):
        """Test that PaginatedResponse can be serialized to JSON."""
        response = PaginatedResponse.create(
            items=[{"id": 1, "name": "Item 1"}],
            total=1,
            page=1,
            page_size=20,
        )

        # Should be serializable
        json_str = response.model_dump_json()
        assert isinstance(json_str, str)

        # Should deserialize back
        data = json.loads(json_str)
        assert data["total"] == 1
        assert data["page"] == 1
        assert len(data["items"]) == 1

    def test_cursor_response_serializes(self):
        """Test CursorPaginationResponse JSON serialization."""
        response = CursorPaginationResponse(
            items=[{"id": 1}],
            cursor="test-cursor",
            has_next=True,
            count=1,
        )

        json_str = response.model_dump_json()
        data = json.loads(json_str)
        assert data["cursor"] == "test-cursor"
        assert data["has_next"] is True
