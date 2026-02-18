"""Console resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyRevokeResponse,
    ConsoleBootstrapResponse,
    ConsoleMeResponse,
    ConsoleOrgResponse,
    ConsoleProjectItem,
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
        """Retrieve the current console user profile.

        Args:
            project_id: Optional project context to include in the response.

        Returns:
            The authenticated user's console profile information.

        Raises:
            Knowledge2Error: If the API request fails.
        """
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
        """Bootstrap a new console session, creating org/project if needed.

        Args:
            org_name: Name for the organisation to create or associate.
            project_name: Name for the default project to create.
            email: Contact email for the new organisation.
            name: Display name for the user.

        Returns:
            Bootstrap result containing created or existing org/project details.

        Raises:
            Knowledge2Error: If the API request fails.
        """
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
        """Retrieve a high-level summary of the console (corpora, jobs, etc.).

        Returns:
            Aggregated summary statistics for the current organisation.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/console/summary")
        return cast("ConsoleSummaryResponse", data)

    def console_projects(self) -> ConsoleProjectListResponse:
        """List all projects visible in the console.

        Returns:
            A list of console project summaries.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/console/projects")
        return cast("ConsoleProjectListResponse", data)

    def console_get_project(self, project_id: str) -> ConsoleProjectItem:
        """Retrieve details of a single console project.

        Args:
            project_id: Unique identifier of the project.

        Returns:
            Detailed project information.

        Raises:
            NotFoundError: If the project does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", f"/v1/console/projects/{project_id}")
        return cast("ConsoleProjectItem", data)

    def console_update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        graph_rag_policy: dict[str, Any] | None = None,
    ) -> ConsoleProjectItem:
        """Update a console project's settings.

        Args:
            project_id: Unique identifier of the project to update.
            name: New display name for the project.
            graph_rag_policy: Updated GraphRAG policy configuration.

        Returns:
            The updated project information.

        Raises:
            NotFoundError: If the project does not exist.
            Knowledge2Error: If the API request fails.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if graph_rag_policy is not None:
            payload["graph_rag_policy"] = graph_rag_policy
        data = self._request("PATCH", f"/v1/console/projects/{project_id}", json=payload)
        return cast("ConsoleProjectItem", data)

    def console_get_org(self) -> ConsoleOrgResponse:
        """Retrieve the current organisation's console profile.

        Returns:
            Organisation details including name and settings.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/console/org")
        return cast("ConsoleOrgResponse", data)

    def console_update_org(
        self, *, name: str | None = None, contact_email: str | None = None
    ) -> ConsoleOrgResponse:
        """Update the current organisation's settings.

        Args:
            name: New display name for the organisation.
            contact_email: New contact email address.

        Returns:
            The updated organisation details.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if contact_email is not None:
            payload["contact_email"] = contact_email
        data = self._request("PATCH", "/v1/console/org", json=payload)
        return cast("ConsoleOrgResponse", data)

    def console_list_team(self) -> TeamListResponse:
        """List all team members in the current organisation.

        Returns:
            A list of team member records with roles.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/console/team")
        return cast("TeamListResponse", data)

    def console_list_invites(self) -> InviteListResponse:
        """List pending team invitations for the current organisation.

        Returns:
            A list of pending invitation records.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/console/invites")
        return cast("InviteListResponse", data)

    def console_create_invite(self, email: str, role: str = "member") -> InviteCreateResponse:
        """Invite a new member to the current organisation.

        Args:
            email: Email address of the person to invite.
            role: Role to assign (e.g. ``"member"``, ``"admin"``).

        Returns:
            The created invitation record.

        Raises:
            ConflictError: If an invitation for this email already exists.
            Knowledge2Error: If the API request fails.
        """
        payload = {"email": email, "role": role}
        data = self._request("POST", "/v1/console/invites", json=payload)
        return cast("InviteCreateResponse", data)

    def console_accept_invite(self, token: str) -> InviteAcceptResponse:
        """Accept a pending team invitation.

        Args:
            token: The invitation token received via email.

        Returns:
            Confirmation of the accepted invitation.

        Raises:
            NotFoundError: If the invitation token is invalid or expired.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("POST", f"/v1/console/invites/{token}/accept")
        return cast("InviteAcceptResponse", data)

    def console_update_member_role(self, membership_id: str, role: str) -> MemberUpdateResponse:
        """Update a team member's role within the organisation.

        Args:
            membership_id: Unique identifier of the membership to update.
            role: New role to assign (e.g. ``"member"``, ``"admin"``).

        Returns:
            The updated membership record.

        Raises:
            NotFoundError: If the membership does not exist.
            Knowledge2Error: If the API request fails.
        """
        payload = {"role": role}
        data = self._request("PATCH", f"/v1/console/team/{membership_id}", json=payload)
        return cast("MemberUpdateResponse", data)

    def console_remove_member(self, membership_id: str) -> MemberRemoveResponse:
        """Remove a member from the organisation.

        Args:
            membership_id: Unique identifier of the membership to remove.

        Returns:
            Confirmation of the member removal.

        Raises:
            NotFoundError: If the membership does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("DELETE", f"/v1/console/team/{membership_id}")
        return cast("MemberRemoveResponse", data)

    def console_list_api_keys(self) -> ApiKeyListResponse:
        """List API keys managed through the console.

        Returns:
            A list of API key metadata objects.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/console/api-keys")
        return cast("ApiKeyListResponse", data)

    def console_create_api_key(self, name: str, access: str = "retrieval") -> ApiKeyCreateResponse:
        """Create a new API key through the console.

        Args:
            name: Human-readable name for the key.
            access: Access level for the key (e.g. ``"retrieval"``, ``"admin"``).

        Returns:
            The newly created API key, including the raw secret (shown only once).

        Raises:
            Knowledge2Error: If the API request fails.
        """
        payload = {"name": name, "access": access}
        data = self._request("POST", "/v1/console/api-keys", json=payload)
        return cast("ApiKeyCreateResponse", data)

    def console_revoke_api_key(self, key_id: str) -> ApiKeyRevokeResponse:
        """Revoke an API key through the console.

        Args:
            key_id: Unique identifier of the API key to revoke.

        Returns:
            Confirmation of the revocation.

        Raises:
            NotFoundError: If the key does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("POST", f"/v1/console/api-keys/{key_id}:revoke")
        return cast("ApiKeyRevokeResponse", data)
