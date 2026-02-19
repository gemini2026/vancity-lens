#!/bin/bash
#
# Smoke tests for VanCity Lens deployment
# Verifies all critical services are reachable and functioning
#
# Usage:
#   ./scripts/smoke-test.sh https://staging.vancitylens.com
#   ./scripts/smoke-test.sh https://vancitylens.com
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BASE_URL="${1:-https://staging.vancitylens.com}"
FAILED_TESTS=0
TOTAL_TESTS=0

echo "🧪 Running smoke tests against: $BASE_URL"
echo ""

# Helper function to run a test
run_test() {
    local name="$1"
    local command="$2"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    echo -n "Testing $name... "
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo "  Command failed: $command"
    fi
}

# Test 1: Frontend root URL
run_test "Frontend root" \
    "curl -f -s -L --max-time 10 '$BASE_URL/' | grep -q 'VanCity Lens'"

# Test 2: API signals endpoint
run_test "API signals" \
    "curl -f -s --max-time 10 '$BASE_URL/api/v1/intel/signals?limit=1' | grep -q 'signals'"

# Test 3: RAG chat endpoint (requires valid JSON body)
run_test "RAG chat" \
    "curl -f -s --max-time 30 -X POST '$BASE_URL/api/v1/intel/chat' \
        -H 'Content-Type: application/json' \
        -d '{\"query\":\"test\"}' | grep -q 'answer'"

# Test 5: Check that API routes don't leak to frontend
run_test "API routing isolation" \
    "! curl -s '$BASE_URL/api' | grep -q 'Next.js'"

# Test 6: Check that frontend doesn't return API JSON for root
run_test "Frontend routing isolation" \
    "! curl -s '$BASE_URL/' | grep -q '{\"detail\"'"

echo ""
echo "─────────────────────────────"

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}✅ All $TOTAL_TESTS smoke tests passed${NC}"
    exit 0
else
    echo -e "${RED}❌ $FAILED_TESTS/$TOTAL_TESTS smoke tests failed${NC}"
    exit 1
fi
