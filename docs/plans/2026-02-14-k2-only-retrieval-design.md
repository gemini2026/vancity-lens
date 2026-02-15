# K2-Only Retrieval with Local RAG Isolation

**Date:** 2026-02-14
**Status:** Approved

## Problem

The codebase maintains two parallel retrieval systems: the K2 SDK (production) and a local Cohere+pgvector+BM25 pipeline. K2 handles embedding, chunking, and search — the local pipeline is redundant in production and adds complexity (Cohere API key threading, FULL/PARTIAL/DEMO mode logic, shadow validation).

## Decision

Make K2 the sole production retrieval path. Move all local Cohere+pgvector code into `api/intelligence/local_rag/` for local development use only.

## Target Architecture

```
api/intelligence/
├── local_rag/                        # isolated local dev module
│   ├── __init__.py                   # re-exports for local dev convenience
│   ├── embeddings.py                 # Cohere embed + pgvector hybrid/sparse search
│   ├── chunker.py                    # semchunk-based document chunking
│   ├── external_clients_cohere.py    # Cohere semaphore/timeout constants
│   └── query_planner.py             # multi-hop query decomposition
├── retrieval_backend.py              # simplified: K2 primary, lazy local_rag fallback
├── k2_client.py                      # unchanged
├── chat.py                           # simplified: no Cohere key threading
├── routes.py                         # ingestion endpoints rewired to K2
├── external_clients.py               # Anthropic-only (Cohere constants removed)
└── ...
```

## Changes

### 1. Move to `local_rag/`

| File | From | To |
|------|------|----|
| `embeddings.py` | `api/intelligence/` | `api/intelligence/local_rag/` |
| `chunker.py` | `api/intelligence/` | `api/intelligence/local_rag/` |
| `query_planner.py` | `api/intelligence/` | `api/intelligence/local_rag/` |

### 2. Simplify `retrieval_backend.py`

- K2 is the default backend (no env var needed for production)
- `RAG_BACKEND=local` still works — imports from `local_rag.embeddings` lazily
- Remove all shadow validation code (migration artifact)
- Remove `cohere_api_key` parameter from `retrieve_document_chunks()`

### 3. Simplify `chat.py`

- Remove `cohere_api_key` parameter from `handle_chat()`
- Remove FULL/PARTIAL/DEMO mode logic based on Cohere key
- Two modes only: has Anthropic key = RAG mode, no key = demo mode

### 4. Simplify `routes.py`

- Remove `get_cohere_api_key()` and `get_cohere_api_key_optional()` helpers
- Stop threading `cohere_key` through chat endpoint
- Ingestion endpoints (`admin/process`, `admin/ingest-url`) use K2 ingestion
  - Local dev can still use the old pipeline via `local_rag` imports

### 5. Simplify `external_clients.py`

- Remove `COHERE_SEMAPHORE`, `COHERE_MAX_CONCURRENT_REQUESTS`, `COHERE_TIMEOUT_SECONDS`
- Move Cohere constants to `local_rag/external_clients_cohere.py`
- File becomes Anthropic-only

### 6. Dependencies

- `cohere` stays in `requirements.txt` for now (local dev needs it)
- Can be moved to `requirements-dev.txt` in a follow-up

## What Gets Deleted

- Shadow validation code in `retrieval_backend.py` (`_shadow_validate_k2_vs_local`, `_maybe_start_shadow_validation`, related helpers)
- Cohere API key helpers in `routes.py`
- FULL/PARTIAL/DEMO search mode branching in `chat.py`

## What Stays Untouched

- `k2_client.py` — no changes
- All K2 migration scripts under `migration/`
- `sdk/` directory
- Database schema (pgvector tables remain for local dev)

## Fallback Behavior

- `RAG_BACKEND=local` → lazily imports `local_rag.embeddings` (requires Cohere key + pgvector)
- `K2_FALLBACK_TO_LOCAL` → if K2 fails at runtime, falls back to BM25-only sparse search from `local_rag` (no Cohere needed)
- Default (no env var or `RAG_BACKEND=k2`) → K2 only
