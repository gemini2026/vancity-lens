# Migration Folder

This folder contains the execution backlog and validation harness for migrating Bill47 RAG runtime to K2 via the K2 SDK.

## Files

- `migration/migration-plan.md`: ticket backlog, stages, acceptance criteria, gates
- `migration/K2_MIGRATION_TESTS_AND_VALIDATIONS.md`: test/validation matrix + run commands
- `migration/validate_k2_migration.sh`: executable validation harness used by `make validate-k2-migration*`
- `migration/k2_smoke_corpus_setup.py`: optional helper to bootstrap a tiny K2 corpus for E2E validation (requires K2 permissions)
- `migration/K2_MUST_HAVES_EFFORT.md`: background analysis of K2 “must-haves” and effort estimate

## Quick Run

1. `make up`
2. `make validate-k2-migration`

For local + K2 validation:

1. Export `K2_API_HOST`, `K2_API_KEY`, `K2_CORPUS_ID`
2. `make validate-k2-migration-both`
