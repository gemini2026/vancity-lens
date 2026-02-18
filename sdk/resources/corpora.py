"""Corpus resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, Iterator, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
    CorpusDeleteResponse,
    CorpusListResponse,
    CorpusResponse,
    CorpusStatusResponse,
    ModelListResponse,
)


class CorporaMixin(RequesterMixin):
    def create_corpus(
        self, project_id: str, name: str, description: str | None = None
    ) -> CorpusResponse:
        """Create a new corpus within a project.

        Args:
            project_id: The project that will own the corpus.
            name: Human-readable name for the corpus.
            description: Optional description of the corpus contents.

        Returns:
            The newly created corpus record.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        payload: dict[str, Any] = {"project_id": project_id, "name": name}
        if description is not None:
            payload["description"] = description
        data = self._request("POST", "/v1/corpora", json=payload)
        return cast("CorpusResponse", data)

    def list_corpora(self, limit: int = 100, offset: int = 0) -> CorpusListResponse:
        """List corpora accessible to the current credentials.

        Args:
            limit: Maximum number of corpora to return per page.
            offset: Number of corpora to skip for pagination.

        Returns:
            A paginated list of corpus records.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/corpora", params={"limit": limit, "offset": offset})
        return cast("CorpusListResponse", data)

    def iter_corpora(self, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Lazily paginate corpora, yielding individual corpus items.

        Args:
            limit: Page size used for each underlying API request.

        Yields:
            Individual corpus response dicts.

        Raises:
            Knowledge2Error: If any underlying API request fails.
        """
        return self._paginate(
            "GET",
            "/v1/corpora",
            items_key="corpora",
            limit=limit,
        )

    def get_corpus(self, corpus_id: str) -> CorpusResponse:
        """Retrieve a single corpus by ID.

        Args:
            corpus_id: Unique identifier of the corpus.

        Returns:
            The corpus record.

        Raises:
            NotFoundError: If the corpus does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", f"/v1/corpora/{corpus_id}")
        return cast("CorpusResponse", data)

    def get_corpus_status(self, corpus_id: str) -> CorpusStatusResponse:
        """Retrieve the ingestion and indexing status of a corpus.

        Args:
            corpus_id: Unique identifier of the corpus.

        Returns:
            Status information including document counts and index state.

        Raises:
            NotFoundError: If the corpus does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", f"/v1/corpora/{corpus_id}/status")
        return cast("CorpusStatusResponse", data)

    def update_corpus(
        self,
        corpus_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        chunking_config: dict[str, Any] | None = None,
        graph_rag_policy: dict[str, Any] | None = None,
    ) -> CorpusResponse:
        """Update corpus settings.

        Args:
            corpus_id: ID of the corpus to update
            name: New name for the corpus
            description: New description for the corpus
            chunking_config: Default chunking configuration for documents in this corpus.
                Example: {"strategy": "unstructured", "chunking_strategy": "by_title",
                          "chunk_size": 1000, "overlap": 100}
            graph_rag_policy: Optional corpus-level GraphRAG defaults that override
                project-level settings when present.

        Returns:
            Updated corpus response
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if chunking_config is not None:
            payload["chunking_config"] = chunking_config
        if graph_rag_policy is not None:
            payload["graph_rag_policy"] = graph_rag_policy
        data = self._request("PATCH", f"/v1/corpora/{corpus_id}", json=payload)
        return cast("CorpusResponse", data)

    def delete_corpus(self, corpus_id: str, force: bool = False) -> CorpusDeleteResponse:
        """Delete a corpus and its associated data.

        Args:
            corpus_id: Unique identifier of the corpus to delete.
            force: If ``True``, delete even if the corpus has active
                deployments or running jobs.

        Returns:
            Confirmation of the deletion.

        Raises:
            NotFoundError: If the corpus does not exist.
            ConflictError: If *force* is ``False`` and the corpus has
                active resources.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("DELETE", f"/v1/corpora/{corpus_id}", params={"force": force})
        return cast("CorpusDeleteResponse", data)

    def list_corpus_models(
        self, corpus_id: str, limit: int = 100, offset: int = 0
    ) -> ModelListResponse:
        """List models associated with a corpus.

        Args:
            corpus_id: Unique identifier of the corpus.
            limit: Maximum number of models to return per page.
            offset: Number of models to skip for pagination.

        Returns:
            A paginated list of model records for the corpus.

        Raises:
            NotFoundError: If the corpus does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/models",
            params={"limit": limit, "offset": offset},
        )
        return cast("ModelListResponse", data)

    def iter_corpus_models(self, corpus_id: str, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Lazily paginate corpus models, yielding individual model items.

        Args:
            corpus_id: Unique identifier of the corpus.
            limit: Page size used for each underlying API request.

        Yields:
            Individual model dicts.

        Raises:
            Knowledge2Error: If any underlying API request fails.
        """
        yield from self._paginate(
            "GET",
            f"/v1/corpora/{corpus_id}/models",
            items_key="models",
            limit=limit,
        )
