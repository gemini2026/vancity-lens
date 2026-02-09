"""
VanCity Lens — Audit Logging for Admin Operations
Implements VCL-35 [SEC-012] — structured audit logging for all admin endpoint access.

Logs admin operations in JSON format with:
- timestamp: ISO 8601 timestamp
- operation: admin endpoint path
- endpoint: full path with method
- method: HTTP method (GET, POST, etc.)
- client_ip: source IP address
- user_agent: client User-Agent header
- admin_key_hash: last 4 characters of admin key (hashed)
- status_code: HTTP response status
- duration_ms: request processing time in milliseconds
- request_id: unique request identifier
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import Request


def _hash_admin_key_tail(admin_key: Optional[str]) -> str:
    """Hash the last 4 chars of the admin key for safe logging."""
    if not admin_key:
        return "none"
    if len(admin_key) < 4:
        return "short"
    tail = admin_key[-4:]
    # Use SHA256 hash of the tail
    return hashlib.sha256(tail.encode()).hexdigest()[:8]


class AuditLogger:
    """Structured JSON audit logger for admin operations."""

    def __init__(self, logger_name: str = "audit"):
        """Initialize the audit logger with a dedicated logger instance."""
        self.logger = logging.getLogger(logger_name)

    def log_admin_operation(
        self,
        operation: str,
        endpoint: str,
        method: str,
        client_ip: str,
        user_agent: str,
        admin_key: Optional[str],
        status_code: int,
        duration_ms: float,
        request_id: str,
        additional_fields: Optional[dict] = None,
    ) -> None:
        """
        Log an admin operation as a structured JSON event.

        All logging happens in a non-blocking manner. If logging fails,
        it is silently caught to prevent affecting request processing.

        Args:
            operation: Human-readable operation name (e.g., "load-bca")
            endpoint: Full endpoint path (e.g., "/api/v1/admin/load-bca")
            method: HTTP method (GET, POST, etc.)
            client_ip: Source IP address
            user_agent: Client User-Agent header
            admin_key: The admin API key (will be hashed before logging)
            status_code: HTTP response status code
            duration_ms: Request duration in milliseconds
            request_id: Unique request identifier
            additional_fields: Optional dict of extra fields to include
        """
        try:
            audit_event = {
                "timestamp": time.time(),
                "operation": operation,
                "endpoint": endpoint,
                "method": method,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "admin_key_hash": _hash_admin_key_tail(admin_key),
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "request_id": request_id,
            }

            # Add optional fields if provided
            if additional_fields:
                audit_event.update(additional_fields)

            # Log as JSON line
            self.logger.info(json.dumps(audit_event))
        except Exception:
            # Silently fail to avoid affecting request processing
            pass

    def log_async(
        self,
        operation: str,
        endpoint: str,
        method: str,
        client_ip: str,
        user_agent: str,
        admin_key: Optional[str],
        status_code: int,
        duration_ms: float,
        request_id: str,
        additional_fields: Optional[dict] = None,
    ) -> None:
        """
        Asynchronously log an admin operation (non-blocking).

        Submits the log to the event loop to run in the background.
        This is useful in high-throughput scenarios where we want to
        ensure logging doesn't block the response.
        """
        try:
            # Schedule the logging to happen in the background
            asyncio.create_task(
                asyncio.to_thread(
                    self.log_admin_operation,
                    operation,
                    endpoint,
                    method,
                    client_ip,
                    user_agent,
                    admin_key,
                    status_code,
                    duration_ms,
                    request_id,
                    additional_fields,
                )
            )
        except Exception:
            # Silently fail on async submission too
            pass


# Global audit logger instance
_audit_logger = AuditLogger("audit")


async def audit_log_dependency(request: Request) -> dict:
    """
    FastAPI dependency that extracts and stores audit information from a request.

    Returns a dict with timing info that should be stored on the request state:
        {
            "request_id": str,
            "start_time": float,
            "client_ip": str,
            "user_agent": str,
        }

    Usage:
        @router.post("/my-endpoint", dependencies=[Depends(audit_log_dependency)])
        async def my_endpoint(audit_info: dict = Depends(audit_log_dependency)):
            ...
    """
    return {
        "request_id": str(uuid.uuid4()),
        "start_time": time.time(),
        "client_ip": _get_client_ip(request),
        "user_agent": request.headers.get("user-agent", "unknown"),
    }


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For headers."""
    # Check for X-Forwarded-For (common in proxied environments)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs; take the first one
        return forwarded_for.split(",")[0].strip()
    # Fall back to direct client connection
    if request.client:
        return request.client.host
    return "unknown"


class AuditMiddleware:
    """
    ASGI middleware that logs all requests to admin endpoints.

    Wraps the request/response cycle and logs audit events to the audit logger.
    Designed to be non-blocking: if logging fails, it doesn't affect the response.
    """

    def __init__(self, app, audit_logger_instance: Optional[AuditLogger] = None):
        self.app = app
        self.audit_logger = audit_logger_instance or _audit_logger

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract request details
        request = Request(scope, receive)
        start_time = time.time()
        request_id = str(uuid.uuid4())

        # Capture response status
        response_status = None

        async def send_wrapper(message):
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
            await send(message)

        # Process the request
        await self.app(scope, receive, send_wrapper)

        # Log the admin operation asynchronously
        duration_ms = (time.time() - start_time) * 1000
        path = scope.get("path", "")
        method = scope.get("method", "UNKNOWN")

        if path.startswith("/api/v1/admin/"):
            # Extract operation name from path
            operation = path.split("/")[-1]

            # Get admin key from headers (with fallback)
            admin_key = request.headers.get("x-admin-key")

            self.audit_logger.log_async(
                operation=operation,
                endpoint=f"{method} {path}",
                method=method,
                client_ip=_get_client_ip(request),
                user_agent=request.headers.get("user-agent", "unknown"),
                admin_key=admin_key,
                status_code=response_status or 500,
                duration_ms=duration_ms,
                request_id=request_id,
            )
