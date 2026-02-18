"""Logging utilities for the Knowledge2 SDK.

The SDK uses a logger named ``knowledge2``.  By default no handlers are
attached (standard library convention) — consumers configure logging as
they see fit.  :func:`set_debug` is a convenience shortcut that adds a
``StreamHandler`` with ``DEBUG`` level.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("knowledge2")

_REDACT_HEADERS: frozenset[str] = frozenset({"x-api-key", "authorization", "x-admin-token"})


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of *headers* with auth values replaced by ``***``."""
    return {k: ("***" if k.lower() in _REDACT_HEADERS else v) for k, v in headers.items()}


def set_debug(enabled: bool = True) -> None:
    """Enable or disable SDK debug logging to stderr.

    Args:
        enabled: When *True*, adds a ``StreamHandler`` at ``DEBUG`` level
            to the ``knowledge2`` logger.  When *False*, removes all
            handlers and resets the level.
    """
    if enabled:
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
            )
            logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    else:
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)
