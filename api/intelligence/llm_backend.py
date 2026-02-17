"""Unified LLM backend for chat and extraction.

Supports Gemini (via Vertex AI) and Anthropic (Claude).  Gemini is the default
for low-latency generation; Anthropic is kept as a fallback.

Selection is controlled by the LLM_BACKEND env var ("gemini" or "anthropic").
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy singletons ─────────────────────────────────────────────────
_GEMINI_CLIENT = None
_ANTHROPIC_CLIENT: dict[str, object] = {}  # keyed by api_key


def _get_gemini_client():
    """Return a cached google.genai Client (Vertex AI)."""
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is not None:
        return _GEMINI_CLIENT

    from google import genai  # lazy import

    from .external_clients import GEMINI_LOCATION, GEMINI_PROJECT

    _GEMINI_CLIENT = genai.Client(
        vertexai=True,
        project=GEMINI_PROJECT,
        location=GEMINI_LOCATION,
    )
    logger.info(
        "Gemini client initialised (project=%s, location=%s)",
        GEMINI_PROJECT,
        GEMINI_LOCATION,
    )
    return _GEMINI_CLIENT


# ── Public API ───────────────────────────────────────────────────────

async def generate_chat(
    *,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 2000,
    anthropic_api_key: Optional[str] = None,
) -> tuple[str, str, float]:
    """Generate a chat completion using the configured LLM backend.

    Returns:
        (answer_text, model_used, latency_seconds)
    """
    from .external_clients import LLM_BACKEND

    if LLM_BACKEND == "gemini":
        return await _generate_gemini(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=max_tokens,
            timeout_attr="GEMINI_CHAT_TIMEOUT_SECONDS",
        )

    return await _generate_anthropic_chat(
        system_prompt=system_prompt,
        user_message=user_message,
        max_tokens=max_tokens,
        api_key=anthropic_api_key,
    )


async def generate_extraction(
    *,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 2000,
    anthropic_api_key: Optional[str] = None,
) -> tuple[str, str, float]:
    """Generate an extraction completion using the configured LLM backend.

    Returns:
        (response_text, model_used, latency_seconds)
    """
    from .external_clients import LLM_BACKEND

    if LLM_BACKEND == "gemini":
        return await _generate_gemini(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=max_tokens,
            timeout_attr="GEMINI_EXTRACTION_TIMEOUT_SECONDS",
        )

    return await _generate_anthropic_extraction(
        system_prompt=system_prompt,
        user_message=user_message,
        max_tokens=max_tokens,
        api_key=anthropic_api_key,
    )


# ── Gemini implementation ────────────────────────────────────────────

async def _generate_gemini(
    *,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    timeout_attr: str,
) -> tuple[str, str, float]:
    from google.genai import types  # lazy import

    from .external_clients import GEMINI_MODEL, LLM_SEMAPHORE

    timeout_seconds = getattr(
        __import__("api.intelligence.external_clients", fromlist=[timeout_attr]),
        timeout_attr,
    )

    client = _get_gemini_client()
    t0 = time.perf_counter()

    # Gemini 2.5 Flash uses a "thinking" phase that consumes output tokens.
    # Reserve most tokens for the actual response by capping the thinking budget.
    config_kwargs: dict = {
        "system_instruction": system_prompt,
        "max_output_tokens": max(max_tokens, 8192),
        "temperature": 0.3,
    }
    if "2.5" in GEMINI_MODEL:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=2048)

    async with LLM_SEMAPHORE:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_message,
                config=types.GenerateContentConfig(**config_kwargs),
            ),
            timeout=timeout_seconds,
        )

    latency = time.perf_counter() - t0
    text = response.text or ""
    logger.info("Gemini response in %.1fs (model=%s, chars=%d)", latency, GEMINI_MODEL, len(text))
    return text, GEMINI_MODEL, latency


# ── Anthropic implementation ─────────────────────────────────────────

_ANTHROPIC_CHAT_MODELS = [
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
]

_ANTHROPIC_EXTRACTION_MODELS = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
]


async def _generate_anthropic_chat(
    *,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    api_key: Optional[str],
) -> tuple[str, str, float]:
    from anthropic import AsyncAnthropic, NotFoundError

    from .external_clients import ANTHROPIC_CHAT_TIMEOUT_SECONDS, ANTHROPIC_SEMAPHORE

    client = AsyncAnthropic(api_key=api_key)
    t0 = time.perf_counter()

    model_candidates = _build_anthropic_model_list(_ANTHROPIC_CHAT_MODELS)

    try:
        text, model = await _anthropic_with_fallback(
            client=client,
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=max_tokens,
            timeout=ANTHROPIC_CHAT_TIMEOUT_SECONDS,
            semaphore=ANTHROPIC_SEMAPHORE,
            model_candidates=model_candidates,
        )
    finally:
        await client.close()

    latency = time.perf_counter() - t0
    logger.info("Anthropic chat response in %.1fs (model=%s)", latency, model)
    return text, model, latency


async def _generate_anthropic_extraction(
    *,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    api_key: Optional[str],
) -> tuple[str, str, float]:
    from anthropic import AsyncAnthropic

    from .external_clients import ANTHROPIC_EXTRACTION_TIMEOUT_SECONDS, ANTHROPIC_SEMAPHORE

    client = AsyncAnthropic(api_key=api_key)
    t0 = time.perf_counter()

    model_candidates = _build_anthropic_model_list(_ANTHROPIC_EXTRACTION_MODELS)

    try:
        text, model = await _anthropic_with_fallback(
            client=client,
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=max_tokens,
            timeout=ANTHROPIC_EXTRACTION_TIMEOUT_SECONDS,
            semaphore=ANTHROPIC_SEMAPHORE,
            model_candidates=model_candidates,
        )
    finally:
        await client.close()

    latency = time.perf_counter() - t0
    logger.info("Anthropic extraction response in %.1fs (model=%s)", latency, model)
    return text, model, latency


def _build_anthropic_model_list(defaults: list[str]) -> list[str]:
    configured = (os.environ.get("ANTHROPIC_MODEL") or "").strip()
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    candidates.extend(defaults)
    # dedupe preserving order
    seen: set[str] = set()
    result: list[str] = []
    for m in candidates:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


async def _anthropic_with_fallback(
    *,
    client,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    timeout: float,
    semaphore: asyncio.Semaphore,
    model_candidates: list[str],
) -> tuple[str, str]:
    """Try model candidates in order, skip 404s."""
    from anthropic import NotFoundError

    last_exc: Exception | None = None
    for model in model_candidates:
        try:
            async with semaphore:
                response = await asyncio.wait_for(
                    client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_message}],
                    ),
                    timeout=timeout,
                )
            return response.content[0].text, model
        except NotFoundError as e:
            last_exc = e
            logger.warning("Anthropic model not found: %s; trying fallback.", model)
            continue
        except Exception as e:
            msg = str(e)
            if "Error code: 404" in msg and ("model:" in msg or "not_found_error" in msg):
                last_exc = e
                logger.warning("Anthropic model not found: %s; trying fallback.", model)
                continue
            raise

    assert last_exc is not None
    raise last_exc
