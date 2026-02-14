from __future__ import annotations

from typing import List, Optional, TypedDict


class ApiKeyCreateResponse(TypedDict):
    id: str
    org_id: str
    name: str
    api_key: str


class ApiKeyRotateResponse(TypedDict):
    id: str
    org_id: str
    name: str
    api_key: str


class ApiKeyRevokeResponse(TypedDict):
    id: str
    revoked: bool


class ApiKeyListItem(TypedDict, total=False):
    id: str
    org_id: str
    name: str
    scopes: dict
    revoked: bool
    created_at: str | None
    last_used_at: str | None


class ApiKeyListResponse(TypedDict):
    keys: list[ApiKeyListItem]


class WhoAmIResponse(TypedDict):
    org_id: str
    api_key_id: str
    name: str
