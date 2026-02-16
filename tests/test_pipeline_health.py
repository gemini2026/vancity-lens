"""
Tests for Pipeline Health Dashboard endpoints.

Covers:
- GET /api/v1/admin/scraper-health — response shape, field presence, DB queries
- POST /api/v1/admin/scraper/{name}/run — valid name, invalid name, no function
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.admin import router as admin_router
from api.intelligence.scheduler import (
    ScraperScheduler,
    ScraperSchedule,
    ScraperResult,
    ScraperStatus,
)


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pool():
    """Create a mock asyncpg pool."""
    pool = AsyncMock()

    # Default: fetchrow returns None (no prior runs)
    pool.fetchrow = AsyncMock(return_value=None)
    # Default: fetchval returns 0
    pool.fetchval = AsyncMock(return_value=0)

    return pool


@pytest.fixture
def mock_scheduler(mock_pool):
    """Create a scheduler with default scrapers (functions are None)."""
    scheduler = ScraperScheduler(db_pool=mock_pool)
    return scheduler


@pytest.fixture
def app_with_scheduler(mock_pool, mock_scheduler):
    """Create a FastAPI test app with admin router, pool, and scheduler."""
    app = FastAPI()

    # Bypass admin auth for tests
    app.include_router(admin_router)

    app.state.pool = mock_pool
    app.state.scheduler = mock_scheduler

    return app


@pytest.fixture
def client(app_with_scheduler):
    """Provide a test client with admin auth bypassed."""
    # Patch require_admin to be a no-op
    with patch("api.admin.require_admin", return_value="test-key"):
        # Re-create router dependencies at request time
        app_with_scheduler.dependency_overrides[
            __import__("api.auth", fromlist=["require_admin"]).require_admin
        ] = lambda: "test-key"
        return TestClient(app_with_scheduler)


@pytest.fixture
def authed_client(mock_pool, mock_scheduler):
    """Create a fully authed test client with admin key bypass."""
    from api.auth import require_admin

    app = FastAPI()
    app.dependency_overrides[require_admin] = lambda: "test-key"
    app.include_router(admin_router)
    app.state.pool = mock_pool
    app.state.scheduler = mock_scheduler

    return TestClient(app)


# ─────────────────────────────────────────────────────────────
# GET /api/v1/admin/scraper-health
# ─────────────────────────────────────────────────────────────


class TestScraperHealth:
    """Tests for the scraper-health endpoint."""

    def test_health_response_shape(self, authed_client, mock_pool):
        """Response has scrapers list and totals dict."""
        resp = authed_client.get("/api/v1/admin/scraper-health")
        assert resp.status_code == 200

        body = resp.json()
        assert "scrapers" in body
        assert "totals" in body
        assert isinstance(body["scrapers"], list)
        assert "documents" in body["totals"]
        assert "signals" in body["totals"]

    def test_health_scraper_fields(self, authed_client, mock_pool):
        """Each scraper entry has all expected fields."""
        resp = authed_client.get("/api/v1/admin/scraper-health")
        body = resp.json()

        expected_fields = {
            "name",
            "enabled",
            "cron",
            "has_function",
            "last_run",
            "status",
            "documents_found",
            "documents_new",
            "next_run",
        }

        for scraper in body["scrapers"]:
            assert expected_fields.issubset(
                scraper.keys()
            ), f"Missing fields in {scraper['name']}: {expected_fields - set(scraper.keys())}"

    def test_health_default_scrapers_present(self, authed_client):
        """Default scrapers from scheduler are listed."""
        resp = authed_client.get("/api/v1/admin/scraper-health")
        body = resp.json()

        names = {s["name"] for s in body["scrapers"]}
        # At minimum, the default scheduler registers these
        assert "council" in names
        assert "dpb" in names
        assert "rezoning" in names
        assert "news" in names

    def test_health_never_run_status(self, authed_client, mock_pool):
        """Scrapers with no DB runs show never_run status."""
        mock_pool.fetchrow = AsyncMock(return_value=None)

        resp = authed_client.get("/api/v1/admin/scraper-health")
        body = resp.json()

        for scraper in body["scrapers"]:
            assert scraper["status"] == "never_run"
            assert scraper["last_run"] is None

    def test_health_with_run_data(self, authed_client, mock_pool):
        """Scrapers with DB runs reflect last run info."""
        mock_pool.fetchrow = AsyncMock(
            return_value={
                "status": "success",
                "started_at": datetime(2026, 2, 16, 10, 0, 0),
                "completed_at": datetime(2026, 2, 16, 10, 5, 0),
                "documents_found": 42,
                "documents_new": 7,
            }
        )

        resp = authed_client.get("/api/v1/admin/scraper-health")
        body = resp.json()

        # At least one scraper should have run data
        statuses = [s["status"] for s in body["scrapers"]]
        assert "success" in statuses

        for scraper in body["scrapers"]:
            if scraper["status"] == "success":
                assert scraper["documents_found"] == 42
                assert scraper["documents_new"] == 7
                assert scraper["last_run"] is not None

    def test_health_totals_from_db(self, authed_client, mock_pool):
        """Totals come from counting documents and intelligence_signals tables."""
        call_count = 0
        async def fake_fetchval(query):
            nonlocal call_count
            call_count += 1
            if "documents" in query:
                return 1500
            if "intelligence_signals" in query:
                return 350
            return 0

        mock_pool.fetchval = fake_fetchval

        resp = authed_client.get("/api/v1/admin/scraper-health")
        body = resp.json()

        assert body["totals"]["documents"] == 1500
        assert body["totals"]["signals"] == 350

    def test_health_no_scheduler(self, mock_pool):
        """Endpoint works even if scheduler is not initialized (empty scrapers)."""
        from api.auth import require_admin

        app = FastAPI()
        app.dependency_overrides[require_admin] = lambda: "test-key"
        app.include_router(admin_router)
        app.state.pool = mock_pool
        # Deliberately do NOT set app.state.scheduler

        client = TestClient(app)
        resp = client.get("/api/v1/admin/scraper-health")
        assert resp.status_code == 200

        body = resp.json()
        assert body["scrapers"] == []

    def test_health_db_error_graceful(self, authed_client, mock_pool):
        """DB errors are handled gracefully, not 500."""
        mock_pool.fetchrow = AsyncMock(side_effect=Exception("DB down"))
        mock_pool.fetchval = AsyncMock(side_effect=Exception("DB down"))

        resp = authed_client.get("/api/v1/admin/scraper-health")
        # Should still return 200 with degraded data
        assert resp.status_code == 200
        body = resp.json()
        assert "scrapers" in body
        assert body["totals"]["documents"] == 0
        assert body["totals"]["signals"] == 0


# ─────────────────────────────────────────────────────────────
# POST /api/v1/admin/scraper/{name}/run
# ─────────────────────────────────────────────────────────────


class TestScraperRun:
    """Tests for the manual scraper trigger endpoint."""

    def test_run_unknown_scraper(self, authed_client):
        """Unknown scraper name returns 404."""
        resp = authed_client.post("/api/v1/admin/scraper/nonexistent/run")
        assert resp.status_code == 404
        assert "Unknown scraper" in resp.json()["detail"]

    def test_run_scraper_no_function(self, authed_client, mock_scheduler):
        """Scraper with no function registered returns 400."""
        # Default scrapers have func=None
        resp = authed_client.post("/api/v1/admin/scraper/council/run")
        assert resp.status_code == 400
        assert "no function registered" in resp.json()["detail"]

    def test_run_scraper_success(self, authed_client, mock_scheduler, mock_pool):
        """Scraper with function registered runs and returns result."""
        # Register a real (mock) function for 'council'
        async def fake_scraper(pool, start, end):
            return {"documents_found": 10, "documents_new": 3, "documents_skipped": 7}

        mock_scheduler.register_scraper(
            "council", fake_scraper, "0 6 * * *"
        )

        # Mock _store_run to avoid real DB write
        mock_scheduler._store_run = AsyncMock()

        resp = authed_client.post("/api/v1/admin/scraper/council/run")
        assert resp.status_code == 200

        body = resp.json()
        assert body["ok"] is True
        assert "result" in body
        assert body["result"]["scraper_name"] == "council"
        assert body["result"]["documents_found"] == 10
        assert body["result"]["documents_new"] == 3
        assert body["result"]["status"] == "success"

    def test_run_scraper_failure(self, authed_client, mock_scheduler, mock_pool):
        """Scraper that raises an exception returns failed result."""
        async def failing_scraper(pool, start, end):
            raise RuntimeError("Network timeout")

        mock_scheduler.register_scraper(
            "council", failing_scraper, "0 6 * * *"
        )
        mock_scheduler._store_run = AsyncMock()

        resp = authed_client.post("/api/v1/admin/scraper/council/run")
        assert resp.status_code == 200

        body = resp.json()
        assert body["ok"] is True
        assert body["result"]["status"] == "failed"
        assert len(body["result"]["errors"]) > 0

    def test_run_no_scheduler(self, mock_pool):
        """Returns 503 if scheduler is not initialized."""
        from api.auth import require_admin

        app = FastAPI()
        app.dependency_overrides[require_admin] = lambda: "test-key"
        app.include_router(admin_router)
        app.state.pool = mock_pool
        # No scheduler

        client = TestClient(app)
        resp = client.post("/api/v1/admin/scraper/council/run")
        assert resp.status_code == 503
        assert "Scheduler not initialized" in resp.json()["detail"]

    def test_run_result_shape(self, authed_client, mock_scheduler, mock_pool):
        """Run result has all expected ScraperResult fields."""
        async def fake_scraper(pool, start, end):
            return {"documents_found": 5, "documents_new": 2, "documents_skipped": 3}

        mock_scheduler.register_scraper("news", fake_scraper, "0 */6 * * *")
        mock_scheduler._store_run = AsyncMock()

        resp = authed_client.post("/api/v1/admin/scraper/news/run")
        body = resp.json()

        result = body["result"]
        expected_fields = {
            "scraper_name",
            "started_at",
            "completed_at",
            "duration_seconds",
            "documents_found",
            "documents_new",
            "documents_skipped",
            "errors",
            "status",
        }
        assert expected_fields.issubset(
            result.keys()
        ), f"Missing fields: {expected_fields - set(result.keys())}"
