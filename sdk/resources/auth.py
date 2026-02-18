"""Authentication resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

import warnings
from typing import Any, cast

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
        """Create a new API key for the given organisation.

        Args:
            org_id: Organisation that will own the key.
            name: Human-readable name for the key.
            scopes: Optional scope restrictions for the key.

        Returns:
            The newly created API key, including the raw secret (shown only once).

        Raises:
            Knowledge2Error: If the API request fails.
        """
        payload: dict[str, Any] = {"org_id": org_id, "name": name}
        if scopes is not None:
            payload["scopes"] = scopes
        data = self._request("POST", "/v1/auth/api-keys", json=payload)
        return cast("ApiKeyCreateResponse", data)

    def list_api_keys(self) -> ApiKeyListResponse:
        """List all API keys visible to the current credentials.

        Returns:
            A list of API key metadata objects.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/auth/api-keys")
        return cast("ApiKeyListResponse", data)

    def revoke_api_key(self, key_id: str) -> ApiKeyRevokeResponse:
        """Revoke an API key so it can no longer be used for authentication.

        Args:
            key_id: Unique identifier of the API key to revoke.

        Returns:
            Confirmation of the revocation.

        Raises:
            NotFoundError: If the key does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("POST", f"/v1/auth/api-keys/{key_id}:revoke")
        return cast("ApiKeyRevokeResponse", data)

    def rotate_api_key(self, key_id: str) -> ApiKeyRotateResponse:
        """Rotate an API key, generating a new secret and invalidating the old one.

        Args:
            key_id: Unique identifier of the API key to rotate.

        Returns:
            The rotated key with the new raw secret (shown only once).

        Raises:
            NotFoundError: If the key does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("POST", f"/v1/auth/api-keys/{key_id}:rotate")
        return cast("ApiKeyRotateResponse", data)

    def get_whoami(self) -> WhoAmIResponse:
        """Return information about the current API key.

        Returns:
            A dict containing ``org_id``, ``key_id``, ``name``,
            ``scopes``, and other metadata for the authenticated key.
        """
        data = self._request("GET", "/v1/auth/whoami")
        return cast("WhoAmIResponse", data)

    def fetch_whoami(self) -> WhoAmIResponse:
        """Return information about the current API key.

        .. deprecated::
            Use :meth:`get_whoami` instead.
        """
        warnings.warn(
            "fetch_whoami() is deprecated, use get_whoami() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get_whoami()
