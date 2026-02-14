from __future__ import annotations

from typing import List, TypedDict


class ProjectResponse(TypedDict):
    id: str
    name: str
    org_id: str


class ProjectListResponse(TypedDict):
    projects: list[ProjectResponse]
