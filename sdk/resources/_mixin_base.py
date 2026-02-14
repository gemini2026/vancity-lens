from __future__ import annotations

from typing import Any, Callable, Dict, Optional


class RequesterMixin:
    _request: Callable[..., Any]
    _idempotency_headers: Callable[[str | None], dict[str, str]]
    _wait_for_job: Callable[..., dict[str, Any]]
