"""Shared limits and timeouts for external AI services (Anthropic, Gemini).

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


# ── LLM Backend Selection ───────────────────────────────────────────
# "gemini" (default — fast, uses Vertex AI) or "anthropic"
LLM_BACKEND = (os.environ.get("LLM_BACKEND") or "gemini").strip().lower()

# Gemini model — Gemini 2.5 Flash is optimised for low-latency generation
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_PROJECT = os.environ.get("GCP_PROJECT_ID", "openclaw-antonmishel-03460").strip()
GEMINI_LOCATION = os.environ.get("GCP_REGION", "us-west1").strip()

# Concurrency limits (process-wide)
ANTHROPIC_MAX_CONCURRENT_REQUESTS = _env_int("ANTHROPIC_MAX_CONCURRENT_REQUESTS", 3)
LLM_MAX_CONCURRENT_REQUESTS = _env_int("LLM_MAX_CONCURRENT_REQUESTS", 5)

ANTHROPIC_SEMAPHORE = asyncio.Semaphore(ANTHROPIC_MAX_CONCURRENT_REQUESTS)
LLM_SEMAPHORE = asyncio.Semaphore(LLM_MAX_CONCURRENT_REQUESTS)

# Timeouts (seconds)
ANTHROPIC_CHAT_TIMEOUT_SECONDS = _env_float("ANTHROPIC_CHAT_TIMEOUT_SECONDS", 30.0)
ANTHROPIC_EXTRACTION_TIMEOUT_SECONDS = _env_float("ANTHROPIC_EXTRACTION_TIMEOUT_SECONDS", 45.0)
GEMINI_CHAT_TIMEOUT_SECONDS = _env_float("GEMINI_CHAT_TIMEOUT_SECONDS", 15.0)
GEMINI_EXTRACTION_TIMEOUT_SECONDS = _env_float("GEMINI_EXTRACTION_TIMEOUT_SECONDS", 25.0)
