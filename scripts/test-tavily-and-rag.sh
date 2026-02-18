#!/bin/bash
#
# Test Tavily integration and RAG performance on staging
# Usage: ./scripts/test-tavily-and-rag.sh [staging|prod]

set -e

ENV="${1:-staging}"
NAMESPACE="vancity-lens"

if [ "$ENV" = "prod" ]; then
    BASE_URL="https://vancitylens.com"
else
    BASE_URL="https://staging.vancitylens.com"
    echo "Testing on STAGING environment"
fi

echo "=========================================="
echo "Tavily & RAG Performance Test"
echo "=========================================="
echo "Environment: $ENV"
echo "Base URL: $BASE_URL"
echo ""

# ────────────────────────────────────────────────────────────
# Step 1: Check Current Document Count
# ────────────────────────────────────────────────────────────

echo "Step 1: Checking current document count..."
echo "──────────────────────────────────────────"

BEFORE_STATS=$(curl -s "$BASE_URL/api/v1/admin/scraper-health" | jq -r '.aggregate_stats // {}')
BEFORE_DOCS=$(echo "$BEFORE_STATS" | jq -r '.total_documents // 0')
BEFORE_SIGNALS=$(echo "$BEFORE_STATS" | jq -r '.total_signals // 0')

echo "Documents: $BEFORE_DOCS"
echo "Signals: $BEFORE_SIGNALS"
echo ""

# ────────────────────────────────────────────────────────────
# Step 2: Check Tavily CronJob Status
# ────────────────────────────────────────────────────────────

echo "Step 2: Checking Tavily CronJob..."
echo "──────────────────────────────────────────"

if ! kubectl get cronjob -n "$NAMESPACE" vancity-lens-tavily-search &>/dev/null; then
    echo "⚠️  Tavily CronJob not deployed!"
    echo "Deploy with: kubectl apply -f k8s/cronjob-tavily-search.yaml"
    exit 1
fi

TAVILY_SCHEDULE=$(kubectl get cronjob -n "$NAMESPACE" vancity-lens-tavily-search -o jsonpath='{.spec.schedule}')
TAVILY_SUSPENDED=$(kubectl get cronjob -n "$NAMESPACE" vancity-lens-tavily-search -o jsonpath='{.spec.suspend}')

echo "✓ Tavily CronJob exists"
echo "  Schedule: $TAVILY_SCHEDULE (every 8 hours)"
echo "  Suspended: $TAVILY_SUSPENDED"
echo ""

# Check last run
LAST_JOB=$(kubectl get jobs -n "$NAMESPACE" -l app=vancity-lens-tavily-search --sort-by=.metadata.creationTimestamp -o json | jq -r '.items[-1].metadata.name // "none"')

if [ "$LAST_JOB" != "none" ]; then
    echo "Last Tavily job: $LAST_JOB"
    LAST_STATUS=$(kubectl get job -n "$NAMESPACE" "$LAST_JOB" -o jsonpath='{.status.conditions[0].type}')
    echo "Status: $LAST_STATUS"
else
    echo "No Tavily jobs found (hasn't run yet)"
fi
echo ""

# ────────────────────────────────────────────────────────────
# Step 3: Trigger Tavily Manually
# ────────────────────────────────────────────────────────────

echo "Step 3: Triggering Tavily search..."
echo "──────────────────────────────────────────"

JOB_NAME="tavily-test-$(date +%s)"
kubectl create job -n "$NAMESPACE" --from=cronjob/vancity-lens-tavily-search "$JOB_NAME" >/dev/null

echo "✓ Created job: $JOB_NAME"
echo "Waiting for job to start..."
sleep 5

# Wait for job to complete (max 2 minutes)
for i in {1..24}; do
    STATUS=$(kubectl get job -n "$NAMESPACE" "$JOB_NAME" -o jsonpath='{.status.conditions[0].type}' 2>/dev/null || echo "Running")
    if [ "$STATUS" = "Complete" ]; then
        echo "✓ Job completed successfully!"
        break
    elif [ "$STATUS" = "Failed" ]; then
        echo "✗ Job failed!"
        kubectl logs -n "$NAMESPACE" -l job-name="$JOB_NAME" --tail=50
        exit 1
    fi
    echo "  Waiting... ($i/24)"
    sleep 5
done

# Get job logs
echo ""
echo "Tavily Results:"
echo "──────────────────────────────────────────"
kubectl logs -n "$NAMESPACE" -l job-name="$JOB_NAME" --tail=30
echo ""

# ────────────────────────────────────────────────────────────
# Step 4: Check New Document Count
# ────────────────────────────────────────────────────────────

echo "Step 4: Checking updated document count..."
echo "──────────────────────────────────────────"
sleep 3  # Give time for documents to be indexed

AFTER_STATS=$(curl -s "$BASE_URL/api/v1/admin/scraper-health" | jq -r '.aggregate_stats // {}')
AFTER_DOCS=$(echo "$AFTER_STATS" | jq -r '.total_documents // 0')
AFTER_SIGNALS=$(echo "$AFTER_STATS" | jq -r '.total_signals // 0')

NEW_DOCS=$((AFTER_DOCS - BEFORE_DOCS))
NEW_SIGNALS=$((AFTER_SIGNALS - BEFORE_SIGNALS))

echo "Before: $BEFORE_DOCS documents, $BEFORE_SIGNALS signals"
echo "After:  $AFTER_DOCS documents, $AFTER_SIGNALS signals"
echo "Added:  +$NEW_DOCS documents, +$NEW_SIGNALS signals"
echo ""

if [ "$NEW_DOCS" -gt 0 ]; then
    echo "✓ Tavily added $NEW_DOCS new documents!"
else
    echo "⚠️  No new documents added (all were duplicates)"
fi
echo ""

# ────────────────────────────────────────────────────────────
# Step 5: Test RAG Performance
# ────────────────────────────────────────────────────────────

echo "Step 5: Testing RAG performance..."
echo "──────────────────────────────────────────"

SESSION_ID="perf-test-$(date +%s)"

echo "Sending query: 'What new rezoning applications were approved recently?'"
echo ""

START_TIME=$(date +%s.%N)

RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/intel/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What new rezoning applications were approved recently?\",
    \"session_id\": \"$SESSION_ID\"
  }" \
  -w "\n%{time_total}")

END_TIME=$(date +%s.%N)
RESPONSE_TIME=$(echo "$RESPONSE" | tail -1)
RESPONSE_BODY=$(echo "$RESPONSE" | head -n -1)

echo "Response time: ${RESPONSE_TIME}s"
echo ""
echo "Response preview:"
echo "$RESPONSE_BODY" | jq -r '.message' | head -c 500
echo ""
echo ""

# Parse response time
RESPONSE_TIME_MS=$(echo "$RESPONSE_TIME * 1000" | bc | cut -d. -f1)

if [ "$RESPONSE_TIME_MS" -lt 3000 ]; then
    echo "✓ FAST: Response in ${RESPONSE_TIME}s (< 3s)"
elif [ "$RESPONSE_TIME_MS" -lt 5000 ]; then
    echo "✓ OK: Response in ${RESPONSE_TIME}s (3-5s is normal)"
else
    echo "⚠️  SLOW: Response in ${RESPONSE_TIME}s (> 5s)"
    echo "Check LLM backend setting (should be 'gemini' for best performance)"
fi
echo ""

# ────────────────────────────────────────────────────────────
# Summary
# ────────────────────────────────────────────────────────────

echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Tavily: Added $NEW_DOCS documents"
echo "RAG: ${RESPONSE_TIME}s response time"
echo ""
echo "Next steps:"
echo "1. Open $BASE_URL/#intel"
echo "2. Ask: 'What new developments did you find?'"
echo "3. Verify Intelligence tab is clickable"
echo ""
echo "Clean up test job:"
echo "kubectl delete job -n $NAMESPACE $JOB_NAME"
echo "=========================================="
