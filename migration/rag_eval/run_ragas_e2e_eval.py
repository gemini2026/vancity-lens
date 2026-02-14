#!/usr/bin/env python3
"""Run fair end-to-end RAGAS evaluation for local vs K2 backends.

Fairness rules enforced by this harness:
- Same query set (from one golden dataset file)
- Same generation path (`api.intelligence.chat.handle_chat`)
- Same evaluator metrics, evaluator model, embeddings, and run config
- Only samples that succeed for BOTH backends are scored
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from langchain_anthropic import ChatAnthropic  # noqa: E402
from langchain_cohere import CohereEmbeddings  # noqa: E402
from ragas import evaluate  # noqa: E402
from ragas.dataset_schema import EvaluationDataset, SingleTurnSample  # noqa: E402
from ragas.metrics import (  # noqa: E402
    Faithfulness,
    LLMContextPrecisionWithoutReference,
    LLMContextRecall,
    ResponseRelevancy,
)
from ragas.run_config import RunConfig  # noqa: E402

from api.intelligence.chat import handle_chat  # noqa: E402
from api.intelligence.retrieval_backend import retrieve_document_chunks  # noqa: E402


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def _search_mode(anthropic_api_key: str, cohere_api_key: str) -> str:
    if anthropic_api_key and cohere_api_key:
        return "full"
    if anthropic_api_key:
        return "partial"
    return "demo"


def _load_golden_rows(path: Path, *, n_queries: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            row = json.loads(raw)
            query = str(row.get("query") or "").strip()
            expected_url = _normalize_url(str(row.get("expected_url") or ""))
            if not query or not expected_url:
                continue
            rows.append(
                {
                    "id": row.get("id"),
                    "query": query,
                    "expected_url": expected_url,
                    "expected_title": row.get("expected_title"),
                    "reference": str(row.get("golden_anchor_text") or row.get("golden_chunk_text") or "").strip(),
                }
            )
            if len(rows) >= n_queries:
                break
    return rows


async def _get_db_pool(db_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(db_url, min_size=1, max_size=5)


async def _run_backend_sample(
    db_pool: asyncpg.Pool,
    *,
    backend: str,
    query: str,
    anthropic_api_key: str,
    cohere_api_key: str,
) -> dict[str, Any]:
    os.environ["RAG_BACKEND"] = backend
    os.environ["K2_SHADOW_VALIDATE"] = "false"
    # Fairness guard: never allow K2 evaluation rows to silently use local fallback.
    if backend == "k2":
        os.environ["K2_FALLBACK_TO_LOCAL"] = "false"

    mode = _search_mode(anthropic_api_key, cohere_api_key)
    retrieval_t0 = time.perf_counter()
    chunks = await retrieve_document_chunks(
        db_pool=db_pool,
        query=query,
        search_mode=mode,
        cohere_api_key=cohere_api_key or None,
        neighborhood_filter=None,
        date_from=None,
        date_to=None,
    )
    retrieval_ms = (time.perf_counter() - retrieval_t0) * 1000.0

    generation_t0 = time.perf_counter()
    response = await handle_chat(
        db_pool=db_pool,
        query=query,
        anthropic_api_key=anthropic_api_key or None,
        cohere_api_key=cohere_api_key or None,
        session_id=str(uuid.uuid4()),
        neighborhood_filter=None,
        date_from=None,
        date_to=None,
    )
    generation_ms = (time.perf_counter() - generation_t0) * 1000.0

    contexts = [str(chunk.get("chunk_text") or "").strip() for chunk in chunks if str(chunk.get("chunk_text") or "").strip()]

    return {
        "answer": response.answer,
        "contexts": contexts[:10],
        "citations": [c.document_url for c in response.citations],
        "retrieval_ms": retrieval_ms,
        "generation_ms": generation_ms,
        "chunk_count": len(contexts),
    }


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
        if math.isnan(parsed):
            return None
        return parsed
    except Exception:
        return None


def _aggregate_metric_mean(rows: list[dict[str, Any]], metric_name: str) -> float:
    values = [_safe_float(row.get(metric_name)) for row in rows]
    clean = [v for v in values if v is not None]
    if not clean:
        return 0.0
    return float(statistics.mean(clean))


def _to_jsonable_rows(df: Any, sample_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = df.to_dict(orient="records")
    out: list[dict[str, Any]] = []
    for idx, record in enumerate(records):
        base = sample_rows[idx] if idx < len(sample_rows) else {}
        merged = dict(base)
        for key, value in record.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                merged[key] = value
            else:
                merged[key] = str(value)
        out.append(merged)
    return out


async def main() -> int:
    parser = argparse.ArgumentParser(description="RAGAS E2E eval for local vs K2.")
    parser.add_argument("--golden-jsonl", required=True, help="Path to golden dataset JSONL.")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL") or "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens",
        help="Postgres URL for chat runtime.",
    )
    parser.add_argument("--n-queries", type=int, default=25, help="Max rows to attempt from golden dataset.")
    parser.add_argument(
        "--ragas-model",
        default=os.environ.get("RAGAS_ANTHROPIC_MODEL") or "claude-3-5-haiku-20241022",
        help="Anthropic model used as RAGAS evaluator LLM.",
    )
    parser.add_argument(
        "--ragas-embed-model",
        default=os.environ.get("RAGAS_COHERE_EMBED_MODEL") or "embed-english-v3.0",
        help="Cohere embedding model used by RAGAS evaluator.",
    )
    parser.add_argument(
        "--ragas-max-workers",
        type=int,
        default=4,
        help="RAGAS evaluator concurrency.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Default: migration/rag_eval/output/<timestamp>/",
    )
    args = parser.parse_args()

    anthropic_api_key = _require_env("ANTHROPIC_API_KEY")
    cohere_api_key = _require_env("COHERE_API_KEY")
    # Validate K2 env eagerly so failures happen before long local runs.
    _require_env("K2_API_KEY")
    _require_env("K2_CORPUS_ID")

    rows = _load_golden_rows(Path(args.golden_jsonl), n_queries=max(1, int(args.n_queries)))
    if not rows:
        raise SystemExit("No valid rows loaded from golden dataset.")

    out_dir = Path(args.output_dir) if args.output_dir else Path("migration/rag_eval/output") / _now_ts()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_results_path = out_dir / "ragas_e2e_raw_results.jsonl"
    local_scores_path = out_dir / "ragas_local_scores.jsonl"
    k2_scores_path = out_dir / "ragas_k2_scores.jsonl"
    summary_path = out_dir / "ragas_e2e_summary.md"

    pool = await _get_db_pool(args.db_url)
    try:
        paired_rows: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        with raw_results_path.open("w", encoding="utf-8") as raw_out:
            for row in rows:
                query = row["query"]
                item_id = row.get("id")

                item_record: dict[str, Any] = {
                    "id": item_id,
                    "query": query,
                    "expected_url": row.get("expected_url"),
                    "expected_title": row.get("expected_title"),
                    "reference": row.get("reference"),
                }

                local_error = None
                k2_error = None
                local_payload: dict[str, Any] | None = None
                k2_payload: dict[str, Any] | None = None

                try:
                    local_payload = await _run_backend_sample(
                        pool,
                        backend="local",
                        query=query,
                        anthropic_api_key=anthropic_api_key,
                        cohere_api_key=cohere_api_key,
                    )
                    item_record["local"] = local_payload
                except Exception as exc:
                    local_error = str(exc)
                    item_record["local_error"] = local_error

                try:
                    k2_payload = await _run_backend_sample(
                        pool,
                        backend="k2",
                        query=query,
                        anthropic_api_key=anthropic_api_key,
                        cohere_api_key=cohere_api_key,
                    )
                    item_record["k2"] = k2_payload
                except Exception as exc:
                    k2_error = str(exc)
                    item_record["k2_error"] = k2_error

                raw_out.write(json.dumps(item_record, ensure_ascii=True) + "\n")

                if local_payload and k2_payload and row.get("reference"):
                    paired_rows.append(item_record)
                else:
                    failures.append(
                        {
                            "id": item_id,
                            "query": query,
                            "local_error": local_error,
                            "k2_error": k2_error,
                            "missing_reference": not bool(row.get("reference")),
                        }
                    )

        if not paired_rows:
            raise SystemExit("No paired samples succeeded for both backends.")

        eval_llm = ChatAnthropic(model=args.ragas_model, temperature=0, api_key=anthropic_api_key)
        eval_embeddings = CohereEmbeddings(model=args.ragas_embed_model, cohere_api_key=cohere_api_key)

        metrics = [
            Faithfulness(),
            ResponseRelevancy(),
            LLMContextPrecisionWithoutReference(),
            LLMContextRecall(),
        ]
        run_config = RunConfig(max_workers=max(1, int(args.ragas_max_workers)), timeout=180, max_retries=2)

        local_samples: list[SingleTurnSample] = []
        k2_samples: list[SingleTurnSample] = []
        local_base_rows: list[dict[str, Any]] = []
        k2_base_rows: list[dict[str, Any]] = []

        for row in paired_rows:
            reference = str(row["reference"])
            local_payload = row["local"]
            k2_payload = row["k2"]

            local_samples.append(
                SingleTurnSample(
                    user_input=str(row["query"]),
                    response=str(local_payload["answer"]),
                    retrieved_contexts=list(local_payload["contexts"]),
                    reference=reference,
                )
            )
            k2_samples.append(
                SingleTurnSample(
                    user_input=str(row["query"]),
                    response=str(k2_payload["answer"]),
                    retrieved_contexts=list(k2_payload["contexts"]),
                    reference=reference,
                )
            )
            local_base_rows.append(
                {
                    "id": row.get("id"),
                    "query": row.get("query"),
                    "expected_url": row.get("expected_url"),
                    "backend": "local",
                    "retrieval_ms": local_payload.get("retrieval_ms"),
                    "generation_ms": local_payload.get("generation_ms"),
                    "chunk_count": local_payload.get("chunk_count"),
                }
            )
            k2_base_rows.append(
                {
                    "id": row.get("id"),
                    "query": row.get("query"),
                    "expected_url": row.get("expected_url"),
                    "backend": "k2",
                    "retrieval_ms": k2_payload.get("retrieval_ms"),
                    "generation_ms": k2_payload.get("generation_ms"),
                    "chunk_count": k2_payload.get("chunk_count"),
                }
            )

        local_dataset = EvaluationDataset(samples=local_samples)
        k2_dataset = EvaluationDataset(samples=k2_samples)

        local_result = evaluate(
            dataset=local_dataset,
            metrics=metrics,
            llm=eval_llm,
            embeddings=eval_embeddings,
            run_config=run_config,
            show_progress=True,
            raise_exceptions=False,
        )
        k2_result = evaluate(
            dataset=k2_dataset,
            metrics=metrics,
            llm=eval_llm,
            embeddings=eval_embeddings,
            run_config=run_config,
            show_progress=True,
            raise_exceptions=False,
        )

        local_rows = _to_jsonable_rows(local_result.to_pandas(), local_base_rows)
        k2_rows = _to_jsonable_rows(k2_result.to_pandas(), k2_base_rows)

        with local_scores_path.open("w", encoding="utf-8") as out:
            for row in local_rows:
                out.write(json.dumps(row, ensure_ascii=True) + "\n")
        with k2_scores_path.open("w", encoding="utf-8") as out:
            for row in k2_rows:
                out.write(json.dumps(row, ensure_ascii=True) + "\n")

        metric_names = [
            "faithfulness",
            "answer_relevancy",
            "llm_context_precision_without_reference",
            "context_recall",
        ]

        local_means = {metric: _aggregate_metric_mean(local_rows, metric) for metric in metric_names}
        k2_means = {metric: _aggregate_metric_mean(k2_rows, metric) for metric in metric_names}
        deltas = {metric: (k2_means[metric] - local_means[metric]) for metric in metric_names}

        local_retrieval_latencies = [float(row["retrieval_ms"]) for row in local_base_rows if row.get("retrieval_ms") is not None]
        k2_retrieval_latencies = [float(row["retrieval_ms"]) for row in k2_base_rows if row.get("retrieval_ms") is not None]
        local_generation_latencies = [float(row["generation_ms"]) for row in local_base_rows if row.get("generation_ms") is not None]
        k2_generation_latencies = [float(row["generation_ms"]) for row in k2_base_rows if row.get("generation_ms") is not None]
        local_context_chars = sum(len(str(s.response or "")) + sum(len(c) for c in (s.retrieved_contexts or [])) for s in local_samples)
        k2_context_chars = sum(len(str(s.response or "")) + sum(len(c) for c in (s.retrieved_contexts or [])) for s in k2_samples)

        summary_lines = [
            "# RAGAS E2E Eval Summary (Local vs K2)",
            "",
            f"- Timestamp (UTC): `{datetime.now(timezone.utc).isoformat()}`",
            f"- Attempted queries: `{len(rows)}`",
            f"- Paired successful samples (scored): `{len(paired_rows)}`",
            f"- Skipped/failed samples: `{len(failures)}`",
            f"- RAGAS evaluator model: `{args.ragas_model}`",
            f"- RAGAS embedding model: `{args.ragas_embed_model}`",
            "",
            "## Fairness Controls",
            "",
            "- Same golden query set for both backends",
            "- Same chat runtime (`handle_chat`) and same API keys",
            "- Same RAGAS metrics and evaluator config",
            "- Only paired-success samples included in scoring",
            "",
            "## Mean RAGAS Scores",
            "",
            f"- Local faithfulness: `{local_means['faithfulness']:.3f}`",
            f"- K2 faithfulness: `{k2_means['faithfulness']:.3f}`",
            f"- Delta (K2-local): `{deltas['faithfulness']:+.3f}`",
            "",
            f"- Local answer_relevancy: `{local_means['answer_relevancy']:.3f}`",
            f"- K2 answer_relevancy: `{k2_means['answer_relevancy']:.3f}`",
            f"- Delta (K2-local): `{deltas['answer_relevancy']:+.3f}`",
            "",
            f"- Local llm_context_precision_without_reference: `{local_means['llm_context_precision_without_reference']:.3f}`",
            f"- K2 llm_context_precision_without_reference: `{k2_means['llm_context_precision_without_reference']:.3f}`",
            f"- Delta (K2-local): `{deltas['llm_context_precision_without_reference']:+.3f}`",
            "",
            f"- Local context_recall: `{local_means['context_recall']:.3f}`",
            f"- K2 context_recall: `{k2_means['context_recall']:.3f}`",
            f"- Delta (K2-local): `{deltas['context_recall']:+.3f}`",
            "",
            "## Runtime",
            "",
            f"- Avg local retrieval latency (ms): `{_mean(local_retrieval_latencies):.1f}`",
            f"- Avg K2 retrieval latency (ms): `{_mean(k2_retrieval_latencies):.1f}`",
            f"- Avg local generation latency (ms): `{_mean(local_generation_latencies):.1f}`",
            f"- Avg K2 generation latency (ms): `{_mean(k2_generation_latencies):.1f}`",
            "",
            "## Approx Evaluated Text Volume",
            "",
            f"- Local evaluated chars (contexts + responses): `{local_context_chars:,}` (~`{local_context_chars / 4.0:,.0f}` tokens)",
            f"- K2 evaluated chars (contexts + responses): `{k2_context_chars:,}` (~`{k2_context_chars / 4.0:,.0f}` tokens)",
            "",
            "## Artifacts",
            "",
            f"- Raw paired attempts: `{raw_results_path}`",
            f"- Local RAGAS scores: `{local_scores_path}`",
            f"- K2 RAGAS scores: `{k2_scores_path}`",
            f"- Summary: `{summary_path}`",
            "",
        ]

        if failures:
            summary_lines.extend(
                [
                    "## Failure Samples (first 10)",
                    "",
                ]
            )
            for failure in failures[:10]:
                summary_lines.append(
                    f"- id `{failure.get('id')}` query=`{str(failure.get('query') or '')[:100]}` "
                    f"local_error=`{failure.get('local_error')}` k2_error=`{failure.get('k2_error')}` "
                    f"missing_reference=`{failure.get('missing_reference')}`"
                )
            summary_lines.append("")

        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
        print(str(summary_path))
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
