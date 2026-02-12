from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

try:  # Python 3.11+
    from typing import Self
except ImportError:  # pragma: no cover - Python < 3.11
    from typing_extensions import Self

import httpx

from sdk.errors import Knowledge2Error


@dataclass
class ClientLimits:
    """HTTP connection pool limits for the SDK client."""

    max_connections: int = 20
    max_keepalive_connections: int = 10
    keepalive_expiry: float = 30.0


class BaseClient:
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.admin_token = admin_token
        self._default_headers = dict(headers or {})
        self._user_agent = user_agent

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

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        merged_headers = self._headers(headers)
        response = self._client.request(method, path, headers=merged_headers, **kwargs)
        if response.is_error:
            raise self._error_from_response(response)
        if response.content:
            return response.json()
        return None

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

    @staticmethod
    def _error_from_response(response: httpx.Response) -> Knowledge2Error:
        request_id = response.headers.get("X-Request-Id")
        code = None
        details: Any = None
        message = response.text or response.reason_phrase
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
        return Knowledge2Error(
            message,
            status_code=response.status_code,
            code=code,
            details=details,
            request_id=request_id,
        )
