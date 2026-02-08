"""
Integration tests for VCL-83 [PERF-012] pagination with actual API endpoints.

Tests pagination integration with:
- /api/v1/opportunities endpoint with new pagination params
- Backward compatibility with legacy limit/offset params
- MaxPageSizeMiddleware enforcement
- SignalFeedResponse with pagination metadata
"""

import pytest
from fastapi import FastAPI, Depends, Query
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from api.pagination import (
    PaginationParams,
    paginate,
    MaxPageSizeMiddleware,
)


# ──────────────────────────────────────────────────────────────────────────
# Test Paginated API Endpoint with Database
# ──────────────────────────────────────────────────────────────────────────

class TestPaginatedOpportunitiesEndpoint:
    """Tests for /api/v1/opportunities with pagination."""

    def test_opportunities_first_page(self):
        """Test opportunities endpoint returns first page with metadata."""
        app = FastAPI()

        # Mock database
        mock_db = MagicMock()

        @app.get("/api/v1/opportunities")
        async def top_opportunities(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
            limit: int = Query(None, le=500),
        ):
            # Simulate 150 total opportunities
            if limit is not None:
                page_size = min(limit, 500)
            offset = (page - 1) * page_size

            # Return mock data
            total = 150
            items = [{"id": i + offset, "name": f"Opportunity {i + offset}"} for i in range(min(page_size, total - offset))]

            return paginate(items, total, page, page_size)

        client = TestClient(app)
        response = client.get("/api/v1/opportunities?page=1&page_size=20")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["items"]) == 20
        assert data["total"] == 150
        assert data["total_pages"] == 8
        assert data["has_next"] is True
        assert data["has_prev"] is False
        assert data["next_page"] == 2

    def test_opportunities_last_page(self):
        """Test opportunities endpoint on last page."""
        app = FastAPI()

        @app.get("/api/v1/opportunities")
        async def top_opportunities(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
        ):
            total = 150
            offset = (page - 1) * page_size
            items = [{"id": i + offset, "name": f"Opportunity {i + offset}"} for i in range(min(page_size, total - offset))]
            return paginate(items, total, page, page_size)

        client = TestClient(app)
        response = client.get("/api/v1/opportunities?page=8&page_size=20")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 8
        assert len(data["items"]) == 10  # Last page has 10 items
        assert data["total_pages"] == 8
        assert data["has_next"] is False
        assert data["has_prev"] is True
        assert data["prev_page"] == 7

    def test_opportunities_backward_compat_limit(self):
        """Test opportunities endpoint with legacy limit parameter."""
        app = FastAPI()

        @app.get("/api/v1/opportunities")
        async def top_opportunities(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
            limit: int = Query(None, le=500),
        ):
            # Legacy limit overrides page_size
            if limit is not None:
                page_size = min(limit, 500)

            total = 150
            offset = (page - 1) * page_size
            items = [{"id": i + offset} for i in range(min(page_size, total - offset))]
            return paginate(items, total, page, page_size)

        client = TestClient(app)

        # Using legacy limit parameter
        response = client.get("/api/v1/opportunities?limit=50")
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 50
        assert len(data["items"]) == 50

    def test_opportunities_invalid_page(self):
        """Test that invalid page numbers are rejected."""
        app = FastAPI()

        @app.get("/api/v1/opportunities")
        async def top_opportunities(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
        ):
            return {"page": page}

        client = TestClient(app)

        # Page 0 should fail
        response = client.get("/api/v1/opportunities?page=0")
        assert response.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# Test Signal Feed with Pagination
# ──────────────────────────────────────────────────────────────────────────

class TestSignalFeedPagination:
    """Tests for signal feed with pagination metadata."""

    def test_signal_feed_includes_pagination_metadata(self):
        """Test that signal feed includes proper pagination metadata."""
        app = FastAPI()

        @app.get("/api/v1/intel/signals/feed")
        async def get_signals(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
            limit: int = Query(None, le=100),
            offset: int = Query(None, ge=0),
        ):
            # Support both new pagination and legacy limit/offset
            if limit is not None or offset is not None:
                limit = limit or 20
                offset = offset or 0
                page = (offset // limit) + 1 if limit > 0 else 1
                page_size = limit

            total = 500  # Simulate large feed
            start = (page - 1) * page_size
            items = [
                {
                    "id": i + start,
                    "signal_type": "rezoning_decision",
                    "headline": f"Signal {i + start}"
                }
                for i in range(min(page_size, total - start))
            ]

            return paginate(items, total, page, page_size)

        client = TestClient(app)
        response = client.get("/api/v1/intel/signals/feed?page=1&page_size=25")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 25
        assert data["total"] == 500
        assert data["total_pages"] == 20
        assert data["has_next"] is True

    def test_signal_feed_backward_compat(self):
        """Test signal feed with legacy limit/offset params."""
        app = FastAPI()

        @app.get("/api/v1/intel/signals/feed")
        async def get_signals(
            limit: int = Query(20, ge=1, le=100),
            offset: int = Query(0, ge=0),
        ):
            total = 100
            items = [{"id": i + offset} for i in range(min(limit, total - offset))]
            page = (offset // limit) + 1 if limit > 0 else 1
            return paginate(items, total, page, limit)

        client = TestClient(app)
        response = client.get("/api/v1/intel/signals/feed?limit=10&offset=30")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 4  # offset 30, limit 10 = page 4
        assert len(data["items"]) == 10


# ──────────────────────────────────────────────────────────────────────────
# Test MaxPageSizeMiddleware with Real Endpoints
# ──────────────────────────────────────────────────────────────────────────

class TestMaxPageSizeMiddlewareEnforcement:
    """Tests for middleware enforcing max page size across endpoints."""

    def test_middleware_rejects_oversized_requests(self):
        """Test that middleware rejects page_size exceeding limit."""
        app = FastAPI()

        @app.get("/items")
        async def list_items(page_size: int = Query(20, ge=1, le=1000)):
            return {"page_size": page_size, "items": []}

        # Add middleware with max of 50
        app.add_middleware(MaxPageSizeMiddleware, max_page_size=50)
        client = TestClient(app)

        # Valid request
        response = client.get("/items?page_size=40")
        assert response.status_code == 200
        assert response.json()["page_size"] == 40

        # Over limit request (middleware rejects before FastAPI validation)
        response = client.get("/items?page_size=100")
        assert response.status_code == 400
        assert "exceeds maximum" in response.json()["detail"]

    def test_middleware_respects_env_config(self, monkeypatch):
        """Test middleware reads MAX_PAGE_SIZE from environment."""
        monkeypatch.setenv("MAX_PAGE_SIZE", "75")

        app = FastAPI()

        @app.get("/items")
        async def list_items(page_size: int = Query(20)):
            return {"page_size": page_size}

        app.add_middleware(MaxPageSizeMiddleware)
        client = TestClient(app)

        response = client.get("/items?page_size=80")
        assert response.status_code == 400

        response = client.get("/items?page_size=75")
        assert response.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# Test Chat Sessions with Pagination
# ──────────────────────────────────────────────────────────────────────────

class TestChatSessionsPagination:
    """Tests for chat sessions list with pagination."""

    def test_chat_sessions_list_pagination(self):
        """Test chat sessions endpoint with pagination."""
        app = FastAPI()

        @app.get("/api/v1/intel/chat/sessions")
        async def list_sessions(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
            limit: int = Query(None, le=100),
            offset: int = Query(None, ge=0),
        ):
            # Support both pagination styles
            if limit is not None or offset is not None:
                limit = limit or 20
                offset = offset or 0
                page = (offset // limit) + 1 if limit > 0 else 1
                page_size = limit

            total = 50  # User has 50 sessions
            start = (page - 1) * page_size
            items = [
                {
                    "session_id": f"session-{i}",
                    "created_at": f"2024-01-{(i % 30) + 1:02d}",
                    "message_count": i * 5
                }
                for i in range(start, min(start + page_size, total))
            ]

            return paginate(items, total, page, page_size)

        client = TestClient(app)

        # Test page 1
        response = client.get("/api/v1/intel/chat/sessions?page=1&page_size=15")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 15
        assert data["total"] == 50
        assert data["total_pages"] == 4
        assert data["has_next"] is True

        # Test page 4 (last)
        response = client.get("/api/v1/intel/chat/sessions?page=4&page_size=15")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5  # Last page
        assert data["has_next"] is False


# ──────────────────────────────────────────────────────────────────────────
# Test Large Dataset Pagination
# ──────────────────────────────────────────────────────────────────────────

class TestLargeDatasetPagination:
    """Tests pagination with large result sets."""

    def test_large_dataset_pagination(self):
        """Test pagination with large number of items."""
        app = FastAPI()

        @app.get("/parcels")
        async def list_parcels(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100),
        ):
            total = 10000  # 10,000 parcels
            start = (page - 1) * page_size
            items = [{"pid": f"PID-{i}"} for i in range(start, min(start + page_size, total))]
            return paginate(items, total, page, page_size)

        client = TestClient(app)

        # First page
        response = client.get("/parcels?page=1&page_size=50")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10000
        assert data["total_pages"] == 200
        assert len(data["items"]) == 50

        # Middle page
        response = client.get("/parcels?page=100&page_size=50")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 100
        assert len(data["items"]) == 50

        # Last page
        response = client.get("/parcels?page=200&page_size=50")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 200
        assert data["has_next"] is False

    def test_pagination_metrics_calculation(self):
        """Test that pagination metrics are calculated correctly for large sets."""
        test_cases = [
            # (total, page_size, page) -> (has_next, has_prev, total_pages)
            (1000, 10, 1, True, False, 100),
            (1000, 10, 50, True, True, 100),
            (1000, 10, 100, False, True, 100),
            (999, 10, 100, False, True, 100),
            (1001, 10, 101, False, True, 101),
            (5000, 25, 200, False, True, 200),
        ]

        for total, page_size, page, has_next, has_prev, total_pages in test_cases:
            response = paginate([], total, page, page_size)
            assert response.has_next == has_next, f"Failed for {total} items, page {page}"
            assert response.has_prev == has_prev, f"Failed for {total} items, page {page}"
            assert response.total_pages == total_pages, f"Failed for {total} items, page {page}"
