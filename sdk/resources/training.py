"""Training and tuning resource mixin for the Knowledge2 SDK."""

from __future__ import annotations

from typing import Any, Iterator, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
    CancelTuningRunResponse,
    EvalRunDetailResponse,
    PromoteResponse,
    TrainingDataBuildResponse,
    TrainingDatasetListResponse,
    TuningRunBuildResponse,
    TuningRunDetailResponse,
    TuningRunListResponse,
    TuningRunLogsResponse,
    TuningRunResponse,
)


class TrainingMixin(RequesterMixin):
    def build_training_data(
        self,
        corpus_id: str,
        idempotency_key: str | None = None,
    ) -> TrainingDataBuildResponse:
        """Trigger a training data build job for a corpus.

        Generates query-document pairs from the corpus content for use
        in model tuning.

        Args:
            corpus_id: The corpus to build training data from.
            idempotency_key: Optional idempotency key to prevent
                duplicate builds.

        Returns:
            The training data build response, including the background
            job ID.

        Raises:
            NotFoundError: If the corpus does not exist.
            ConflictError: If a duplicate idempotency key is detected.
            Knowledge2Error: If the API request fails.
        """
        headers = self._idempotency_headers(idempotency_key)
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/training-data:build",
            json={},
            headers=headers,
        )
        return cast("TrainingDataBuildResponse", data)

    def list_training_data(
        self, corpus_id: str, limit: int = 100, offset: int = 0
    ) -> TrainingDatasetListResponse:
        """List training datasets generated for a corpus.

        Args:
            corpus_id: The corpus whose training data to list.
            limit: Maximum number of datasets to return per page.
            offset: Number of datasets to skip for pagination.

        Returns:
            A paginated list of training dataset records.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/training-data",
            params={"limit": limit, "offset": offset},
        )
        return cast("TrainingDatasetListResponse", data)

    def iter_training_data(self, corpus_id: str, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Iterate over training data, automatically paginating.

        Args:
            corpus_id: The corpus whose training data to iterate.
            limit: Page size used for each underlying API request.

        Yields:
            Individual training dataset dicts.

        Raises:
            Knowledge2Error: If any underlying API request fails.
        """
        return self._paginate(
            "GET",
            f"/v1/corpora/{corpus_id}/training-data",
            items_key="datasets",
            limit=limit,
        )

    def list_tuning_runs(
        self, corpus_id: str, limit: int = 100, offset: int = 0
    ) -> TuningRunListResponse:
        """List tuning runs for a corpus.

        Args:
            corpus_id: The corpus whose tuning runs to list.
            limit: Maximum number of tuning runs to return per page.
            offset: Number of tuning runs to skip for pagination.

        Returns:
            A paginated list of tuning run records.

        Raises:
            Knowledge2Error: If the API request fails.
        """
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/tuning-runs",
            params={"limit": limit, "offset": offset},
        )
        return cast("TuningRunListResponse", data)

    def iter_tuning_runs(self, corpus_id: str, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Iterate over tuning runs, automatically paginating.

        Args:
            corpus_id: The corpus whose tuning runs to iterate.
            limit: Page size used for each underlying API request.

        Yields:
            Individual tuning run dicts.

        Raises:
            Knowledge2Error: If any underlying API request fails.
        """
        return self._paginate(
            "GET",
            f"/v1/corpora/{corpus_id}/tuning-runs",
            items_key="runs",
            limit=limit,
        )

    def create_tuning_run(
        self,
        corpus_id: str,
        idempotency_key: str | None = None,
        *,
        use_ftk: bool = False,
    ) -> TuningRunResponse:
        """Create a tuning run for the corpus.

        Args:
            corpus_id: The corpus to tune.
            idempotency_key: Optional idempotency key.
            use_ftk: If True, use FTK trainer (BiEncoder with InfoNCE loss).
                     If False (default), use standard sentence-transformers trainer.
        """
        headers = self._idempotency_headers(idempotency_key)
        body: dict[str, Any] = {}
        if use_ftk:
            body["use_ftk"] = True
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/tuning-runs",
            json=body,
            headers=headers,
        )
        return cast("TuningRunResponse", data)

    def build_and_start_tuning_run(
        self,
        corpus_id: str,
        idempotency_key: str | None = None,
        *,
        wait: bool = True,
        poll_s: int = 5,
    ) -> TuningRunBuildResponse:
        """Build training data and start a tuning run in one step.

        This is a convenience method that combines training data
        generation and tuning run creation into a single call.

        Args:
            corpus_id: The corpus to tune.
            idempotency_key: Optional idempotency key to prevent
                duplicate runs.
            wait: If ``True`` (default), block until the build job
                completes.
            poll_s: Polling interval in seconds when *wait* is ``True``.

        Returns:
            The tuning run build response, including the background
            job ID.

        Raises:
            NotFoundError: If the corpus does not exist.
            ConflictError: If a duplicate idempotency key is detected.
            Knowledge2Error: If the API request fails.
        """
        headers = self._idempotency_headers(idempotency_key)
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/tuning-runs:build",
            json={},
            headers=headers,
        )
        if wait:
            job_id = data.get("build_job_id") or data.get("job_id")
            if job_id:
                self._wait_for_job(job_id, poll_s=poll_s)
        return cast("TuningRunBuildResponse", data)

    def get_tuning_run(self, run_id: str) -> TuningRunDetailResponse:
        """Retrieve details of a tuning run.

        Args:
            run_id: Unique identifier of the tuning run.

        Returns:
            Detailed tuning run information including status, metrics,
            and configuration.

        Raises:
            NotFoundError: If the tuning run does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", f"/v1/tuning-runs/{run_id}")
        return cast("TuningRunDetailResponse", data)

    def get_tuning_run_logs(self, run_id: str, tail: int = 200) -> TuningRunLogsResponse:
        """Retrieve log output from a tuning run.

        Args:
            run_id: Unique identifier of the tuning run.
            tail: Number of most recent log lines to return.

        Returns:
            The requested log lines from the tuning run.

        Raises:
            NotFoundError: If the tuning run does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", f"/v1/tuning-runs/{run_id}/logs", params={"tail": tail})
        return cast("TuningRunLogsResponse", data)

    def cancel_tuning_run(self, run_id: str) -> CancelTuningRunResponse:
        """Cancel a running or pending tuning run.

        Args:
            run_id: Unique identifier of the tuning run to cancel.

        Returns:
            Confirmation of the cancellation.

        Raises:
            NotFoundError: If the tuning run does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("POST", f"/v1/tuning-runs/{run_id}:cancel")
        return cast("CancelTuningRunResponse", data)

    def promote_tuning_run(self, run_id: str) -> PromoteResponse:
        """Promote a completed tuning run to create a deployable model.

        Args:
            run_id: Unique identifier of the tuning run to promote.

        Returns:
            The promotion result, including the created model ID.

        Raises:
            NotFoundError: If the tuning run does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("POST", f"/v1/tuning-runs/{run_id}:promote")
        return cast("PromoteResponse", data)

    def get_eval_run(self, eval_id: str) -> EvalRunDetailResponse:
        """Retrieve details of an evaluation run.

        Args:
            eval_id: Unique identifier of the evaluation run.

        Returns:
            Detailed evaluation run information including metrics and
            status.

        Raises:
            NotFoundError: If the evaluation run does not exist.
            Knowledge2Error: If the API request fails.
        """
        data = self._request("GET", f"/v1/eval-runs/{eval_id}")
        return cast("EvalRunDetailResponse", data)
