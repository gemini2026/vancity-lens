# Bill47 RAG Evaluation Report (Local Postgres vs K2)

Date: 2026-02-12

This report documents what data is loaded, where chunking happens, what we evaluated, and the current evaluation results comparing:

- **Local** retrieval (Postgres BM25 and optional hybrid pgvector+BM25)
- **K2** retrieval (Knowledge2 corpus + hybrid search via K2 SDK)

This is primarily a **retrieval evaluation** (did we retrieve the right source URL in top-K), not a full answer-quality evaluation.

## Executive Summary

- K2 corpus is populated and indexed (`dense_status=ready`, `sparse_status=ready`) and the app runs end-to-end with `RAG_BACKEND=k2`.
- On our URL-level retrieval benchmark (document-derived eval set), **K2 retrieval outperforms local retrieval** on both recall@10 and MRR@10.
- **Latency tradeoff**: K2 retrieval adds ~0.5-0.6s average retrieval latency (network call) vs local BM25 at a few ms.
- We did **not** use “golden chunks” (human-labeled chunk relevance set). Ground truth is document URL presence in top-K.

## What Was Migrated (Scope)

- Retrieval layer is feature-flagged:
  - `RAG_BACKEND=local`: retrieve chunks from local Postgres (BM25/hybrid).
  - `RAG_BACKEND=k2`: retrieve chunks from K2 via `sdk.Knowledge2.search(...)`.
- Generation/reporting/UI flows remain in Bill47:
  - `/api/v1/intel/chat` still builds context and calls Anthropic (if configured) the same way.
  - Citations are mapped from retrieved chunks (local or K2).

Key code:
- `api/intelligence/retrieval_backend.py` (backend switch + shadow validation)
- `api/intelligence/k2_client.py` (K2 search wrapper + result normalization)
- `migration/k2_ingest_sources.py` (URL-based ingestion into K2)
- `migration/rag_eval/run_retrieval_eval.py` (evaluation harness)

## Data Loaded (Local vs K2)

### Local Postgres (current)

Source: local DB at `postgresql://vancity:vancity_dev@localhost:5432/vancity_lens`.

- Documents: `293`
- Documents with chunks: `288`
- Chunks: `753`
- Chunks with embeddings (pgvector): `119`
- Chunks without embeddings: `634`
- Intelligence signals: `155`

Chunk text volume (local):
- Total chunk chars: `1,329,504`
- Avg chunk length: `1,765.6` chars (p50 `1,558`, max `5,599`)
- Approx tokens in stored chunk text: `~332k` (rough estimate: `chars / 4`)

Top local `documents.source_type` (counts):
- `syc_development_application_page`: 146
- `syc_development_application_document`: 79
- `council_minutes`: 20
- `rezoning_application`: 18
- `news`: 12
- `dpb_minutes`: 8
- `provincial_legislation`: 4

Notes:
- Many local chunks are BM25-only (`embedding IS NULL`). This is expected if documents were ingested without `--process`, or if we used chunk backfill for evaluation.

### K2 Corpus (current)

Corpus: `name=vancity` (resolved id `bb158585-b616-4aed-ab63-55604093a3b8`)

- Documents: `528` (all `status=indexed`)
- Chunks: `4,631`
- Corpus status: `degraded` (dense/sparse indexes are ready). This is likely due to historical ingestion failures; see “Corpus Health” below.

Document content types (top):
- `application/pdf`: 311
- `text/html; charset=utf-8` (and variants): ~214

Top K2 `metadata.source_type` (counts):
- `syc_development_application_document`: 272
- `syc_development_application_page`: 151
- `syc_plan_document`: 30
- `news`: 32
- `web_search`: 32
- `provincial_legislation`: 4

Document bytes (K2):
- Total `size_bytes`: `477,024,089` (avg `903,454` bytes per document)

Chunk text volume (K2):
- Total chunk chars: `5,558,408`
- Avg chunk length: `1,200.3` chars (p50 `1,176`, p90 `1,953`, p95 `2,053`, max `2,537`)
- Approx tokens in stored chunk text: `~1.39M` (rough estimate: `chars / 4`)

## Where Chunks Are Created

### Local chunk creation (Bill47)

Local pipeline stores text in Postgres and chunking happens in the Bill47 codebase:

- URL discovery + scraping: `scripts/ingest_sources.py` + `api/intelligence/scraper_url.py`
- Document storage: `documents` table (`raw_text`, `source_url`, metadata)
- Chunking: `api/intelligence/chunker.py` producing rows in `document_chunks`
- Embeddings (optional): Cohere (pgvector column populated when processed)

### K2 chunk creation

K2 handles parsing + chunking + embeddings on ingestion:

- We ingest URLs via `Knowledge2.ingest_urls(...)`.
- Retrieval uses `Knowledge2.search(...)` and returns chunks with text + provenance metadata.
- Bill47 does **not** run docling/semchunk for K2 retrieval.

## “Golden Chunks”: Used or Not?

Not used.

We do **not** currently have a human-labeled dataset that says “for query Q, these chunks are relevant.” The evaluation ground truth is URL-level (document identity), derived from local DB records.

## What We Evaluated

### Evaluation type

Retrieval-only evaluation:
- No LLM answer generation
- No LLM-as-judge scoring
- Metrics computed from retrieved URLs (document-level)

### Eval set construction

Primary eval set: `documents`-derived.

For each local document:
1. Choose the longest available local chunk (`document_chunks`) for that document.
2. Extract up to 8 distinctive alphabetic tokens from that chunk to build a query string.
3. Set `expected_url = documents.source_url`.
4. Filter to items whose `expected_url` is present in the K2 corpus (URL intersection filter).

Resulting sizes (latest run):
- Local docs with chunks available: `288`
- After K2 URL intersection filter: `231`
- Queries evaluated: `230`
- Query length: avg `~8` words (avg `~65` chars)

Secondary eval set: `signals`-derived (realistic), but currently too small after intersection filtering.

### Retrieval backends measured

- Local sparse: `api.intelligence.embeddings.sparse_search` (BM25/tsvector)
- Local hybrid: `api.intelligence.embeddings.hybrid_search` (pgvector + BM25 with RRF fusion)
  - In eval we run **without rerank** (`use_rerank=False`) to keep costs down.
  - Hybrid eval requires `COHERE_API_KEY` for query embeddings.
- K2: `sdk.Knowledge2.search(...)`

### Metrics

For each query:
- **Recall@K**: is `expected_url` in the top-K unique URLs?
- **MRR@K**: `1/rank` of the first occurrence of `expected_url` (else 0).
- **Overlap@K**: number of shared URLs between local and K2 top-K lists.
- **Latency**: wall time to execute retrieval call (ms).

Artifacts:
- Per-query rows: `migration/rag_eval/output/<run>/results.jsonl`
- Aggregate summary: `migration/rag_eval/output/<run>/summary.md`

## Results

### Primary run (documents eval, local sparse vs K2)

Summary: `migration/rag_eval/output/20260212-164739/summary.md`

- Queries: `230` (post intersection filter)
- Top-K: `10`
- Local recall@10: `0.804`
- K2 recall@10: `0.948`
- Local MRR@10: `0.793`
- K2 MRR@10: `0.918`
- Avg overlap@10 (URLs): `0.79`
- Avg local latency: `3.8ms`
- Avg K2 latency: `602.2ms`

### Hybrid run (documents eval, local hybrid vs K2)

Summary: `migration/rag_eval/output/20260212-165021/summary.md`

- Queries: `100`
- Top-K: `10`
- Local recall@10: `0.780`
- K2 recall@10: `0.910`
- Local MRR@10: `0.569`
- K2 MRR@10: `0.872`
- Avg overlap@10 (URLs): `0.80`
- Avg local latency: `191.8ms` (includes Cohere query embedding call)
- Avg K2 latency: `531.0ms`

### Signals run (too small to trust)

Summary: `migration/rag_eval/output/20260212-165155/summary.md`

Only `6` items after URL intersection filtering; treat as informational only.

## Tokens / Cost Accounting

### What we can say precisely

- The retrieval evaluation scripts (`migration/rag_eval/run_retrieval_eval.py`) **do not call Anthropic**, so Anthropic tokens used for these eval runs are **0**.
- Local hybrid eval does call Cohere for query embeddings (per query). We did **not** instrument Cohere usage/cost in this harness.
- K2 usage/cost is not instrumented in this harness (K2 handles chunking/indexing internally).

### Corpus “token volume” (approx)

We estimate stored retrieval text volume by `sum(len(chunk_text)) / 4`:

- Local chunks: `1,329,504 chars` → `~332k tokens`
- K2 chunks: `5,558,408 chars` → `~1.39M tokens`

This is **not billing token usage**; it is an approximate measure of corpus text size.

## Corpus Health (K2)

K2 corpus status currently reports `status=degraded` even though:
- `dense_status=ready`
- `sparse_status=ready`
- all documents show `status=indexed`

We previously observed a single `.docx` document with `status=failed`; deleting it moved corpus `status` from `error` → `degraded`.

Action:
- Ask K2 to clarify what `degraded` means and whether it affects retrieval quality/availability.

## Local RAG Architecture (Text Diagram)

```text
                +---------------------------+
User / UI  ---> | Next.js Frontend         |
                | (Intelligence tab)       |
                +------------+--------------+
                             |
                             v
                +---------------------------+
                | FastAPI                   |
                | POST /api/v1/intel/chat   |
                | api/intelligence/chat.py  |
                +------------+--------------+
                             |
                             v
                +---------------------------+
                | Retrieval Backend Switch  |
                | api/intelligence/         |
                | retrieval_backend.py      |
                +------+--------------------+
                       |
       +---------------+-------------------+
       |                                   |
       v                                   v
+---------------+                 +------------------+
| LOCAL (Postgres)|                 | K2 (Knowledge2) |
| sparse_search   |                 | Knowledge2.search|
| hybrid_search   |                 | + K2 chunking    |
+-------+---------+                 +--------+---------+
        |                                    |
        v                                    v
  document_chunks rows                  K2 chunks (text + metadata)
  (chunk_text, tsvector, embedding?)          |
        |                                    |
        +------------------+-----------------+
                           v
                +---------------------------+
                | Context Builder           |
                | (chunks + signals)        |
                +------------+--------------+
                             |
                             v
                +---------------------------+
                | LLM Generation (optional) |
                | Anthropic (Claude)        |
                +------------+--------------+
                             |
                             v
                +---------------------------+
                | Response + Citations      |
                | sessions stored in DB     |
                +---------------------------+

Ingestion (Local):
  pipeline/sources.yaml -> scripts/ingest_sources.py -> documents -> chunker -> document_chunks
  (optional) extractor -> intelligence_signals
```

## Gaps / Next Improvements (Evaluation)

- Create a small **golden set** (human-labeled relevance per query) to measure chunk-level precision/recall.
- Add **answer-quality evaluation** (LLM-as-judge) comparing K2 vs local end-to-end outputs.
- Increase overlap for `signals` eval set by ingesting more of the local-only sources into K2 (or regenerate signals from K2-backed corpora).

