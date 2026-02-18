"""Deployment resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, Iterator, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import DeploymentResponse


class DeploymentsMixin(RequesterMixin):
    def create_deployment(
        self, corpus_id: str, model_id: str, *, traffic_pct: int = 100, reindex: bool = True
    ) -> DeploymentResponse:
        """Deploy a tuned model to a corpus for serving retrieval traffic.

        Args:
            corpus_id: The corpus to deploy the model to.
            model_id: The tuned model to deploy.
            traffic_pct: Percentage of retrieval traffic to route through
                this deployment (0-100).
            reindex: Whether to trigger a re-index after deployment.

        Returns:
            The created deployment record.

        Raises:
            NotFoundError: If the corpus or model does not exist.
            Knowledge2Error: If the API request fails.
        """
        payload = {"model_id": model_id, "traffic_pct": traffic_pct, "reindex": reindex}
        data = self._request("POST", f"/v1/corpora/{corpus_id}/deployments", json=payload)
        return cast("DeploymentResponse", data)

    def list_deployments(
        self, corpus_id: str, limit: int = 100, offset: int = 0
    ) -> list[DeploymentResponse]:
        """List deployments for a corpus.

        Args:
            corpus_id: The corpus whose deployments to list.
            limit: Maximum number of deployments to return per page.
            offset: Number of deployments to skip for pagination.

        Returns:
            A list of deployment records for the corpus.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/deployments",
            params={"limit": limit, "offset": offset},
        )
        return cast("list[DeploymentResponse]", data)

    def iter_deployments(self, corpus_id: str, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Iterate over deployments, automatically paginating.

        Args:
            corpus_id: The corpus whose deployments to iterate.
            limit: Page size used for each underlying API request.

        Yields:
            Individual deployment dicts.

        Raises:
            Knowledge2Error: If any underlying API request fails.
        """
        return self._paginate(
            "GET",
            f"/v1/corpora/{corpus_id}/deployments",
            items_key="items",
            limit=limit,
        )
