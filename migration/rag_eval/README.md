# RAG Evaluation (Local vs K2)

This folder contains side-by-side evaluation tooling for Bill47 migration quality:

- Retrieval-only (URL-level baseline): `run_retrieval_eval.py`
- Retrieval-only with golden chunks: `generate_golden_chunks.py` + `run_golden_retrieval_eval.py`
- End-to-end answer quality with RAGAS: `run_ragas_e2e_eval.py`

All evaluators are designed to compare `local` and `k2` on the same query set.

## Prerequisites

- Local Postgres running (default `postgresql://vancity:vancity_dev@localhost:5432/vancity_lens`)
- Env vars:
  - `K2_API_HOST`, `K2_API_KEY`, `K2_CORPUS_ID`
  - `ANTHROPIC_API_KEY`, `COHERE_API_KEY` (required for RAGAS E2E)
- Python deps in `.venv` include `ragas`, `langchain-anthropic`, `langchain-cohere`

Example:

```bash
set -a && source .env && set +a
export K2_API_HOST="https://api-dev.knowledge2.ai/"
export K2_CORPUS_ID="vancity"
```

## 1) Generate Golden Chunk Dataset

Creates shared `(query, expected_url, golden_anchor/chunk)` rows filtered to local∩K2 URL overlap.

```bash
python3 migration/rag_eval/generate_golden_chunks.py --n-queries 150
```

Output:
- `migration/rag_eval/output/<ts>/golden_chunks.jsonl`
- `migration/rag_eval/output/<ts>/golden_chunks_summary.md`

## 2) Retrieval-Only Eval with Golden Chunks

Measures both:
- URL metrics: recall@K + MRR@K
- Golden chunk metrics: expected URL + chunk content match

```bash
python3 migration/rag_eval/run_golden_retrieval_eval.py \
  --golden-jsonl migration/rag_eval/output/<ts>/golden_chunks.jsonl \
  --top-k 10 \
  --n-queries 120 \
  --local-mode sparse
```

Output:
- `golden_retrieval_results.jsonl`
- `golden_retrieval_summary.md`

## 3) RAGAS End-to-End Eval (Fair Local vs K2)

Runs full chat generation for each backend and scores with RAGAS:
- `faithfulness`
- `answer_relevancy`
- `llm_context_precision_without_reference`
- `context_recall`

Fairness controls:
- same golden query set
- same runtime generation path (`handle_chat`)
- same RAGAS evaluator LLM/embeddings
- only paired-success rows scored

```bash
python3 migration/rag_eval/run_ragas_e2e_eval.py \
  --golden-jsonl migration/rag_eval/output/<ts>/golden_chunks.jsonl \
  --n-queries 25 \
  --ragas-model claude-3-5-haiku-20241022
```

Output:
- `ragas_e2e_raw_results.jsonl`
- `ragas_local_scores.jsonl`
- `ragas_k2_scores.jsonl`
- `ragas_e2e_summary.md`

## Optional: Baseline URL-Level Retrieval Eval

```bash
python3 migration/rag_eval/run_retrieval_eval.py --top-k 10 --n-queries 100
```

## Shadow Validation Logs

If runtime shadow validation is enabled (`K2_SHADOW_VALIDATE=true`), summarize logs with:

```bash
python3 migration/rag_eval/parse_shadow_validate_logs.py path/to/api.jsonl --out shadow-summary.md
```
