"""
VanCity Lens — API Authentication
Simple API-key authentication for admin endpoints.

Usage:
    from .auth import require_admin

    @router.post("/my-admin-endpoint", dependencies=[Depends(require_admin)])
    async def my_endpoint():
        ...

Set the ADMIN_API_KEY environment variable to enable authentication.
In development, if ADMIN_API_KEY is not set, admin endpoints are unrestricted.
"""

import os
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
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
    - If ADMIN_API_KEY env var is NOT set: logs a warning but allows access
      (development mode only)
    """
    expected = _get_admin_key()

    if not expected:
        logger.warning(
            "ADMIN_API_KEY not set — admin endpoints are UNPROTECTED. "
            "Set ADMIN_API_KEY env var for production."
        )
        return "dev-mode"

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Admin-Key header. Admin authentication required.",
        )

    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key.",
        )

    return api_key
