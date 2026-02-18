"""Knowledge2 SDK exception hierarchy.

All SDK exceptions inherit from :class:`Knowledge2Error`, so callers can
use ``except Knowledge2Error`` as a catch-all.

Hierarchy::

    Knowledge2Error (base)
    ├── APIError (HTTP errors from the API)
    │   ├── AuthenticationError (401)
    │   ├── PermissionDeniedError (403)
    │   ├── NotFoundError (404)
    │   ├── ConflictError (409)
    │   ├── ValidationError (422)
    │   ├── RateLimitError (429)
    │   └── ServerError (500, 502, 503, 504)
    ├── APIConnectionError (network / DNS failures)
    └── APITimeoutError (request timeout)
"""

from __future__ import annotations

from typing import Any


class Knowledge2Error(Exception):
    """Base exception for all Knowledge2 SDK errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    @property
    def retryable(self) -> bool:
        """Whether the operation that caused this error can be retried."""
        return False


class APIError(Knowledge2Error):
    """Error returned by the Knowledge2 API (HTTP 4xx / 5xx)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        details: Any = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.details = details
        self.request_id = request_id


class AuthenticationError(APIError):
    """HTTP 401 — invalid or missing API key / bearer token."""

    @property
    def retryable(self) -> bool:
        return False


class PermissionDeniedError(APIError):
    """HTTP 403 — the API key lacks the required scopes."""

    @property
    def retryable(self) -> bool:
        return False


class NotFoundError(APIError):
    """HTTP 404 — the requested resource does not exist."""

    @property
    def retryable(self) -> bool:
        return False


class ConflictError(APIError):
    """HTTP 409 — resource conflict (e.g. duplicate idempotency key)."""

    @property
    def retryable(self) -> bool:
        return False


class ValidationError(APIError):
    """HTTP 422 — request validation failed."""

    @property
    def retryable(self) -> bool:
        return False


class RateLimitError(APIError):
    """HTTP 429 — too many requests.

    The :attr:`retry_after` attribute contains the server-suggested
    wait time in seconds (from the ``Retry-After`` header), or *None*
    if the header was absent.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 429,
        retry_after: float | None = None,
        code: str | None = None,
        details: Any = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            code=code,
            details=details,
            request_id=request_id,
        )
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return True


class ServerError(APIError):
    """HTTP 500 / 502 / 503 / 504 — server-side failure."""

    @property
    def retryable(self) -> bool:
        return True


class APIConnectionError(Knowledge2Error):
    """Network connectivity failure (DNS, connection refused, etc.)."""

    @property
    def retryable(self) -> bool:
        return True


class APITimeoutError(Knowledge2Error):
    """The request timed out."""

    @property
    def retryable(self) -> bool:
        return True
