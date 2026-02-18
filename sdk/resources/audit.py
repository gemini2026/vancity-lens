"""Audit-log resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, Iterator, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import AuditLogListResponse


class AuditMixin(RequesterMixin):
    def list_audit_logs(
        self,
        *,
        corpus_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> AuditLogListResponse:
        """List audit log entries with optional filters.

        Args:
            corpus_id: Filter logs to a specific corpus.
            project_id: Filter logs to a specific project.
            limit: Maximum number of entries to return per page.
            offset: Number of entries to skip for pagination.

        Returns:
            A paginated list of audit log entries.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if corpus_id:
            params["corpus_id"] = corpus_id
        if project_id:
            params["project_id"] = project_id
        data = self._request("GET", "/v1/audit-logs", params=params)
        return cast("AuditLogListResponse", data)

    def iter_audit_logs(
        self,
        *,
        corpus_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
    ) -> Iterator[dict[str, Any]]:
        """Iterate over audit logs, automatically paginating.

        Args:
            corpus_id: Filter logs to a specific corpus.
            project_id: Filter logs to a specific project.
            limit: Page size used for each underlying API request.

        Yields:
            Individual audit log entry dicts.

        Raises:
            Knowledge2Error: If any underlying API request fails.
        """
        params: dict[str, Any] = {}
        if corpus_id:
            params["corpus_id"] = corpus_id
        if project_id:
            params["project_id"] = project_id
        return self._paginate(
            "GET", "/v1/audit-logs", items_key="logs", params=params or None, limit=limit
        )
