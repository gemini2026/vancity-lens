from __future__ import annotations

from typing import Any, Optional


class Knowledge2Error(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        details: Any = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.details = details
        self.request_id = request_id
