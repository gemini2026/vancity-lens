#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# VanCity Lens — Google Cloud Deployment Script
# Provisions: Cloud SQL (PostgreSQL 16 + pgvector + PostGIS)
#             Cloud Run (FastAPI backend)
#             Secret Manager integration
#             Health check configuration
#             Custom domain: api.vancitylens.com
# ─────────────────────────────────────────────────────────

# Configuration — edit these or pass as env vars
PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-west1}"
DB_INSTANCE_NAME="${DB_INSTANCE_NAME:-vancity-lens-db}"
DB_NAME="vancity_lens"
DB_USER="vancity"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 16)}"
SERVICE_NAME="vancity-lens-api"
CUSTOM_DOMAIN="${CUSTOM_DOMAIN:-api.vancitylens.com}"
ANTHROPIC_KEY="${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY}"
COHERE_KEY="${COHERE_API_KEY:?Set COHERE_API_KEY}"
CORS_ORIGINS="${CORS_ORIGINS:-https://app.vancitylens.com}"
HEALTH_CHECK_PATH="${HEALTH_CHECK_PATH:-/health}"
HEALTH_CHECK_INITIAL_DELAY="${HEALTH_CHECK_INITIAL_DELAY:-10}"
HEALTH_CHECK_TIMEOUT="${HEALTH_CHECK_TIMEOUT:-5}"
HEALTH_CHECK_PERIOD="${HEALTH_CHECK_PERIOD:-10}"

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

# 6. Store secrets in Secret Manager
echo ""
echo "▶ Storing secrets in Secret Manager..."

# Helper function to create or update secret
upsert_secret() {
    local secret_name="$1"
    local secret_value="$2"

    if gcloud secrets describe "${secret_name}" --project="${PROJECT_ID}" &>/dev/null; then
        echo "  Updating ${secret_name}..."
        echo -n "${secret_value}" | gcloud secrets versions add "${secret_name}" \
            --data-file=- --project="${PROJECT_ID}" > /dev/null
    else
        echo "  Creating ${secret_name}..."
        echo -n "${secret_value}" | gcloud secrets create "${secret_name}" \
            --data-file=- --replication-policy="automatic" \
            --project="${PROJECT_ID}" > /dev/null
    fi
}

upsert_secret "anthropic-api-key" "${ANTHROPIC_KEY}"
upsert_secret "cohere-api-key" "${COHERE_KEY}"
upsert_secret "database-password" "${DB_PASSWORD}"

# Construct DATABASE_URL and store as secret
CLOUD_SQL_CONNECTION="${PROJECT_ID}:${REGION}:${DB_INSTANCE_NAME}"
DB_SOCKET="/cloudsql/${CLOUD_SQL_CONNECTION}"
DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=${DB_SOCKET}"
upsert_secret "database-url" "${DATABASE_URL}"

echo "  ✓ All secrets stored securely in Secret Manager"

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

# 9. Deploy to Cloud Run with advanced configuration
echo ""
echo "▶ Deploying to Cloud Run..."
echo "  Service: ${SERVICE_NAME}"
echo "  Region: ${REGION}"
echo "  Min instances: 0, Max instances: 5"
echo "  Health check: ${HEALTH_CHECK_PATH}"

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
    --set-env-vars="CORS_ORIGINS=${CORS_ORIGINS}" \
    --set-secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest,COHERE_API_KEY=cohere-api-key:latest,DATABASE_URL=database-url:latest" \
    --add-cloudsql-instances="${CLOUD_SQL_CONNECTION}" \
    --health-check-path="${HEALTH_CHECK_PATH}" \
    --startup-cpu-boost \
    --no-cpu-throttling

echo "  ✓ Cloud Run deployment complete"

# Get the service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --format="value(status.url)")

echo ""
echo "▶ Configuring custom domain..."
# Create Cloud Run domain mapping for custom domain
gcloud run domain-mappings create \
    --service="${SERVICE_NAME}" \
    --domain="${CUSTOM_DOMAIN}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" 2>/dev/null || echo "  Domain mapping already exists or in progress"

echo "  ✓ Custom domain configuration complete"
echo "  Note: Point DNS A record to GCP Load Balancer IP (shown in Cloud Run console)"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Deployment Complete!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  API Service URL:  ${SERVICE_URL}"
echo "  Custom Domain:    https://${CUSTOM_DOMAIN}"
echo "  Health Check:     https://${CUSTOM_DOMAIN}${HEALTH_CHECK_PATH}"
echo "  Chat Endpoint:    POST https://${CUSTOM_DOMAIN}/api/v1/intel/chat"
echo "  Signals Endpoint: GET  https://${CUSTOM_DOMAIN}/api/v1/intel/signals"
echo ""
echo "  Database:"
echo "    Instance: ${DB_INSTANCE_NAME}"
echo "    Database: ${DB_NAME}"
echo "    User: ${DB_USER}"
echo "    (Password stored in Secret Manager as 'database-password')"
echo ""
echo "  Secrets stored in Secret Manager:"
echo "    - anthropic-api-key"
echo "    - cohere-api-key"
echo "    - database-password"
echo "    - database-url"
echo ""
echo "  Next steps:"
echo "  1. Configure DNS: Point ${CUSTOM_DOMAIN} to GCP's load balancer"
echo "  2. Update frontend: NEXT_PUBLIC_API_URL=https://${CUSTOM_DOMAIN}"
echo "  3. Run seeding: python scripts/seed_data.py"
echo "  4. Test health: curl https://${CUSTOM_DOMAIN}${HEALTH_CHECK_PATH}"
echo "  5. Monitor logs: gcloud run logs read ${SERVICE_NAME} --region=${REGION} --limit=50"
echo ""
