from __future__ import annotations

from typing import cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import ModelDeleteResponse, ModelListResponse


class ModelsMixin(RequesterMixin):
    def list_models(self, limit: int = 100, offset: int = 0) -> ModelListResponse:
        data = self._request("GET", "/v1/models", params={"limit": limit, "offset": offset})
        return cast("ModelListResponse", data)

    def delete_model(self, model_id: str, force: bool = False) -> ModelDeleteResponse:
        data = self._request("DELETE", f"/v1/models/{model_id}", params={"force": force})
        return cast("ModelDeleteResponse", data)
