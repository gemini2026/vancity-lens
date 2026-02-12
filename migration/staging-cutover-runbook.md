# Staging Cutover Runbook (Local -> K2 Retrieval)

This runbook is for switching a *staging* environment from local Postgres retrieval to K2 retrieval using the existing feature flag.

## Preconditions

- Staging has a working deploy pipeline (Cloud Run / k8s / VM) and you can change env vars.
- You have a K2 corpus populated with your sources and indexes built.
- You can roll back quickly by toggling an env var and redeploying.

## Required Env Vars (Staging)

- `RAG_BACKEND=k2`
- `K2_API_HOST=https://api-dev.knowledge2.ai` (or your K2 prod host)
- `K2_API_KEY=...` (secret)
- `K2_CORPUS_ID=vancity` (or UUID)
- `K2_TOP_K=10`
- `K2_TIMEOUT_SECONDS=20`
- `K2_FALLBACK_TO_LOCAL=true` (recommended for first soak period)

## Optional: Shadow Validation (Recommended During Soak)

Shadow validation runs a background local retrieval compare and emits structured logs. It does not change the user-facing response.

- `K2_SHADOW_VALIDATE=true`
- `K2_SHADOW_VALIDATE_SAMPLE_RATE=0.05`
- `K2_SHADOW_VALIDATE_LOCAL_MODE=sparse` (cheap) or `hybrid` (closer to local quality; requires Cohere key in env)
- `K2_SHADOW_VALIDATE_TOP_N=5`
- `K2_SHADOW_VALIDATE_MAX_CONCURRENCY=2`
- `K2_SHADOW_VALIDATE_TIMEOUT_SECONDS=8`

## Cutover Steps

1. Deploy to staging with `RAG_BACKEND=local` (baseline).
2. Run validation against staging in `local` mode:
   - `API_URL=https://<staging-host> bash migration/validate_k2_migration.sh --backend local --skip-pytest`
3. Switch staging env to `RAG_BACKEND=k2` (leave `K2_FALLBACK_TO_LOCAL=true` for first soak).
4. Deploy.
5. Run validation against staging in `k2` mode:
   - `API_URL=https://<staging-host> K2_API_HOST=... K2_API_KEY=... K2_CORPUS_ID=... bash migration/validate_k2_migration.sh --backend k2 --skip-pytest`

## Monitoring During Soak (24-72h)

Track:

- `/api/v1/intel/chat` error rate (5xx + upstream K2 timeouts).
- Latency deltas (K2 retrieval adds network round-trips; expect higher p50/p95 than local).
- Citation completeness (citations should have title + URL).
- Shadow logs (if enabled): `message=k2_shadow_validate`

To summarize JSON logs captured to a file:

```bash
python3 migration/rag_eval/parse_shadow_validate_logs.py path/to/api.jsonl --out shadow-summary.md
```

## Rollback Drill

1. Set `RAG_BACKEND=local`.
2. Deploy.
3. Run:
   - `API_URL=https://<staging-host> bash migration/validate_k2_migration.sh --backend local --skip-pytest`

## Production Readiness Checklist

- Shadow validation shows acceptable overlap/mismatch rates for your key query set.
- K2 timeout rate is within acceptable bounds.
- Rollback verified in staging.
- Monitoring dashboards/alerts are in place (errors, latency, timeouts).

