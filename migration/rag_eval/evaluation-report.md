# Bill47 Comprehensive RAG Evaluation Report (Local vs K2)

Date: 2026-02-12  
Branch: `k2-migration`

## Scope

This rerun covers the two requested evaluation types:

1. **RAGAS end-to-end evaluation** (full chat generation) comparing `local` vs `k2`.
2. **Retrieval-only evaluation with golden chunks** created once and applied to both systems.

## Fairness Protocol

To keep comparisons fair:

- Same golden query set for both backends.
- Same chat pipeline for E2E (`api.intelligence.chat.handle_chat`).
- Same evaluator configuration for both backends (`ragas`, same evaluator model + embedding model).
- K2 fallback to local disabled during K2 E2E scoring (`K2_FALLBACK_TO_LOCAL=false`) to prevent contamination.
- Only paired-success rows included in RAGAS scoring.

## Data Snapshot

### Local Postgres

- Documents: `293`
- Documents with chunks: `288`
- Chunks: `753`
- Chunks with embeddings: `119`
- Chunks without embeddings: `634`
- Total chunk chars: `1,329,504` (~`332,376` tokens at chars/4 heuristic)

### K2 Corpus (`vancity`)

- Corpus ID: `bb158585-b616-4aed-ab63-55604093a3b8`
- Corpus status: `degraded` (`dense_status=ready`, `sparse_status=ready`)
- Documents: `528`
- Failed documents: `0`
- Total bytes: `477,024,089`
- Chunks: `4,631`
- Total chunk chars: `5,558,408` (~`1,389,602` tokens at chars/4 heuristic)

## Golden Chunk Dataset

Artifact: `migration/rag_eval/output/20260212-184055/golden_chunks.jsonl`

- Rows: `180` (180 unique expected URLs)
- Avg query length: `7.88` words
- Avg anchor length: `34.24` words
- Avg golden chunk length: `2,458.83` chars
- Total golden chunk chars: `442,589` (~`110,647` tokens)
- Filter: local docs/chunks intersected with K2 URLs

Golden-chunk hit rule used in retrieval eval:

- `expected_url` match AND
- (`golden_anchor_text` substring match OR token overlap >= `0.35`)

## Evaluation A: Retrieval-Only with Golden Chunks

### Run A1: local sparse vs K2

Artifact summary: `migration/rag_eval/output/20260212-184111/golden_retrieval_summary.md`

- Queries: `180`
- URL recall@10: local `0.800`, K2 `0.956` (delta `+0.156`)
- URL MRR@10: local `0.785`, K2 `0.928` (delta `+0.143`)
- Golden recall@10: local `0.800`, K2 `0.900` (delta `+0.100`)
- Golden MRR@10: local `0.784`, K2 `0.872` (delta `+0.088`)
- Avg latency: local `3.4ms`, K2 `589.5ms`
- URL overlap@10: `0.80`

Breakdown (`both / K2-only / local-only / none`):

- URL hit: `138 / 34 / 6 / 2`
- Golden hit: `130 / 32 / 14 / 4`

### Run A2: local hybrid vs K2

Artifact summary: `migration/rag_eval/output/20260212-184312/golden_retrieval_summary.md`

- Queries: `120`
- URL recall@10: local `0.800`, K2 `0.933` (delta `+0.133`)
- URL MRR@10: local `0.603`, K2 `0.897` (delta `+0.294`)
- Golden recall@10: local `0.800`, K2 `0.850` (delta `+0.050`)
- Golden MRR@10: local `0.602`, K2 `0.812` (delta `+0.210`)
- Avg latency: local `186.9ms`, K2 `532.8ms`
- URL overlap@10: `0.82`

Breakdown (`both / K2-only / local-only / none`):

- URL hit: `91 / 21 / 5 / 3`
- Golden hit: `83 / 19 / 13 / 5`

## Evaluation B: RAGAS End-to-End (Chat + Retrieval + Answer)

Artifact summary: `migration/rag_eval/output/20260212-184945/ragas_e2e_summary.md`

Run config:

- Attempted queries: `15`
- Paired successful (scored): `15`
- Evaluator LLM: `claude-3-5-haiku-20241022`
- Evaluator embedding model: `embed-english-v3.0`
- Metrics: `faithfulness`, `answer_relevancy`, `llm_context_precision_without_reference`, `context_recall`

### Mean Scores (with valid-count handling)

| Metric | Local mean | K2 mean | Delta (K2-local) | Valid rows (local/k2) |
|---|---:|---:|---:|---:|
| faithfulness | 0.791 | 0.703 | -0.088 | 15 / 15 |
| answer_relevancy | 0.151 | 0.196 | +0.045 | 15 / 15 |
| llm_context_precision_without_reference | 0.642 | 0.726 | +0.085 | 15 / 15 |
| context_recall | 0.786 | 0.756 | -0.030 | 14 / 15 |

Notes:

- One local `context_recall` row was NaN due a single RAGAS parser exception during metric execution; run continued with `raise_exceptions=false`.
- Raw paired E2E samples had no local/k2 runtime errors (`15/15` both successful).

### E2E Runtime

- Avg local retrieval latency: `467.0ms`
- Avg K2 retrieval latency: `664.1ms`
- Avg local generation latency: `9552.0ms`
- Avg K2 generation latency: `8277.7ms`

## Token / Text Volume Accounting

What we can report precisely from this run:

- Golden evaluation dataset text volume: `~110,647` tokens (chars/4 heuristic).
- RAGAS evaluated text volume:
  - Local contexts + responses: `284,859` chars (~`71,215` tokens)
  - K2 contexts + responses: `194,726` chars (~`48,682` tokens)

What is not fully instrumented:

- Exact Anthropic/Cohere billed token usage for generation and evaluator calls is not tracked in these scripts.
- K2 internal ingestion/indexing token usage is not exposed by this harness.

## Interpretation

- **Retrieval quality:** K2 is stronger on URL-level and golden-chunk retrieval across both sparse and hybrid local baselines.
- **Latency:** K2 retrieval remains slower than local retrieval due remote call overhead.
- **End-to-end quality (RAGAS):**
  - K2 leads on `answer_relevancy` and `llm_context_precision_without_reference`.
  - Local leads on `faithfulness` and `context_recall` in this 15-query sample.
  - Given sample size and one metric parse miss, treat E2E deltas as directional, not definitive.

## Artifacts Index

- Golden dataset summary: `migration/rag_eval/output/20260212-184055/golden_chunks_summary.md`
- Golden dataset rows: `migration/rag_eval/output/20260212-184055/golden_chunks.jsonl`
- Retrieval sparse summary: `migration/rag_eval/output/20260212-184111/golden_retrieval_summary.md`
- Retrieval sparse rows: `migration/rag_eval/output/20260212-184111/golden_retrieval_results.jsonl`
- Retrieval hybrid summary: `migration/rag_eval/output/20260212-184312/golden_retrieval_summary.md`
- Retrieval hybrid rows: `migration/rag_eval/output/20260212-184312/golden_retrieval_results.jsonl`
- RAGAS summary: `migration/rag_eval/output/20260212-184945/ragas_e2e_summary.md`
- RAGAS raw paired runs: `migration/rag_eval/output/20260212-184945/ragas_e2e_raw_results.jsonl`
- RAGAS local scores: `migration/rag_eval/output/20260212-184945/ragas_local_scores.jsonl`
- RAGAS K2 scores: `migration/rag_eval/output/20260212-184945/ragas_k2_scores.jsonl`
