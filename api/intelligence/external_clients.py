"""Shared limits and timeouts for external AI services (Cohere + Anthropic).

These calls are high-latency and quota-limited. To keep the API responsive under
load, we:
- bound concurrent in-flight vendor requests with process-wide semaphores
- apply explicit request timeouts (so one hung call doesn't stall the event loop)
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default
    if value <= 0:
        logger.warning("Invalid %s=%r (must be > 0); using default %s", name, raw, default)
        return default
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default
    if value <= 0:
        logger.warning("Invalid %s=%r (must be > 0); using default %s", name, raw, default)
        return default
    return value


# Concurrency limits (process-wide)
COHERE_MAX_CONCURRENT_REQUESTS = _env_int("COHERE_MAX_CONCURRENT_REQUESTS", 3)
ANTHROPIC_MAX_CONCURRENT_REQUESTS = _env_int("ANTHROPIC_MAX_CONCURRENT_REQUESTS", 3)

COHERE_SEMAPHORE = asyncio.Semaphore(COHERE_MAX_CONCURRENT_REQUESTS)
ANTHROPIC_SEMAPHORE = asyncio.Semaphore(ANTHROPIC_MAX_CONCURRENT_REQUESTS)


# Timeouts (seconds)
COHERE_TIMEOUT_SECONDS = _env_float("COHERE_TIMEOUT_SECONDS", 10.0)
ANTHROPIC_CHAT_TIMEOUT_SECONDS = _env_float("ANTHROPIC_CHAT_TIMEOUT_SECONDS", 30.0)
ANTHROPIC_EXTRACTION_TIMEOUT_SECONDS = _env_float("ANTHROPIC_EXTRACTION_TIMEOUT_SECONDS", 45.0)

