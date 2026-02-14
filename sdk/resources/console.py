from __future__ import annotations

from typing import Any, Dict, Optional, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyRevokeResponse,
    ConsoleBootstrapResponse,
    ConsoleMeResponse,
    ConsoleOrgResponse,
    ConsoleProjectListResponse,
    ConsoleSummaryResponse,
    InviteAcceptResponse,
    InviteCreateResponse,
    InviteListResponse,
    MemberRemoveResponse,
    MemberUpdateResponse,
    TeamListResponse,
)


class ConsoleMixin(RequesterMixin):
    def console_me(self, *, project_id: str | None = None) -> ConsoleMeResponse:
        params: dict[str, Any] = {}
        if project_id is not None:
            params["project_id"] = project_id
        data = self._request("GET", "/v1/console/me", params=params or None)
        return cast("ConsoleMeResponse", data)

    def console_bootstrap(
        self,
        *,
        org_name: str | None = None,
        project_name: str | None = None,
        email: str | None = None,
        name: str | None = None,
    ) -> ConsoleBootstrapResponse:
        payload: dict[str, Any] = {}
        if org_name is not None:
            payload["org_name"] = org_name
        if project_name is not None:
            payload["project_name"] = project_name
        if email is not None:
            payload["email"] = email
        if name is not None:
            payload["name"] = name
        data = self._request("POST", "/v1/console/bootstrap", json=payload)
        return cast("ConsoleBootstrapResponse", data)

    def console_summary(self) -> ConsoleSummaryResponse:
        data = self._request("GET", "/v1/console/summary")
        return cast("ConsoleSummaryResponse", data)

    def console_projects(self) -> ConsoleProjectListResponse:
        data = self._request("GET", "/v1/console/projects")
        return cast("ConsoleProjectListResponse", data)

    def console_get_org(self) -> ConsoleOrgResponse:
        data = self._request("GET", "/v1/console/org")
        return cast("ConsoleOrgResponse", data)

    def console_update_org(
        self, *, name: str | None = None, contact_email: str | None = None
    ) -> ConsoleOrgResponse:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if contact_email is not None:
            payload["contact_email"] = contact_email
        data = self._request("PATCH", "/v1/console/org", json=payload)
        return cast("ConsoleOrgResponse", data)

    def console_list_team(self) -> TeamListResponse:
        data = self._request("GET", "/v1/console/team")
        return cast("TeamListResponse", data)

    def console_list_invites(self) -> InviteListResponse:
        data = self._request("GET", "/v1/console/invites")
        return cast("InviteListResponse", data)

    def console_create_invite(self, email: str, role: str = "member") -> InviteCreateResponse:
        payload = {"email": email, "role": role}
        data = self._request("POST", "/v1/console/invites", json=payload)
        return cast("InviteCreateResponse", data)

    def console_accept_invite(self, token: str) -> InviteAcceptResponse:
        data = self._request("POST", f"/v1/console/invites/{token}/accept")
        return cast("InviteAcceptResponse", data)

    def console_update_member_role(self, membership_id: str, role: str) -> MemberUpdateResponse:
        payload = {"role": role}
        data = self._request("PATCH", f"/v1/console/team/{membership_id}", json=payload)
        return cast("MemberUpdateResponse", data)

    def console_remove_member(self, membership_id: str) -> MemberRemoveResponse:
        data = self._request("DELETE", f"/v1/console/team/{membership_id}")
        return cast("MemberRemoveResponse", data)

    def console_list_api_keys(self) -> ApiKeyListResponse:
        data = self._request("GET", "/v1/console/api-keys")
        return cast("ApiKeyListResponse", data)

    def console_create_api_key(self, name: str, access: str = "retrieval") -> ApiKeyCreateResponse:
        payload = {"name": name, "access": access}
        data = self._request("POST", "/v1/console/api-keys", json=payload)
        return cast("ApiKeyCreateResponse", data)

    def console_revoke_api_key(self, key_id: str) -> ApiKeyRevokeResponse:
        data = self._request("POST", f"/v1/console/api-keys/{key_id}:revoke")
        return cast("ApiKeyRevokeResponse", data)
