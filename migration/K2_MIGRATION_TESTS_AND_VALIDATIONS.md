# K2 Migration Tests and Validations

This document defines the execution-grade test matrix for migrating Bill47 RAG runtime to K2 via K2 SDK without data migration.

## Preconditions

| Check | Requirement |
|---|---|
| Services | `make up` completed and `/health` returns `{"status":"ok"}` |
| Baseline backend | `RAG_BACKEND=local` available |
| K2 backend | `K2_API_HOST`, `K2_API_KEY`, `K2_CORPUS_ID` set for K2 mode (corpus must already exist and be accessible to the key) |
| Test tooling | `python3`, `pytest`, `curl`, `frontend` Playwright dependencies |

## Automated Command Entrypoints

| Command | Purpose |
|---|---|
| `make validate-k2-migration` | Run migration parity suite in `local` mode (recreates API container for correct env) |
| `make validate-k2-migration-both` | Run parity suite in `local` and `k2` modes (recreates API container between modes) |
| `bash migration/validate_k2_migration.sh --backend k2 --restart-api --skip-e2e` | Fast K2-only backend validation with local Docker Compose stack |

## Validation Matrix

| ID | Stage | Ticket | Validation Type | Acceptance Criteria | Command |
|---|---|---|---|---|---|
| VAL-001 | Stage 0 | MIG-001 | API contract | `/api/v1/intel/chat` schema unchanged | `python3 -m pytest tests/test_api_contracts.py tests/test_routes.py -q` |
| VAL-002 | Stage 0 | MIG-002 | Config safety | Missing/invalid runtime config fails safely | `python3 -m pytest tests/test_external_failures.py -q` |
| VAL-003 | Stage 1 | MIG-003 | Wrapper reliability | K2 client error paths handled without crashing API | `python3 -m pytest tests/test_external_failures.py -q` |
| VAL-004 | Stage 1 | MIG-004 | Backend abstraction | Retrieval mode switch does not break chat contract | `python3 -m pytest tests/test_chat.py tests/test_routes.py -q` |
| VAL-005 | Stage 2 | MIG-005 | Retrieval mapping | K2 retrieval normalized to existing chunk shape | `python3 -m pytest tests/test_chat.py tests/test_full_pipeline.py -q -k chat` |
| VAL-006 | Stage 2 | MIG-006 | Citation parity | `SourceCitation` fields populated/nullable exactly as contract | `python3 -m pytest tests/test_rag_hardening.py tests/test_chat.py -q` |
| VAL-007 | Stage 2 | MIG-007 | Signal continuity | `related_signals` behavior unchanged | `python3 -m pytest tests/test_signals.py tests/test_chat.py -q` |
| VAL-008 | Stage 3 | MIG-008 | Runtime switch | `RAG_BACKEND=local|k2` both return valid chat responses | `bash migration/validate_k2_migration.sh --backend both --skip-e2e` |
| VAL-009 | Stage 3 | MIG-009 | Fallback behavior | K2 failure falls back to local when enabled | `python3 -m pytest tests/test_external_failures.py -q` |
| VAL-010 | Stage 4 | MIG-010 | Report parity | PDF/report APIs still succeed with citations/sources | `python3 -m pytest tests/test_report_generator.py -q` |
| VAL-011 | Stage 4 | MIG-011 | Due diligence parity | DD evidence endpoints and report section remain functional | `python3 -m pytest tests/test_due_diligence.py tests/test_report_generator.py -q` |
| VAL-012 | Stage 5 | MIG-012 | UI parity (Intel) | Chat renders answer + citations + session behavior | `cd frontend && API_BASE_URL=http://localhost:8080 npx playwright test e2e/intelligence.spec.ts` |
| VAL-013 | Stage 5 | MIG-013 | UI parity (journey) | Full user journey passes in migrated backend mode | `cd frontend && API_BASE_URL=http://localhost:8080 npx playwright test e2e/e2e-full.spec.ts` |
| VAL-014 | Stage 6 | MIG-014 | Shadow validation | Local vs K2 citation mismatch rate within threshold | Compare structured logs / offline diff report |
| VAL-015 | Stage 6 | MIG-015 | Rollback drill | Rollback to `local` works in one toggle and passes smoke | Toggle env + run `bash migration/validate_k2_migration.sh --backend local --skip-e2e` |
| VAL-016 | Stage 7 | MIG-016 | Production health | Error rate, latency, citation completeness within SLO | Monitor metrics/logs for 24-72h |
| VAL-017 | Stage 7 | MIG-017 | Hardening exit | No critical regressions after cleanup | Full regression suite + E2E |

## Smoke API Checks (Included in Script)

| Check | Pass Condition |
|---|---|
| `GET /health` | JSON status is `ok` |
| `POST /api/v1/intel/chat` | Response contains `answer`, `citations`, `related_signals`, `session_id`, `mode` |
| Citation object checks | Each citation includes `document_title`, `document_url`, `source_type`, `relevance_score`, `excerpt` |

## Evidence Collection Template

| Run Date | Backend | Command | Result | Notes |
|---|---|---|---|---|
| YYYY-MM-DD | local | `make validate-k2-migration` | pass/fail |  |
| YYYY-MM-DD | k2 | `bash migration/validate_k2_migration.sh --backend k2 --skip-e2e` | pass/fail |  |
| YYYY-MM-DD | both | `make validate-k2-migration-both` | pass/fail |  |
