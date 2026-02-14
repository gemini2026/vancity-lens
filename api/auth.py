"""
VanCity Lens — API Authentication
Simple API-key authentication for admin endpoints.

Usage:
    from .auth import require_admin

    @router.post("/my-admin-endpoint", dependencies=[Depends(require_admin)])
    async def my_endpoint():
        ...

Set the ADMIN_API_KEY environment variable to enable authentication.
If ADMIN_API_KEY is not set, admin endpoints return 503 Service Unavailable.
Uses constant-time comparison (hmac.compare_digest) to prevent timing attacks.
"""

import hmac
import os
import logging
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


def _get_admin_key() -> Optional[str]:
    """Get the configured admin API key."""
    return os.environ.get("ADMIN_API_KEY")


async def require_admin(
    api_key: Optional[str] = Security(_api_key_header),
) -> str:
    """
    Dependency that enforces admin authentication.

    - If ADMIN_API_KEY env var is set: requires matching X-Admin-Key header
    - If ADMIN_API_KEY env var is NOT set: returns 503 Service Unavailable
    """
    expected = _get_admin_key()

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY not configured. Admin access is disabled.",
        )

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Admin-Key header. Admin authentication required.",
        )

    if not hmac.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key.",
        )

    return api_key
