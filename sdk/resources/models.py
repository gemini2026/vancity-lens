"""Model resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, Iterator, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import ModelDeleteResponse, ModelListResponse


class ModelsMixin(RequesterMixin):
    def list_models(self, limit: int = 100, offset: int = 0) -> ModelListResponse:
        """List models accessible to the current credentials.

        Args:
            limit: Maximum number of models to return per page.
            offset: Number of models to skip for pagination.

        Returns:
            A paginated list of model records.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", "/v1/models", params={"limit": limit, "offset": offset})
        return cast("ModelListResponse", data)

    def iter_models(self, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Lazily paginate models, yielding individual model items.

        Args:
            limit: Page size used for each underlying API request.

        Yields:
            Individual model dicts.

        Raises:
            Knowledge2Error: If any underlying API request fails.
        """
        yield from self._paginate(
            "GET",
            "/v1/models",
            items_key="models",
            limit=limit,
        )

    def delete_model(self, model_id: str, force: bool = False) -> ModelDeleteResponse:
        """Delete a model and its associated artifacts.

        Args:
            model_id: Unique identifier of the model to delete.
            force: If ``True``, delete even if the model is currently
                deployed.

        Returns:
            Confirmation of the deletion.

        Raises:
            NotFoundError: If the model does not exist.
            ConflictError: If *force* is ``False`` and the model has
                active deployments.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("DELETE", f"/v1/models/{model_id}", params={"force": force})
        return cast("ModelDeleteResponse", data)
