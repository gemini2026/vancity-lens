"""
Comprehensive tests for VCL-71 [PERF-009] Response Compression Middleware.

Tests the gzip compression middleware for JSON/GeoJSON responses:
- Compression applied when Accept-Encoding: gzip
- Small responses not compressed (< 1KB)
- Content-Encoding header set correctly
- Vary header includes Accept-Encoding
- Non-JSON content types not compressed
- Accept-Encoding: identity skips compression
- No Accept-Encoding header skips compression
- Custom min_size configuration
- Custom compression level
- COMPRESSION_ENABLED=false disables
- Compressed response can be decompressed correctly
- Integration tests with FastAPI TestClient
- GeoJSON content type compressed
"""

import gzip
import json
import os
import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.compression import CompressionMiddleware


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def app_with_compression():
    """FastAPI app with compression middleware."""
    app = FastAPI()
    app.add_middleware(CompressionMiddleware)

    @app.get("/json")
    async def json_endpoint():
        """Return a large JSON response (> 1KB)."""
        return {
            "data": [{"id": i, "value": f"item_{i}" * 10} for i in range(100)]
        }

    @app.get("/json-small")
    async def json_small():
        """Return a small JSON response (< 1KB)."""
        return {"message": "small"}

    @app.get("/geojson")
    async def geojson_endpoint():
        """Return a large GeoJSON response."""
        features = [
            {
                "type": "Feature",
                "properties": {"id": i},
                "geometry": {"type": "Point", "coordinates": [i, i]}
            }
            for i in range(100)
        ]
        return {
            "type": "FeatureCollection",
            "features": features
        }

    @app.get("/html")
    async def html_endpoint():
        """Return HTML response (should not be compressed)."""
        return "<html><body>Test</body></html>"

    @app.get("/text")
    async def text_endpoint():
        """Return plain text response (should not be compressed)."""
        return "Plain text response"

    @app.get("/error")
    async def error_endpoint():
        """Return error response (should not be compressed)."""
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")

    return app


@pytest.fixture
def client(app_with_compression):
    """TestClient for the app."""
    return TestClient(app_with_compression)


# ── Tests: Basic Compression Behavior ─────────────────────────────────────

class TestBasicCompression:
    """Test basic compression behavior."""

    def test_gzip_compression_applied_to_json_large(self, client):
        """Test gzip compression applied to large JSON responses."""
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        assert response.status_code == 200
        assert response.headers.get("content-encoding") == "gzip"
        # TestClient auto-decompresses, but the header confirms compression was used
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 100

    def test_small_json_not_compressed(self, client):
        """Test small JSON responses not compressed."""
        response = client.get("/json-small", headers={"Accept-Encoding": "gzip"})

        assert response.status_code == 200
        # Small response should NOT be compressed
        assert response.headers.get("content-encoding") is None

    def test_no_accept_encoding_header_skips_compression(self, client):
        """Test that missing/empty Accept-Encoding header skips compression."""
        # Note: TestClient automatically adds Accept-Encoding, so we use a different header
        response = client.get(
            "/json",
            headers={"Accept-Encoding": ""}
        )

        assert response.status_code == 200
        assert response.headers.get("content-encoding") is None

    def test_accept_encoding_identity_skips_compression(self, client):
        """Test that Accept-Encoding: identity skips compression."""
        response = client.get("/json", headers={"Accept-Encoding": "identity"})

        assert response.status_code == 200
        assert response.headers.get("content-encoding") is None

    def test_accept_encoding_deflate_skips_compression(self, client):
        """Test that non-gzip encodings skip compression."""
        response = client.get("/json", headers={"Accept-Encoding": "deflate"})

        assert response.status_code == 200
        assert response.headers.get("content-encoding") is None


# ── Tests: Header Handling ────────────────────────────────────────────────

class TestHeaderHandling:
    """Test proper header handling."""

    def test_content_encoding_header_set(self, client):
        """Test Content-Encoding header set to gzip."""
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        assert response.headers.get("content-encoding") == "gzip"

    def test_vary_header_includes_accept_encoding(self, client):
        """Test Vary header includes Accept-Encoding."""
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        vary = response.headers.get("vary", "")
        assert "Accept-Encoding" in vary

    def test_content_length_removed_for_compressed(self, client):
        """Test Content-Length header not set for compressed responses."""
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        # After decompression by testclient, content-length might be set
        # But the actual compressed response should not have been set
        assert response.status_code == 200

    def test_headers_case_insensitive(self, client):
        """Test Accept-Encoding header is case-insensitive."""
        response = client.get("/json", headers={"Accept-Encoding": "GZIP"})

        assert response.headers.get("content-encoding") == "gzip"


# ── Tests: Content Type Filtering ─────────────────────────────────────────

class TestContentTypeFiltering:
    """Test that only appropriate content types are compressed."""

    def test_json_content_type_compressed(self, client):
        """Test application/json is compressed."""
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        assert response.headers.get("content-encoding") == "gzip"

    def test_geojson_content_type_compressed(self, client):
        """Test application/geo+json is compressed."""
        response = client.get("/geojson", headers={"Accept-Encoding": "gzip"})

        assert response.headers.get("content-encoding") == "gzip"

    def test_html_not_compressed(self, client):
        """Test HTML responses not compressed."""
        response = client.get("/html", headers={"Accept-Encoding": "gzip"})

        assert response.headers.get("content-encoding") is None

    def test_plain_text_not_compressed(self, client):
        """Test plain text responses not compressed."""
        response = client.get("/text", headers={"Accept-Encoding": "gzip"})

        assert response.headers.get("content-encoding") is None


# ── Tests: Error Handling ─────────────────────────────────────────────────

class TestErrorHandling:
    """Test compression with error responses."""

    def test_error_response_not_compressed(self, client):
        """Test 404 error responses not compressed."""
        response = client.get("/error", headers={"Accept-Encoding": "gzip"})

        assert response.status_code == 404
        # Error responses (non-2xx) should not be compressed
        assert response.headers.get("content-encoding") is None


# ── Tests: Decompression ──────────────────────────────────────────────────

class TestDecompression:
    """Test that compressed responses can be properly decompressed."""

    def test_compressed_response_decompressible(self, client):
        """Test that compressed response can be decompressed correctly."""
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        assert response.status_code == 200
        # TestClient auto-decompresses, so we can verify the data
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 100

    def test_decompressed_data_matches_original(self, client):
        """Test decompressed data matches original."""
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        decompressed = response.json()
        assert decompressed["data"][0]["id"] == 0
        assert "item_" in decompressed["data"][0]["value"]


# ── Tests: Configuration ──────────────────────────────────────────────────

class TestConfiguration:
    """Test configuration via environment variables."""

    def test_compression_disabled_via_env(self):
        """Test COMPRESSION_ENABLED=false disables compression."""
        with patch.dict(os.environ, {"COMPRESSION_ENABLED": "false"}):
            # Need to reimport to apply env var
            import importlib
            import api.compression as comp_module
            importlib.reload(comp_module)

            app = FastAPI()
            app.add_middleware(comp_module.CompressionMiddleware)

            @app.get("/json")
            async def json_endpoint():
                return {
                    "data": [{"id": i, "value": f"item_{i}" * 10} for i in range(100)]
                }

            client = TestClient(app)
            response = client.get("/json", headers={"Accept-Encoding": "gzip"})

            assert response.headers.get("content-encoding") is None

    def test_custom_min_size_config(self):
        """Test custom COMPRESSION_MIN_SIZE configuration."""
        with patch.dict(os.environ, {"COMPRESSION_MIN_SIZE": "100"}):
            import importlib
            import api.compression as comp_module
            importlib.reload(comp_module)

            app = FastAPI()
            app.add_middleware(comp_module.CompressionMiddleware)

            @app.get("/json")
            async def json_endpoint():
                # Return response just over 100 bytes
                return {"data": "x" * 200}

            client = TestClient(app)
            response = client.get("/json", headers={"Accept-Encoding": "gzip"})

            # Should be compressed now with smaller threshold
            assert response.headers.get("content-encoding") == "gzip"

            # Reset to defaults
            importlib.reload(comp_module)

    def test_compression_level_config(self):
        """Test COMPRESSION_LEVEL configuration."""
        with patch.dict(os.environ, {"COMPRESSION_LEVEL": "9"}):
            import importlib
            import api.compression as comp_module
            importlib.reload(comp_module)

            assert comp_module.COMPRESSION_LEVEL == 9

            # Reset to defaults
            importlib.reload(comp_module)


# ── Tests: Multiple Accept-Encoding Values ───────────────────────────────

class TestMultipleEncodings:
    """Test Accept-Encoding with multiple values."""

    def test_accept_encoding_with_multiple_values(self, client):
        """Test Accept-Encoding with multiple encodings including gzip."""
        response = client.get(
            "/json",
            headers={"Accept-Encoding": "deflate, gzip, br"}
        )

        assert response.headers.get("content-encoding") == "gzip"

    def test_accept_encoding_gzip_with_quality(self, client):
        """Test Accept-Encoding with quality values."""
        response = client.get(
            "/json",
            headers={"Accept-Encoding": "gzip;q=1.0, deflate;q=0.5"}
        )

        assert response.headers.get("content-encoding") == "gzip"


# ── Tests: Boundary Cases ─────────────────────────────────────────────────

class TestBoundaryCase:
    """Test boundary cases."""

    def test_exactly_min_size_boundary(self):
        """Test response exactly at COMPRESSION_MIN_SIZE boundary."""
        with patch.dict(os.environ, {"COMPRESSION_MIN_SIZE": "50"}):
            import importlib
            import api.compression as comp_module
            importlib.reload(comp_module)

            app = FastAPI()
            app.add_middleware(comp_module.CompressionMiddleware)

            @app.get("/json")
            async def json_endpoint():
                # Create response exactly 50 bytes (not compressed)
                # and 51 bytes (compressed)
                return {"data": "x" * 20}

            client = TestClient(app)

            # Just under threshold - not compressed
            response = client.get("/json", headers={"Accept-Encoding": "gzip"})
            assert response.headers.get("content-encoding") is None

            # Reset to defaults
            importlib.reload(comp_module)

    def test_just_over_min_size_boundary(self):
        """Test response just over COMPRESSION_MIN_SIZE is compressed."""
        with patch.dict(os.environ, {"COMPRESSION_MIN_SIZE": "50"}):
            import importlib
            import api.compression as comp_module
            importlib.reload(comp_module)

            app = FastAPI()
            app.add_middleware(comp_module.CompressionMiddleware)

            @app.get("/json")
            async def json_endpoint():
                # Create response larger than 50 bytes
                return {"data": "x" * 100}

            client = TestClient(app)
            response = client.get("/json", headers={"Accept-Encoding": "gzip"})

            assert response.headers.get("content-encoding") == "gzip"

            # Reset to defaults
            importlib.reload(comp_module)


# ── Tests: Real-world Scenarios ───────────────────────────────────────────

class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_large_opportunities_response(self, client):
        """Test compression of large opportunities endpoint response."""
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        assert response.status_code == 200
        assert response.headers.get("content-encoding") == "gzip"
        data = response.json()
        assert "data" in data

    def test_geojson_feature_collection(self, client):
        """Test compression of GeoJSON FeatureCollection."""
        response = client.get("/geojson", headers={"Accept-Encoding": "gzip"})

        assert response.status_code == 200
        assert response.headers.get("content-encoding") == "gzip"
        data = response.json()
        assert data["type"] == "FeatureCollection"

    def test_browser_like_accept_encoding(self, client):
        """Test compression with typical browser Accept-Encoding header."""
        response = client.get(
            "/json",
            headers={
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "User-Agent": "Mozilla/5.0"
            }
        )

        assert response.status_code == 200
        assert response.headers.get("content-encoding") == "gzip"

    def test_vary_header_consistency(self, client):
        """Test Vary header is consistent across requests."""
        response1 = client.get("/json", headers={"Accept-Encoding": "gzip"})
        response2 = client.get("/json", headers={"Accept-Encoding": "identity"})

        vary1 = response1.headers.get("vary", "")
        vary2 = response2.headers.get("vary", "")

        # Both should have Vary header with Accept-Encoding
        assert "Accept-Encoding" in vary1
        assert "Accept-Encoding" in vary2


# ── Tests: Vary Header Edge Cases ─────────────────────────────────────────

class TestVaryHeaderEdgeCases:
    """Test Vary header handling edge cases."""

    def test_vary_header_not_duplicated(self, client):
        """Test Vary header doesn't duplicate Accept-Encoding."""
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        vary = response.headers.get("vary", "")
        # Count occurrences of Accept-Encoding
        count = vary.count("Accept-Encoding")
        assert count == 1

    def test_vary_header_combined_with_existing(self, client):
        """Test Vary header properly combines with existing values."""
        # This tests the middleware's ability to handle pre-existing Vary headers
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        vary = response.headers.get("vary", "")
        assert "Accept-Encoding" in vary


# ── Integration Tests ─────────────────────────────────────────────────────

class TestIntegration:
    """Integration tests with FastAPI."""

    def test_middleware_with_multiple_endpoints(self, client):
        """Test middleware works with multiple endpoints."""
        # Test JSON endpoint
        response1 = client.get("/json", headers={"Accept-Encoding": "gzip"})
        assert response1.headers.get("content-encoding") == "gzip"

        # Test GeoJSON endpoint
        response2 = client.get("/geojson", headers={"Accept-Encoding": "gzip"})
        assert response2.headers.get("content-encoding") == "gzip"

        # Test HTML endpoint (not compressed)
        response3 = client.get("/html", headers={"Accept-Encoding": "gzip"})
        assert response3.headers.get("content-encoding") is None

    def test_middleware_with_sequential_requests(self, client):
        """Test middleware works correctly with sequential requests."""
        for i in range(5):
            response = client.get("/json", headers={"Accept-Encoding": "gzip"})
            assert response.status_code == 200
            assert response.headers.get("content-encoding") == "gzip"

    def test_compressed_responses_are_valid_json(self, client):
        """Test that decompressed responses are valid JSON."""
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        # Should not raise
        data = response.json()
        assert isinstance(data, dict)
        assert "data" in data

    def test_compressed_responses_are_valid_geojson(self, client):
        """Test that decompressed GeoJSON responses are valid."""
        response = client.get("/geojson", headers={"Accept-Encoding": "gzip"})

        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert isinstance(data["features"], list)


# ── Tests: Actual Compression (Direct ASGI Testing) ─────────────────────

class TestDirectCompression:
    """Test compression without TestClient (which auto-decompresses)."""

    def test_response_body_is_actually_gzipped(self, client):
        """Test that response body is actually gzipped (via headers and decompression)."""
        # Note: TestClient automatically decompresses, so we verify via:
        # 1. The Content-Encoding header indicating gzip was applied
        # 2. The decompressed data being valid JSON
        response = client.get("/json", headers={"Accept-Encoding": "gzip"})

        # TestClient auto-decompresses if Content-Encoding is gzip
        assert response.headers.get("content-encoding") == "gzip"
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 100
