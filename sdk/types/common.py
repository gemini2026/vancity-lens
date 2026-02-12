from __future__ import annotations

from typing import Any, TypedDict


class ApiErrorDetail(TypedDict, total=False):
    code: str
    message: str
    details: Any
    request_id: str
