# RAG & Scraping Troubleshooting Guide

## Problem: "I don't have sufficient information"

When the Intelligence chat returns this message, it means the RAG system couldn't find relevant documents in the vector database.

### Common Causes

1. **No data yet** - Scrapers run on cron schedules and haven't run since deployment
2. **Scraper failures** - Scrapers encountered errors during execution
3. **Vector embeddings not generated** - Documents ingested but not vectorized
4. **Query doesn't match content** - Available docs don't cover the topic

---

## Quick Diagnosis

### 1. Check Scraper Status

```bash
curl https://staging.vancitylens.com/api/v1/admin/scraper-health | jq
```

**Look for:**
- `last_run`: When each scraper last executed
- `last_status`: "success", "partial", or "failed"
- `aggregate_stats.total_documents`: Total docs in database
- `aggregate_stats.total_signals`: Total intelligence signals

**Expected on fresh deployment:** Most scrapers show `last_run: null` (haven't run yet)

### 2. Check Document Count

```bash
curl https://staging.vancitylens.com/api/v1/admin/scraper-health | \
  jq '.aggregate_stats'
```

**Healthy system:**
```json
{
  "total_documents": 500+,
  "total_signals": 100+
}
```

**Fresh deployment (no data):**
```json
{
  "total_documents": 0,
  "total_signals": 0
}
```

---

## Solution 1: Manual Scraper Trigger (Immediate)

Use the provided script to trigger scrapers manually:

```bash
# Trigger all priority scrapers
./scripts/trigger-scrapers.sh https://staging.vancitylens.com

# Trigger specific scrapers only
./scripts/trigger-scrapers.sh https://staging.vancitylens.com rezoning news

# Trigger a single scraper
curl -X POST https://staging.vancitylens.com/api/v1/admin/scraper/rezoning/run
```

**Wait time:** 1-5 minutes per scraper (varies by data source)

---

## Solution 2: Deploy Scraper Init Job (Automated)

For fresh deployments, run the one-time initialization job:

```bash
# Deploy the job
kubectl apply -f k8s/job-scraper-init.yaml

# Watch progress
kubectl logs -n vancity-lens -l component=scraper-init -f

# Check completion
kubectl get jobs -n vancity-lens scraper-init
```

**Expected output:**
```
Running council scraper...
council: {'status': 'success', 'found': 45, 'new': 45}
Running dpb scraper...
dpb: {'status': 'success', 'found': 12, 'new': 12}
...
Total new documents: 150
```

**To re-run:** Delete and recreate the job
```bash
kubectl delete job -n vancity-lens scraper-init
kubectl apply -f k8s/job-scraper-init.yaml
```

---

## Solution 3: Wait for Scheduled Run

If you prefer not to trigger manually, wait for the next cron run:

### Scraper Schedules

| Scraper | Schedule | Next Run (UTC) |
|---------|----------|----------------|
| `council` | Daily at 06:00 | Tomorrow 06:00 |
| `dpb` | Daily at 07:00 | Tomorrow 07:00 |
| `rezoning` | Daily at 08:00 | Tomorrow 08:00 |
| `news` | Every 6 hours | Next :00 on the hour |
| `bclaws` | Daily at 05:00 | Tomorrow 05:00 |
| `opendata` | Mondays at 03:00 | Next Monday |
| `gazette` | Monthly (30th) at 05:00 | Next month |
| `contaminated` | Monthly (1st) at 04:00 | Next month |
| `statscan` | Monthly (1st) at 03:00 | Next month |
| `cmhc` | Monthly (15th) at 03:00 | Next month |

**Note:** Times are in UTC. Convert to your local timezone.

---

## Verifying RAG Works

After triggering scrapers, test the RAG system:

### 1. Check Document Count Again

```bash
curl https://staging.vancitylens.com/api/v1/admin/scraper-health | \
  jq '.aggregate_stats.total_documents'
```

**Expected:** > 0 (should have documents now)

### 2. Test a Query

**Via UI:**
1. Open https://staging.vancitylens.com/#intel
2. Ask: "What rezoning applications were approved recently?"
3. Expect: Structured response with sources (not "insufficient information")

**Via API:**
```bash
curl -X POST https://staging.vancitylens.com/api/v1/intel/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What rezoning applications were approved recently?",
    "session_id": "test-session"
  }'
```

**Expected response:**
```json
{
  "message": "Based on recent documents...",
  "sources": [
    {"title": "...", "url": "...", "relevance": 0.85}
  ]
}
```

---

## Advanced Debugging

### Check Vector Embeddings

```sql
-- Connect to database
psql $DATABASE_URL

-- Check embedding table
SELECT COUNT(*) FROM document_embeddings;

-- Check recent documents
SELECT title, scraped_at FROM documents
ORDER BY scraped_at DESC LIMIT 10;
```

### Check Scraper Logs

```bash
# Live logs from API pods
kubectl logs -n vancity-lens -l app=vancity-lens-api --tail=100 -f | grep scraper

# Check for errors
kubectl logs -n vancity-lens -l app=vancity-lens-api --tail=1000 | grep -i error
```

### Force Scraper Restart

```bash
# Restart API pods to reinitialize scheduler
kubectl rollout restart deployment/vancity-lens-api -n vancity-lens

# Wait for rollout
kubectl rollout status deployment/vancity-lens-api -n vancity-lens
```

---

## Expected Behavior

### Fresh Deployment (Day 0)
- **Documents:** 0
- **Signals:** 0
- **RAG Response:** "I don't have sufficient information"
- **Action:** Run `./scripts/trigger-scrapers.sh` or wait for first cron run

### After Initial Scraping (Day 0 + 5 minutes)
- **Documents:** 100-500
- **Signals:** 50-200
- **RAG Response:** Contextual answers with sources

### Steady State (Day 1+)
- **Documents:** Growing daily (500-2000+)
- **Signals:** Growing daily (200-1000+)
- **RAG Response:** Rich, multi-source answers

---

## Support

If scrapers are running but RAG still returns "no information":

1. Check the **specific question** - it might not match available content
2. Verify **RAG backend** setting in ConfigMap (should be "local" or "k2")
3. Check **LLM backend** setting (should be "gemini" or "anthropic")
4. Review **document content** to ensure it's relevant to the query

For persistent issues, check the logs:
```bash
kubectl logs -n vancity-lens -l app=vancity-lens-api --tail=500 | grep -E "(RAG|embedding|vector)"
```

---

## K2 Document Sync

### What is K2?

K2 (Knowledge2.ai) is the production RAG backend that VanCity Lens uses for vector search and retrieval. Documents scraped into the PostgreSQL database need to be uploaded to the K2 corpus before RAG can find them.

### Sync Architecture

```
PostgreSQL documents (195)
    ↓ (k2_sync.py)
K2 Corpus (api-dev.knowledge2.ai)
    ↓ (RAG queries)
Intelligence Chat responses
```

### Check K2 Sync Status

```bash
# Quick status check
./scripts/sync-k2.sh --status
```

This shows:
- Total documents in PostgreSQL
- How many are synced to K2
- How many are pending sync
- K2 corpus document count
- Recent sync jobs

### Manual Sync

```bash
# Dry run - see what would be synced
./scripts/sync-k2.sh --dry-run --limit 10

# Sync unsynced documents
./scripts/sync-k2.sh

# Force re-sync all documents
./scripts/sync-k2.sh --force

# Sync specific number of documents
./scripts/sync-k2.sh --limit 50
```

### Initial Bulk Upload

After fresh deployment or when K2 corpus is empty, run the initial sync job to upload all documents:

```bash
./scripts/sync-k2.sh --initial
```

This creates a Kubernetes Job that:
- Uploads all 195 documents to K2 in batches of 100
- Takes ~5-10 minutes
- Shows progress logs in real-time
- Auto-indexes documents for immediate RAG availability

### Ongoing Sync (CronJob)

Deploy the K2 sync CronJob for automatic syncing:

```bash
kubectl apply -f k8s/cronjob-k2-sync.yaml
```

This runs every 30 minutes and uploads any new documents from scrapers to K2.

**Schedule:** `*/30 * * * *` (every 30 minutes)

### How Sync Tracking Works

The sync system uses `metadata->>'k2_synced'` in the documents table to track which documents have been uploaded to K2:
- Unsynced: `k2_synced` is `NULL` or `'false'`
- Synced: `k2_synced` is `'true'` with `k2_synced_at` timestamp

Idempotency: K2 deduplicates by `source_uri` (mapped to `source_url` from PostgreSQL), so re-uploading the same document is safe.

### Troubleshooting

**Issue: "K2 corpus has 0 documents"**
- Run initial sync: `./scripts/sync-k2.sh --initial`
- Check sync status: `./scripts/sync-k2.sh --status`

**Issue: "New Tavily documents not showing in RAG"**
- Check if CronJob is running: `kubectl get cronjob vancity-lens-k2-sync`
- Manually trigger sync: `./scripts/sync-k2.sh`
- Verify K2 corpus count increased: `./scripts/sync-k2.sh --status`

**Issue: "Sync job failed"**
- Check job logs: `kubectl logs -n vancity-lens -l component=k2-sync --tail=100`
- Common causes: K2 API rate limits, network timeout, invalid credentials
- Retry: Delete and recreate the job

---

## Tavily Search Integration

### What is Tavily?

Tavily is an AI-powered web search API that discovers Vancouver development news, rezoning applications, and Bill 47 TOD content across the entire web. It supplements the built-in scrapers by finding content from sources we haven't explicitly configured.

### Tavily CronJob Schedule

Unlike other scrapers that run in-process, Tavily runs as a **Kubernetes CronJob**:

- **Schedule:** Every 8 hours (00:00, 08:00, 16:00 UTC)
- **Configuration:** `k8s/cronjob-tavily-search.yaml`
- **Queries:** 
  - "Vancouver rezoning application 2026"
  - "Bill 47 TOD development Vancouver"
  - "Vancouver density development news"

### Check if Tavily is Running

```bash
# Check CronJob status
kubectl get cronjobs -n vancity-lens | grep tavily

# Check recent jobs
kubectl get jobs -n vancity-lens | grep tavily

# Check logs from last run
kubectl logs -n vancity-lens -l app=vancity-lens-tavily-search --tail=100
```

### Manually Trigger Tavily

```bash
# Create a one-time job from the CronJob
kubectl create job -n vancity-lens --from=cronjob/vancity-lens-tavily-search tavily-manual-run

# Watch the job
kubectl logs -n vancity-lens -l job-name=tavily-manual-run -f

# Expected output
{
  "searches_performed": 3,
  "urls_discovered": 25,
  "new_documents": 8,
  "skipped_duplicates": 17
}
```

### Verify Tavily API Key

```bash
# Check if secret exists
kubectl get secret -n vancity-lens vancity-lens-secrets -o jsonpath='{.data.tavily-api-key}' | base64 -d | wc -c

# Expected: Should show character count > 0
# If 0, the API key is not set - add it to the secret
```

### Why No Tavily Data?

1. **CronJob not deployed** - Run: `kubectl apply -f k8s/cronjob-tavily-search.yaml`
2. **API key not set** - Check secret: `kubectl get secret vancity-lens-secrets`
3. **Haven't hit schedule yet** - Runs every 8 hours, may not have executed
4. **Quota exceeded** - Tavily free tier: 1,000 credits/month
5. **Job failing** - Check logs for errors

---

## RAG Performance Optimization

### Why is RAG Slow?

Common causes of slow RAG responses:

1. **Vector search latency** - Searching 1000+ documents takes time
2. **LLM generation time** - Gemini/Anthropic API calls take 2-5 seconds
3. **No caching** - Every query is a fresh API call
4. **Network latency** - GCP → Vertex AI / Anthropic API round-trip

### Current Performance Characteristics

**Typical response time breakdown:**
- Vector similarity search: 500-1000ms
- LLM generation (Gemini 2.5 Flash): 2-4 seconds
- Total: **3-5 seconds**

### Quick Wins

#### 1. Use Gemini (Faster)

Check your LLM backend setting:

```bash
kubectl get configmap -n vancity-lens vancity-lens-config -o yaml | grep llm-backend
```

**Fastest:** `llm-backend: "gemini"` with `gemini-model: "gemini-2.5-flash"`
**Slower:** `llm-backend: "anthropic"`

#### 2. Reduce Vector Search Scope

Edit `/api/intelligence/retrieval_backend.py`:

```python
# Current (slower but more comprehensive)
limit=10

# Faster (fewer documents retrieved)
limit=5
```

#### 3. Add Response Streaming (Future Enhancement)

Currently RAG waits for the full LLM response before returning. Adding streaming would make responses **feel** faster by showing partial results immediately.

**Status:** Not implemented yet (requires frontend + backend changes)

### Advanced: Add Redis Caching

For frequently asked questions, add Redis caching:

```python
# Pseudo-code
cache_key = f"rag:{hash(query)}"
cached = redis.get(cache_key)
if cached:
    return cached
result = await handle_chat(...)
redis.setex(cache_key, 3600, result)  # Cache for 1 hour
```

**Status:** Not implemented (would require Redis deployment)

### Monitoring RAG Performance

Check actual response times in logs:

```bash
kubectl logs -n vancity-lens -l app=vancity-lens-api --tail=500 | grep "chat request"
```

Expected log format:
```
INFO chat request completed in 3.2s (query: "What rezoning...", docs: 8, tokens: 1234)
```

---

## Common Issues & Solutions

### Issue: "RAG is slow"

**Solution:**
1. Confirm you're using Gemini (faster than Anthropic)
2. Check network latency: `kubectl logs` should show <5s total
3. If >10s, investigate vector search performance or database issues
4. Consider reducing retrieval limit from 10 to 5 documents

### Issue: "No Tavily content"

**Solution:**
1. Verify CronJob is deployed: `kubectl get cronjob vancity-lens-tavily-search`
2. Check API key exists: `kubectl get secret vancity-lens-secrets`
3. Manually trigger: `kubectl create job --from=cronjob/vancity-lens-tavily-search tavily-test`
4. Check logs for errors: `kubectl logs -l job-name=tavily-test`

### Issue: "Intelligence tab not clickable"

**Solution:**
- Fixed in latest deployment (z-index conflict with Disclaimer)
- Update to commit `55d2726` or later
- Verify: `kubectl get deployment vancity-lens-api -o jsonpath='{.spec.template.spec.containers[0].image}'`

