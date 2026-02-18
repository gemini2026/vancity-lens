"""Organisation resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import OrgResponse


class OrgsMixin(RequesterMixin):
    def create_org(self, name: str, contact_email: str | None = None) -> OrgResponse:
        """Create a new organisation.

        Args:
            name: Display name for the organisation.
            contact_email: Optional contact email address for the org.

        Returns:
            The newly created organisation record.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        payload: dict[str, Any] = {"name": name}
        if contact_email is not None:
            payload["contact_email"] = contact_email
        data = self._request("POST", "/v1/orgs", json=payload)
        return cast("OrgResponse", data)
