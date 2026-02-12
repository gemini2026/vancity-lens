from __future__ import annotations

from typing import Any, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
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
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/training-data",
            params={"limit": limit, "offset": offset},
        )
        return cast("TrainingDatasetListResponse", data)

    def list_tuning_runs(
        self, corpus_id: str, limit: int = 100, offset: int = 0
    ) -> TuningRunListResponse:
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/tuning-runs",
            params={"limit": limit, "offset": offset},
        )
        return cast("TuningRunListResponse", data)

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
        data = self._request("GET", f"/v1/tuning-runs/{run_id}")
        return cast("TuningRunDetailResponse", data)

    def get_tuning_run_logs(self, run_id: str, tail: int = 200) -> TuningRunLogsResponse:
        data = self._request("GET", f"/v1/tuning-runs/{run_id}/logs", params={"tail": tail})
        return cast("TuningRunLogsResponse", data)

    def cancel_tuning_run(self, run_id: str) -> dict[str, Any]:
        data = self._request("POST", f"/v1/tuning-runs/{run_id}:cancel")
        return cast("dict[str, Any]", data)

    def promote_tuning_run(self, run_id: str) -> PromoteResponse:
        data = self._request("POST", f"/v1/tuning-runs/{run_id}:promote")
        return cast("PromoteResponse", data)

    def get_eval_run(self, eval_id: str) -> EvalRunDetailResponse:
        data = self._request("GET", f"/v1/eval-runs/{eval_id}")
        return cast("EvalRunDetailResponse", data)
