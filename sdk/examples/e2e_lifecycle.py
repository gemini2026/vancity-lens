from __future__ import annotations

import os
import time
import uuid
from typing import Iterable

from sdk import Knowledge2, Knowledge2Error
from sdk.types.jobs import JobResponse
from sdk.types.search import SearchResult
from sdk.types.training import TuningRunDetailResponse

TERMINAL_JOB_STATUSES = {"succeeded", "failed", "canceled"}
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "canceled"}


def _wait_for_job(
    client: Knowledge2,
    job_id: str,
    *,
    poll_s: float = 5.0,
    timeout_s: float = 900.0,
) -> JobResponse:
    deadline = time.time() + timeout_s
    while True:
        job = client.get_job(job_id)
        status = job.get("status")
        if status in TERMINAL_JOB_STATUSES:
            return job
        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for job {job_id}")
        time.sleep(poll_s)


def _wait_for_tuning_run(
    client: Knowledge2,
    run_id: str,
    *,
    poll_s: float = 10.0,
    timeout_s: float = 7200.0,
) -> TuningRunDetailResponse:
    deadline = time.time() + timeout_s
    while True:
        run = client.get_tuning_run(run_id)
        status = run.get("status")
        if status in TERMINAL_RUN_STATUSES:
            return run
        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for tuning run {run_id}")
        time.sleep(poll_s)


def _print_hits(results: Iterable[SearchResult]) -> None:
    for idx, result in enumerate(results, start=1):
        text = (result.get("text") or "").strip().replace("\n", " ")
        print(f"{idx:02d}. score={result.get('score'):.4f} text={text[:120]}")


def main() -> None:
    api_key = os.getenv("K2_API_KEY")
    if not api_key:
        raise SystemExit("K2_API_KEY is required")

    client = Knowledge2(
        api_host=os.getenv("K2_BASE_URL", "https://api.knowledge2.ai"),
        api_key=api_key,
    )
    idempotency_suffix = os.getenv("K2_IDEMPOTENCY_SUFFIX", uuid.uuid4().hex[:8])

    def _key(base: str) -> str:
        return f"{base}-{idempotency_suffix}"

    project_id = os.getenv("K2_PROJECT_ID")
    if not project_id:
        project = client.create_project("knowledge2-demo")
        project_id = project["id"]

    corpus = client.create_corpus(
        project_id,
        "knowledge2-demo-corpus",
        description="Sample corpus for the Knowledge2 end-to-end lifecycle.",
    )
    corpus_id = corpus["id"]

    docs = [
        {
            "source_uri": "doc://overview",
            "raw_text": "Knowledge2 organizes knowledge into projects and corpora. Documents are chunked into passages that can be indexed for search. Stable source_uris let you update content without duplicates.",
            "metadata": {"topic": "overview", "product": "knowledge2"},
        },
        {
            "source_uri": "doc://ingestion",
            "raw_text": "Batch ingestion accepts documents with source_uri, raw_text, and optional metadata. Use idempotency keys to prevent duplicate ingest jobs. Upload in batches to stay within API limits.",
            "metadata": {"topic": "ingestion", "product": "knowledge2"},
        },
        {
            "source_uri": "doc://indexing",
            "raw_text": "Dense indexes capture semantic similarity while sparse indexes capture keyword matches. Building both enables hybrid retrieval. Rebuild indexes after large content updates.",
            "metadata": {"topic": "indexing", "product": "knowledge2"},
        },
        {
            "source_uri": "doc://hybrid-search",
            "raw_text": "Hybrid retrieval blends dense and sparse scores using RRF or weighted fusion. Adjust dense_weight and sparse_weight to balance semantics vs exact terms. You can request scores and provenance in the response.",
            "metadata": {"topic": "search", "product": "knowledge2"},
        },
        {
            "source_uri": "doc://tuning",
            "raw_text": "Tuning runs train a better embedding model from query-document pairs. Training data can be auto-built or uploaded as JSONL. Successful runs can be promoted to a deployable model.",
            "metadata": {"topic": "tuning", "product": "knowledge2"},
        },
        {
            "source_uri": "doc://deployments",
            "raw_text": "Deployments attach a tuned model to a corpus and optionally trigger reindexing. Track the reindex job until it succeeds. Once complete, searches use the tuned model.",
            "metadata": {"topic": "deployments", "product": "knowledge2"},
        },
        {
            "source_uri": "doc://evaluation",
            "raw_text": "Evaluation runs compute metrics like nDCG, recall, and MRR on labeled data. Compare baseline and tuned models before promotion. Keep eval sets representative of real queries.",
            "metadata": {"topic": "evaluation", "product": "knowledge2"},
        },
        {
            "source_uri": "doc://security",
            "raw_text": "API keys authenticate requests and can be rotated without downtime. Admin tokens are required for org bootstrap and should be stored securely. Audit logs and usage endpoints help with governance.",
            "metadata": {"topic": "security", "product": "knowledge2"},
        },
    ]
    ingest = client.upload_documents_batch(
        corpus_id,
        docs,
        idempotency_key=_key("demo-ingest-1"),
        wait=False,
    )
    print("Ingest job:", ingest["job_id"])
    _wait_for_job(client, ingest["job_id"])

    index_job = client.build_indexes(
        corpus_id,
        dense=True,
        sparse=True,
        mode="full",
        idempotency_key=_key("demo-index-1"),
        wait=False,
    )
    print("Index build job:", index_job["job_id"])
    _wait_for_job(client, index_job["job_id"])

    baseline = client.search(
        corpus_id,
        "How does hybrid retrieval blend dense and sparse signals?",
        top_k=5,
        hybrid={
            "enabled": True,
            "fusion_mode": "rrf",
            "rrf_k": 60,
            "dense_weight": 0.6,
            "sparse_weight": 0.4,
        },
        return_config={"include_text": True, "include_scores": True, "include_provenance": True},
    )
    print("Baseline hybrid results:")
    _print_hits(baseline["results"])

    training_build = client.build_training_data(
        corpus_id,
        idempotency_key=_key("demo-training-data-1"),
    )
    print("Training data build job:", training_build["job_id"])
    _wait_for_job(client, training_build["job_id"])

    tuning_run = client.create_tuning_run(
        corpus_id,
        idempotency_key=_key("demo-tuning-1"),
    )

    print("Tuning run:", tuning_run["run_id"])
    run = _wait_for_tuning_run(client, tuning_run["run_id"])
    if run.get("status") != "succeeded":
        raise SystemExit(f"Tuning run failed with status {run.get('status')}")

    try:
        promoted = client.promote_tuning_run(tuning_run["run_id"])
    except Knowledge2Error as exc:
        raise SystemExit(f"Promotion failed: {exc}") from exc

    model_id = promoted["model_id"]
    deployment = client.create_deployment(corpus_id, model_id, reindex=True)
    reindex_job_id = deployment.get("reindex_job_id")
    if reindex_job_id:
        print("Reindex job:", reindex_job_id)
        _wait_for_job(client, reindex_job_id)

    tuned = client.search(
        corpus_id,
        "Explain hybrid retrieval in Knowledge2.",
        top_k=5,
        hybrid={
            "enabled": True,
            "fusion_mode": "rrf",
            "rrf_k": 60,
            "dense_weight": 0.5,
            "sparse_weight": 0.5,
        },
        return_config={"include_text": True, "include_scores": True, "include_provenance": True},
    )
    print("Tuned hybrid results:")
    _print_hits(tuned["results"])

    print("Eval runs will be generated automatically after tuning completes.")


if __name__ == "__main__":
    main()
