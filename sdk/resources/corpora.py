from __future__ import annotations

from typing import Any, Dict, Optional, cast

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
        payload: dict[str, Any] = {"project_id": project_id, "name": name}
        if description is not None:
            payload["description"] = description
        data = self._request("POST", "/v1/corpora", json=payload)
        return cast("CorpusResponse", data)

    def list_corpora(self, limit: int = 100, offset: int = 0) -> CorpusListResponse:
        data = self._request("GET", "/v1/corpora", params={"limit": limit, "offset": offset})
        return cast("CorpusListResponse", data)

    def get_corpus(self, corpus_id: str) -> CorpusResponse:
        data = self._request("GET", f"/v1/corpora/{corpus_id}")
        return cast("CorpusResponse", data)

    def get_corpus_status(self, corpus_id: str) -> CorpusStatusResponse:
        data = self._request("GET", f"/v1/corpora/{corpus_id}/status")
        return cast("CorpusStatusResponse", data)

    def update_corpus(
        self,
        corpus_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        chunking_config: dict[str, Any] | None = None,
    ) -> CorpusResponse:
        """Update corpus settings.

        Args:
            corpus_id: ID of the corpus to update
            name: New name for the corpus
            description: New description for the corpus
            chunking_config: Default chunking configuration for documents in this corpus.
                Example: {"strategy": "unstructured", "chunking_strategy": "by_title",
                          "chunk_size": 1000, "overlap": 100}

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
        data = self._request("PATCH", f"/v1/corpora/{corpus_id}", json=payload)
        return cast("CorpusResponse", data)

    def delete_corpus(self, corpus_id: str, force: bool = False) -> CorpusDeleteResponse:
        data = self._request("DELETE", f"/v1/corpora/{corpus_id}", params={"force": force})
        return cast("CorpusDeleteResponse", data)

    def list_corpus_models(
        self, corpus_id: str, limit: int = 100, offset: int = 0
    ) -> ModelListResponse:
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/models",
            params={"limit": limit, "offset": offset},
        )
        return cast("ModelListResponse", data)
