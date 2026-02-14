from __future__ import annotations

from typing import List, Optional, TypedDict


class AuditLogItem(TypedDict, total=False):
    id: str
    action: str
    entity_type: str
    entity_id: str | None
    org_id: str
    project_id: str | None
    corpus_id: str | None
    api_key_id: str | None
    payload: dict
    created_at: str


class AuditLogListResponse(TypedDict):
    logs: list[AuditLogItem]
