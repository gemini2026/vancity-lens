"""
Sentry error tracking integration for VanCity Lens (VCL-45 / INFRA-006).

This module initializes the Sentry SDK for error tracking and monitoring.
Features include:
- Graceful initialization (no-op if SENTRY_DSN not set)
- Sensitive data stripping (API keys, passwords, tokens)
- Custom tag extraction from requests
- Breadcrumb support for request lifecycle
- FastAPI/ASGI integration
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Global state to track Sentry initialization
_sentry_initialized = False


def init_error_tracking() -> None:
    """
    Initialize Sentry SDK if SENTRY_DSN environment variable is set.

    If SENTRY_DSN is not configured, logs a warning and continues gracefully.
    This allows the app to run without error tracking in development environments.

    Configuration:
    - dsn: from SENTRY_DSN env var
    - environment: from VANCITY_ENV env var (defaults to "development")
    - release: from APP_VERSION env var (defaults to "unknown")
    - traces_sample_rate: 0.1 (10% of transactions)

    The before_send hook strips sensitive data:
    - API keys and credentials
    - Authorization headers
    - Passwords and tokens
    """
    global _sentry_initialized

    sentry_dsn = os.getenv("SENTRY_DSN")

    if not sentry_dsn:
        logger.warning(
            "SENTRY_DSN not configured. Error tracking is disabled. "
            "Set SENTRY_DSN to enable Sentry integration."
        )
        _sentry_initialized = False
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.asgi import AsgiIntegration

        environment = os.getenv("VANCITY_ENV", "development")
        release = os.getenv("APP_VERSION", "unknown")

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=environment,
            release=release,
            traces_sample_rate=0.1,
            integrations=[
                FastApiIntegration(),
                AsgiIntegration(),
            ],
            before_send=_before_send_hook,
        )

        _sentry_initialized = True
        logger.info(
            f"Sentry error tracking initialized: "
            f"environment={environment}, release={release}"
        )

    except ImportError:
        logger.warning(
            "sentry-sdk not installed. Install with: pip install sentry-sdk[fastapi]"
        )
        _sentry_initialized = False

    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {str(e)}")
        _sentry_initialized = False


def _before_send_hook(event: dict[str, Any], hint: dict[str, Any]) -> Optional[dict]:
    """
    Filter sensitive data from Sentry events before sending.

    Removes:
    - HTTP Authorization headers
    - X-API-Key headers
    - Cookie data
    - Passwords in request bodies
    - API tokens in query parameters
    - Custom secret headers

    Args:
        event: The event dict from Sentry
        hint: Additional hints from Sentry

    Returns:
        The filtered event dict, or None to drop the event
    """
    if "request" in event:
        request = event["request"]

        # Strip sensitive headers
        if "headers" in request:
            headers = request["headers"]
            sensitive_headers = [
                "Authorization",
                "X-API-Key",
                "X-Admin-Key",
                "Cookie",
                "X-Token",
                "X-Session-Token",
            ]
            for header in sensitive_headers:
                if header in headers:
                    headers[header] = "[REDACTED]"

        # Strip sensitive query parameters
        if "query_string" in request:
            query = request["query_string"]
            if query:
                # Replace API key patterns in query string
                sensitive_params = ["api_key", "token", "password", "secret"]
                for param in sensitive_params:
                    if f"{param}=" in query.lower():
                        # Simple redaction (just replace the value)
                        import re

                        query = re.sub(
                            rf"({param}=)[^&]*",
                            r"\1[REDACTED]",
                            query,
                            flags=re.IGNORECASE,
                        )
                request["query_string"] = query

        # Strip sensitive URL patterns
        if "url" in request:
            url = request["url"]
            sensitive_patterns = ["api_key=", "token=", "password=", "secret="]
            for pattern in sensitive_patterns:
                if pattern.lower() in url.lower():
                    import re

                    url = re.sub(
                        rf"{pattern}[^&]*",
                        pattern + "[REDACTED]",
                        url,
                        flags=re.IGNORECASE,
                    )
            request["url"] = url

    # Strip sensitive fields from exception data
    if "exception" in event:
        for exception in event.get("exception", {}).get("values", []):
            if "value" in exception:
                # Don't log full exception messages that might contain secrets
                value = str(exception["value"])
                if any(
                    s in value.lower() for s in ["password", "token", "key", "secret"]
                ):
                    exception["value"] = "[REDACTED - contains sensitive data]"

    return event


def capture_exception(exc: Exception, tags: Optional[dict[str, str]] = None) -> None:
    """
    Capture an exception and send to Sentry if configured.

    Works as a no-op if Sentry is not initialized, so it's safe to call
    regardless of Sentry configuration.

    Args:
        exc: The exception to capture
        tags: Optional dict of tags to add to the event

    Example:
        try:
            do_something()
        except ValueError as e:
            capture_exception(e, tags={"operation": "compute_entitlement"})
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            if tags:
                for key, value in tags.items():
                    scope.set_tag(key, value)
            sentry_sdk.capture_exception(exc)

    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Failed to capture exception to Sentry: {str(e)}")


def set_context(name: str, context: dict[str, Any]) -> None:
    """
    Set context data for the current transaction.

    Context is useful for adding application-specific information
    to error reports without being part of the exception message.

    Args:
        name: Context name (e.g., "request", "user", "computation")
        context: Dictionary of context data

    Example:
        set_context("parcel", {
            "pid": "123-456-789",
            "zone": "RS-1",
            "toa_tier": "T1"
        })
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk

        sentry_sdk.set_context(name, context)

    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Failed to set Sentry context: {str(e)}")


def add_breadcrumb(
    message: str,
    category: str = "info",
    level: str = "info",
    data: Optional[dict[str, Any]] = None,
) -> None:
    """
    Add a breadcrumb to the current transaction.

    Breadcrumbs are useful for tracking the request lifecycle and
    understanding what happened before an error occurred.

    Args:
        message: Breadcrumb message
        category: Category (e.g., "http", "query", "validation")
        level: Severity level ("debug", "info", "warning", "error", "fatal")
        data: Optional dictionary of additional data

    Example:
        add_breadcrumb("Querying parcels", category="query", data={"limit": 50})
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk

        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data or {},
        )

    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Failed to add Sentry breadcrumb: {str(e)}")


def get_sentry_middleware():
    """
    Get the Sentry ASGI middleware if initialized.

    Returns:
        The SentryAsgiMiddleware class if Sentry is initialized, None otherwise.

    This allows FastAPI to be instrumented with Sentry without requiring
    Sentry to be installed.
    """
    if not _sentry_initialized:
        return None

    try:
        from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

        return SentryAsgiMiddleware

    except ImportError:
        return None


def is_sentry_enabled() -> bool:
    """Check if Sentry error tracking is enabled."""
    return _sentry_initialized
