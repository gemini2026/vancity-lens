# K2 Migration Plan (Execution Backlog)

## Scope and Constraints

| Item | Decision |
|---|---|
| Target | Migrate Bill47 RAG runtime to K2 using K2 SDK |
| Data migration | Not required (no backfill/move of existing Bill47 DB data) |
| Functional parity | Required (`/api/v1/intel/chat`, citations, sessions, reports, UI behavior) |
| Rollback | Required via feature flag (`RAG_BACKEND=local`) |
| Integration style | Keep Bill47 generation/reporting logic; replace retrieval layer first |

## Status Legend

| Status | Meaning |
|---|---|
| `TODO` | Not started |
| `IN_PROGRESS` | Actively being implemented |
| `BLOCKED` | Waiting on dependency/decision |
| `DONE` | Completed and validated |

## Backlog by Stage

| Stage | Ticket | Backlog Item | Status | Acceptance Criteria | Validation |
|---|---|---|---|---|---|
| Stage 0 - Design Lock | MIG-001 | Freeze parity contract for RAG endpoints and UI payloads | DONE | Existing request/response contract for `/api/v1/intel/chat` documented and approved; no schema regressions allowed | Run `python3 -m pytest tests/test_api_contracts.py tests/test_routes.py -q` and confirm green baseline |
| Stage 0 - Design Lock | MIG-002 | Define K2 runtime config contract | DONE | `.env.example` includes `RAG_BACKEND`, `K2_API_HOST`, `K2_API_KEY`, `K2_CORPUS_ID`, `K2_TOP_K`, `K2_TIMEOUT_SECONDS`, `K2_FALLBACK_TO_LOCAL`; defaults are safe | Run `python3 -m pytest tests/test_k2_backend.py tests/test_chat.py -q` |
| Stage 1 - SDK Integration | MIG-003 | Add K2 SDK client module (`api/intelligence/k2_client.py`) | DONE | Centralized K2 SDK wrapper exists; handles auth, timeouts, request IDs, errors | Run `python3 -m pytest tests/test_k2_backend.py -q` |
| Stage 1 - SDK Integration | MIG-004 | Add retrieval backend abstraction (`local` vs `k2`) | DONE | `chat.py` consumes one normalized retrieval interface; no direct K2 calls scattered across code | Run `python3 -m pytest tests/test_k2_backend.py tests/test_chat.py -q` |
| Stage 2 - K2 Retrieval | MIG-005 | Implement K2 retrieval path using `Knowledge2.search(...)` | DONE | K2 search returns normalized chunk objects matching current chat pipeline expectations | Run `python3 -m pytest tests/test_k2_backend.py -q` |
| Stage 2 - K2 Retrieval | MIG-005A | Provision an accessible K2 corpus for real end-to-end retrieval validation | DONE | `K2_CORPUS_ID` is reachable by the runtime API key; K2 search returns >0 results for a known query | Run `K2_API_HOST=... K2_API_KEY=... K2_CORPUS_ID=... bash migration/validate_k2_migration.sh --backend k2 --restart-api --skip-e2e` with `K2_FALLBACK_TO_LOCAL=false` |
| Stage 2 - K2 Retrieval | MIG-005B | Ingest `pipeline/sources.yaml` into K2 (URL-based) | DONE | K2 corpus contains the enabled sources (SYC plans/dev apps, BC laws, Broadway Subway, optional RSS); indexes are built and `dense_status/sparse_status=ready` | Run `K2_API_HOST=... K2_API_KEY=... K2_CORPUS_ID=... python3 migration/k2_ingest_sources.py --include-disabled --wait --build-indexes` then verify `python3 migration/k2_corpus_status.py` |
| Stage 2 - K2 Retrieval | MIG-006 | Map K2 results to existing citation model (`SourceCitation`) | DONE | Citations still include `document_title`, `document_url`, `source_type`, `relevance_score`, `excerpt`; optional fields nullable when unavailable | Run `bash migration/validate_k2_migration.sh --backend local --restart-api --skip-e2e` |
| Stage 2 - K2 Retrieval | MIG-007 | Keep related signals path unchanged from local DB | DONE | `related_signals` in chat responses still populated using existing signal queries | Run `python3 -m pytest tests/test_signals.py tests/test_chat.py -q` |
| Stage 3 - Runtime Switching | MIG-008 | Feature-flag switch in chat handler (`RAG_BACKEND=local|k2`) | DONE | Runtime can switch backend without code change; local remains default-safe | Run `bash migration/validate_k2_migration.sh --backend both --restart-api --skip-e2e` |
| Stage 3 - Runtime Switching | MIG-009 | Implement resilient fallback (`k2` failure -> local when enabled) | DONE | On K2 errors/timeouts, system returns valid chat response using local retrieval when fallback enabled; no 500 for transient K2 issues | Run `python3 -m pytest tests/test_k2_backend.py -q` and `bash migration/validate_k2_migration.sh --backend k2 --restart-api --skip-e2e` |
| Stage 4 - Report Parity | MIG-010 | Ensure report generation remains contract-compatible | DONE | Report flows (`investor memo`, PDF preview/download) work with K2-backed chat retrieval | Run `python3 -m pytest tests/test_report_generator.py tests/test_due_diligence.py -q` |
| Stage 4 - Report Parity | MIG-011 | Ensure due diligence evidence flows remain unchanged | DONE | Due diligence evidence endpoints and PDF evidence sections still render and include source links | Run `python3 -m pytest tests/test_due_diligence.py tests/test_report_generator.py -q` |
| Stage 5 - UI Parity | MIG-012 | Validate Intel UI chat and citations with K2 backend | DONE | Frontend chat still shows answer + citations + session continuity; no UI schema changes required | Run `cd frontend && API_BASE_URL=http://localhost:8080 npx playwright test e2e/intelligence.spec.ts` |
| Stage 5 - UI Parity | MIG-013 | Validate full E2E journey for primary user flows | DONE | Existing full-flow UI tests pass with K2 backend enabled; no critical regressions | Run `cd frontend && API_BASE_URL=http://localhost:8080 npx playwright test e2e/e2e-full.spec.ts` |
| Stage 6 - Rollout | MIG-014 | Add shadow validation mode (optional but recommended) | DONE | System logs side-by-side local vs K2 top citations for sample traffic without changing user response | Enable `K2_SHADOW_VALIDATE=true` with `K2_SHADOW_VALIDATE_SAMPLE_RATE=1.0` and verify `k2_shadow_validate` log events; parse with `python3 migration/rag_eval/parse_shadow_validate_logs.py` |
| Stage 6 - Rollout | MIG-014A | Add offline retrieval evaluation harness (local vs K2) | DONE | `migration/rag_eval/` scripts exist; can run against a shared URL set and produce `results.jsonl` + `summary.md` with recall/MRR/latency | Run `python3 migration/rag_eval/local_chunk_backfill.py --only-k2-intersection ...` (optional) then `python3 migration/rag_eval/run_retrieval_eval.py ...` |
| Stage 6 - Rollout | MIG-015 | Staging cutover with rollback runbook | TODO | Staging runs with `RAG_BACKEND=k2` for agreed soak period; rollback tested via env toggle | Run smoke tests + contract suite + E2E in staging; record rollback time |
| Stage 7 - Production | MIG-016 | Production cutover and monitoring | TODO | Production switched to K2 retrieval with error/latency/SLA within target; rollback ready | Monitor `/api/v1/intel/chat` error rate, latency, citation completeness for 24-72h |
| Stage 7 - Production | MIG-017 | Post-cutover hardening and cleanup | TODO | Remove dead code paths only after stability window; docs updated for operations | Run full regression suite and publish runbook/docs |

## Stage Gates (Must Pass Before Advancing)

| Gate | Required Pass Conditions |
|---|---|
| Gate A (after Stage 1) | K2 SDK client and backend abstraction merged; local mode unchanged |
| Gate B (after Stage 3) | `k2` mode + fallback mode pass contract tests |
| Gate C (after Stage 5) | UI E2E parity passes in `k2` mode |
| Gate D (before production) | Staging soak complete, rollback drill completed, monitoring dashboard live |

## Definition of Done

| Item | Done Criteria |
|---|---|
| K2 SDK usage | Retrieval path uses K2 SDK (`Knowledge2.search`) in production mode |
| No data migration | No document/chunk backfill jobs required for existing Bill47 DB |
| Same functionality | Chat, citations, sessions, reports, due diligence, and UI workflows remain functional |
| Operational safety | Feature-flag rollback path documented and tested |
