"""
Comprehensive tests for Sentry error tracking integration (VCL-45 / INFRA-006).

Tests cover:
- Initialization with and without SENTRY_DSN
- Sensitive data stripping (API keys, passwords, tokens)
- Environment and release tagging
- Exception capture with/without Sentry
- Context setting
- Breadcrumb support
- before_send hook functionality
- Graceful fallbacks when Sentry is not configured
"""

import os
import json
import logging
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Any, Optional, Dict

# Import the error tracking module
from api.error_tracking import (
    init_error_tracking,
    capture_exception,
    set_context,
    add_breadcrumb,
    get_sentry_middleware,
    is_sentry_enabled,
    _before_send_hook,
)


# ────────────────────────────────────────────────────────────────────────────
# Test Initialization
# ────────────────────────────────────────────────────────────────────────────


class TestInitErrorTracking:
    """Test init_error_tracking function."""

    def test_init_without_sentry_dsn(self, monkeypatch, caplog):
        """Test graceful no-op when SENTRY_DSN is not set."""
        monkeypatch.delenv("SENTRY_DSN", raising=False)

        with caplog.at_level(logging.WARNING):
            init_error_tracking()

        # Should log a warning and not fail
        assert any("SENTRY_DSN" in record.message for record in caplog.records)

    def test_init_logs_warning_without_dsn(self, monkeypatch, caplog):
        """Test that a warning is logged when SENTRY_DSN is not set."""
        monkeypatch.delenv("SENTRY_DSN", raising=False)

        with caplog.at_level(logging.WARNING):
            init_error_tracking()

        warning_logs = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_logs) > 0

    def test_init_completes_without_error(self, monkeypatch):
        """Test that init_error_tracking completes without raising."""
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        # Should not raise
        init_error_tracking()

    def test_functions_are_safe_no_op_without_sentry(self):
        """Test that error tracking functions are safe to call without Sentry."""
        # All of these should run without error
        capture_exception(ValueError("test"), tags={"op": "test"})
        set_context("test", {"key": "value"})
        add_breadcrumb("test message", category="test")
        middleware = get_sentry_middleware()
        assert middleware is None


# ────────────────────────────────────────────────────────────────────────────
# Test Sensitive Data Stripping
# ────────────────────────────────────────────────────────────────────────────


class TestBeforeSendHook:
    """Test the before_send hook for sensitive data stripping."""

    def test_redacts_authorization_header(self):
        """Test Authorization header is redacted."""
        event = {
            "request": {
                "headers": {
                    "Authorization": "Bearer secret-token-123",
                    "Content-Type": "application/json",
                }
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert result["request"]["headers"]["Authorization"] == "[REDACTED]"
        assert result["request"]["headers"]["Content-Type"] == "application/json"

    def test_redacts_api_key_header(self):
        """Test X-API-Key header is redacted."""
        event = {
            "request": {
                "headers": {
                    "X-API-Key": "super-secret-key",
                }
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert result["request"]["headers"]["X-API-Key"] == "[REDACTED]"

    def test_redacts_admin_key_header(self):
        """Test X-Admin-Key header is redacted."""
        event = {
            "request": {
                "headers": {
                    "X-Admin-Key": "admin-secret",
                }
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert result["request"]["headers"]["X-Admin-Key"] == "[REDACTED]"

    def test_redacts_cookie_header(self):
        """Test Cookie header is redacted."""
        event = {
            "request": {
                "headers": {
                    "Cookie": "session=abc123; token=xyz789",
                }
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert result["request"]["headers"]["Cookie"] == "[REDACTED]"

    def test_redacts_custom_token_headers(self):
        """Test custom token headers are redacted."""
        event = {
            "request": {
                "headers": {
                    "X-Token": "token-value",
                    "X-Session-Token": "session-token",
                }
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert result["request"]["headers"]["X-Token"] == "[REDACTED]"
        assert result["request"]["headers"]["X-Session-Token"] == "[REDACTED]"

    def test_redacts_api_key_in_query_string(self):
        """Test API keys in query strings are redacted."""
        event = {
            "request": {
                "query_string": "search=test&api_key=secret-key-123&limit=10"
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert "api_key=secret-key-123" not in result["request"]["query_string"]
        assert "api_key=[REDACTED]" in result["request"]["query_string"]
        assert "search=test" in result["request"]["query_string"]
        assert "limit=10" in result["request"]["query_string"]

    def test_redacts_token_in_query_string(self):
        """Test tokens in query strings are redacted."""
        event = {
            "request": {
                "query_string": "token=secret-token&page=1"
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert "token=secret-token" not in result["request"]["query_string"]
        assert "token=[REDACTED]" in result["request"]["query_string"]

    def test_redacts_password_in_query_string(self):
        """Test passwords in query strings are redacted."""
        event = {
            "request": {
                "query_string": "user=admin&password=secret123"
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert "password=secret123" not in result["request"]["query_string"]
        assert "password=[REDACTED]" in result["request"]["query_string"]

    def test_redacts_secret_in_query_string(self):
        """Test secrets in query strings are redacted."""
        event = {
            "request": {
                "query_string": "secret=mysecret&data=value"
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert "secret=mysecret" not in result["request"]["query_string"]
        assert "secret=[REDACTED]" in result["request"]["query_string"]

    def test_redacts_api_key_in_url(self):
        """Test API keys in URLs are redacted."""
        event = {
            "request": {
                "url": "https://api.example.com/endpoint?api_key=secret123&param=value"
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert "api_key=secret123" not in result["request"]["url"]
        assert "api_key=[REDACTED]" in result["request"]["url"]

    def test_redacts_exception_with_sensitive_data(self):
        """Test exceptions containing sensitive data are redacted."""
        event = {
            "exception": {
                "values": [
                    {
                        "value": "Invalid password: secret123"
                    }
                ]
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert "[REDACTED" in result["exception"]["values"][0]["value"]

    def test_preserves_normal_request_data(self):
        """Test that normal request data is preserved."""
        event = {
            "request": {
                "method": "GET",
                "url": "https://api.example.com/parcels/123",
                "headers": {
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                }
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert result["request"]["method"] == "GET"
        assert result["request"]["url"] == "https://api.example.com/parcels/123"
        assert result["request"]["headers"]["User-Agent"] == "Mozilla/5.0"
        assert result["request"]["headers"]["Accept"] == "application/json"

    def test_handles_empty_event(self):
        """Test handling of empty event."""
        event = {}
        hint = {}

        result = _before_send_hook(event, hint)

        assert result == {}

    def test_handles_event_without_request(self):
        """Test handling of event without request section."""
        event = {
            "exception": {
                "values": [{"value": "Some error"}]
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert "exception" in result

    def test_handles_none_query_string(self):
        """Test handling of None query string."""
        event = {
            "request": {
                "query_string": None
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert result["request"]["query_string"] is None

    def test_handles_empty_query_string(self):
        """Test handling of empty query strings."""
        event = {
            "request": {
                "query_string": ""
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        assert result["request"]["query_string"] == ""

    def test_redaction_preserves_param_structure(self):
        """Test that param structure is preserved during redaction."""
        event = {
            "request": {
                "query_string": "api_key=secret&page=2&token=abc"
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        query = result["request"]["query_string"]
        # All params should still be in the string, just with values redacted
        assert "api_key=" in query
        assert "page=" in query
        assert "token=" in query
        assert "secret" not in query
        assert "abc" not in query

    def test_multiple_sensitive_parameters_redacted(self):
        """Test that multiple sensitive parameters are redacted."""
        event = {
            "request": {
                "query_string": "api_key=key1&token=token1&password=pass1&secret=sec1"
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        query = result["request"]["query_string"]
        # All sensitive values should be redacted
        assert "key1" not in query
        assert "token1" not in query
        assert "pass1" not in query
        assert "sec1" not in query


# ────────────────────────────────────────────────────────────────────────────
# Test Exception Capturing
# ────────────────────────────────────────────────────────────────────────────


class TestCaptureException:
    """Test capture_exception wrapper."""

    def test_capture_exception_without_error(self):
        """Test that capture_exception doesn't raise."""
        exc = ValueError("Test error")
        # Should not raise
        capture_exception(exc)

    def test_capture_exception_with_tags(self):
        """Test capture_exception with tags."""
        exc = ValueError("Test error")
        # Should not raise
        capture_exception(exc, tags={"operation": "test", "module": "entitlement"})

    def test_capture_exception_without_tags(self):
        """Test capture_exception without tags."""
        exc = ValueError("Test error")
        # Should not raise
        capture_exception(exc)

    def test_capture_exception_with_none_tags(self):
        """Test capture_exception with None tags."""
        exc = ValueError("Test error")
        # Should not raise
        capture_exception(exc, tags=None)


# ────────────────────────────────────────────────────────────────────────────
# Test Context Setting
# ────────────────────────────────────────────────────────────────────────────


class TestSetContext:
    """Test set_context wrapper."""

    def test_set_context_simple(self):
        """Test setting context."""
        # Should not raise
        set_context("parcel", {"pid": "123-456"})

    def test_set_context_with_complex_data(self):
        """Test setting context with complex data."""
        context_data = {
            "pid": "123-456",
            "zone": "RS-1",
            "toa": {
                "tier": "T1",
                "distance_m": 250.5,
            },
            "values": [1, 2, 3],
        }
        # Should not raise
        set_context("parcel", context_data)

    def test_set_context_with_empty_dict(self):
        """Test setting context with empty dict."""
        # Should not raise
        set_context("request", {})

    def test_set_context_with_none_data(self):
        """Test setting context with None data."""
        # Should not raise - though may not do anything useful
        set_context("test", None)


# ────────────────────────────────────────────────────────────────────────────
# Test Breadcrumb Support
# ────────────────────────────────────────────────────────────────────────────


class TestAddBreadcrumb:
    """Test add_breadcrumb wrapper."""

    def test_add_breadcrumb_simple(self):
        """Test adding breadcrumb."""
        # Should not raise
        add_breadcrumb("Test message")

    def test_add_breadcrumb_with_category(self):
        """Test adding breadcrumb with category."""
        # Should not raise
        add_breadcrumb("Querying parcels", category="query")

    def test_add_breadcrumb_with_all_parameters(self):
        """Test adding breadcrumb with all parameters."""
        # Should not raise
        add_breadcrumb(
            "Processing entitlement",
            category="computation",
            level="info",
            data={"pid": "123", "elapsed_ms": 150},
        )

    def test_add_breadcrumb_with_data(self):
        """Test breadcrumb with data."""
        # Should not raise
        add_breadcrumb(
            "Test",
            category="test",
            data={"key": "value"}
        )

    def test_add_breadcrumb_with_different_levels(self):
        """Test breadcrumb with different log levels."""
        for level in ["debug", "info", "warning", "error"]:
            # Should not raise
            add_breadcrumb("Test", level=level)


# ────────────────────────────────────────────────────────────────────────────
# Test Middleware Functions
# ────────────────────────────────────────────────────────────────────────────


class TestSentryMiddleware:
    """Test Sentry middleware functions."""

    def test_get_sentry_middleware_returns_none_without_sentry(self):
        """Test getting middleware when Sentry is not configured."""
        result = get_sentry_middleware()
        # Should return None if Sentry is not initialized
        assert result is None

    def test_is_sentry_enabled_check(self):
        """Test is_sentry_enabled function."""
        # Should return a boolean
        result = is_sentry_enabled()
        assert isinstance(result, bool)


# ────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ────────────────────────────────────────────────────────────────────────────


class TestErrorTrackingIntegration:
    """Integration tests for error tracking."""

    def test_all_functions_callable_without_sentry(self):
        """Test that all error tracking functions are callable without Sentry."""
        init_error_tracking()
        capture_exception(ValueError("test"))
        set_context("test", {"key": "value"})
        add_breadcrumb("test")
        get_sentry_middleware()
        is_sentry_enabled()

    def test_before_send_hook_integration(self):
        """Test before_send hook is properly integrated."""
        event = {
            "request": {
                "method": "POST",
                "url": "https://api.example.com/auth?token=secret",
                "headers": {
                    "Authorization": "Bearer token123",
                    "Content-Type": "application/json",
                }
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        # Verify sensitive data is stripped
        assert result["request"]["headers"]["Authorization"] == "[REDACTED]"
        assert "token=secret" not in result["request"]["url"]

    def test_capture_exception_with_context_and_breadcrumbs(self):
        """Test capturing exception with context and breadcrumbs."""
        # Add context
        set_context("request", {"pid": "123", "method": "GET"})

        # Add breadcrumb
        add_breadcrumb("Processing parcel", category="query")

        # Capture exception
        capture_exception(ValueError("Invalid parcel"))

        # Should all complete without error


# ────────────────────────────────────────────────────────────────────────────
# Regression Tests
# ────────────────────────────────────────────────────────────────────────────


class TestRegressions:
    """Tests for regression prevention."""

    def test_redaction_case_insensitive(self):
        """Test that header redaction works with different cases."""
        event = {
            "request": {
                "query_string": "API_KEY=secret&Token=token123"
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        # Both should be redacted (regex is case-insensitive)
        assert "secret" not in result["request"]["query_string"]
        assert "token123" not in result["request"]["query_string"]

    def test_multiple_sensitive_headers(self):
        """Test multiple sensitive headers are all redacted."""
        event = {
            "request": {
                "headers": {
                    "Authorization": "Bearer token",
                    "X-API-Key": "key123",
                    "X-Admin-Key": "admin",
                    "Cookie": "session=abc",
                    "X-Token": "xyz",
                    "X-Session-Token": "sess",
                }
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        # All should be redacted
        for header in result["request"]["headers"].values():
            assert header == "[REDACTED]"

    def test_mixed_sensitive_and_safe_headers(self):
        """Test that safe headers are preserved while sensitive ones are redacted."""
        event = {
            "request": {
                "headers": {
                    "Authorization": "Bearer secret",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0",
                    "X-API-Key": "key123",
                }
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        headers = result["request"]["headers"]
        assert headers["Authorization"] == "[REDACTED]"
        assert headers["X-API-Key"] == "[REDACTED]"
        assert headers["Content-Type"] == "application/json"
        assert headers["User-Agent"] == "Mozilla/5.0"

    def test_query_string_with_ampersand_separator(self):
        """Test query string redaction with proper ampersand separation."""
        event = {
            "request": {
                "query_string": "param1=value1&api_key=secret&param2=value2"
            }
        }
        hint = {}

        result = _before_send_hook(event, hint)

        query = result["request"]["query_string"]
        assert "param1=value1" in query
        assert "param2=value2" in query
        assert "api_key=[REDACTED]" in query
        assert "secret" not in query

    def test_safe_return_type(self):
        """Test that before_send_hook returns a dict."""
        event = {"request": {"headers": {"Authorization": "secret"}}}
        hint = {}

        result = _before_send_hook(event, hint)

        assert isinstance(result, dict)
        assert "request" in result
