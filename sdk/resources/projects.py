from __future__ import annotations

from typing import Any, Dict, Optional, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import ProjectListResponse, ProjectResponse


class ProjectsMixin(RequesterMixin):
    def create_project(
        self,
        name: str,
        *,
        org_id: str | None = None,
        org_name: str | None = None,
    ) -> ProjectResponse:
        payload: dict[str, Any] = {"name": name}
        resolved_org_id = org_id or getattr(self, "org_id", None)
        if resolved_org_id:
            payload["org_id"] = resolved_org_id
        if org_name:
            payload["org_name"] = org_name
        data = self._request("POST", "/v1/projects", json=payload)
        return cast("ProjectResponse", data)

    def list_projects(self, limit: int = 100, offset: int = 0) -> ProjectListResponse:
        data = self._request("GET", "/v1/projects", params={"limit": limit, "offset": offset})
        return cast("ProjectListResponse", data)
