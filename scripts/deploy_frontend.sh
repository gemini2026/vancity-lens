#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# VanCity Lens — Cloudflare Pages Frontend Deployment
# ─────────────────────────────────────────────────────────

PROJECT_NAME="${CF_PROJECT_NAME:-vancity-lens}"
API_URL="${NEXT_PUBLIC_API_URL:?Set NEXT_PUBLIC_API_URL (e.g. https://vancity-lens-api-xxx.run.app)}"
MAPBOX_TOKEN="${NEXT_PUBLIC_MAPBOX_TOKEN:?Set NEXT_PUBLIC_MAPBOX_TOKEN}"

echo "═══════════════════════════════════════════════════"
echo "  VanCity Lens — Cloudflare Pages Deployment"
echo "  Project: ${PROJECT_NAME}"
echo "  API URL: ${API_URL}"
echo "═══════════════════════════════════════════════════"

cd "$(dirname "$0")/../frontend"

# 1. Install dependencies
echo ""
echo "▶ Installing dependencies..."
npm ci

# 2. Build Next.js
echo ""
echo "▶ Building Next.js app..."
NEXT_PUBLIC_API_URL="${API_URL}" \
NEXT_PUBLIC_MAPBOX_TOKEN="${MAPBOX_TOKEN}" \
npm run build

# 3. Deploy to Cloudflare Pages
echo ""
echo "▶ Deploying to Cloudflare Pages..."
npx wrangler pages deploy out \
    --project-name="${PROJECT_NAME}" \
    --branch=production

PAGES_URL="https://${PROJECT_NAME}.pages.dev"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Frontend Deployed!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  URL:      ${PAGES_URL}"
echo "  API:      ${API_URL}"
echo ""
echo "  Ensure CORS_ORIGINS includes: ${PAGES_URL}"
echo ""
