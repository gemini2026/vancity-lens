from __future__ import annotations

from typing import List, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import DeploymentResponse


class DeploymentsMixin(RequesterMixin):
    def create_deployment(
        self, corpus_id: str, model_id: str, *, traffic_pct: int = 100, reindex: bool = True
    ) -> DeploymentResponse:
        payload = {"model_id": model_id, "traffic_pct": traffic_pct, "reindex": reindex}
        data = self._request("POST", f"/v1/corpora/{corpus_id}/deployments", json=payload)
        return cast("DeploymentResponse", data)

    def list_deployments(
        self, corpus_id: str, limit: int = 100, offset: int = 0
    ) -> list[DeploymentResponse]:
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/deployments",
            params={"limit": limit, "offset": offset},
        )
        return cast("list[DeploymentResponse]", data)
