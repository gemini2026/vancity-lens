# VanCity Lens - Deployment Guide

This guide explains the Terragrunt and Kubernetes manifests created for deploying VanCity Lens.

## Directory Structure

```
/sessions/zen-relaxed-lamport/mnt/bill47/
├── terraform/
│   ├── terragrunt.hcl                  # Root Terragrunt config
│   ├── environments/
│   │   └── dev/
│   │       ├── terragrunt.hcl          # Dev environment config
│   │       └── env.hcl                 # Local values
│   └── modules/                        # Existing TF modules
└── k8s/
    ├── namespace.yaml                  # Kubernetes namespace
    ├── deployment.yaml                 # FastAPI backend deployment
    ├── service.yaml                    # ClusterIP service
    ├── ingress.yaml                    # Ingress with GKE SSL
    ├── configmap.yaml                  # Configuration (CORS_ORIGINS)
    ├── secret.yaml                     # Secrets (DB, API keys)
    ├── cronjob.yaml                    # Daily data scraping job
    └── kustomization.yaml              # Kustomize orchestration
```

## Part 1: Terragrunt Configuration

### Files Created

1. **terraform/terragrunt.hcl** (Root Configuration)
   - Sets up GCS remote state backend
   - Bucket: `openclaw-antonmishel-03460-tf-state`
   - Configures common inputs for all environments
   - Generates backend.tf automatically

2. **terraform/environments/dev/terragrunt.hcl**
   - Sources terraform modules from `../../`
   - Sets inputs:
     - `project_id`: "openclaw-antonmishel-03460"
     - `region`: "us-west1"
     - `cluster_name`: "vancity-lens-dev"

3. **terraform/environments/dev/env.hcl**
   - Local values for dev environment
   - `environment`: "dev"

### Usage

Before deploying, verify the GCP project configuration:

```bash
# In terraform/terragrunt.hcl
# GCP project ID: openclaw-antonmishel-03460
# GCS state bucket: openclaw-antonmishel-03460-tf-state

# Deploy dev environment
cd terraform/environments/dev
terragrunt init
terragrunt plan
terragrunt apply
```

## Part 2: Kubernetes Manifests

### Files Created

#### 1. namespace.yaml
- Creates `vancity-lens` namespace
- Labels for identification and management

#### 2. deployment.yaml - FastAPI Backend
**Key Features:**
- Image: `us-west1-docker.pkg.dev/openclaw-antonmishel-03460/vancity-lens/vancity-lens-api:latest`
- Replicas: 1 (POC - scale up in production)
- Container port: 8000
- Liveness probe: GET /health (restarts if unhealthy)
- Readiness probe: GET /health (removes from service if not ready)

**Resource Allocation:**
- Requests: 256Mi memory, 250m CPU
- Limits: 512Mi memory, 500m CPU

**Environment Variables:**
- `DATABASE_URL` → from secret
- `ANTHROPIC_API_KEY` → from secret
- `COHERE_API_KEY` → from secret
- `CORS_ORIGINS` → from configmap

#### 3. service.yaml
- Type: ClusterIP
- Exposes port 80 → container port 8000
- Service name: `vancity-lens-api`

#### 4. ingress.yaml
- GKE-managed SSL certificate support
- Host: `vancity-lens.example.com` (update with your domain)
- Routes path / to service port 80
- Includes example for ManagedCertificate setup

#### 5. configmap.yaml
- `CORS_ORIGINS`: "https://vancity-lens.pages.dev"
- Update origin URLs as needed for your frontend

#### 6. secret.yaml
- Contains placeholders for:
  - `DATABASE_URL`: PostgreSQL connection string
  - `ANTHROPIC_API_KEY`: Anthropic API key
  - `COHERE_API_KEY`: Cohere API key

**Production Setup:**
Use GCP Secret Manager + External Secrets Operator instead. Example configuration provided in comments.

#### 7. cronjob.yaml
- Schedule: "0 6 * * *" (6 AM UTC daily)
- Runs: `python scripts/seed_data.py --scrape-only --source all --days-back 3`
- Same environment variables and resource limits as deployment
- Keeps 3 successful + 1 failed job for debugging

#### 8. kustomization.yaml
- Orchestrates all resources
- Applies common labels and annotations
- Configured for image replacement

### Deployment Steps

#### Step 1: Update Placeholders

```bash
# 1. Update registry and image tag in kustomization.yaml
# 2. Update domain in ingress.yaml
# 3. Update CORS_ORIGINS in configmap.yaml
# 4. Update secrets with actual values in secret.yaml
```

#### Step 2: Deploy with Kustomize

```bash
# Validate manifests
kubectl kustomize k8s/ | kubectl apply --dry-run=client -f -

# Deploy to cluster
kubectl kustomize k8s/ | kubectl apply -f -

# Or deploy individually (not recommended)
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/cronjob.yaml
```

#### Step 3: Verify Deployment

```bash
# Check namespace
kubectl get namespace vancity-lens

# Check deployment status
kubectl get deployment -n vancity-lens
kubectl describe deployment vancity-lens-api -n vancity-lens

# Check pod status
kubectl get pods -n vancity-lens
kubectl logs -n vancity-lens -l app=vancity-lens-api

# Check service
kubectl get service -n vancity-lens

# Check ingress
kubectl get ingress -n vancity-lens

# Check cronjob
kubectl get cronjob -n vancity-lens
```

## Production Considerations

### Security
1. Use External Secrets Operator for secret management (GCP Secret Manager)
2. Enable RBAC and network policies
3. Use image signing and verification
4. Enable pod security policies

### Scaling
1. Increase deployment replicas
2. Add HPA (Horizontal Pod Autoscaler)
3. Use pod disruption budgets

### Monitoring
1. Add Prometheus scraping annotations
2. Configure CloudTrace for tracing
3. Set up CloudLogging for logs
4. Create alerts for pod restarts and failures

### Database
1. Use Cloud SQL with private IP
2. Enable automated backups
3. Set up read replicas for scaling
4. Use connection pooling (PgBouncer)

### Networking
1. Set up VPC-native cluster
2. Configure private GKE cluster
3. Use Workload Identity for GCP authentication
4. Enable network policies

## Image Building

Before deploying, build and push the Docker image:

```bash
# Build image
docker build -t REGISTRY/vancity-lens-api:v1.0.0 .

# Push to registry
docker push REGISTRY/vancity-lens-api:v1.0.0

# Update kustomization.yaml with new image tag
```

## Cleanup

To remove all resources:

```bash
# Using Kustomize
kubectl kustomize k8s/ | kubectl delete -f -

# Or delete namespace (removes all resources)
kubectl delete namespace vancity-lens
```

## Troubleshooting

### Pod Not Starting
```bash
kubectl describe pod POD_NAME -n vancity-lens
kubectl logs POD_NAME -n vancity-lens
```

### Image Pull Errors
```bash
# Check image exists in registry
# Verify registry credentials are configured in cluster
# Check imagePullPolicy (set to Always for development)
```

### Health Check Failures
```bash
# Verify /health endpoint exists in FastAPI app
# Check liveness/readiness probe configuration
# Increase initialDelaySeconds if app takes time to start
```

### CronJob Not Running
```bash
# Verify CronJob is created
kubectl get cronjob -n vancity-lens

# Check CronJob status
kubectl describe cronjob vancity-lens-daily-scrape -n vancity-lens

# Manually trigger job for testing
kubectl create job --from=cronjob/vancity-lens-daily-scrape test-scrape -n vancity-lens
```

## Next Steps

1. Configure GCP project and enable required APIs
2. Create GCS bucket for Terraform state
3. Set up GKE cluster
4. Configure kubectl access
5. Update all placeholder values
6. Run Terragrunt to provision infrastructure
7. Deploy Kubernetes manifests
8. Verify application is accessible
9. Set up monitoring and logging

