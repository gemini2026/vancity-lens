#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# VanCity Lens — Google Cloud Deployment Script
# Provisions: Cloud SQL (PostgreSQL 16 + pgvector + PostGIS)
#             Cloud Run (FastAPI backend)
# ─────────────────────────────────────────────────────────

# Configuration — edit these or pass as env vars
PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-west1}"
DB_INSTANCE_NAME="${DB_INSTANCE_NAME:-vancity-lens-db}"
DB_NAME="vancity_lens"
DB_USER="vancity"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 16)}"
SERVICE_NAME="vancity-lens-api"
ANTHROPIC_KEY="${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY}"
COHERE_KEY="${COHERE_API_KEY:?Set COHERE_API_KEY}"
CORS_ORIGINS="${CORS_ORIGINS:-https://vancity-lens.pages.dev}"

echo "═══════════════════════════════════════════════════"
echo "  VanCity Lens — GCP Deployment"
echo "  Project: ${PROJECT_ID}  Region: ${REGION}"
echo "═══════════════════════════════════════════════════"

# 1. Enable required APIs
echo ""
echo "▶ Enabling GCP APIs..."
gcloud services enable \
    sqladmin.googleapis.com \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    --project="${PROJECT_ID}"

# 2. Create Cloud SQL instance (PostgreSQL 16)
echo ""
echo "▶ Creating Cloud SQL instance: ${DB_INSTANCE_NAME}..."
if gcloud sql instances describe "${DB_INSTANCE_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "  Instance already exists, skipping creation"
else
    gcloud sql instances create "${DB_INSTANCE_NAME}" \
        --project="${PROJECT_ID}" \
        --database-version=POSTGRES_16 \
        --tier=db-f1-micro \
        --region="${REGION}" \
        --storage-type=SSD \
        --storage-size=10GB \
        --database-flags="cloudsql.enable_pgaudit=off" \
        --availability-type=zonal
    echo "  ✓ Instance created"
fi

# 3. Create database and user
echo ""
echo "▶ Setting up database..."
gcloud sql databases create "${DB_NAME}" \
    --instance="${DB_INSTANCE_NAME}" \
    --project="${PROJECT_ID}" 2>/dev/null || echo "  Database already exists"

gcloud sql users create "${DB_USER}" \
    --instance="${DB_INSTANCE_NAME}" \
    --password="${DB_PASSWORD}" \
    --project="${PROJECT_ID}" 2>/dev/null || echo "  User already exists"

# 4. Enable extensions (pgvector + PostGIS)
echo ""
echo "▶ Enabling PostgreSQL extensions..."
CLOUD_SQL_CONNECTION="${PROJECT_ID}:${REGION}:${DB_INSTANCE_NAME}"

# Use Cloud SQL Auth Proxy or gcloud sql connect
gcloud sql connect "${DB_INSTANCE_NAME}" \
    --database="${DB_NAME}" \
    --user="${DB_USER}" \
    --project="${PROJECT_ID}" \
    <<SQL
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
SQL

echo "  ✓ PostGIS and pgvector enabled"

# 5. Run database migrations
echo ""
echo "▶ Running database migrations..."
for sql_file in db/001_schema.sql db/002_seed_stations.sql db/003_add_rew_url.sql \
    db/004_risk_layers.sql db/005_v2_risk_layers.sql db/006_v3_execution_risk.sql \
    db/007_intelligence_layer.sql; do
    echo "  Running ${sql_file}..."
    gcloud sql connect "${DB_INSTANCE_NAME}" \
        --database="${DB_NAME}" \
        --user="${DB_USER}" \
        --project="${PROJECT_ID}" \
        < "${sql_file}" 2>/dev/null || echo "  (already applied or warning)"
done
echo "  ✓ Migrations complete"

# 6. Store secrets
echo ""
echo "▶ Storing secrets in Secret Manager..."
echo -n "${ANTHROPIC_KEY}" | gcloud secrets create anthropic-api-key \
    --data-file=- --project="${PROJECT_ID}" 2>/dev/null || \
    echo -n "${ANTHROPIC_KEY}" | gcloud secrets versions add anthropic-api-key \
    --data-file=- --project="${PROJECT_ID}"

echo -n "${COHERE_KEY}" | gcloud secrets create cohere-api-key \
    --data-file=- --project="${PROJECT_ID}" 2>/dev/null || \
    echo -n "${COHERE_KEY}" | gcloud secrets versions add cohere-api-key \
    --data-file=- --project="${PROJECT_ID}"

echo -n "${DB_PASSWORD}" | gcloud secrets create db-password \
    --data-file=- --project="${PROJECT_ID}" 2>/dev/null || \
    echo -n "${DB_PASSWORD}" | gcloud secrets versions add db-password \
    --data-file=- --project="${PROJECT_ID}"

echo "  ✓ Secrets stored"

# 7. Create Artifact Registry repo
echo ""
echo "▶ Setting up Artifact Registry..."
gcloud artifacts repositories create vancity-lens \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT_ID}" 2>/dev/null || echo "  Repository already exists"

# 8. Build and push container
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/vancity-lens"
IMAGE="${REGISTRY}/${SERVICE_NAME}:latest"

echo ""
echo "▶ Building container image..."
gcloud builds submit \
    --tag="${IMAGE}" \
    --project="${PROJECT_ID}"
echo "  ✓ Image built and pushed"

# 9. Deploy to Cloud Run
echo ""
echo "▶ Deploying to Cloud Run..."
DB_SOCKET="/cloudsql/${CLOUD_SQL_CONNECTION}"
DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=${DB_SOCKET}"

gcloud run deploy "${SERVICE_NAME}" \
    --image="${IMAGE}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --platform=managed \
    --allow-unauthenticated \
    --memory=1Gi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=5 \
    --timeout=300 \
    --set-env-vars="DATABASE_URL=${DATABASE_URL},CORS_ORIGINS=${CORS_ORIGINS}" \
    --set-secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest,COHERE_API_KEY=cohere-api-key:latest" \
    --add-cloudsql-instances="${CLOUD_SQL_CONNECTION}"

# Get the service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --format="value(status.url)")

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Deployment Complete!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  API URL:     ${SERVICE_URL}"
echo "  Health:      ${SERVICE_URL}/health"
echo "  Chat:        POST ${SERVICE_URL}/api/v1/intel/chat"
echo "  Signals:     GET  ${SERVICE_URL}/api/v1/intel/signals"
echo ""
echo "  DB Instance: ${DB_INSTANCE_NAME}"
echo "  DB Password: ${DB_PASSWORD}"
echo "  (stored in Secret Manager as 'db-password')"
echo ""
echo "  Next steps:"
echo "  1. Update Cloudflare Pages env: NEXT_PUBLIC_API_URL=${SERVICE_URL}"
echo "  2. Run seeding: python scripts/seed_data.py"
echo "  3. Test: curl ${SERVICE_URL}/health"
echo ""
