#!/bin/bash
#
# Manually trigger scrapers via the admin API
# Usage: ./scripts/trigger-scrapers.sh <BASE_URL> [scraper_names...]
#
# Examples:
#   ./scripts/trigger-scrapers.sh https://staging.vancitylens.com
#   ./scripts/trigger-scrapers.sh https://staging.vancitylens.com rezoning news council

set -e

BASE_URL="${1:-https://staging.vancitylens.com}"
shift || true

# Default scrapers to run (priority order for initial data)
if [ $# -eq 0 ]; then
    SCRAPERS=("council" "dpb" "rezoning" "news" "bclaws")
else
    SCRAPERS=("$@")
fi

echo "========================================"
echo "VanCity Lens Scraper Trigger"
echo "========================================"
echo "Base URL: $BASE_URL"
echo "Scrapers: ${SCRAPERS[*]}"
echo ""

# Check scraper health first
echo "Fetching current scraper status..."
curl -s "$BASE_URL/api/v1/admin/scraper-health" | jq -r '
  .scrapers[] |
  "[\(.name)] Last run: \(.last_run // "never") | Status: \(.last_status // "n/a") | Docs: \(.last_document_count // 0)"
' || echo "Could not fetch scraper health"
echo ""

# Trigger each scraper
for scraper in "${SCRAPERS[@]}"; do
    echo "----------------------------------------"
    echo "Triggering: $scraper"
    echo "----------------------------------------"

    response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/v1/admin/scraper/$scraper/run")

    status_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -1)

    if [ "$status_code" = "200" ]; then
        echo "✓ Success!"
        echo "$body" | jq -r '
          "Documents found: \(.documents_found // 0)",
          "Documents new: \(.documents_new // 0)",
          "Documents skipped: \(.documents_skipped // 0)",
          "Duration: \(.duration_seconds // 0)s"
        ' || echo "$body"
    else
        echo "✗ Failed (HTTP $status_code)"
        echo "$body"
    fi
    echo ""
done

echo "========================================"
echo "Trigger complete!"
echo ""
echo "Check updated status:"
echo "curl $BASE_URL/api/v1/admin/scraper-health | jq '.aggregate_stats'"
echo "========================================"
