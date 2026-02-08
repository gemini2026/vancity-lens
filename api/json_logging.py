"""
Structured JSON logging configuration for VanCity Lens.

Provides:
- JsonFormatter: Custom logging.Formatter that outputs structured JSON
- setup_json_logging(): Configures root logger with JSON or text formatting
- Context variables for request_id propagation

Environment variables:
- VANCITY_ENV: "production" (defaults to JSON) or "development" (defaults to text)
- LOG_FORMAT: "json" or "text" (overrides environment default)
- LOG_LEVEL: Logging level (default: INFO)
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Optional


class JsonFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs.

    Fields:
    - timestamp: ISO 8601 formatted timestamp
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - logger_name: Name of the logger
    - message: Log message
    - module: Module name where log was called
    - function: Function name where log was called
    - line: Line number where log was called
    - request_id: Request ID from context (if available)
    - exc_info: Exception traceback (if present)
    - extra: Any additional fields
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON.

        Args:
            record: LogRecord to format

        Returns:
            JSON string representation of the log record
        """
        # Build the base log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger_name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request_id if present in record
        if hasattr(record, "request_id") and record.request_id:
            log_entry["request_id"] = record.request_id

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            try:
                log_entry["exc_info"] = self.formatException(record.exc_info)
            except Exception:
                log_entry["exc_info"] = "Error formatting exception"

        # Add any extra fields (excluding standard LogRecord attributes)
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "msecs",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "process",
            "processName",
            "thread",
            "threadName",
            "getMessage",
            "request_id",
        }

        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                try:
                    # Ensure the value is JSON serializable
                    json.dumps(value)
                    extra_fields[key] = value
                except (TypeError, ValueError):
                    extra_fields[key] = str(value)

        if extra_fields:
            log_entry["extra"] = extra_fields

        return json.dumps(log_entry, default=str)


class TextFormatter(logging.Formatter):
    """Simple text formatter for development.

    Format: [TIMESTAMP] LEVEL logger_name:function:line - message
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as text.

        Args:
            record: LogRecord to format

        Returns:
            Formatted text string
        """
        timestamp = datetime.fromtimestamp(record.created).isoformat()

        # Build the prefix
        prefix = (
            f"[{timestamp}] {record.levelname} "
            f"{record.name}:{record.funcName}:{record.lineno}"
        )

        # Add request_id if present
        if hasattr(record, "request_id") and record.request_id:
            prefix += f" [req={record.request_id}]"

        # Format message
        msg = record.getMessage()

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            msg += "\n" + self.formatException(record.exc_info)

        return f"{prefix} - {msg}"


def setup_json_logging(
    log_format: Optional[str] = None,
    log_level: Optional[str] = None,
) -> None:
    """Configure the root logger with JSON or text formatting.

    Environment variables:
    - VANCITY_ENV: "production" or "development" (determines default format)
    - LOG_FORMAT: "json" or "text" (overrides environment default)
    - LOG_LEVEL: Logging level (default: INFO)

    Args:
        log_format: Override LOG_FORMAT env var ("json" or "text")
        log_level: Override LOG_LEVEL env var (e.g., "DEBUG", "INFO", "WARNING")
    """
    # Determine log format
    if log_format is None:
        log_format = os.getenv("LOG_FORMAT", "").lower()
    else:
        log_format = log_format.lower()

    # If not explicitly set, use environment default
    if not log_format:
        vancity_env = os.getenv("VANCITY_ENV", "development").lower()
        log_format = "json" if vancity_env == "production" else "text"

    # Determine log level
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    else:
        log_level = log_level.upper()

    # Validate log level
    if not hasattr(logging, log_level):
        log_level = "INFO"

    # Get or create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))

    # Set formatter based on format choice
    if log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = TextFormatter()

    console_handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger.addHandler(console_handler)

    # Log startup info
    logger = logging.getLogger(__name__)
    logger.debug(
        f"JSON logging configured",
        extra={
            "format": log_format,
            "level": log_level,
            "environment": os.getenv("VANCITY_ENV", "development"),
        },
    )
