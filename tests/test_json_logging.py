"""
Comprehensive tests for structured JSON logging (VCL-53 / INFRA-008).

Tests cover:
- JsonFormatter output structure and fields
- Timestamp ISO 8601 formatting
- Log level filtering
- Exception info inclusion
- Request ID propagation
- LOG_FORMAT environment variable handling
- VANCITY_ENV-based defaults
- Extra fields preservation
- Module/function/line info accuracy
"""

import json
import logging
import os
import sys
from io import StringIO
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from api.json_logging import JsonFormatter, TextFormatter, setup_json_logging


# ────────────────────────────────────────────────────────────────────────────
# Test JsonFormatter
# ────────────────────────────────────────────────────────────────────────────


class TestJsonFormatter:
    """Test JsonFormatter class."""

    def test_json_formatter_basic_output(self):
        """Test JsonFormatter produces valid JSON."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed is not None

    def test_json_formatter_has_required_fields(self):
        """Test JsonFormatter includes all required fields."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.WARNING,
            pathname="/path/to/test.py",
            lineno=99,
            msg="Test warning",
            args=(),
            exc_info=None,
            func="test_function",
        )

        result = json.loads(formatter.format(record))

        # Check required fields
        assert "timestamp" in result
        assert "level" in result
        assert "logger_name" in result
        assert "message" in result
        assert "module" in result
        assert "function" in result
        assert "line" in result

    def test_json_formatter_timestamp_iso8601(self):
        """Test timestamp is in ISO 8601 format."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )

        result = json.loads(formatter.format(record))
        timestamp = result["timestamp"]

        # Should end with 'Z' and be ISO format
        assert timestamp.endswith("Z")
        # Try to parse as ISO 8601
        try:
            # Remove the Z and parse
            dt = datetime.fromisoformat(timestamp[:-1])
            assert dt is not None
        except ValueError:
            pytest.fail("Timestamp is not valid ISO 8601 format")

    def test_json_formatter_log_levels(self):
        """Test JsonFormatter preserves all log levels."""
        formatter = JsonFormatter()
        levels = [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ]

        for level, expected_name in levels:
            record = logging.LogRecord(
                name="test",
                level=level,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )
            result = json.loads(formatter.format(record))
            assert result["level"] == expected_name

    def test_json_formatter_message_content(self):
        """Test message content is preserved."""
        formatter = JsonFormatter()
        test_message = "This is a test message with special chars: !@#$%"
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=test_message,
            args=(),
            exc_info=None,
        )

        result = json.loads(formatter.format(record))
        assert result["message"] == test_message

    def test_json_formatter_module_function_line(self):
        """Test module, function, and line info is correct."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="mymodule",
            level=logging.INFO,
            pathname="/path/to/mymodule.py",
            lineno=123,
            msg="Test",
            args=(),
            exc_info=None,
            func="my_function",
        )

        result = json.loads(formatter.format(record))
        assert result["module"] == "mymodule"
        assert result["function"] == "my_function"
        assert result["line"] == 123

    def test_json_formatter_with_request_id(self):
        """Test request_id is included when present in record."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        # Add request_id to the record
        record.request_id = "550e8400-e29b-41d4-a716-446655440000"

        result = json.loads(formatter.format(record))
        assert "request_id" in result
        assert result["request_id"] == "550e8400-e29b-41d4-a716-446655440000"

    def test_json_formatter_without_request_id(self):
        """Test request_id is omitted when not in record."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )

        result = json.loads(formatter.format(record))
        assert "request_id" not in result

    def test_json_formatter_with_exception_info(self):
        """Test exception info is included when present."""
        formatter = JsonFormatter()

        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = json.loads(formatter.format(record))
        assert "exc_info" in result
        assert "ValueError" in result["exc_info"]
        assert "Test exception" in result["exc_info"]

    def test_json_formatter_without_exception_info(self):
        """Test exc_info is omitted when not present."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )

        result = json.loads(formatter.format(record))
        assert "exc_info" not in result

    def test_json_formatter_with_extra_fields(self):
        """Test extra fields are included."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        # Add extra fields
        record.custom_field = "custom_value"
        record.another_field = 42

        result = json.loads(formatter.format(record))
        assert "extra" in result
        assert result["extra"]["custom_field"] == "custom_value"
        assert result["extra"]["another_field"] == 42

    def test_json_formatter_extra_fields_with_non_serializable(self):
        """Test non-JSON-serializable fields are converted to strings."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        # Add non-serializable field
        record.object_field = MagicMock()

        result = json.loads(formatter.format(record))
        assert "extra" in result
        assert "object_field" in result["extra"]
        assert isinstance(result["extra"]["object_field"], str)

    def test_json_formatter_message_with_args(self):
        """Test message formatting with args."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="User %s logged in from %s",
            args=("alice", "192.168.1.1"),
            exc_info=None,
        )

        result = json.loads(formatter.format(record))
        assert result["message"] == "User alice logged in from 192.168.1.1"


# ────────────────────────────────────────────────────────────────────────────
# Test TextFormatter
# ────────────────────────────────────────────────────────────────────────────


class TestTextFormatter:
    """Test TextFormatter class."""

    def test_text_formatter_basic_output(self):
        """Test TextFormatter produces valid text output."""
        formatter = TextFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_func",
        )
        result = formatter.format(record)

        # Should contain expected components
        assert "test_logger" in result
        assert "test_func" in result
        assert "42" in result
        assert "Test message" in result

    def test_text_formatter_with_request_id(self):
        """Test request_id is included in text format."""
        formatter = TextFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
            func="test_func",
        )
        record.request_id = "test-request-id"

        result = formatter.format(record)
        assert "req=test-request-id" in result

    def test_text_formatter_with_exception(self):
        """Test exception info is included in text format."""
        formatter = TextFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error",
            args=(),
            exc_info=exc_info,
            func="test_func",
        )

        result = formatter.format(record)
        assert "Traceback" in result
        assert "ValueError" in result


# ────────────────────────────────────────────────────────────────────────────
# Test setup_json_logging function
# ────────────────────────────────────────────────────────────────────────────


class TestSetupJsonLogging:
    """Test setup_json_logging configuration function."""

    @pytest.fixture(autouse=True)
    def cleanup_logging(self):
        """Clean up logging configuration after each test."""
        yield
        # Reset root logger
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    def test_setup_json_logging_json_format(self):
        """Test setup with JSON format."""
        setup_json_logging(log_format="json", log_level="INFO")

        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0

        handler = root_logger.handlers[0]
        assert isinstance(handler.formatter, JsonFormatter)

    def test_setup_json_logging_text_format(self):
        """Test setup with text format."""
        setup_json_logging(log_format="text", log_level="INFO")

        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0

        handler = root_logger.handlers[0]
        assert isinstance(handler.formatter, TextFormatter)

    def test_setup_json_logging_log_levels(self):
        """Test setup with different log levels."""
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in levels:
            # Cleanup
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)

            setup_json_logging(log_format="json", log_level=level)
            root_logger = logging.getLogger()
            assert root_logger.level == getattr(logging, level)

    def test_setup_json_logging_default_development(self):
        """Test default to text format in development."""
        with patch.dict(os.environ, {"VANCITY_ENV": "development"}, clear=False):
            # Remove LOG_FORMAT to use environment default
            with patch.dict(os.environ, {}, clear=False):
                if "LOG_FORMAT" in os.environ:
                    del os.environ["LOG_FORMAT"]

                setup_json_logging(log_level="INFO")

                root_logger = logging.getLogger()
                handler = root_logger.handlers[0]
                assert isinstance(handler.formatter, TextFormatter)

    def test_setup_json_logging_default_production(self):
        """Test default to JSON format in production."""
        with patch.dict(os.environ, {"VANCITY_ENV": "production"}, clear=False):
            # Remove LOG_FORMAT to use environment default
            with patch.dict(os.environ, {}, clear=False):
                if "LOG_FORMAT" in os.environ:
                    del os.environ["LOG_FORMAT"]

                setup_json_logging(log_level="INFO")

                root_logger = logging.getLogger()
                handler = root_logger.handlers[0]
                assert isinstance(handler.formatter, JsonFormatter)

    def test_setup_json_logging_env_var_override(self):
        """Test LOG_FORMAT env var overrides VANCITY_ENV."""
        with patch.dict(
            os.environ,
            {"VANCITY_ENV": "production", "LOG_FORMAT": "text"},
            clear=False,
        ):
            setup_json_logging(log_level="INFO")

            root_logger = logging.getLogger()
            handler = root_logger.handlers[0]
            # Should use text despite production environment
            assert isinstance(handler.formatter, TextFormatter)

    def test_setup_json_logging_parameter_override(self):
        """Test function parameters override env vars."""
        with patch.dict(os.environ, {"LOG_FORMAT": "json"}, clear=False):
            # Parameter overrides env var
            setup_json_logging(log_format="text", log_level="INFO")

            root_logger = logging.getLogger()
            handler = root_logger.handlers[0]
            assert isinstance(handler.formatter, TextFormatter)

    def test_setup_json_logging_case_insensitive(self):
        """Test format parameter is case-insensitive."""
        for format_str in ["JSON", "Json", "TEXT", "Text"]:
            # Cleanup
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)

            setup_json_logging(log_format=format_str, log_level="INFO")
            root_logger = logging.getLogger()
            handler = root_logger.handlers[0]

            if format_str.upper() == "JSON":
                assert isinstance(handler.formatter, JsonFormatter)
            else:
                assert isinstance(handler.formatter, TextFormatter)

    def test_setup_json_logging_invalid_level_defaults_to_info(self):
        """Test invalid log level defaults to INFO."""
        setup_json_logging(log_format="json", log_level="INVALID_LEVEL")

        root_logger = logging.getLogger()
        # Should default to INFO
        assert root_logger.level == logging.INFO

    def test_setup_json_logging_removes_existing_handlers(self):
        """Test setup removes existing handlers."""
        root_logger = logging.getLogger()

        # Add a dummy handler
        dummy_handler = logging.StreamHandler()
        root_logger.addHandler(dummy_handler)
        initial_count = len(root_logger.handlers)
        assert initial_count > 0

        # Setup should remove old handlers
        setup_json_logging(log_format="json", log_level="INFO")

        # Should have exactly one handler now
        assert len(root_logger.handlers) == 1
        assert root_logger.handlers[0] != dummy_handler

    def test_setup_json_logging_output_to_stdout(self):
        """Test logging output goes to stdout."""
        setup_json_logging(log_format="json", log_level="INFO")

        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]

        # Should be a StreamHandler writing to stdout
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream == sys.stdout


# ────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ────────────────────────────────────────────────────────────────────────────


class TestJsonLoggingIntegration:
    """Integration tests with actual logging calls."""

    @pytest.fixture(autouse=True)
    def cleanup_logging(self):
        """Clean up logging configuration after each test."""
        yield
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    def test_json_logging_end_to_end(self):
        """Test complete logging flow with JSON output."""
        # Setup logging
        log_stream = StringIO()
        root_logger = logging.getLogger()
        root_logger.handlers = []

        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(JsonFormatter())
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        # Log a message
        test_logger = logging.getLogger("test.module")
        test_logger.info("Integration test message", extra={"user_id": 123})

        # Parse output
        output = log_stream.getvalue().strip()
        log_entry = json.loads(output)

        assert log_entry["level"] == "INFO"
        assert log_entry["message"] == "Integration test message"
        assert log_entry["logger_name"] == "test.module"
        assert log_entry["extra"]["user_id"] == 123

    def test_text_logging_end_to_end(self):
        """Test complete logging flow with text output."""
        log_stream = StringIO()
        root_logger = logging.getLogger()
        root_logger.handlers = []

        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(TextFormatter())
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        # Log a message
        test_logger = logging.getLogger("test.module")
        test_logger.info("Text test message")

        output = log_stream.getvalue().strip()
        assert "INFO" in output
        assert "test.module" in output
        assert "Text test message" in output

    def test_logging_with_exception(self):
        """Test logging exceptions with JSON formatter."""
        log_stream = StringIO()
        root_logger = logging.getLogger()
        root_logger.handlers = []

        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(JsonFormatter())
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.ERROR)

        test_logger = logging.getLogger("test.module")

        try:
            1 / 0
        except ZeroDivisionError:
            test_logger.exception("Math error occurred")

        output = log_stream.getvalue().strip()
        log_entry = json.loads(output)

        assert log_entry["level"] == "ERROR"
        assert "exc_info" in log_entry
        assert "ZeroDivisionError" in log_entry["exc_info"]

    def test_multiple_loggers_with_request_id(self):
        """Test multiple loggers properly propagate request_id."""
        log_stream = StringIO()
        root_logger = logging.getLogger()
        root_logger.handlers = []

        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(JsonFormatter())
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        # Create loggers
        logger1 = logging.getLogger("module1")
        logger2 = logging.getLogger("module2")

        # Create a record with request_id
        record1 = logging.LogRecord(
            "module1",
            logging.INFO,
            "test.py",
            1,
            "msg1",
            (),
            None,
        )
        record1.request_id = "req-123"

        record2 = logging.LogRecord(
            "module2",
            logging.INFO,
            "test.py",
            2,
            "msg2",
            (),
            None,
        )
        record2.request_id = "req-123"

        # Handle records
        for record in [record1, record2]:
            for h in root_logger.handlers:
                h.handle(record)

        output = log_stream.getvalue()
        lines = output.strip().split("\n")

        for line in lines:
            entry = json.loads(line)
            assert entry["request_id"] == "req-123"
