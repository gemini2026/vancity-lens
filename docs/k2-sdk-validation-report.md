# K2 SDK Timeout Issue Validation Report

**Date:** 2026-02-18
**Validator:** Claude Code
**SDK Location:** `/Users/antonmishel/k2/devops/k2_mvp`

## Executive Summary

**Finding: ❌ ISSUE NOT FIXED**

The K2 SDK still has the same blocking wait issue that caused our `k2_sync.py` to timeout. While the K2 team has added timeout infrastructure, it is **not being used** by the core document upload methods.

---

## Original Issue (What We Encountered)

In our `api/intelligence/k2_sync.py`, we experienced:
- Batch document uploads hanging indefinitely
- No timeout mechanism to prevent infinite waits
- Had to implement workaround: explicitly pass `wait=False` to avoid blocking

**Our Fix (commit 116d715):**
```python
# api/intelligence/k2_sync.py, line 344
response = client.documents.upload_documents_batch(
    corpus_id=CORPUS_ID,
    documents=batch,
    idempotency_key=batch_uuid,
    wait=False,  # ← CRITICAL: Prevents blocking indefinitely
)
```

---

## Current SDK State Analysis

### ❌ Issue Still Exists

**File:** `sdk/resources/documents.py`

**Line 134:** Default is still `wait=True` (blocking behavior)
```python
def upload_documents_batch(
    self,
    corpus_id: str,
    documents: list[dict[str, Any]],
    idempotency_key: str | None = None,
    *,
    auto_index: bool | None = None,
    chunk_strategy: str | None = None,
    chunking: ChunkingConfig | None = None,
    wait: bool = True,  # ← STILL DEFAULTS TO BLOCKING
    poll_s: int = 5,
) -> DocumentCreateResponse:
```

**Line 166:** Calls `_wait_for_job` WITHOUT timeout
```python
if wait:
    job_id = data.get("job_id")
    if job_id:
        self._wait_for_job(job_id, poll_s=poll_s)  # ← NO timeout_s parameter
```

---

### ✅ Timeout Infrastructure Available (But Unused)

**File:** `sdk/_base.py`

**Lines 267-281:** `_wait_for_job` DOES have `timeout_s` parameter
```python
def _wait_for_job(
    self, job_id: str, *, poll_s: int = 5, timeout_s: float | None = None
) -> dict[str, Any]:
    start = time.monotonic()
    while True:
        job = self._request("GET", f"/v1/jobs/{job_id}")
        status = job.get("status")
        if status in {"succeeded", "failed", "canceled"}:
            if status != "succeeded":
                message = job.get("error_message") or f"Job {job_id} ended with status={status}"
                raise RuntimeError(message)
            return job
        if timeout_s is not None and (time.monotonic() - start) > timeout_s:
            raise TimeoutError(f"Timed out waiting for job {job_id}")
        time.sleep(poll_s)
```

**Key Points:**
- ✅ Timeout mechanism exists (`timeout_s` parameter)
- ✅ Will raise `TimeoutError` after `timeout_s` seconds
- ❌ Defaults to `None` (infinite wait if not specified)
- ❌ **NOT USED** by `upload_documents_batch`

---

### ✅ Evidence of Progress

**Recent Commits:**
```
4b207887 - Issue #200: bounded retries for transient retrieval timeouts
933a64de - fix: clamp timeout budget, guard metrics
e6c2f3d3 - fix(worker): enforce bounded FTK summarization and fix parser stall
6767fae2 - fix(indexes): stop summary wait when parent build job is canceled
```

**LlamaIndex Integration** (properly uses timeout):
```python
# sdk/integrations/llamaindex/vector_store.py, line 120
ingest_timeout_s: float | None = 300.0  # ← 5 minute default timeout

# Lines 167-171
if (
    self.ingest_timeout_s is not None
    and (time.monotonic() - start) > self.ingest_timeout_s
):
    raise TimeoutError(f"Timed out waiting for ingest job {job_id}")
```

**Interpretation:**
- The K2 team IS aware of timeout issues
- They've implemented timeout infrastructure
- Their LlamaIndex integration uses it correctly (300s default)
- BUT: They haven't updated the core SDK methods to use it

---

## Impact Assessment

### Our Codebase: ✅ Unaffected

**Status:** Our workaround remains valid and necessary.

We explicitly pass `wait=False` to avoid blocking:
```python
# api/intelligence/k2_sync.py
response = client.documents.upload_documents_batch(
    corpus_id=CORPUS_ID,
    documents=batch,
    idempotency_key=batch_uuid,
    wait=False,  # ← Our workaround
)

# Then we poll manually with our own timeout logic
if job_id:
    await asyncio.wait_for(
        poll_k2_job_completion(client, job_id),
        timeout=600  # 10 minute timeout
    )
```

**Action Required:** NONE. Our code is safe.

---

## Recommended Actions

### For K2 Team (GitHub Issue)

**Title:** `upload_documents_batch` should expose `timeout_s` parameter

**Description:**
The `upload_documents_batch` method currently waits indefinitely when `wait=True` (the default). While `_wait_for_job` has a `timeout_s` parameter, it's not exposed or used by the batch upload methods.

**Proposed Fix:**
```python
def upload_documents_batch(
    self,
    corpus_id: str,
    documents: list[dict[str, Any]],
    idempotency_key: str | None = None,
    *,
    auto_index: bool | None = None,
    chunk_strategy: str | None = None,
    chunking: ChunkingConfig | None = None,
    wait: bool = True,
    poll_s: int = 5,
    timeout_s: float | None = 300.0,  # ← NEW: Default 5min timeout
) -> DocumentCreateResponse:
    # ... existing payload construction ...

    if wait:
        job_id = data.get("job_id")
        if job_id:
            self._wait_for_job(job_id, poll_s=poll_s, timeout_s=timeout_s)  # ← Pass timeout
    return cast("DocumentCreateResponse", data)
```

**Benefits:**
- Prevents infinite hangs in production
- Consistent with LlamaIndex integration (which uses 300s default)
- Backward compatible (None = infinite wait, like current behavior)
- Aligns with recent timeout work (Issue #200, commits 4b207887, e6c2f3d3)

**Alternative:** Change `wait` default to `False` for non-blocking behavior by default.

---

### For Our Team

**Action:** Continue using `wait=False` workaround until K2 SDK is fixed.

**Documentation:** This report serves as evidence that our workaround is necessary and correct.

**Monitoring:** Check K2 SDK releases for updates to `upload_documents_batch` signature.

---

## Verification Evidence

**Files Analyzed:**
- `/Users/antonmishel/k2/devops/k2_mvp/sdk/resources/documents.py` (lines 125-167)
- `/Users/antonmishel/k2/devops/k2_mvp/sdk/_base.py` (lines 267-281)
- `/Users/antonmishel/k2/devops/k2_mvp/sdk/integrations/llamaindex/vector_store.py` (lines 115-174)

**Git History:**
```bash
cd /Users/antonmishel/k2/devops/k2_mvp
git log --oneline --all --since="2025-12-01" --grep="timeout\|wait\|poll" | head -10
```

**Result:** Multiple timeout-related fixes in retrieval, worker, and index modules, but none in `upload_documents_batch`.

---

## Conclusion

**Summary:** The K2 SDK timeout issue is **NOT fixed**. The infrastructure exists (`timeout_s` parameter in `_wait_for_job`), but it's not exposed or used by the document upload methods.

**Our Workaround:** Valid, necessary, and should be maintained.

**Next Steps:**
1. ✅ Continue using `wait=False` in our code
2. ⚠️ Optionally: File GitHub issue with K2 team (details above)
3. ⏳ Monitor K2 SDK releases for fixes
