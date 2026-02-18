from __future__ import annotations

from typing import Any, TypedDict


class ProjectResponse(TypedDict):
    id: str
    name: str
    org_id: str
    graph_rag_policy: dict[str, Any] | None


class ProjectListResponse(TypedDict):
    projects: list[ProjectResponse]
