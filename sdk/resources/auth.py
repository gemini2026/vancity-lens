from __future__ import annotations

from typing import Any, Dict, Optional, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyRevokeResponse,
    ApiKeyRotateResponse,
    WhoAmIResponse,
)


class AuthMixin(RequesterMixin):
    def create_api_key(
        self, org_id: str, name: str, scopes: dict[str, Any] | None = None
    ) -> ApiKeyCreateResponse:
        payload: dict[str, Any] = {"org_id": org_id, "name": name}
        if scopes is not None:
            payload["scopes"] = scopes
        data = self._request("POST", "/v1/auth/api-keys", json=payload)
        return cast("ApiKeyCreateResponse", data)

    def list_api_keys(self) -> ApiKeyListResponse:
        data = self._request("GET", "/v1/auth/api-keys")
        return cast("ApiKeyListResponse", data)

    def revoke_api_key(self, key_id: str) -> ApiKeyRevokeResponse:
        data = self._request("POST", f"/v1/auth/api-keys/{key_id}:revoke")
        return cast("ApiKeyRevokeResponse", data)

    def rotate_api_key(self, key_id: str) -> ApiKeyRotateResponse:
        data = self._request("POST", f"/v1/auth/api-keys/{key_id}:rotate")
        return cast("ApiKeyRotateResponse", data)

    def fetch_whoami(self) -> WhoAmIResponse:
        data = self._request("GET", "/v1/auth/whoami")
        return cast("WhoAmIResponse", data)
