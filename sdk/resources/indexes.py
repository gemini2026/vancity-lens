from __future__ import annotations

from typing import Optional, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import IndexBuildResponse, IndexCompactResponse, IndexStatusResponse


class IndexesMixin(RequesterMixin):
    def build_indexes(
        self,
        corpus_id: str,
        dense: bool = True,
        sparse: bool = True,
        mode: str = "full",
        idempotency_key: str | None = None,
        *,
        wait: bool = True,
        poll_s: int = 5,
    ) -> IndexBuildResponse:
        payload = {"dense": dense, "sparse": sparse, "mode": mode}
        headers = self._idempotency_headers(idempotency_key)
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/indexes:build",
            json=payload,
            headers=headers,
        )
        if wait:
            job_id = data.get("job_id")
            if job_id:
                self._wait_for_job(job_id, poll_s=poll_s)
        return cast("IndexBuildResponse", data)

    def index_status(self, corpus_id: str) -> IndexStatusResponse:
        data = self._request("GET", f"/v1/corpora/{corpus_id}/indexes/status")
        return cast("IndexStatusResponse", data)

    def rebuild_indexes(
        self,
        corpus_id: str,
        dense: bool = True,
        sparse: bool = True,
        idempotency_key: str | None = None,
    ) -> IndexBuildResponse:
        payload = {"dense": dense, "sparse": sparse, "mode": "full"}
        headers = self._idempotency_headers(idempotency_key)
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/indexes:rebuild",
            json=payload,
            headers=headers,
        )
        return cast("IndexBuildResponse", data)

    def compact_indexes(
        self, corpus_id: str, *, dense: bool = True, sparse: bool = True, keep: int = 1
    ) -> IndexCompactResponse:
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/indexes:compact",
            params={"dense": dense, "sparse": sparse, "keep": keep},
        )
        return cast("IndexCompactResponse", data)
