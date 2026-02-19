# K2 Service Status Summary

**Date:** 2026-02-19
**Status:** Waiting for K2 retrieval service restoration

---

## Current State

### ✅ Working Components

| Component | Status | Details |
|-----------|--------|---------|
| **VanCity Lens App** | ✅ Operational | Map, intelligence feed, Tavily ingestion all working |
| **Tavily Expansion** | ✅ Deployed | 15 queries, producing 141 docs/run, 1.4% duplication |
| **K2 Document Ingest** | ✅ Working | 152 documents synced successfully |
| **RAG Configuration** | ✅ Fixed | ConfigMap set to `rag-backend: k2` |
| **API Pods** | ✅ Running | Restarted with correct K2 config |

### ❌ Blocked by K2 Outage

| Component | Status | Details |
|-----------|--------|---------|
| **K2 Retrieval Service** | ❌ Down | Returning 500 errors consistently |
| **RAG Chat** | ❌ Non-functional | Falls back to empty local BM25 |

---

## What's Ready

**When K2 retrieval service is restored, RAG will immediately work because:**

1. ✅ ConfigMap is set to `rag-backend: k2` (permanent fix in base config)
2. ✅ API pods are running with correct configuration
3. ✅ 152 documents are synced to K2 corpus `bb158585-b616-4aed-ab63-55604093a3b8`
4. ✅ K2 fallback is enabled (`k2-fallback-to-local: true`)

**No action needed from you** - RAG will automatically start working when K2 search service is restored.

---

## Session Accomplishments

### 1. Tavily Query Expansion (✅ Complete)

**Before:**
- 3 queries
- 29 URLs found
- 1 new document per run
- 96.5% duplication

**After:**
- 15 queries across 5 categories
- 143 URLs found
- 141 new documents per run
- 1.4% duplication

**Impact:**
- 141x more unique content
- ~12,690 new documents/month
- Pre-official signals (developer announcements, neighborhood momentum, economic drivers)

**Cost:** $30/month Tavily Pro (upgraded ✅)

**Deployment:** Commit `32a6da3`, deployed to staging

### 2. K2 SDK Timeout Issue (✅ Reported)

**Issue:** SDK `upload_documents_batch` defaults to `wait=True` with no timeout

**Impact:** Can cause production hangs

**Action:** Created [GitHub Issue #279](https://github.com/posterity-ventures/k2_mvp/issues/279)

**Workaround:** Our code uses `wait=False` (already implemented)

### 3. K2 Retrieval Service Outage (⏳ Waiting)

**Issue:** K2 search/retrieval returning 500 errors

**Impact:** RAG chat non-functional

**Action:** Created [GitHub Issue #283](https://github.com/posterity-ventures/k2_mvp/issues/283)

**Workaround:** None - waiting for K2 team

**Readiness:** 152 documents synced, config fixed, pods restarted

### 4. RAG Backend Configuration (✅ Fixed)

**Issue:** ConfigMap reverted to `rag-backend: local` during deployment

**Root Cause:** Base `k8s/configmap.yaml` had `local` as default

**Fix:** Changed base default to `k2` (commit `f0e4234`)

**Result:** Future deployments won't revert to local backend

---

## Monitoring

**Check if K2 is restored:**

```bash
kubectl exec deployment/vancity-lens-api -n vancity-lens -- python -c "
from sdk import Knowledge2
import os
client = Knowledge2(api_key=os.environ['K2_API_KEY'], api_host=os.environ['K2_API_HOST'])
r = client.search(corpus_id=os.environ['K2_CORPUS_ID'], query='test')
print(f'K2 Status: OK ({len(r.get(\"results\", []))} results)')
"
```

**Test RAG:**

```bash
curl -s -X POST 'https://staging.vancitylens.com/api/v1/intel/chat' \
  -H 'Content-Type: application/json' \
  -d '{"query":"What rezoning applications were recently approved?"}' \
  | jq -r '.answer'
```

---

## What Works Right Now

Despite RAG being down, **VanCity Lens is 95% functional**:

- ✅ **Map View** - Parcel details, entitlement, pro forma, HBU
- ✅ **Intelligence Feed** - 250+ signals, 42 neighborhoods
- ✅ **Opportunity Discovery** - Top deals, composite scoring
- ✅ **Neighborhood Scorecards** - Quality metrics, comparisons
- ✅ **Tavily Ingestion** - 141 new docs every 8 hours
- ✅ **Data Pipeline** - All 12 scrapers + Tavily running
- ❌ **RAG Chat** - Blocked by K2 outage (only affected feature)

---

## K2 GitHub Issues

| Issue | Status | Link |
|-------|--------|------|
| #279 - SDK timeout parameter | Open | https://github.com/posterity-ventures/k2_mvp/issues/279 |
| #283 - Retrieval service 500 errors | Open | https://github.com/posterity-ventures/k2_mvp/issues/283 |

---

## Commits This Session

| Commit | Description |
|--------|-------------|
| `27f14db` | docs: add K2 SDK timeout issue validation report |
| `32a6da3` | feat(intelligence): expand Tavily queries to 15 for realtor intelligence |
| `1da9a6d` | docs: document Tavily 15-query expansion success |
| `f0e4234` | fix(k8s): set RAG backend to K2 by default in base configmap |

All commits pushed to GitHub ✅

---

## Expected Timeline

**K2 Team Response:** Within 24-48 hours (typical for GitHub issues)

**Service Restoration:** Unknown - depends on K2 infrastructure team

**RAG Auto-Recovery:** Immediate once K2 search is restored (no action needed)

---

**Next Action:** Monitor [K2 Issue #283](https://github.com/posterity-ventures/k2_mvp/issues/283) for updates.
