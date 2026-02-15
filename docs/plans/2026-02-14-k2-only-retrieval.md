# K2-Only Retrieval Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make K2 the sole production retrieval path; isolate local Cohere+pgvector code into `api/intelligence/local_rag/` for local dev only.

**Architecture:** K2 SDK handles embedding, chunking, and search. Production code drops all Cohere API key threading and FULL/PARTIAL/DEMO mode branching. The old local pipeline moves to `api/intelligence/local_rag/` and is only imported when `RAG_BACKEND=local`.

**Tech Stack:** K2 SDK, FastAPI, asyncpg, Anthropic Claude API

---

### Task 1: Create `local_rag/` package with moved files

**Files:**
- Create: `api/intelligence/local_rag/__init__.py`
- Create: `api/intelligence/local_rag/embeddings.py` (copy from `api/intelligence/embeddings.py`)
- Create: `api/intelligence/local_rag/chunker.py` (copy from `api/intelligence/chunker.py`)
- Create: `api/intelligence/local_rag/query_planner.py` (copy from `api/intelligence/query_planner.py`)
- Create: `api/intelligence/local_rag/external_clients_cohere.py` (extracted from `api/intelligence/external_clients.py`)

**Step 1: Create the `local_rag/` directory and `__init__.py`**

```python
# api/intelligence/local_rag/__init__.py
"""Local RAG pipeline (Cohere + pgvector + BM25).

This package is for local development only. Production uses K2 for retrieval.
Set RAG_BACKEND=local to activate.
"""
```

**Step 2: Copy `embeddings.py` to `local_rag/embeddings.py`**

Copy `api/intelligence/embeddings.py` → `api/intelligence/local_rag/embeddings.py`.

Fix the relative import on line 25:
```python
# OLD
from .external_clients import COHERE_SEMAPHORE, COHERE_TIMEOUT_SECONDS
# NEW
from .external_clients_cohere import COHERE_SEMAPHORE, COHERE_TIMEOUT_SECONDS
```

**Step 3: Create `local_rag/external_clients_cohere.py`**

Extract Cohere-specific constants from `api/intelligence/external_clients.py`:

```python
"""Cohere-specific concurrency limits and timeouts for local RAG pipeline."""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default
    if value <= 0:
        logger.warning("Invalid %s=%r (must be > 0); using default %s", name, raw, default)
        return default
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default
    if value <= 0:
        logger.warning("Invalid %s=%r (must be > 0); using default %s", name, raw, default)
        return default
    return value


COHERE_MAX_CONCURRENT_REQUESTS = _env_int("COHERE_MAX_CONCURRENT_REQUESTS", 3)
COHERE_SEMAPHORE = asyncio.Semaphore(COHERE_MAX_CONCURRENT_REQUESTS)
COHERE_TIMEOUT_SECONDS = _env_float("COHERE_TIMEOUT_SECONDS", 10.0)
```

**Step 4: Copy `chunker.py` to `local_rag/chunker.py`**

Copy `api/intelligence/chunker.py` → `api/intelligence/local_rag/chunker.py` (no import changes needed — it has no intra-package imports).

**Step 5: Copy `query_planner.py` to `local_rag/query_planner.py`**

Copy `api/intelligence/query_planner.py` → `api/intelligence/local_rag/query_planner.py` (no import changes needed — it has no intra-package imports).

**Step 6: Verify local_rag imports work**

Run: `python3 -c "from api.intelligence.local_rag.embeddings import hybrid_search, sparse_search; print('OK')"`
Expected: `OK`

**Step 7: Commit**

```bash
git add api/intelligence/local_rag/
git commit -m "refactor: create local_rag/ package with Cohere+pgvector pipeline"
```

---

### Task 2: Simplify `external_clients.py` — remove Cohere constants

**Files:**
- Modify: `api/intelligence/external_clients.py`

**Step 1: Remove Cohere constants from `external_clients.py`**

Remove these lines (keep the Anthropic constants):
- `COHERE_MAX_CONCURRENT_REQUESTS = ...`
- `COHERE_SEMAPHORE = ...`
- `COHERE_TIMEOUT_SECONDS = ...`

The file should only contain `_env_int`, `_env_float`, and the Anthropic constants:
- `ANTHROPIC_MAX_CONCURRENT_REQUESTS`
- `ANTHROPIC_SEMAPHORE`
- `ANTHROPIC_CHAT_TIMEOUT_SECONDS`
- `ANTHROPIC_EXTRACTION_TIMEOUT_SECONDS`

Update the module docstring to remove "Cohere +".

**Step 2: Verify no production code imports Cohere constants from this file**

Run: `python3 -c "from api.intelligence.external_clients import ANTHROPIC_SEMAPHORE; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add api/intelligence/external_clients.py
git commit -m "refactor: remove Cohere constants from external_clients.py"
```

---

### Task 3: Simplify `retrieval_backend.py` — K2 primary, remove shadow validation

**Files:**
- Modify: `api/intelligence/retrieval_backend.py`

**Step 1: Write the failing test — K2 is default without env var**

Add to `tests/test_k2_backend.py`:

```python
class TestK2DefaultBackend:
    """K2 should be the default backend when RAG_BACKEND is not set."""

    def test_default_backend_is_k2(self, monkeypatch):
        monkeypatch.delenv("RAG_BACKEND", raising=False)
        from api.intelligence.retrieval_backend import get_rag_backend
        assert get_rag_backend() == "k2"

    def test_explicit_local_still_works(self, monkeypatch):
        monkeypatch.setenv("RAG_BACKEND", "local")
        from api.intelligence.retrieval_backend import get_rag_backend
        assert get_rag_backend() == "local"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_k2_backend.py::TestK2DefaultBackend -v`
Expected: FAIL (current default is "local")

**Step 3: Rewrite `retrieval_backend.py`**

Replace the entire file with a simplified version:

```python
"""Retrieval backend abstraction (K2 primary, local fallback).

K2 is the default production backend. Set RAG_BACKEND=local for local dev
with Cohere+pgvector (requires api.intelligence.local_rag).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import date
from typing import Any, Optional

import asyncpg

from .k2_client import k2_fallback_to_local_enabled, k2_search_chunks

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def get_rag_backend() -> str:
    backend = (os.environ.get("RAG_BACKEND") or "k2").strip().lower()
    if backend not in {"local", "k2"}:
        return "k2"
    return backend


async def _retrieve_local(
    db_pool: asyncpg.Pool,
    *,
    query: str,
    search_mode: str,
    cohere_api_key: Optional[str],
    neighborhood_filter: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
) -> list[dict]:
    """Local retrieval using Cohere+pgvector. Lazily imports from local_rag."""
    from .local_rag.embeddings import hybrid_search, sparse_search
    from .local_rag.query_planner import is_multi_hop, multi_hop_search

    if search_mode == "full" and cohere_api_key:
        if is_multi_hop(query):
            logger.info("Multi-hop query detected, using decomposed retrieval")
            return await multi_hop_search(
                db_pool,
                query,
                cohere_api_key,
                search_fn=hybrid_search,
                limit_per_hop=8,
                final_limit=12,
                use_rerank=True,
            )
        return await hybrid_search(
            db_pool, query, cohere_api_key, limit=10, use_rerank=True,
        )

    return await sparse_search(
        db_pool, query, limit=10,
        neighborhood=neighborhood_filter,
        date_from=date_from, date_to=date_to,
    )


async def _fallback_sparse(
    db_pool: asyncpg.Pool,
    query: str,
    neighborhood_filter: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """BM25-only fallback — no external API keys needed."""
    from .local_rag.embeddings import sparse_search

    return await sparse_search(
        db_pool, query, limit=10,
        neighborhood=neighborhood_filter,
        date_from=date_from, date_to=date_to,
    )


async def retrieve_document_chunks(
    db_pool: asyncpg.Pool,
    *,
    query: str,
    search_mode: str = "full",
    cohere_api_key: Optional[str] = None,
    neighborhood_filter: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """Retrieve document chunks using the configured backend."""

    backend = get_rag_backend()
    if backend == "local":
        return await _retrieve_local(
            db_pool,
            query=query,
            search_mode=search_mode,
            cohere_api_key=cohere_api_key,
            neighborhood_filter=neighborhood_filter,
            date_from=date_from,
            date_to=date_to,
        )

    # K2 retrieval path
    t0 = time.perf_counter()
    try:
        k2_chunks = await asyncio.to_thread(k2_search_chunks, query)
    except Exception as exc:
        if k2_fallback_to_local_enabled():
            logger.warning("K2 retrieval failed; falling back to BM25. error=%s", exc)
            return await _fallback_sparse(
                db_pool, query,
                neighborhood_filter=neighborhood_filter,
                date_from=date_from, date_to=date_to,
            )
        raise

    latency_ms = (time.perf_counter() - t0) * 1000.0
    logger.info("K2 search completed in %.1fms, %d chunks", latency_ms, len(k2_chunks))
    return k2_chunks
```

**Step 4: Run tests to verify**

Run: `python3 -m pytest tests/test_k2_backend.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add api/intelligence/retrieval_backend.py tests/test_k2_backend.py
git commit -m "refactor: make K2 default backend, remove shadow validation"
```

---

### Task 4: Simplify `chat.py` — remove Cohere key threading

**Files:**
- Modify: `api/intelligence/chat.py`

**Step 1: Remove `cohere_api_key` parameter from `handle_chat()`**

In `api/intelligence/chat.py`:

- Remove `cohere_api_key` parameter from the `handle_chat()` signature
- Remove the `has_cohere` variable and FULL/PARTIAL/DEMO branching
- Search mode becomes: has `anthropic_api_key` → `"full"`, else → `"demo"`
- Remove `cohere_api_key=cohere_api_key` from the `retrieve_document_chunks()` call

The simplified mode logic:

```python
    has_anthropic = bool(anthropic_api_key)
    search_mode = "full" if has_anthropic else "demo"
    logger.info(f"Chat mode: {search_mode} (anthropic={has_anthropic})")
```

And the retrieval call:

```python
    chunks = await retrieve_document_chunks(
        db_pool=db_pool,
        query=query,
        search_mode=search_mode,
        neighborhood_filter=neighborhood_filter,
        date_from=date_from,
        date_to=date_to,
    )
```

Update the module docstring to remove "Cohere" references. Update the `handle_chat()` docstring to reflect two modes instead of three.

**Step 2: Run existing chat tests**

Run: `python3 -m pytest tests/test_chat.py -v`
Expected: PASS (tests mock `retrieve_document_chunks` so signature change is transparent)

**Step 3: Commit**

```bash
git add api/intelligence/chat.py
git commit -m "refactor: remove Cohere key threading from chat.py"
```

---

### Task 5: Simplify `routes.py` — remove Cohere helpers and key threading

**Files:**
- Modify: `api/intelligence/routes.py`

**Step 1: Remove `get_cohere_api_key()` and `get_cohere_api_key_optional()`**

Delete functions at lines 117-136.

**Step 2: Remove Cohere key from chat endpoint**

In `post_chat()` (line 165):
- Remove `cohere_key = get_cohere_api_key_optional()` (line 177)
- Remove the FULL/PARTIAL/DEMO mode logging based on cohere_key (lines 180-186)
- Remove `cohere_api_key=cohere_key` from the `handle_chat()` call (around line 192)
- Simplify to: has anthropic → "FULL", else → "DEMO"

```python
    anthropic_key = get_anthropic_api_key_optional()
    mode = "FULL" if anthropic_key else "DEMO"
    logger.info(f"Chat query received ({mode} mode): {chat_request.query[:100]}...")

    response = await handle_chat(
        db_pool=db_pool,
        query=chat_request.query,
        anthropic_api_key=anthropic_key,
        session_id=chat_request.session_id,
        neighborhood_filter=chat_request.neighborhood_filter,
        date_from=chat_request.date_from,
        date_to=chat_request.date_to,
    )
```

**Step 3: Update ingestion endpoints to note K2 handles this**

In `_background_process_task()` (line 774) and `_background_ingest_url_process()` (line 1039):
- Remove `cohere_key = os.environ.get("COHERE_API_KEY", "")`
- Remove `from .embeddings import process_document_chunks`
- Remove the `chunks_stored = await process_document_chunks(...)` calls
- Add a log line: `logger.info("Skipping local embedding — K2 handles ingestion")`
- Keep the signal extraction via `process_document()` (Claude-based extraction is separate from retrieval)

**Step 4: Update endpoint description strings**

Change the `/chat` endpoint description from:
> "retrieves relevant document chunks via hybrid search (Cohere + BM25)"

To:
> "retrieves relevant document chunks via K2 search"

**Step 5: Run route tests**

Run: `python3 -m pytest tests/test_chat.py tests/test_k2_backend.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add api/intelligence/routes.py
git commit -m "refactor: remove Cohere key helpers and threading from routes.py"
```

---

### Task 6: Update `main.py` readiness check

**Files:**
- Modify: `api/main.py:379`

**Step 1: Replace Cohere key check with K2 key check**

Change:
```python
checks["cohere_key"] = bool(os.getenv("COHERE_API_KEY"))
```
To:
```python
checks["k2_key"] = bool(os.getenv("K2_API_KEY"))
```

**Step 2: Commit**

```bash
git add api/main.py
git commit -m "refactor: check K2_API_KEY instead of COHERE_API_KEY in readiness probe"
```

---

### Task 7: Delete original files (now in `local_rag/`)

**Files:**
- Delete: `api/intelligence/embeddings.py`
- Delete: `api/intelligence/chunker.py`
- Delete: `api/intelligence/query_planner.py`

**Step 1: Delete the files**

```bash
git rm api/intelligence/embeddings.py
git rm api/intelligence/chunker.py
git rm api/intelligence/query_planner.py
```

**Step 2: Verify production imports still work**

Run: `python3 -c "from api.intelligence.retrieval_backend import retrieve_document_chunks; print('OK')"`
Expected: `OK`

Run: `python3 -c "from api.intelligence.chat import handle_chat; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git commit -m "refactor: delete original embeddings/chunker/query_planner (moved to local_rag/)"
```

---

### Task 8: Update tests to import from `local_rag/`

**Files:**
- Modify: `tests/test_embeddings.py:5` — change `from api.intelligence.embeddings` to `from api.intelligence.local_rag.embeddings`
- Modify: `tests/test_chunker.py:5` — change `from api.intelligence.chunker` to `from api.intelligence.local_rag.chunker`
- Modify: `tests/test_rag_hardening.py` — all `from api.intelligence.query_planner` → `from api.intelligence.local_rag.query_planner`
- Modify: `tests/test_rag_demo_ready.py:438` — change `from api.intelligence.chunker` → `from api.intelligence.local_rag.chunker`
- Modify: `scripts/seed_data.py:115` — change `from api.intelligence.embeddings` → `from api.intelligence.local_rag.embeddings`
- Modify: `scripts/ingest_sources.py:621` — change `from api.intelligence.embeddings` → `from api.intelligence.local_rag.embeddings`
- Modify: `scripts/embed_chunks.py:23` — change `from api.intelligence.embeddings` → `from api.intelligence.local_rag.embeddings`

**Step 1: Update all import paths**

Perform the replacements listed above in each file.

**Step 2: Run full test suite**

Run: `python3 -m pytest tests/ -x -q`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_embeddings.py tests/test_chunker.py tests/test_rag_hardening.py tests/test_rag_demo_ready.py scripts/seed_data.py scripts/ingest_sources.py scripts/embed_chunks.py
git commit -m "refactor: update test and script imports to use local_rag/"
```

---

### Task 9: Update `.env.example` and `docker-compose.yml`

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml:103`

**Step 1: Update `.env.example`**

- Change `RAG_BACKEND=local` to `RAG_BACKEND=k2`
- Move `COHERE_API_KEY` to a "Local dev only" section
- Ensure `K2_API_HOST`, `K2_API_KEY`, `K2_CORPUS_ID` are prominent

**Step 2: Update `docker-compose.yml`**

Change:
```yaml
RAG_BACKEND: "${RAG_BACKEND:-local}"
```
To:
```yaml
RAG_BACKEND: "${RAG_BACKEND:-k2}"
```

**Step 3: Commit**

```bash
git add .env.example docker-compose.yml
git commit -m "config: default RAG_BACKEND to k2 in env example and docker-compose"
```

---

### Task 10: Run full test suite and verify

**Step 1: Run full tests**

Run: `python3 -m pytest tests/ -x -q`
Expected: ALL PASS (4494+ tests)

**Step 2: Verify K2 import path (production)**

```bash
RAG_BACKEND=k2 python3 -c "
from api.intelligence.retrieval_backend import retrieve_document_chunks, get_rag_backend
assert get_rag_backend() == 'k2'
print('K2 backend: OK')
"
```

**Step 3: Verify local import path (dev)**

```bash
RAG_BACKEND=local python3 -c "
from api.intelligence.retrieval_backend import get_rag_backend
assert get_rag_backend() == 'local'
print('Local backend: OK')
"
```

**Step 4: Final commit if any fixups needed, then done**
