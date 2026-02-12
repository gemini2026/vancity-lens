from __future__ import annotations

from typing import Any, Dict, Optional, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import AuditLogListResponse


class AuditMixin(RequesterMixin):
    def list_audit_logs(
        self,
        *,
        corpus_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> AuditLogListResponse:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if corpus_id:
            params["corpus_id"] = corpus_id
        if project_id:
            params["project_id"] = project_id
        data = self._request("GET", "/v1/audit-logs", params=params)
        return cast("AuditLogListResponse", data)
