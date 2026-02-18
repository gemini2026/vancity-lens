"""Usage metrics resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import UsageByCorpusResponse, UsageByKeyResponse, UsageSummaryResponse


class UsageMixin(RequesterMixin):
    def usage_summary(
        self, *, range_value: str = "7d", corpus_id: str | None = None
    ) -> UsageSummaryResponse:
        """Retrieve an aggregate usage summary.

        Args:
            range_value: Time range for the summary (e.g. ``"7d"``,
                ``"30d"``).
            corpus_id: Optional corpus to scope the summary to.

        Returns:
            Aggregated usage statistics for the requested period.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        params: dict[str, Any] = {"range": range_value}
        if corpus_id:
            params["corpus_id"] = corpus_id
        data = self._request("GET", "/v1/usage/summary", params=params)
        return cast("UsageSummaryResponse", data)

    def usage_by_corpus(self, *, range_value: str = "7d") -> UsageByCorpusResponse:
        """Retrieve usage metrics broken down by corpus.

        Args:
            range_value: Time range for the breakdown (e.g. ``"7d"``,
                ``"30d"``).

        Returns:
            Per-corpus usage statistics for the requested period.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/usage/by_corpus", params={"range": range_value})
        return cast("UsageByCorpusResponse", data)

    def usage_by_key(self) -> UsageByKeyResponse:
        """Retrieve usage metrics broken down by API key.

        Returns:
            Per-key usage statistics.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/usage/by_key")
        return cast("UsageByKeyResponse", data)
