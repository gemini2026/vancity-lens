#!/bin/bash
#
# Verify every k8s service has an ingress path configured
# Run this as a pre-commit hook or in CI to catch missing routes
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Extract service names from k8s manifests
SERVICES=$(grep -h "kind: Service" -A 5 k8s/*.yaml k8s/overlays/staging/*.yaml 2>/dev/null | \
    grep "name:" | sed 's/.*name: *//' | sort -u || true)

# Extract backend service names from ingress.yaml
BACKENDS=$(grep -A 3 "backend:" k8s/ingress.yaml | \
    grep "name:" | sed 's/.*name: *//' | sort -u || true)

echo "🔍 Checking ingress coverage for k8s services..."
echo ""

MISSING_COUNT=0
COVERED_COUNT=0

for svc in $SERVICES; do
    # Skip headless services and postgres (not user-facing)
    if [[ "$svc" == *"headless"* ]] || [[ "$svc" == *"postgres"* ]] || [[ "$svc" == *"redis"* ]]; then
        continue
    fi

    if echo "$BACKENDS" | grep -q "^${svc}$"; then
        echo -e "${GREEN}✓${NC} $svc"
        COVERED_COUNT=$((COVERED_COUNT + 1))
    else
        echo -e "${YELLOW}⚠${NC}  $svc ${RED}(missing ingress route)${NC}"
        MISSING_COUNT=$((MISSING_COUNT + 1))
    fi
done

echo ""
echo "─────────────────────────────"
echo "Services with routes: $COVERED_COUNT"
echo "Services missing routes: $MISSING_COUNT"

if [ $MISSING_COUNT -gt 0 ]; then
    echo ""
    echo -e "${RED}❌ Some services are not exposed via ingress${NC}"
    echo ""
    echo "To fix: Update k8s/ingress.yaml with path rules for missing services"
    exit 1
else
    echo ""
    echo -e "${GREEN}✅ All user-facing services have ingress routes${NC}"
    exit 0
fi
