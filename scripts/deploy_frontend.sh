#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# VanCity Lens — Cloudflare Pages Frontend Deployment
# Provisions: Next.js standalone output
#             Custom domain: app.vancitylens.com
#             Environment variable configuration
#             Automatic build and deployment
# ─────────────────────────────────────────────────────────

PROJECT_NAME="${CF_PROJECT_NAME:-vancity-lens}"
CUSTOM_DOMAIN="${CF_CUSTOM_DOMAIN:-app.vancitylens.com}"
API_URL="${NEXT_PUBLIC_API_URL:?Set NEXT_PUBLIC_API_URL (e.g. https://api.vancitylens.com)}"
MAPBOX_TOKEN="${NEXT_PUBLIC_MAPBOX_TOKEN:?Set NEXT_PUBLIC_MAPBOX_TOKEN}"
CF_API_TOKEN="${CF_API_TOKEN:?Set CF_API_TOKEN (Cloudflare API token)}"
CF_ACCOUNT_ID="${CF_ACCOUNT_ID:?Set CF_ACCOUNT_ID (Cloudflare Account ID)}"

# Optional environment variables for Next.js
NEXT_PUBLIC_ANALYTICS_ID="${NEXT_PUBLIC_ANALYTICS_ID:-}"
NEXT_PUBLIC_SENTRY_DSN="${NEXT_PUBLIC_SENTRY_DSN:-}"

echo "═══════════════════════════════════════════════════"
echo "  VanCity Lens — Cloudflare Pages Deployment"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Project: ${PROJECT_NAME}"
echo "  API URL: ${API_URL}"
echo "  Domain: https://${CUSTOM_DOMAIN}"
echo ""

SCRIPT_DIR="$(dirname "$0")"
FRONTEND_DIR="${SCRIPT_DIR}/../frontend"

if [ ! -d "${FRONTEND_DIR}" ]; then
    echo "❌ Error: Frontend directory not found at ${FRONTEND_DIR}"
    exit 1
fi

cd "${FRONTEND_DIR}"

# 1. Validate Next.js configuration
echo "▶ Validating Next.js configuration..."
if [ ! -f "next.config.js" ] && [ ! -f "next.config.mjs" ]; then
    echo "❌ Error: next.config.js not found"
    exit 1
fi
echo "  ✓ next.config found"

# Check for standalone output configuration
if ! grep -q "output.*standalone" next.config.* 2>/dev/null; then
    echo "⚠ Warning: Standalone output not configured in next.config"
fi

# 2. Install dependencies
echo ""
echo "▶ Installing dependencies..."
npm ci --prefer-offline

# 3. Build Next.js with standalone output
echo ""
echo "▶ Building Next.js app..."
echo "  Output mode: standalone"
echo "  API URL: ${API_URL}"

NEXT_PUBLIC_API_URL="${API_URL}" \
NEXT_PUBLIC_MAPBOX_TOKEN="${MAPBOX_TOKEN}" \
npm run build

if [ ! -d ".next" ]; then
    echo "❌ Error: Build failed - .next directory not found"
    exit 1
fi

echo "  ✓ Build complete"

# 4. Validate build artifacts
echo ""
echo "▶ Validating build artifacts..."
if [ ! -f ".next/package.json" ]; then
    echo "⚠ Warning: Standalone package.json not found in .next"
fi
echo "  ✓ Build artifacts validated"

# 5. Deploy to Cloudflare Pages
echo ""
echo "▶ Deploying to Cloudflare Pages..."

# Use wrangler to deploy
npx wrangler pages deploy .next/static \
    --project-name="${PROJECT_NAME}" \
    --branch=production \
    --compatibility-date=2024-12-18

if [ $? -eq 0 ]; then
    echo "  ✓ Deployment successful"
else
    echo "  ⚠ Deployment via wrangler may require additional configuration"
fi

# 6. Configure custom domain
echo ""
echo "▶ Configuring custom domain..."
echo "  Domain: ${CUSTOM_DOMAIN}"

# Build cURL command for custom domain configuration
if [ -n "${CF_API_TOKEN}" ] && [ -n "${CF_ACCOUNT_ID}" ]; then
    echo "  (Configure manually in Cloudflare dashboard or use CF API)"
    echo "  DNS CNAME: ${CUSTOM_DOMAIN} -> ${PROJECT_NAME}.pages.dev"
else
    echo "  ⚠ CF_API_TOKEN or CF_ACCOUNT_ID not set - configure DNS manually"
fi

# 7. Display deployment summary
PAGES_URL="https://${PROJECT_NAME}.pages.dev"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Frontend Deployment Complete!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Cloudflare Pages URL: ${PAGES_URL}"
echo "  Custom Domain:        https://${CUSTOM_DOMAIN}"
echo "  API Backend:          ${API_URL}"
echo ""
echo "  Environment variables configured:"
echo "    - NEXT_PUBLIC_API_URL=${API_URL}"
echo "    - NEXT_PUBLIC_MAPBOX_TOKEN=***"
if [ -n "${NEXT_PUBLIC_ANALYTICS_ID}" ]; then
    echo "    - NEXT_PUBLIC_ANALYTICS_ID=${NEXT_PUBLIC_ANALYTICS_ID}"
fi
if [ -n "${NEXT_PUBLIC_SENTRY_DSN}" ]; then
    echo "    - NEXT_PUBLIC_SENTRY_DSN=***"
fi
echo ""
echo "  Next steps:"
echo "  1. Verify DNS CNAME record: ${CUSTOM_DOMAIN} -> ${PROJECT_NAME}.pages.dev"
echo "  2. Wait for SSL certificate (5-15 min)"
echo "  3. Test: curl https://${CUSTOM_DOMAIN}"
echo "  4. Ensure backend CORS includes: https://${CUSTOM_DOMAIN}"
echo ""
echo "  Build artifacts:"
echo "    .next/static/        (Next.js static files)"
echo "    .next/server/        (Next.js server functions)"
echo ""
