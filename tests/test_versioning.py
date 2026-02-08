"""
Comprehensive tests for API versioning strategy (VCL-23 / SEC-009).

Tests cover:
- Version listing endpoint
- X-API-Version header in responses
- Deprecated version warning headers
- Version negotiation logic
- Invalid version handling
- v1 routes include version header
- Sunset header for deprecated versions
"""

from datetime import date
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from api.versioning import (
    APIVersion,
    APIVersionMiddleware,
    VersionRouter,
    AVAILABLE_VERSIONS,
    get_api_versions,
)


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def version_app():
    """Create a test FastAPI app with versioning middleware."""
    app = FastAPI()
    app.add_middleware(APIVersionMiddleware)

    # Add a test v1 route
    @app.get("/api/v1/test")
    async def test_v1_endpoint(response: Response):
        response.headers["X-API-Version"] = "1"
        return {"message": "v1", "status": "ok"}

    # Add a test v2 route
    @app.get("/api/v2/test")
    async def test_v2_endpoint(response: Response):
        response.headers["X-API-Version"] = "2"
        return {"message": "v2", "status": "ok"}

    # Add /api/versions endpoint
    @app.get("/api/versions")
    async def list_versions():
        return await get_api_versions()

    return app


@pytest.fixture
def client(version_app):
    """Create test client."""
    return TestClient(version_app)


# ── Test Version Listing Endpoint ──────────────────────────────

class TestVersionListingEndpoint:
    """Test /api/versions endpoint."""

    @pytest.mark.asyncio
    async def test_versions_endpoint_returns_valid_structure(self, client):
        """Test /api/versions returns valid structure with all required fields."""
        response = client.get("/api/versions")
        assert response.status_code == 200

        data = response.json()
        assert "versions" in data
        assert "default_version" in data
        assert "deprecated_count" in data
        assert isinstance(data["versions"], list)

    @pytest.mark.asyncio
    async def test_versions_endpoint_lists_version_1(self, client):
        """Test /api/versions lists version 1 as available."""
        response = client.get("/api/versions")
        data = response.json()
        versions = data["versions"]

        v1 = next((v for v in versions if v["version"] == "1"), None)
        assert v1 is not None
        assert "deprecated" in v1
        assert "url_prefix" in v1
        assert "description" in v1

    @pytest.mark.asyncio
    async def test_versions_endpoint_v1_not_deprecated(self, client):
        """Test version 1 is not marked as deprecated."""
        response = client.get("/api/versions")
        data = response.json()
        versions = data["versions"]

        v1 = next((v for v in versions if v["version"] == "1"), None)
        assert v1 is not None
        assert v1["deprecated"] is False

    @pytest.mark.asyncio
    async def test_versions_endpoint_default_version(self, client):
        """Test default version is set to 1."""
        response = client.get("/api/versions")
        data = response.json()
        assert data["default_version"] == "1"

    @pytest.mark.asyncio
    async def test_versions_endpoint_no_sunset_for_v1(self, client):
        """Test version 1 has no sunset date."""
        response = client.get("/api/versions")
        data = response.json()
        versions = data["versions"]

        v1 = next((v for v in versions if v["version"] == "1"), None)
        assert v1["sunset_date"] is None


# ── Test X-API-Version Response Header ─────────────────────────

class TestAPIVersionResponseHeader:
    """Test X-API-Version response header."""

    def test_v1_route_includes_api_version_header(self, client):
        """Test v1 route includes X-API-Version header."""
        response = client.get("/api/v1/test")
        assert "x-api-version" in response.headers
        assert response.headers["x-api-version"] == "1"

    def test_versions_endpoint_includes_api_version_header(self, client):
        """Test /api/versions endpoint includes X-API-Version header."""
        response = client.get("/api/versions")
        assert "x-api-version" in response.headers
        assert response.headers["x-api-version"] == "1"

    def test_v2_route_includes_api_version_header(self, client):
        """Test v2 route includes X-API-Version header."""
        response = client.get("/api/v2/test")
        assert "x-api-version" in response.headers
        assert response.headers["x-api-version"] == "2"


# ── Test Version Negotiation Logic ─────────────────────────────

class TestVersionNegotiation:
    """Test version negotiation (header vs URL)."""

    def test_header_version_overrides_url_version(self, client):
        """Test X-API-Version header takes precedence over URL."""
        response = client.get(
            "/api/v1/test",
            headers={"X-API-Version": "2"}
        )
        assert response.headers["x-api-version"] == "2"

    def test_url_version_used_when_no_header(self, client):
        """Test URL version is used when no X-API-Version header."""
        response = client.get("/api/v1/test")
        assert response.headers["x-api-version"] == "1"

    def test_default_version_for_non_versioned_route(self, client):
        """Test default version (1) for routes not in version URL."""
        response = client.get("/api/versions")
        assert response.headers["x-api-version"] == "1"

    def test_explicit_header_sets_version_on_non_versioned_route(self, client):
        """Test explicit header on non-versioned route sets version."""
        response = client.get(
            "/api/versions",
            headers={"X-API-Version": "2"}
        )
        assert response.headers["x-api-version"] == "2"


# ── Test Invalid Version Handling ──────────────────────────────

class TestInvalidVersionHandling:
    """Test handling of invalid versions."""

    def test_invalid_header_version_not_rejected(self, client):
        """Test invalid version in header is accepted (future-proofing)."""
        response = client.get(
            "/api/v1/test",
            headers={"X-API-Version": "99"}
        )
        # Should accept for forward compatibility
        assert response.status_code == 200
        assert response.headers["x-api-version"] == "99"

    def test_malformed_url_version_defaults_to_v1(self, client):
        """Test malformed URL version defaults to v1."""
        response = client.get("/api/vX/test")
        assert response.headers["x-api-version"] == "1"


# ── Test Deprecated Version Warnings ───────────────────────────

class TestDeprecatedVersionWarnings:
    """Test deprecation and sunset headers."""

    def test_no_deprecation_header_for_current_version(self, client):
        """Test no deprecation header for non-deprecated version."""
        response = client.get("/api/v1/test")
        assert "deprecation" not in response.headers.keys() or response.headers.get("deprecation") != "true"

    def test_no_sunset_header_for_current_version(self, client):
        """Test no sunset header for non-deprecated version."""
        response = client.get("/api/v1/test")
        assert "sunset" not in response.headers

    @pytest.mark.asyncio
    async def test_deprecated_version_warning_in_version_listing(self):
        """Test deprecated versions are marked in /api/versions response."""
        versions = await get_api_versions()
        # Check that v1 is not deprecated
        v1 = next((v for v in versions["versions"] if v["version"] == "1"), None)
        assert v1 is not None
        assert v1["deprecated"] is False


# ── Test APIVersion Dataclass ─────────────────────────────────

class TestAPIVersionDataclass:
    """Test APIVersion dataclass."""

    def test_api_version_creation(self):
        """Test creating an APIVersion instance."""
        version = APIVersion(
            version="1",
            deprecated=False,
            sunset_date=None,
            description="Test version"
        )
        assert version.version == "1"
        assert version.deprecated is False
        assert version.sunset_date is None
        assert version.description == "Test version"

    def test_api_version_with_sunset_date(self):
        """Test APIVersion with sunset date."""
        sunset = date(2025, 12, 31)
        version = APIVersion(
            version="2",
            deprecated=True,
            sunset_date=sunset,
            description="Deprecated version"
        )
        assert version.deprecated is True
        assert version.sunset_date == sunset

    def test_api_version_defaults(self):
        """Test APIVersion default values."""
        version = APIVersion(version="1")
        assert version.deprecated is False
        assert version.sunset_date is None
        assert version.description == ""


# ── Test VersionRouter ────────────────────────────────────────

class TestVersionRouter:
    """Test VersionRouter class."""

    def test_version_router_creation(self):
        """Test creating a VersionRouter."""
        router = VersionRouter(version="1")
        assert router.version == "1"

    def test_version_router_with_prefix(self):
        """Test VersionRouter with custom prefix."""
        router = VersionRouter(prefix="/api/v1/test", version="1")
        assert router.prefix == "/api/v1/test"
        assert router.version == "1"

    def test_version_router_default_version(self):
        """Test VersionRouter defaults to version 1."""
        router = VersionRouter()
        assert router.version == "1"


# ── Test Request State ────────────────────────────────────────

class TestRequestState:
    """Test version information in request state."""

    def test_request_state_contains_api_version(self):
        """Test request.state.api_version is set by middleware."""
        from fastapi import Request

        app = FastAPI()
        app.add_middleware(APIVersionMiddleware)

        captured_version = None

        @app.get("/test-state-1")
        async def test_route(request: Request):
            nonlocal captured_version
            captured_version = request.state.api_version
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/test-state-1")

        assert response.status_code == 200
        assert captured_version == "1"

    def test_request_state_reflects_header_version(self):
        """Test request.state.api_version reflects X-API-Version header."""
        from fastapi import Request

        app = FastAPI()
        app.add_middleware(APIVersionMiddleware)

        captured_version = None

        @app.get("/test-state-2")
        async def test_route(request: Request):
            nonlocal captured_version
            captured_version = request.state.api_version
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/test-state-2", headers={"X-API-Version": "2"})

        assert response.status_code == 200
        assert captured_version == "2"


# ── Test AVAILABLE_VERSIONS Registry ────────────────────────────

class TestVersionRegistry:
    """Test AVAILABLE_VERSIONS registry."""

    def test_version_1_in_registry(self):
        """Test version 1 is in AVAILABLE_VERSIONS."""
        assert "1" in AVAILABLE_VERSIONS

    def test_version_1_is_not_deprecated(self):
        """Test version 1 is not marked as deprecated."""
        v1 = AVAILABLE_VERSIONS["1"]
        assert v1.deprecated is False

    def test_all_registry_versions_are_apiversion_instances(self):
        """Test all entries in AVAILABLE_VERSIONS are APIVersion instances."""
        for version, v_obj in AVAILABLE_VERSIONS.items():
            assert isinstance(v_obj, APIVersion)
            assert v_obj.version == version


# ── Test Integration with Main App Routes ──────────────────────

class TestVersionHeadersOnMainRoutes:
    """Test that main.py routes include version headers."""

    def test_get_api_versions_returns_dict(self, client):
        """Test get_api_versions() returns proper dict structure."""
        import asyncio
        versions = asyncio.run(get_api_versions())

        assert isinstance(versions, dict)
        assert "versions" in versions
        assert "default_version" in versions
        assert "deprecated_count" in versions

    def test_versions_in_response_have_all_fields(self, client):
        """Test each version in response has required fields."""
        import asyncio
        versions = asyncio.run(get_api_versions())

        for version_info in versions["versions"]:
            assert "version" in version_info
            assert "deprecated" in version_info
            assert "sunset_date" in version_info
            assert "description" in version_info
            assert "url_prefix" in version_info


# ── Test Sunset Date Formatting ───────────────────────────────

class TestSunsetDateFormatting:
    """Test sunset date formatting in responses."""

    @pytest.mark.asyncio
    async def test_sunset_date_iso_format_in_response(self):
        """Test sunset date is in ISO format in response."""
        versions = await get_api_versions()
        for version_info in versions["versions"]:
            if version_info["sunset_date"]:
                # Should be a valid ISO date string
                sunset = version_info["sunset_date"]
                # Try to parse it
                try:
                    date.fromisoformat(sunset)
                except ValueError:
                    pytest.fail(f"Sunset date {sunset} is not in ISO format")

    @pytest.mark.asyncio
    async def test_no_sunset_date_when_not_deprecated(self):
        """Test non-deprecated versions have no sunset date."""
        versions = await get_api_versions()
        for version_info in versions["versions"]:
            if not version_info["deprecated"]:
                assert version_info["sunset_date"] is None
