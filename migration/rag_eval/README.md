# RAG Evaluation (Local vs K2)

This folder contains a pragmatic retrieval evaluation harness to compare Bill47's
current local Postgres hybrid/sparse retrieval against K2-backed retrieval.

## What It Measures

- Recall@K for an eval set derived from either:
  - `documents` (default): query = `documents.title` (or URL fallback)
  - `intelligence_signals` (optional): query = `headline`/`summary`
- MRR (Mean Reciprocal Rank) over the same set.
- Overlap@K between local and K2 retrieved document URLs.
- Retrieval latency (local vs K2).

Notes:
- This is a *retrieval* evaluation (not full answer quality). You can layer
  LLM-as-judge later if needed.
- We filter the eval set to the URL intersection between local DB and K2 corpus
  to avoid penalizing either backend for missing documents.

## Shadow Validation Logs

If you enable runtime shadow validation (`K2_SHADOW_VALIDATE=true`), the API will
emit JSON log lines with message `k2_shadow_validate`. You can summarize those
logs with:

```bash
python3 migration/rag_eval/parse_shadow_validate_logs.py path/to/api.jsonl --out shadow-summary.md
```

## Run

The script needs:
- local Postgres running (default `postgresql://vancity:vancity_dev@localhost:5432/vancity_lens`)
- K2 credentials (env): `K2_API_HOST`, `K2_API_KEY`, `K2_CORPUS_ID`

Example (recommended): source `.env` for Cohere/Anthropic (optional), then set K2 vars:

```bash
set -a && source .env && set +a
export K2_API_HOST="https://api-dev.knowledge2.ai/"
export K2_API_KEY="***"
export K2_CORPUS_ID="vancity"   # name or UUID

python3 migration/rag_eval/run_retrieval_eval.py --top-k 10 --n-queries 100
```

Outputs are written under `migration/rag_eval/output/<timestamp>/`.

If you want the more realistic signals-based eval set:

```bash
python3 migration/rag_eval/run_retrieval_eval.py --eval-set signals --top-k 10 --n-queries 100
```
