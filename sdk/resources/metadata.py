"""Metadata discovery resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, cast

from sdk.resources._mixin_base import RequesterMixin


class MetadataMixin(RequesterMixin):
    """Metadata discovery operations."""

    def discover_metadata(
        self,
        corpus_id: str,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Discover metadata fields available in a corpus.

        Returns distinct metadata keys with inferred types, value
        distributions, and basic statistics.

        Args:
            corpus_id: Corpus ID to discover metadata for.
            refresh: Force cache refresh (bypass cached results).

        Returns:
            Discovery response with fields, types, and stats.

        Raises:
            NotFoundError: If the corpus does not exist.
            Knowledge2Error: If the API request fails.

        Example:
            >>> info = client.discover_metadata("corpus-123")
            >>> for field in info["fields"]:
            ...     print(field["key"], field["type"], field["count"])
        """
        params: dict[str, Any] = {}
        if refresh:
            params["refresh"] = "true"
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/metadata/discover",
            params=params,
        )
        return cast("dict[str, Any]", data)
