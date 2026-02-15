"""Integration tests for FastAPI endpoints."""

from datetime import date
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from api.intelligence.routes import router
from api.intelligence.models import SignalResponse


@pytest.fixture
def app(monkeypatch):
    """Create test FastAPI app with intelligence routes."""
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app, headers={"X-Admin-Key": "test-admin-key"})


class TestChatEndpoint:
    """Test chat endpoint."""

    def test_post_chat_valid_request(self, client):
        """Test POST /chat with valid request."""
        request_body = {
            "query": "What rezoning decisions were made?"
        }

        with patch("api.intelligence.routes.get_db_pool") as mock_get_pool:
            with patch("api.intelligence.routes.get_anthropic_api_key_optional") as mock_anth_key:
                with patch("api.intelligence.routes.handle_chat") as mock_handle:
                    mock_get_pool.return_value = AsyncMock()
                    mock_anth_key.return_value = "test-key"

                    mock_response = MagicMock()
                    mock_response.answer = "Test answer"
                    mock_response.citations = []
                    mock_response.related_signals = []
                    mock_response.session_id = "test-session"
                    mock_response.mode = "full"

                    mock_handle.return_value = mock_response

                    response = client.post("/api/v1/intel/chat", json=request_body)

                    assert response.status_code == 200

    def test_post_chat_missing_api_key_falls_to_demo(self, client):
        """Test chat gracefully degrades to demo mode when API keys are missing."""
        request_body = {"query": "Test"}

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.handle_chat") as mock_handle:
                mock_pool.return_value = AsyncMock()

                mock_response = MagicMock()
                mock_response.answer = "Demo answer"
                mock_response.citations = []
                mock_response.related_signals = []
                mock_response.session_id = "test-session"
                mock_response.mode = "demo"
                mock_handle.return_value = mock_response

                response = client.post("/api/v1/intel/chat", json=request_body)

                assert response.status_code == 200
                data = response.json()
                assert data["mode"] == "demo"


class TestSignalFeedEndpoint:
    """Test signal feed endpoint."""

    def test_get_signals_no_filters(self, client):
        """Test GET /signals with no filters."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signal_feed") as mock_feed:
                mock_pool.return_value = AsyncMock()

                mock_response = MagicMock()
                mock_response.signals = []
                mock_response.total_count = 0
                mock_response.has_more = False

                mock_feed.return_value = mock_response

                response = client.get("/api/v1/intel/signals")

                assert response.status_code == 200

    def test_get_signals_with_filters(self, client):
        """Test GET /signals with filters."""
        query_params = {
            "neighborhood": "Downtown",
            "signal_type": "rezoning_decision",
            "severity_min": "high",
            "limit": 20,
            "offset": 0
        }

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signal_feed") as mock_feed:
                mock_pool.return_value = AsyncMock()

                mock_response = MagicMock()
                mock_response.signals = []
                mock_response.total_count = 0
                mock_response.has_more = False

                mock_feed.return_value = mock_response

                response = client.get("/api/v1/intel/signals", params=query_params)

                assert response.status_code == 200

    def test_get_signals_pagination(self, client):
        """Test signal feed pagination."""
        query_params = {"limit": 50, "offset": 100}

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signal_feed") as mock_feed:
                mock_pool.return_value = AsyncMock()

                mock_response = MagicMock()
                mock_response.signals = []
                mock_response.total_count = 200
                mock_response.has_more = True

                mock_feed.return_value = mock_response

                response = client.get("/api/v1/intel/signals", params=query_params)

                assert response.status_code == 200


class TestSignalDetailEndpoint:
    """Test single signal detail endpoint."""

    def test_get_signal_found(self, client):
        """Test GET /signals/{id} for existing signal."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signal_by_id") as mock_get:
                mock_pool.return_value = AsyncMock()

                mock_signal = SignalResponse(
                    id=1,
                    document_id=1,
                    signal_type="rezoning_decision",
                    summary="Test rezoning approved",
                    headline="Test rezoning",
                    addresses=["123 Test St"],
                    neighborhood="Downtown",
                    decision="approved",
                    vote_for=10,
                    vote_against=1,
                    sentiment="positive_for_development",
                    severity="high",
                    confidence=0.95,
                    event_date=date(2024, 1, 15),
                    source_title="Council Meeting",
                    source_url="https://example.com",
                    source_type="council_minutes",
                    source_date=date(2024, 1, 15),
                )

                mock_get.return_value = mock_signal

                response = client.get("/api/v1/intel/signals/1")

                assert response.status_code == 200

    def test_get_signal_not_found(self, client):
        """Test GET /signals/{id} for nonexistent signal."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signal_by_id") as mock_get:
                mock_pool.return_value = AsyncMock()
                mock_get.return_value = None

                response = client.get("/api/v1/intel/signals/999")

                assert response.status_code == 404


class TestParcelSignalsEndpoint:
    """Test signals near parcel endpoint."""

    def test_get_parcel_signals(self, client):
        """Test GET /signals/parcel/{pid}."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signals_for_parcel") as mock_get:
                mock_pool.return_value = AsyncMock()
                mock_get.return_value = []

                response = client.get("/api/v1/intel/signals/parcel/00123456")

                assert response.status_code == 200

    def test_get_parcel_signals_custom_radius(self, client):
        """Test parcel signals with custom radius."""
        query_params = {"radius": 1000}

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signals_for_parcel") as mock_get:
                mock_pool.return_value = AsyncMock()
                mock_get.return_value = []

                response = client.get(
                    "/api/v1/intel/signals/parcel/00123456",
                    params=query_params
                )

                assert response.status_code == 200


class TestSignalsGeoJSONEndpoint:
    """Test signals GeoJSON endpoint for map overlay."""

    def test_get_signals_geojson(self, client):
        """Test GET /signals/geojson returns valid GeoJSON."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signals_geojson") as mock_geojson:
                mock_pool.return_value = AsyncMock()
                mock_geojson.return_value = {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [-123.1, 49.3]},
                            "properties": {"id": 1, "severity": "high"}
                        }
                    ]
                }

                response = client.get("/api/v1/intel/signals/geojson")

                assert response.status_code == 200
                data = response.json()
                assert data["type"] == "FeatureCollection"
                assert len(data["features"]) == 1

    def test_get_signals_geojson_with_params(self, client):
        """Test GeoJSON endpoint with custom limit and days."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signals_geojson") as mock_geojson:
                mock_pool.return_value = AsyncMock()
                mock_geojson.return_value = {"type": "FeatureCollection", "features": []}

                response = client.get("/api/v1/intel/signals/geojson?limit=50&days=30")

                assert response.status_code == 200
                mock_geojson.assert_called_once()


class TestStatsEndpoint:
    """Test statistics endpoint."""

    def test_get_stats(self, client):
        """Test GET /stats."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signal_stats") as mock_stats:
                mock_pool.return_value = AsyncMock()

                mock_stats.return_value = {
                    "total_signals": 100,
                    "recent_count_7d": 10,
                    "recent_count_30d": 25,
                    "by_type": {},
                    "by_neighborhood": {},
                    "by_severity": {}
                }

                response = client.get("/api/v1/intel/stats")

                assert response.status_code == 200
                data = response.json()
                assert data["total_signals"] == 100


class TestNeighborhoodsEndpoint:
    """Test neighborhoods endpoint."""

    def test_get_neighborhoods(self, client):
        """Test GET /neighborhoods."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_neighborhoods") as mock_get:
                mock_pool.return_value = AsyncMock()
                mock_get.return_value = ["Downtown", "Kitsilano", "Mount Pleasant"]

                response = client.get("/api/v1/intel/neighborhoods")

                assert response.status_code == 200
                data = response.json()
                assert len(data) == 3
                assert "Downtown" in data


class TestAdminScrapeEndpoint:
    """Test admin scrape endpoint."""

    def test_admin_scrape_valid_source(self, client):
        """Test POST /admin/scrape with valid source."""
        query_params = {"source": "council", "days_back": 180}

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            mock_pool.return_value = AsyncMock()

            response = client.post("/api/v1/intel/admin/scrape", params=query_params)

            assert response.status_code == 200
            data = response.json()
            assert "status" in data

    def test_admin_scrape_invalid_source(self, client):
        """Test scrape with invalid source."""
        query_params = {"source": "invalid", "days_back": 180}

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            mock_pool.return_value = AsyncMock()

            response = client.post("/api/v1/intel/admin/scrape", params=query_params)

            assert response.status_code == 400


class TestAdminProcessEndpoint:
    """Test admin process endpoint."""

    def test_admin_process(self, client):
        """Test POST /admin/process."""
        query_params = {"batch_size": 10}

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes._background_process_task", new=AsyncMock()) as mock_bg:
                mock_pool.return_value = MagicMock()

                response = client.post("/api/v1/intel/admin/process", params=query_params)

                assert response.status_code == 200
                data = response.json()
                assert "status" in data
                assert mock_bg.await_count >= 1


class TestAdminStatusEndpoint:
    """Test admin status endpoint."""

    def test_admin_get_status(self, client):
        """Test GET /admin/status."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = conn

            doc_stats = {
                "total_documents": 100,
                "processed_documents": 80,
                "unprocessed_documents": 20
            }
            chunk_stats = {"total_chunks": 500}
            signal_stats = {"total_signals": 200}

            conn.fetchrow.side_effect = [doc_stats, chunk_stats, signal_stats]

            response = client.get("/api/v1/intel/admin/status")

            assert response.status_code == 200
            data = response.json()
            assert "documents" in data
            assert "chunks" in data
            assert "signals" in data


class TestErrorHandling:
    """Test error handling in endpoints."""

    def test_missing_db_pool(self, client):
        """Test endpoint when database pool is not available."""
        with patch("api.intelligence.routes.get_db_pool") as mock_get:
            mock_get.side_effect = Exception("DB not available")

            response = client.get("/api/v1/intel/signals")

            assert response.status_code in [500, 503]

    def test_api_error_handling(self, client):
        """Test error handling in chat endpoint."""
        request_body = {"query": "Test"}

        with patch("api.intelligence.routes.get_db_pool"):
            with patch("api.intelligence.routes.get_anthropic_api_key_optional"):
                with patch("api.intelligence.routes.handle_chat") as mock_handle:
                    mock_handle.side_effect = Exception("API Error")

                    response = client.post("/api/v1/intel/chat", json=request_body)

                    assert response.status_code == 500


class TestEndpointResponses:
    """Test endpoint response formats."""

    def test_chat_response_structure(self, client):
        """Test chat response has correct structure."""
        request_body = {"query": "Test query"}

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_anthropic_api_key_optional") as mock_key:
                with patch("api.intelligence.routes.handle_chat") as mock_chat:
                    mock_pool.return_value = AsyncMock()
                    mock_key.return_value = "key"

                    mock_response = MagicMock()
                    mock_response.answer = "Answer"
                    mock_response.citations = []
                    mock_response.related_signals = []
                    mock_response.session_id = "session"
                    mock_response.mode = "full"
                    mock_response.model_dump.return_value = {
                        "answer": "Answer",
                        "citations": [],
                        "related_signals": [],
                        "session_id": "session",
                        "mode": "full",
                    }

                    mock_chat.return_value = mock_response

                    response = client.post("/api/v1/intel/chat", json=request_body)

                    assert response.status_code == 200
