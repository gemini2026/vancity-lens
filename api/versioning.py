"""
VanCity Lens API Versioning Strategy (VCL-23 / SEC-009)

Implements comprehensive API versioning support:
- APIVersion dataclass for version metadata
- VersionRouter for route-level version tracking
- X-API-Version request/response header handling
- Sunset/deprecation warning headers
- Version negotiation (header > URL-based)
- /api/versions endpoint for version listing

Supports both URL-based (/api/v1/, /api/v2/) and header-based (X-API-Version: 2)
versioning strategies.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional
from fastapi import APIRouter, Request
from starlette.middleware.base import BaseHTTPMiddleware


# ── API Version Metadata ───────────────────────────────────────


@dataclass
class APIVersion:
    """Metadata about an API version."""

    version: str
    """Version identifier (e.g., '1', '2')."""

    deprecated: bool = False
    """Whether this version is deprecated."""

    sunset_date: Optional[date] = None
    """Date when this version will be removed (if deprecated)."""

    description: str = ""
    """Human-readable description of this version."""


# ── Version Registry ───────────────────────────────────────────

# Global registry of available API versions
AVAILABLE_VERSIONS = {
    "1": APIVersion(
        version="1",
        deprecated=False,
        sunset_date=None,
        description="Current stable release with parcels, opportunities, and TOA endpoints",
    ),
}


# ── Version Router ─────────────────────────────────────────────


class VersionRouter(APIRouter):
    """
    APIRouter subclass that adds version metadata tracking.

    Allows route handlers to be annotated with which API version(s) they support.
    """

    def __init__(self, *args, version: str = "1", **kwargs):
        """Initialize router with version metadata."""
        super().__init__(*args, **kwargs)
        self.version = version


# ── Version Middleware ────────────────────────────────────────


class APIVersionMiddleware(BaseHTTPMiddleware):
    """
    Middleware for API versioning strategy.

    Implements version negotiation:
    1. If X-API-Version header is present, use that version
    2. Otherwise, extract version from URL path (/api/v1/ -> v1)
    3. Add X-API-Version response header
    4. Add Sunset header if version is deprecated
    5. Store resolved version in request.state for route handlers
    """

    async def dispatch(self, request: Request, call_next):
        """Process request and add version headers."""
        # Extract version from header or URL
        version = self._resolve_version(request)

        # Store version in request state for route handlers
        request.state.api_version = version

        # Process request
        response = await call_next(request)

        # Add X-API-Version response header
        response.headers["X-API-Version"] = version

        # Add Sunset header if version is deprecated
        if version in AVAILABLE_VERSIONS:
            version_info = AVAILABLE_VERSIONS[version]
            if version_info.deprecated and version_info.sunset_date:
                response.headers["Sunset"] = version_info.sunset_date.isoformat()
                response.headers["Deprecation"] = "true"

        return response

    def _resolve_version(self, request: Request) -> str:
        """
        Resolve API version from request.

        Priority:
        1. X-API-Version header
        2. URL path (/api/v1/ -> 1, /api/v2/ -> 2)
        3. Default to "1"
        """
        # Check for explicit version header
        if "x-api-version" in request.headers:
            return request.headers["x-api-version"]

        # Extract version from URL path
        path = request.url.path
        if path.startswith("/api/v"):
            # Try to extract version number: /api/v1/... -> 1, /api/v2/... -> 2
            parts = path.split("/")
            if len(parts) > 2 and parts[2].startswith("v") and len(parts[2]) > 1:
                # Ensure it's a valid version pattern like v1, v2, etc.
                version_str = parts[2][1:]  # Remove 'v' prefix
                if version_str.isdigit():
                    return version_str

        # Default to version 1
        return "1"


# ── Version Listing Endpoint ───────────────────────────────────


async def get_api_versions() -> dict:
    """
    List all available API versions with their metadata.

    Returns:
        dict with 'versions' key containing list of version info
    """
    versions_list = []

    for version_key, version_info in sorted(AVAILABLE_VERSIONS.items()):
        version_dict = {
            "version": version_info.version,
            "deprecated": version_info.deprecated,
            "sunset_date": version_info.sunset_date.isoformat()
            if version_info.sunset_date
            else None,
            "description": version_info.description,
            "url_prefix": f"/api/v{version_info.version}",
        }
        versions_list.append(version_dict)

    return {
        "versions": versions_list,
        "default_version": "1",
        "deprecated_count": sum(1 for v in AVAILABLE_VERSIONS.values() if v.deprecated),
    }
