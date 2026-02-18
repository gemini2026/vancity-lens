#!/bin/bash
#
# K2 Document Sync - Upload PostgreSQL documents to K2 corpus
# Usage: ./scripts/sync-k2.sh [options]
#
# Options:
#   --dry-run     Show what would be synced without uploading
#   --force       Re-sync all documents (ignore sync status)
#   --limit N     Limit to N documents
#   --initial     Run initial bulk sync job (all 195 documents)
#   --status      Check K2 sync status and corpus document count

set -e

NAMESPACE="vancity-lens"

# ────────────────────────────────────────────────────────────
# Parse Arguments
# ────────────────────────────────────────────────────────────

DRY_RUN=""
FORCE=""
LIMIT=""
INITIAL=false
STATUS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --force)
            FORCE="--force"
            shift
            ;;
        --limit)
            LIMIT="--limit $2"
            shift 2
            ;;
        --initial)
            INITIAL=true
            shift
            ;;
        --status)
            STATUS=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run] [--force] [--limit N] [--initial] [--status]"
            exit 1
            ;;
    esac
done

# ────────────────────────────────────────────────────────────
# Status Check
# ────────────────────────────────────────────────────────────

if [ "$STATUS" = true ]; then
    echo "=========================================="
    echo "K2 Sync Status"
    echo "=========================================="
    echo ""

    echo "PostgreSQL document counts:"
    kubectl exec -n "$NAMESPACE" deployment/vancity-lens-api -- python -c "
import asyncio
import asyncpg
import os

async def check():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], min_size=1, max_size=1)
    try:
        total = await pool.fetchval('SELECT COUNT(*) FROM documents')
        synced = await pool.fetchval(\"SELECT COUNT(*) FROM documents WHERE metadata->>'k2_synced' = 'true'\")
        unsynced = await pool.fetchval(\"SELECT COUNT(*) FROM documents WHERE metadata->>'k2_synced' IS NULL OR metadata->>'k2_synced' = 'false'\")
        print(f'  Total: {total}')
        print(f'  Synced to K2: {synced}')
        print(f'  Not synced: {unsynced}')
    finally:
        await pool.close()

asyncio.run(check())
"

    echo ""
    echo "K2 corpus document count:"
    kubectl exec -n "$NAMESPACE" deployment/vancity-lens-api -- python -c "
from sdk import Knowledge2
import os

k2 = Knowledge2(
    api_host=os.environ['K2_API_HOST'],
    api_key=os.environ['K2_API_KEY']
)

corpus_id = os.environ['K2_CORPUS_ID']
corpus = k2.get_corpus(corpus_id)
print(f'  Corpus: {corpus[\"name\"]}')
print(f'  Documents: {corpus[\"document_count\"]}')
print(f'  Corpus ID: {corpus_id}')
"

    echo ""
    echo "Recent sync jobs:"
    kubectl get jobs -n "$NAMESPACE" -l component=k2-sync --sort-by=.metadata.creationTimestamp | tail -5

    echo ""
    echo "=========================================="
    exit 0
fi

# ────────────────────────────────────────────────────────────
# Initial Bulk Sync Job
# ────────────────────────────────────────────────────────────

if [ "$INITIAL" = true ]; then
    echo "=========================================="
    echo "K2 Initial Bulk Sync"
    echo "=========================================="
    echo ""

    # Delete old job if it exists
    kubectl delete job -n "$NAMESPACE" k2-initial-sync 2>/dev/null || true

    # Deploy the job
    echo "Creating initial sync job..."
    kubectl apply -f k8s/job-k2-initial-sync.yaml

    echo ""
    echo "Waiting for job to start..."
    sleep 5

    # Follow logs
    echo ""
    echo "Job logs:"
    echo "──────────────────────────────────────────"
    kubectl logs -n "$NAMESPACE" -l purpose=initial-bulk-upload -f --tail=100

    # Check final status
    echo ""
    echo "Final status:"
    kubectl get job -n "$NAMESPACE" k2-initial-sync

    echo ""
    echo "=========================================="
    exit 0
fi

# ────────────────────────────────────────────────────────────
# Manual Sync (Run in API Pod)
# ────────────────────────────────────────────────────────────

echo "=========================================="
echo "K2 Manual Sync"
echo "=========================================="
echo "Options: $DRY_RUN $FORCE $LIMIT"
echo ""

POD=$(kubectl get pods -n "$NAMESPACE" -l app=vancity-lens-api -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD" ]; then
    echo "❌ No API pods found"
    exit 1
fi

echo "Running sync in pod: $POD"
echo ""

kubectl exec -n "$NAMESPACE" "$POD" -- python -m api.intelligence.k2_sync $DRY_RUN $FORCE $LIMIT

echo ""
echo "=========================================="
