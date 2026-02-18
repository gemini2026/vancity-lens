"""Base HTTP client for the Knowledge2 SDK.

Provides :class:`BaseClient` which handles HTTP transport, automatic
retries with exponential backoff, error classification, pagination,
and debug logging.
"""

from __future__ import annotations

import contextlib
import random
import time
from dataclasses import dataclass
from typing import Any, Iterator

try:  # Python 3.11+
    from typing import Self
except ImportError:  # pragma: no cover - Python < 3.11
    from typing_extensions import Self

import httpx

from sdk._logging import _redact_headers, logger
from sdk.errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    ConflictError,
    Knowledge2Error,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ValidationError,
)

# Status codes that map to specific error subclasses.
_STATUS_ERROR_MAP: dict[int, type[APIError]] = {
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
    429: RateLimitError,
    500: ServerError,
    502: ServerError,
    503: ServerError,
    504: ServerError,
}


@dataclass
class ClientLimits:
    """HTTP connection pool limits for the SDK client."""

    max_connections: int = 20
    max_keepalive_connections: int = 10
    keepalive_expiry: float = 30.0


class BaseClient:
    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        """Normalize and validate base URL input before constructing httpx.Client."""
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            raise ValueError("api_host must not be empty")

        for idx, char in enumerate(normalized):
            if ord(char) < 32 or ord(char) == 127:
                escaped = repr(char).strip("'")
                raise ValueError(
                    f"api_host contains invalid control character {escaped} at position {idx}"
                )
        return normalized

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        *,
        bearer_token: str | None = None,
        admin_token: str | None = None,
        headers: dict[str, str] | None = None,
        user_agent: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        limits: ClientLimits | None = None,
        max_retries: int = 2,
    ) -> None:
        self.base_url = self._normalize_base_url(base_url)
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.admin_token = admin_token
        self._default_headers = dict(headers or {})
        self._user_agent = user_agent
        self._max_retries = max_retries
        self._backoff_factor = 0.5
        self._backoff_max = 8.0

        # Build httpx.Client with optional limits
        client_kwargs: dict[str, Any] = {
            "base_url": self.base_url,
            "timeout": timeout,
        }
        if limits is not None:
            client_kwargs["limits"] = httpx.Limits(
                max_connections=limits.max_connections,
                max_keepalive_connections=limits.max_keepalive_connections,
                keepalive_expiry=limits.keepalive_expiry,
            )

        self._client = httpx.Client(**client_kwargs)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Header helpers
    # ------------------------------------------------------------------

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(self._default_headers)
        extra_headers = extra if extra is not None else {}
        # Normalize auth headers so request-specific extras cannot override client auth.
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            if "X-API-Key" in extra_headers:
                extra_headers["X-API-Key"] = self.api_key
        if self.bearer_token:
            bearer_value = f"Bearer {self.bearer_token}"
            headers["Authorization"] = bearer_value
            if "Authorization" in extra_headers:
                extra_headers["Authorization"] = bearer_value
        if self.admin_token:
            headers["X-Admin-Token"] = self.admin_token
            if "X-Admin-Token" in extra_headers:
                extra_headers["X-Admin-Token"] = self.admin_token
        if self._user_agent and "User-Agent" not in headers and "User-Agent" not in extra_headers:
            headers["User-Agent"] = self._user_agent
        if extra_headers:
            headers.update(extra_headers)
        return headers

    @staticmethod
    def _idempotency_headers(idempotency_key: str | None) -> dict[str, str]:
        if not idempotency_key:
            return {}
        return {"Idempotency-Key": idempotency_key}

    # ------------------------------------------------------------------
    # Retry helpers
    # ------------------------------------------------------------------

    def _backoff_delay(self, attempt: int, error: Knowledge2Error | None = None) -> float:
        """Calculate backoff delay with jitter for retry attempt *attempt*.

        If *error* is a :class:`RateLimitError` with a ``retry_after``
        value, that value is used instead of the calculated backoff.
        """
        if isinstance(error, RateLimitError) and error.retry_after is not None:
            return error.retry_after
        base = self._backoff_factor * (2**attempt)
        jitter = random.random() * 0.25 * base
        return min(base + jitter, self._backoff_max)

    # ------------------------------------------------------------------
    # Core request with retry
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Send an HTTP request with automatic retry on transient failures."""
        last_error: Knowledge2Error | None = None
        merged_headers = self._headers(headers)

        for attempt in range(1 + self._max_retries):
            try:
                logger.debug(
                    "%s %s (attempt %d/%d) headers=%s",
                    method,
                    path,
                    attempt + 1,
                    1 + self._max_retries,
                    _redact_headers(merged_headers),
                )
                response = self._client.request(method, path, headers=merged_headers, **kwargs)
            except httpx.ConnectError as exc:
                last_error = APIConnectionError(f"Connection error: {exc}")
                last_error.__cause__ = exc
                if attempt < self._max_retries:
                    delay = self._backoff_delay(attempt)
                    logger.debug(
                        "Retry %d/%d after %.2fs (connection error)",
                        attempt + 1,
                        self._max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise last_error from exc
            except httpx.TimeoutException as exc:
                last_error = APITimeoutError(f"Request timed out: {exc}")
                last_error.__cause__ = exc
                if attempt < self._max_retries:
                    delay = self._backoff_delay(attempt)
                    logger.debug(
                        "Retry %d/%d after %.2fs (timeout)",
                        attempt + 1,
                        self._max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise last_error from exc

            logger.debug(
                "%s %s → %d",
                method,
                path,
                response.status_code,
            )

            if response.is_error:
                error = self._error_from_response(response)
                if error.retryable and attempt < self._max_retries:
                    delay = self._backoff_delay(attempt, error)
                    logger.debug(
                        "Retry %d/%d after %.2fs (status %d)",
                        attempt + 1,
                        self._max_retries,
                        delay,
                        response.status_code,
                    )
                    time.sleep(delay)
                    last_error = error
                    continue
                raise error

            # Success
            if response.content:
                return response.json()
            return None

        # All retries exhausted — should not normally reach here because
        # the last iteration raises, but satisfies the type checker.
        if last_error is not None:  # pragma: no cover
            raise last_error
        return None  # pragma: no cover

    # ------------------------------------------------------------------
    # Job polling
    # ------------------------------------------------------------------

    def _wait_for_job(
        self, job_id: str, *, poll_s: int = 5, timeout_s: float | None = None
    ) -> dict[str, Any]:
        start = time.monotonic()
        while True:
            job = self._request("GET", f"/v1/jobs/{job_id}")
            status = job.get("status")
            if status in {"succeeded", "failed", "canceled"}:
                if status != "succeeded":
                    message = job.get("error_message") or f"Job {job_id} ended with status={status}"
                    raise RuntimeError(message)
                return job
            if timeout_s is not None and (time.monotonic() - start) > timeout_s:
                raise TimeoutError(f"Timed out waiting for job {job_id}")
            time.sleep(poll_s)

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def _paginate(
        self,
        method: str,
        path: str,
        *,
        items_key: str,
        params: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> Iterator[dict[str, Any]]:
        """Lazily paginate a list endpoint, yielding individual items.

        Pages are fetched on demand — the next page is requested only
        when the current page's items are exhausted.

        Args:
            method: HTTP method (usually ``"GET"``).
            path: API path (e.g. ``"/v1/corpora"``).
            items_key: JSON key that contains the list of items in the
                response (e.g. ``"items"``).
            params: Extra query parameters forwarded to each page
                request.
            limit: Page size (default 100).
        """
        offset = 0
        base_params = dict(params or {})
        while True:
            page_params = {**base_params, "limit": limit, "offset": offset}
            data = self._request(method, path, params=page_params)
            if isinstance(data, dict):
                items = data.get(items_key, [])
            elif isinstance(data, list):
                items = data
            else:
                break
            yield from items
            if len(items) < limit:
                break
            offset += limit

    # ------------------------------------------------------------------
    # Error classification
    # ------------------------------------------------------------------

    @staticmethod
    def _error_from_response(response: httpx.Response) -> APIError:
        """Parse an error response into the appropriate :class:`APIError` subclass."""
        request_id = response.headers.get("X-Request-Id")
        code: str | None = None
        details: Any = None
        message = response.text or response.reason_phrase or "Unknown error"
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                code = error.get("code")
                details = error.get("details")
                request_id = error.get("request_id") or request_id
                message = error.get("message") or message
            elif "detail" in payload:
                detail = payload.get("detail")
                if isinstance(detail, str):
                    message = detail
                else:
                    details = detail
        if request_id:
            message = f"{message} (request_id={request_id})"

        status = response.status_code
        error_cls = _STATUS_ERROR_MAP.get(status)
        if error_cls is None:
            # Treat any unmapped 5xx as ServerError.
            error_cls = ServerError if 500 <= status < 600 else APIError

        # RateLimitError needs the retry_after kwarg
        if error_cls is RateLimitError:
            retry_after_raw = response.headers.get("Retry-After")
            retry_after: float | None = None
            if retry_after_raw is not None:
                with contextlib.suppress(ValueError, TypeError):
                    retry_after = float(retry_after_raw)
            return RateLimitError(
                message,
                status_code=status,
                retry_after=retry_after,
                code=code,
                details=details,
                request_id=request_id,
            )

        return error_cls(
            message,
            status_code=status,
            code=code,
            details=details,
            request_id=request_id,
        )
