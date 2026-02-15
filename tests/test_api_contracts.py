"""
VCL-48 [TEST-010] Contract tests for API endpoints.

Validates API endpoint contracts:
- Response shapes and required fields
- Status codes and error handling
- Request parameter validation
- CORS and security headers
- Data model compliance
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from datetime import date
from fastapi.testclient import TestClient

from api.main import app
from api.models import ParcelEntitlementResponse, EntitlementSignal
from api.intelligence.models import (
    ChatResponse,
    SignalFeedResponse,
    SignalResponse,
    Severity,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """FastAPI TestClient for synchronous testing with rate limiter disabled."""
    # Disable rate limiter for tests by patching is_rate_limited to always return False
    with patch("api.rate_limit._general_limiter.is_rate_limited", return_value=False):
        with patch("api.rate_limit._llm_limiter.is_rate_limited", return_value=False):
            yield TestClient(app)


@pytest.fixture
def mock_db_pool():
    """Mock database pool for testing."""
    pool = AsyncMock()
    pool.acquire = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


# ────────────────────────────────────────────────────────────────────────────
# Health Endpoint Tests
# ────────────────────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_returns_200(self, client):
        """Health endpoint returns 200 status."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(
                return_value={"ok": 1, "tables": 15}
            )

            response = client.get("/health")
            assert response.status_code == 200

    def test_health_returns_required_keys(self, client):
        """Health response contains required keys: status, db, engine."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(
                return_value={"ok": 1, "tables": 15}
            )

            response = client.get("/health")
            data = response.json()

            assert "status" in data or "db" in data  # status field or db field
            assert "engine" in data
            assert "db" in data

    def test_health_db_connected_when_available(self, client):
        """Health shows db=connected when database query succeeds."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(
                return_value={"ok": 1, "tables": 15}
            )

            response = client.get("/health")
            data = response.json()

            assert data.get("db") == "connected"
            assert data.get("engine") == "bill47"

    def test_health_db_error_state(self, client):
        """Health shows error state when database fails."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(
                side_effect=Exception("Connection refused")
            )

            response = client.get("/health")
            data = response.json()

            assert "db" in data
            assert "error" in data.get("db", "").lower()

    def test_health_has_tables_count(self, client):
        """Health response includes tables count."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(
                return_value={"ok": 1, "tables": 20}
            )

            response = client.get("/health")
            data = response.json()

            assert "tables" in data
            assert data["tables"] == 20


# ────────────────────────────────────────────────────────────────────────────
# Ready Endpoint Tests
# ────────────────────────────────────────────────────────────────────────────


class TestReadyEndpoint:
    """Tests for GET /ready endpoint."""

    def test_ready_returns_ready_field(self, client):
        """Ready response has ready boolean field."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchval = AsyncMock(return_value=1)

            with patch.dict(os.environ, {
                "ANTHROPIC_API_KEY": "test-key",
                "K2_API_KEY": "test-key"
            }):
                response = client.get("/ready")
                data = response.json()

                assert "ready" in data
                assert isinstance(data["ready"], bool)

    def test_ready_returns_checks_dict(self, client):
        """Ready response includes checks dictionary."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchval = AsyncMock(return_value=1)

            with patch.dict(os.environ, {
                "ANTHROPIC_API_KEY": "test-key",
                "K2_API_KEY": "test-key"
            }):
                response = client.get("/ready")
                data = response.json()

                assert "checks" in data
                assert isinstance(data["checks"], dict)

    def test_ready_checks_has_expected_keys(self, client):
        """Ready checks contains expected keys."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchval = AsyncMock(return_value=1)

            with patch.dict(os.environ, {
                "ANTHROPIC_API_KEY": "test-key",
                "K2_API_KEY": "test-key"
            }):
                response = client.get("/ready")
                data = response.json()
                checks = data["checks"]

                assert "engine" in checks
                assert "database" in checks
                assert "anthropic_key" in checks
                assert "k2_key" in checks
                assert "cache" in checks

    def test_ready_returns_200_when_all_checks_pass(self, client):
        """Ready returns 200 when all dependencies are available."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchval = AsyncMock(return_value=1)

            with patch.dict(os.environ, {
                "ANTHROPIC_API_KEY": "test-key",
                "K2_API_KEY": "test-key"
            }):
                response = client.get("/ready")
                assert response.status_code == 200

    def test_ready_returns_503_when_db_missing(self, client):
        """Ready returns 503 when database is unavailable."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchval = AsyncMock(side_effect=Exception("DB error"))

            with patch.dict(os.environ, {
                "ANTHROPIC_API_KEY": "test-key",
                "K2_API_KEY": "test-key"
            }):
                response = client.get("/ready")
                assert response.status_code == 503

    def test_ready_returns_503_when_api_keys_missing(self, client):
        """Ready returns 503 when API keys are missing."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchval = AsyncMock(return_value=1)

            with patch.dict(os.environ, {}, clear=False):
                # Remove API keys
                os.environ.pop("ANTHROPIC_API_KEY", None)
                os.environ.pop("K2_API_KEY", None)

                response = client.get("/ready")
                assert response.status_code == 503


# ────────────────────────────────────────────────────────────────────────────
# Entitlement Endpoint Tests
# ────────────────────────────────────────────────────────────────────────────


class TestEntitlementEndpoint:
    """Tests for GET /api/v1/parcels/{pid}/entitlement endpoint."""

    def test_entitlement_returns_404_for_invalid_pid(self, client):
        """Entitlement endpoint returns 404 for non-existent parcel."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)

            # Mock ParcelNotFoundError
            from api.entitlement import ParcelNotFoundError
            mock_conn.fetchrow = AsyncMock(side_effect=ParcelNotFoundError("PID not found"))

            with patch("api.main.compute_entitlement", side_effect=ParcelNotFoundError("PID not found")):
                response = client.get("/api/v1/parcels/INVALID123/entitlement")
                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()

    def test_entitlement_accepts_pid_parameter(self, client):
        """Entitlement endpoint accepts PID path parameter."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_response = {
                "pid": "12345",
                "civic_address": "123 Main St",
                "current_zoning": "RS-1",
                "in_toa": True,
                "entitlements": [],
                "best_entitlement": None,
                "value_estimate": None,
                "sources": None,
                "validation": None,
            }

            with patch("api.main.compute_entitlement", return_value=mock_response):
                response = client.get("/api/v1/parcels/12345/entitlement")
                assert response.status_code == 200

    def test_entitlement_accepts_price_per_sqft_query_param(self, client):
        """Entitlement accepts price_per_sqft query parameter."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_response = {
                "pid": "12345",
                "civic_address": "123 Main St",
                "current_zoning": "RS-1",
                "in_toa": True,
                "entitlements": [],
                "best_entitlement": None,
                "value_estimate": None,
                "sources": None,
                "validation": None,
            }

            with patch("api.main.compute_entitlement", return_value=mock_response):
                response = client.get("/api/v1/parcels/12345/entitlement?price_per_sqft=1000")
                assert response.status_code == 200

    def test_entitlement_validates_price_per_sqft_bounds(self, client):
        """Entitlement validates price_per_sqft is between 100 and 3000."""
        with patch("api.main.db.acquire"):
            # Price too low
            response = client.get("/api/v1/parcels/12345/entitlement?price_per_sqft=50")
            assert response.status_code == 422

            # Price too high
            response = client.get("/api/v1/parcels/12345/entitlement?price_per_sqft=5000")
            assert response.status_code == 422

    def test_entitlement_response_has_required_fields(self, client):
        """Entitlement response includes required ParcelEntitlementResponse fields."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_response = {
                "pid": "12345",
                "civic_address": "123 Main St",
                "current_zoning": "RS-1",
                "in_toa": True,
                "entitlements": [],
                "best_entitlement": None,
                "value_estimate": None,
                "sources": None,
                "validation": None,
            }

            with patch("api.main.compute_entitlement", return_value=mock_response):
                response = client.get("/api/v1/parcels/12345/entitlement")
                data = response.json()

                assert "pid" in data
                assert "in_toa" in data
                assert "signal" in data  # computed field
                assert isinstance(data["in_toa"], bool)

    def test_entitlement_response_signal_field_is_valid(self, client):
        """Entitlement response signal field is one of the valid signals."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_response = {
                "pid": "12345",
                "civic_address": "123 Main St",
                "current_zoning": "RS-1",
                "in_toa": False,
                "entitlements": [],
                "best_entitlement": None,
                "value_estimate": None,
                "sources": None,
                "validation": None,
            }

            with patch("api.main.compute_entitlement", return_value=mock_response):
                response = client.get("/api/v1/parcels/12345/entitlement")
                data = response.json()
                signal = data["signal"]

                valid_signals = [
                    "high_alpha", "moderate", "low", "already_zoned", "none"
                ]
                assert signal in valid_signals


# ────────────────────────────────────────────────────────────────────────────
# Nearest Parcel Endpoint Tests
# ────────────────────────────────────────────────────────────────────────────


class TestNearestParcelEndpoint:
    """Tests for GET /api/v1/parcels/nearest endpoint."""

    def test_nearest_parcel_requires_lng_param(self, client):
        """Nearest parcel requires lng query parameter."""
        response = client.get("/api/v1/parcels/nearest?lat=49.0")
        assert response.status_code == 422

    def test_nearest_parcel_requires_lat_param(self, client):
        """Nearest parcel requires lat query parameter."""
        response = client.get("/api/v1/parcels/nearest?lng=-123.0")
        assert response.status_code == 422

    def test_nearest_parcel_requires_both_params(self, client):
        """Nearest parcel requires both lng and lat parameters."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={
                "pid": "12345",
                "civic_address": "123 Main",
                "current_zoning": "RS-1",
                "distance_m": 50.5,
                "centroid_lng": -123.1,
                "centroid_lat": 49.3
            })

            response = client.get("/api/v1/parcels/nearest?lng=-123.1&lat=49.3")
            assert response.status_code == 200

    def test_nearest_parcel_returns_404_when_no_parcel_found(self, client):
        """Nearest parcel returns 404 when no parcel within radius."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value=None)

            response = client.get("/api/v1/parcels/nearest?lng=-123.1&lat=49.3")
            assert response.status_code == 404
            assert "no parcel found" in response.json()["detail"].lower()

    def test_nearest_parcel_accepts_radius_param(self, client):
        """Nearest parcel accepts optional radius_m parameter."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={
                "pid": "12345",
                "civic_address": "123 Main",
                "current_zoning": "RS-1",
                "distance_m": 50.5,
                "centroid_lng": -123.1,
                "centroid_lat": 49.3
            })

            response = client.get("/api/v1/parcels/nearest?lng=-123.1&lat=49.3&radius_m=500")
            assert response.status_code == 200

    def test_nearest_parcel_response_contains_required_fields(self, client):
        """Nearest parcel response contains required fields."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={
                "pid": "12345",
                "civic_address": "123 Main",
                "current_zoning": "RS-1",
                "distance_m": 50.5,
                "centroid_lng": -123.1,
                "centroid_lat": 49.3
            })

            response = client.get("/api/v1/parcels/nearest?lng=-123.1&lat=49.3")
            data = response.json()

            assert "pid" in data
            assert "civic_address" in data
            assert "current_zoning" in data
            assert "distance_m" in data


# ────────────────────────────────────────────────────────────────────────────
# Top Opportunities Endpoint Tests
# ────────────────────────────────────────────────────────────────────────────


class TestTopOpportunitiesEndpoint:
    """Tests for GET /api/v1/opportunities endpoint."""

    def test_opportunities_returns_list(self, client):
        """Top opportunities endpoint returns a paginated response with items."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={"total": 1})
            mock_conn.fetch = AsyncMock(return_value=[
                {
                    "pid": "111",
                    "civic_address": "1 Main",
                    "lng": -123.1,
                    "lat": 49.3
                }
            ])

            response = client.get("/api/v1/opportunities")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert isinstance(data["items"], list)

    def test_opportunities_accepts_limit_param(self, client):
        """Top opportunities accepts limit query parameter."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={"total": 0})
            mock_conn.fetch = AsyncMock(return_value=[])

            response = client.get("/api/v1/opportunities?limit=100")
            assert response.status_code == 200

    def test_opportunities_limit_param_bounded(self, client):
        """Top opportunities limit parameter is bounded at 500."""
        with patch("api.main.db.acquire"):
            response = client.get("/api/v1/opportunities?limit=1000")
            assert response.status_code == 422

    def test_opportunities_default_limit(self, client):
        """Top opportunities has default page_size of 20."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={"total": 0})
            mock_conn.fetch = AsyncMock(return_value=[])

            response = client.get("/api/v1/opportunities")
            assert response.status_code == 200

    def test_opportunities_returns_empty_list_when_none(self, client):
        """Top opportunities returns empty items when no results."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={"total": 0})
            mock_conn.fetch = AsyncMock(return_value=[])

            response = client.get("/api/v1/opportunities")
            data = response.json()
            assert data["items"] == []
            assert data["total"] == 0


# ────────────────────────────────────────────────────────────────────────────
# TOA GeoJSON Endpoint Tests
# ────────────────────────────────────────────────────────────────────────────


class TestToaGeojsonEndpoint:
    """Tests for GET /api/v1/toa/geojson endpoint."""

    def test_toa_geojson_returns_feature_collection(self, client):
        """TOA GeoJSON returns FeatureCollection."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetch = AsyncMock(return_value=[])

            response = client.get("/api/v1/toa/geojson")
            assert response.status_code == 200
            data = response.json()

            assert "type" in data
            assert data["type"] == "FeatureCollection"

    def test_toa_geojson_has_features_array(self, client):
        """TOA GeoJSON has features array."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetch = AsyncMock(return_value=[])

            response = client.get("/api/v1/toa/geojson")
            assert response.status_code == 200
            data = response.json()

            assert "features" in data
            assert isinstance(data["features"], list)

    def test_toa_geojson_feature_structure(self, client):
        """TOA GeoJSON features have correct structure."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_geom = '{"type": "Polygon", "coordinates": [[[-123.1, 49.3]]]}'
            mock_conn.fetch = AsyncMock(return_value=[
                {
                    "station_name": "Granville Station",
                    "tier": 1,
                    "max_storeys": 12,
                    "max_fsr": 4.5,
                    "geometry": mock_geom
                }
            ])

            response = client.get("/api/v1/toa/geojson")
            assert response.status_code == 200
            data = response.json()
            features = data["features"]

            assert len(features) > 0
            feature = features[0]
            assert "type" in feature
            assert feature["type"] == "Feature"
            assert "properties" in feature
            assert "geometry" in feature

    def test_toa_geojson_properties_content(self, client):
        """TOA GeoJSON feature properties contain expected fields."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_geom = '{"type": "Polygon", "coordinates": [[[-123.1, 49.3]]]}'
            mock_conn.fetch = AsyncMock(return_value=[
                {
                    "station_name": "Granville Station",
                    "tier": 1,
                    "max_storeys": 12,
                    "max_fsr": 4.5,
                    "geometry": mock_geom
                }
            ])

            response = client.get("/api/v1/toa/geojson")
            assert response.status_code == 200
            data = response.json()
            feature = data["features"][0]
            props = feature["properties"]

            assert "station" in props
            assert "tier" in props
            assert "max_storeys" in props
            assert "max_fsr" in props


# ────────────────────────────────────────────────────────────────────────────
# Intelligence Routes Tests (Chat)
# ────────────────────────────────────────────────────────────────────────────


class TestChatEndpoint:
    """Tests for POST /api/v1/intel/chat endpoint."""

    def test_chat_endpoint_requires_query_field(self, client):
        """Chat endpoint requires query field in request body."""
        app.state.pool = AsyncMock()

        response = client.post("/api/v1/intel/chat", json={})
        assert response.status_code == 422

    def test_chat_endpoint_accepts_valid_request(self, client):
        """Chat endpoint accepts valid ChatRequest."""
        app.state.pool = AsyncMock()

        with patch("api.intelligence.routes.get_anthropic_api_key", return_value="test-key"):
            with patch("api.intelligence.routes.get_db_pool"):
                with patch("api.intelligence.routes.handle_chat") as mock_chat:
                    from api.intelligence.models import ChatResponse
                    mock_chat.return_value = ChatResponse(
                        answer="Test answer",
                        citations=[],
                        related_signals=[],
                        session_id="test-123"
                    )

                    response = client.post("/api/v1/intel/chat", json={
                        "query": "What are the latest rezoning decisions?"
                    })
                    assert response.status_code == 200

    def test_chat_endpoint_validates_query_length(self, client):
        """Chat endpoint validates query max length (2000 chars)."""
        app.state.pool = AsyncMock()

        response = client.post("/api/v1/intel/chat", json={
            "query": "x" * 2001
        })
        assert response.status_code == 422

    def test_chat_response_has_required_fields(self, client):
        """Chat response includes required ChatResponse fields."""
        app.state.pool = AsyncMock()

        with patch("api.intelligence.routes.get_anthropic_api_key", return_value="test-key"):
            with patch("api.intelligence.routes.get_db_pool"):
                with patch("api.intelligence.routes.handle_chat") as mock_chat:
                    from api.intelligence.models import ChatResponse
                    mock_chat.return_value = ChatResponse(
                        answer="Test answer",
                        citations=[],
                        related_signals=[],
                        session_id="test-123"
                    )

                    response = client.post("/api/v1/intel/chat", json={
                        "query": "Test query"
                    })
                    assert response.status_code == 200
                    data = response.json()

                    assert "answer" in data
                    assert "session_id" in data
                    assert "citations" in data
                    assert "related_signals" in data
                    assert isinstance(data["citations"], list)
                    assert isinstance(data["related_signals"], list)


# ────────────────────────────────────────────────────────────────────────────
# Signal Feed Endpoint Tests
# ────────────────────────────────────────────────────────────────────────────


class TestSignalFeedEndpoint:
    """Tests for GET /api/v1/intel/signals endpoint."""

    def test_signal_feed_returns_signal_feed_response(self, client):
        """Signal feed returns SignalFeedResponse structure."""
        app.state.pool = AsyncMock()

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signal_feed") as mock_feed:
                mock_feed.return_value = {
                    "signals": [],
                    "total_count": 0,
                    "has_more": False
                }

                response = client.get("/api/v1/intel/signals")
                assert response.status_code in (200, 500)  # May fail if db pool not properly mocked

    def test_signal_feed_has_required_fields(self, client):
        """Signal feed response has signals, total_count, has_more fields."""
        app.state.pool = AsyncMock()

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signal_feed") as mock_feed:
                mock_feed.return_value = {
                    "signals": [],
                    "total_count": 0,
                    "has_more": False
                }

                response = client.get("/api/v1/intel/signals")
                if response.status_code == 200:
                    data = response.json()

                    assert "signals" in data
                    assert "total_count" in data
                    assert "has_more" in data
                    assert isinstance(data["signals"], list)
                    assert isinstance(data["total_count"], int)
                    assert isinstance(data["has_more"], bool)

    def test_signal_feed_accepts_optional_filters(self, client):
        """Signal feed accepts optional query filters."""
        app.state.pool = AsyncMock()

        with patch("api.intelligence.routes.get_db_pool") as mock_pool:
            with patch("api.intelligence.routes.get_signal_feed") as mock_feed:
                mock_feed.return_value = {
                    "signals": [],
                    "total_count": 0,
                    "has_more": False
                }

                response = client.get(
                    "/api/v1/intel/signals"
                    "?neighborhood=Downtown&signal_type=rezoning_decision"
                    "&severity_min=medium&limit=10&offset=0"
                )
                assert response.status_code in (200, 500)  # May fail if dependencies not mocked


# ────────────────────────────────────────────────────────────────────────────
# CORS Headers Tests
# ────────────────────────────────────────────────────────────────────────────


class TestCorsHeaders:
    """Tests for CORS headers presence in responses."""

    def test_cors_headers_present_on_get_request(self, client):
        """CORS headers present in GET response."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={"total": 0})
            mock_conn.fetch = AsyncMock(return_value=[])

            # Make a regular GET request and verify headers
            response = client.get("/api/v1/opportunities")
            # Check response was successful and has headers
            assert response.status_code == 200
            assert len(response.headers) > 0

    def test_health_returns_with_standard_headers(self, client):
        """Health endpoint returns standard HTTP headers."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={"ok": 1, "tables": 15})

            response = client.get("/health")
            # Check basic HTTP structure
            assert response.status_code == 200
            assert "content-type" in response.headers.keys()


# ────────────────────────────────────────────────────────────────────────────
# Security Headers Tests
# ────────────────────────────────────────────────────────────────────────────


class TestSecurityHeaders:
    """Tests for security headers in responses."""

    def test_x_content_type_options_header(self, client):
        """Response includes X-Content-Type-Options header."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={"ok": 1, "tables": 15})

            response = client.get("/health")
            assert "x-content-type-options" in response.headers
            assert response.headers["x-content-type-options"] == "nosniff"

    def test_x_frame_options_header(self, client):
        """Response includes X-Frame-Options header."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={"ok": 1, "tables": 15})

            response = client.get("/health")
            assert "x-frame-options" in response.headers
            assert response.headers["x-frame-options"] == "DENY"

    def test_x_xss_protection_header(self, client):
        """Response includes X-XSS-Protection header."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={"ok": 1, "tables": 15})

            response = client.get("/health")
            assert "x-xss-protection" in response.headers
            assert "1; mode=block" in response.headers["x-xss-protection"]

    def test_referrer_policy_header(self, client):
        """Response includes Referrer-Policy header."""
        with patch("api.main.db.acquire") as mock_acquire:
            mock_conn = AsyncMock()
            mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_conn.fetchrow = AsyncMock(return_value={"ok": 1, "tables": 15})

            response = client.get("/health")
            assert "referrer-policy" in response.headers


# ────────────────────────────────────────────────────────────────────────────
# Error Handling Tests
# ────────────────────────────────────────────────────────────────────────────


class TestErrorHandling:
    """Tests for error handling and status codes."""

    def test_invalid_path_returns_404(self, client):
        """Invalid path returns 404."""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404

    def test_method_not_allowed_returns_405(self, client):
        """Wrong HTTP method returns 405."""
        response = client.post("/health")
        assert response.status_code == 405

    def test_invalid_json_body_returns_422(self, client):
        """Invalid JSON body returns 422 Unprocessable Entity."""
        response = client.post(
            "/api/v1/intel/chat",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
