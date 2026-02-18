"""Project resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, Iterator, cast

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
        """Create a new project within an organisation.

        If neither *org_id* nor *org_name* is supplied, the client's
        default ``org_id`` (if set) is used.

        Args:
            name: Display name for the project.
            org_id: Explicit organisation ID to own the project.
            org_name: Organisation name (resolved server-side if
                *org_id* is not provided).

        Returns:
            The newly created project record.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        payload: dict[str, Any] = {"name": name}
        resolved_org_id = org_id or getattr(self, "org_id", None)
        if resolved_org_id:
            payload["org_id"] = resolved_org_id
        if org_name:
            payload["org_name"] = org_name
        data = self._request("POST", "/v1/projects", json=payload)
        return cast("ProjectResponse", data)

    def list_projects(self, limit: int = 100, offset: int = 0) -> ProjectListResponse:
        """List projects accessible to the current credentials.

        Args:
            limit: Maximum number of projects to return per page.
            offset: Number of projects to skip for pagination.

        Returns:
            A paginated list of project records.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/projects", params={"limit": limit, "offset": offset})
        return cast("ProjectListResponse", data)

    def iter_projects(self, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Iterate over projects, automatically paginating.

        Args:
            limit: Page size used for each underlying API request.

        Yields:
            Individual project dicts.

        Raises:
            Knowledge2Error: If any underlying API request fails.
        """
        return self._paginate("GET", "/v1/projects", items_key="projects", limit=limit)
