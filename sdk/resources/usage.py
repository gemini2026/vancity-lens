from __future__ import annotations

from typing import Any, Dict, Optional, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import UsageByCorpusResponse, UsageByKeyResponse, UsageSummaryResponse


class UsageMixin(RequesterMixin):
    def usage_summary(
        self, *, range_value: str = "7d", corpus_id: str | None = None
    ) -> UsageSummaryResponse:
        params: dict[str, Any] = {"range": range_value}
        if corpus_id:
            params["corpus_id"] = corpus_id
        data = self._request("GET", "/v1/usage/summary", params=params)
        return cast("UsageSummaryResponse", data)

    def usage_by_corpus(self, *, range_value: str = "7d") -> UsageByCorpusResponse:
        data = self._request("GET", "/v1/usage/by_corpus", params={"range": range_value})
        return cast("UsageByCorpusResponse", data)

    def usage_by_key(self) -> UsageByKeyResponse:
        data = self._request("GET", "/v1/usage/by_key")
        return cast("UsageByKeyResponse", data)
