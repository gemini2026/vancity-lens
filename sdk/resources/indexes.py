"""Index management resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import IndexBuildResponse, IndexCompactResponse, IndexStatusResponse


class IndexesMixin(RequesterMixin):
    def build_indexes(
        self,
        corpus_id: str,
        dense: bool = True,
        sparse: bool = True,
        sparse_metadata: bool | None = None,
        mode: str = "full",
        idempotency_key: str | None = None,
        *,
        wait: bool = True,
        poll_s: int = 5,
        graph: bool | None = None,
    ) -> IndexBuildResponse:
        """Build dense and/or sparse indexes for a corpus.

        Args:
            corpus_id: The corpus to build indexes for.
            dense: Whether to build a dense (vector) index.
            sparse: Whether to build a sparse (BM25) index.
            sparse_metadata: Whether to build the metadata sparse (BM25)
                index. ``None`` uses the server default.
            mode: Build mode — ``"full"`` rebuilds from scratch,
                ``"incremental"`` indexes only new documents.
            idempotency_key: Optional idempotency key to prevent
                duplicate builds.
            wait: If ``True`` (default), block until the index build
                job completes.
            poll_s: Polling interval in seconds when *wait* is ``True``.
            graph: Whether to build a GraphRAG index. ``None`` uses
                the server default.

        Returns:
            The index build response, including the background job ID.

        Raises:
            NotFoundError: If the corpus does not exist.
            ConflictError: If a duplicate idempotency key is detected.
            Knowledge2Error: If the API request fails.
        """
        payload = {"dense": dense, "sparse": sparse, "mode": mode}
        if sparse_metadata is not None:
            payload["sparse_metadata"] = bool(sparse_metadata)
        if graph is not None:
            payload["graph"] = bool(graph)
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
        """Retrieve the current index status for a corpus.

        Args:
            corpus_id: The corpus to check.

        Returns:
            Index status including dense/sparse readiness and row counts.

        Raises:
            NotFoundError: If the corpus does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", f"/v1/corpora/{corpus_id}/indexes/status")
        return cast("IndexStatusResponse", data)

    def rebuild_indexes(
        self,
        corpus_id: str,
        dense: bool = True,
        sparse: bool = True,
        sparse_metadata: bool | None = None,
        idempotency_key: str | None = None,
        *,
        graph: bool | None = None,
    ) -> IndexBuildResponse:
        """Force a full rebuild of indexes for a corpus.

        Unlike :meth:`build_indexes`, this always performs a full rebuild
        regardless of existing index state.

        Args:
            corpus_id: The corpus to rebuild indexes for.
            dense: Whether to rebuild the dense (vector) index.
            sparse: Whether to rebuild the sparse (BM25) index.
            sparse_metadata: Whether to rebuild the metadata sparse
                (BM25) index. ``None`` uses the server default.
            idempotency_key: Optional idempotency key to prevent
                duplicate rebuilds.
            graph: Whether to rebuild the GraphRAG index. ``None``
                uses the server default.

        Returns:
            The index build response, including the background job ID.

        Raises:
            NotFoundError: If the corpus does not exist.
            ConflictError: If a duplicate idempotency key is detected.
            Knowledge2Error: If the API request fails.
        """
        payload = {"dense": dense, "sparse": sparse, "mode": "full"}
        if sparse_metadata is not None:
            payload["sparse_metadata"] = bool(sparse_metadata)
        if graph is not None:
            payload["graph"] = bool(graph)
        headers = self._idempotency_headers(idempotency_key)
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/indexes:rebuild",
            json=payload,
            headers=headers,
        )
        return cast("IndexBuildResponse", data)

    def compact_indexes(
        self,
        corpus_id: str,
        *,
        dense: bool = True,
        sparse: bool = True,
        graph: bool = True,
        keep: int = 1,
    ) -> IndexCompactResponse:
        """Compact index artifacts for a corpus, removing old generations.

        Args:
            corpus_id: The corpus whose indexes to compact.
            dense: Whether to compact dense index artifacts.
            sparse: Whether to compact sparse index artifacts.
            graph: Whether to compact graph index artifacts.
            keep: Number of recent index generations to retain.

        Returns:
            A summary of compacted artifacts.

        Raises:
            NotFoundError: If the corpus does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/indexes:compact",
            params={"dense": dense, "sparse": sparse, "graph": graph, "keep": keep},
        )
        return cast("IndexCompactResponse", data)
