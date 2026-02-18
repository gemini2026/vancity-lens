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
