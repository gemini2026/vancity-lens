# VanCity Lens - Terraform Infrastructure

This directory contains the complete Terraform infrastructure for VanCity Lens, a FastAPI backend with AI-powered image analysis capabilities.

## Architecture Overview

The infrastructure is deployed on Google Cloud Platform (GCP) with the following components:

### Networking
- **VPC Network**: Private VPC (`10.0.1.0/24`) in us-west1 region (closest to Vancouver)
- **Cloud NAT**: Provides outbound internet access for private resources
- **Cloud Router**: Manages NAT and network routing

### Compute
- **GKE Autopilot Cluster**: Managed Kubernetes cluster with automatic node provisioning
  - Private cluster (nodes not directly accessible from internet)
  - Workload Identity enabled for pod-to-GCP authentication
  - Multiple node pools (primary and backend-specific)
  - Secondary IP ranges for pods (10.1.0.0/16) and services (10.2.0.0/16)

### Database
- **Cloud SQL PostgreSQL 16**: Managed relational database
  - db-f1-micro instance (suitable for POC)
  - 10GB SSD storage
  - Private IP only (accessed via Cloud SQL Auth proxy)
  - Extensions enabled: pgvector (for embeddings), PostGIS (for geospatial queries)
  - Database: `vancity_lens`
  - User: `vancity`

### Container Registry
- **Artifact Registry**: Docker image repository
  - Location: us-west1
  - Pull access granted to GKE service account

### Secrets Management
- **Cloud Secret Manager**: Stores sensitive configuration
  - Anthropic API Key
  - Cohere API Key
  - Database Password
  - Access granted to GKE service account

## Directory Structure

```
terraform/
├── README.md
├── providers.tf                 # GCP provider configuration
├── variables.tf                 # Root-level variables
├── main.tf                      # Root module (calls submodules)
├── outputs.tf                   # Root-level outputs
├── terraform.tfvars.example     # Example variables file
│
└── modules/
    ├── network/                 # VPC, subnets, NAT
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── cloudsql/               # Cloud SQL PostgreSQL
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── gke/                    # GKE Autopilot cluster
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── registry/               # Artifact Registry
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    └── secrets/                # Cloud Secret Manager
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

## Prerequisites

1. **GCP Project**: Create a GCP project and enable billing
2. **Terraform**: Install Terraform 1.0 or later
3. **Google Cloud CLI**: Install `gcloud` CLI tool
4. **Authentication**: Configure GCP credentials:
   ```bash
   gcloud auth application-default login
   ```

## Setup Instructions

### 1. Clone or Download Configuration

```bash
cd /path/to/terraform
```

### 2. Create Variables File

Copy the example file and fill in your values:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your configuration:
```hcl
project_id = "openclaw-antonmishel-03460"
region = "us-west1"
db_password = "your-secure-password"
anthropic_api_key = "sk-..."
cohere_api_key = "..."
```

### 3. Generate Secure Database Password (Optional)

```bash
openssl rand -base64 32
```

### 4. Initialize Terraform

```bash
terraform init
```

### 5. Review Plan

```bash
terraform plan -out=tfplan
```

### 6. Apply Infrastructure

```bash
terraform apply tfplan
```

### 7. Retrieve Outputs

After successful deployment, retrieve important information:

```bash
terraform output
terraform output gke_cluster_name
terraform output cloudsql_connection_name
terraform output artifact_registry_repository_url
```

## Configuration Details

### Network Configuration

- **VPC CIDR**: 10.0.1.0/24
- **Pod CIDR**: 10.1.0.0/16 (secondary range)
- **Service CIDR**: 10.2.0.0/16 (secondary range)
- **Master CIDR**: 172.16.0.0/28 (GKE master)
- **NAT**: Cloud NAT with automatic IP allocation

### GKE Cluster Details

- **Cluster Type**: GKE Autopilot (fully managed)
- **Network**: Private cluster (no public endpoints)
- **Workload Identity**: Enabled
- **Logging**: Google Cloud Logging
- **Monitoring**: Google Cloud Monitoring
- **Node Pools**:
  - Primary pool: 1-3 e2-medium nodes
  - Backend pool: 1-5 e2-medium nodes (backend workloads)

### Cloud SQL Configuration

- **Engine**: PostgreSQL 16
- **Machine Type**: db-f1-micro
- **Storage**: 10GB SSD
- **Backup**: Daily, 7-day retention
- **High Availability**: Not enabled (suitable for POC)
- **Extensions**:
  - pgvector: For semantic search with embeddings
  - PostGIS: For geospatial queries
- **Network**: Private IP only, no public IP

### Secret Manager Secrets

| Secret Name | Purpose |
|---|---|
| `anthropic-api-key` | Claude API for LLM operations |
| `cohere-api-key` | Cohere API for embeddings |
| `database-password` | Cloud SQL authentication |

All secrets are accessible to the GKE service account.

## Required GCP APIs

The following GCP APIs are automatically enabled:

- Compute Engine API
- Kubernetes Engine API
- Cloud SQL Admin API
- Artifact Registry API
- Secret Manager API
- Service Networking API
- Cloud Logging API
- Cloud Monitoring API

## Deployment Duration

Typical deployment time: 15-25 minutes
- Network setup: ~2 minutes
- GKE cluster creation: ~10-15 minutes
- Cloud SQL instance: ~5-10 minutes
- Other resources: ~1-2 minutes

## Scaling and Configuration

### Increase Node Pool Sizes

Edit the node pool autoscaling in `modules/gke/main.tf`:

```hcl
autoscaling {
  min_node_count = 2  # Increase minimum
  max_node_count = 10 # Increase maximum
}
```

### Upgrade Cloud SQL Machine Type

In `modules/cloudsql/main.tf`, change the tier:

```hcl
tier = "db-custom-2-8192"  # 2 vCPU, 8GB RAM
```

### Add More Secrets

In `modules/secrets/main.tf`, create new secret resources following the same pattern.

## Accessing the Infrastructure

### Connect to GKE Cluster

```bash
gcloud container clusters get-credentials vancity-lens-gke \
  --region us-west1 \
  --project openclaw-antonmishel-03460
```

### Access Cloud SQL from GKE

Use Cloud SQL Auth proxy in your pod:

```yaml
containers:
- name: app
  env:
  - name: CLOUDSQL_CONNECTION
    value: "project:region:instance"
  - name: DB_USER
    value: "vancity"
  - name: DB_NAME
    value: "vancity_lens"
```

### Pull Images from Artifact Registry

```bash
# Configure docker authentication
gcloud auth configure-docker us-west1-docker.pkg.dev

# Push image
docker tag my-image:latest \
  us-west1-docker.pkg.dev/PROJECT_ID/vancity-lens-docker/my-image:latest

docker push \
  us-west1-docker.pkg.dev/PROJECT_ID/vancity-lens-docker/my-image:latest
```

## Monitoring and Logging

### Cloud Logging

View GKE cluster logs:
```bash
gcloud logging read "resource.type=k8s_cluster" \
  --limit 50 \
  --format json
```

### Cloud Monitoring

Metrics available:
- Kubernetes container metrics
- Cloud SQL metrics
- Network metrics

Access via: https://console.cloud.google.com/monitoring

## Cleanup and Destruction

To destroy all infrastructure:

```bash
terraform destroy
```

This will:
- Delete GKE cluster
- Delete Cloud SQL instance (with deletion_protection = false)
- Delete VPC and subnets
- Delete NAT and router
- Delete Artifact Registry
- Delete secrets in Cloud Secret Manager

## Troubleshooting

### Terraform Init Fails

Ensure you're authenticated:
```bash
gcloud auth application-default login
gcloud config set project openclaw-antonmishel-03460
```

### GKE Cluster Not Creating

Check if APIs are enabled:
```bash
gcloud services list --enabled --project=openclaw-antonmishel-03460
```

### Cloud SQL Connection Issues

Verify the service networking connection:
```bash
gcloud compute networks peerings list --network=vancity-lens-vpc
```

### Pod Cannot Access Cloud SQL

1. Verify Cloud SQL Auth proxy is running
2. Check the connection name: `project:region:instance`
3. Ensure Cloud SQL user password is correct

## Cost Optimization

For POC environments, consider:

1. Use db-f1-micro (cheapest Cloud SQL option)
2. Set node autoscaling minimums to 1
3. Use preemptible nodes (not configured by default)
4. Enable committed use discounts for long-term deployments
5. Use VPC Flow Logs only when debugging

## Security Best Practices

Implemented in this configuration:

1. **Private VPC**: All resources in private subnet
2. **Private GKE Cluster**: No public endpoints
3. **Private Cloud SQL**: No public IP
4. **Workload Identity**: Pod-to-GCP service account mapping
5. **Secret Manager**: Encrypted secrets with IAM access control
6. **Network Policy**: GKE Network Policy enabled
7. **Shielded Nodes**: Secure boot and integrity monitoring
8. **Cloud NAT**: Outbound traffic through NAT

Additional recommendations:

1. Use Ingress with SSL/TLS for external traffic
2. Implement service account key rotation
3. Enable audit logging
4. Set up VPC Flow Logs for security monitoring
5. Use Binary Authorization for container deployment
6. Implement Pod Security Policies

## Support and Documentation

- Terraform Docs: https://registry.terraform.io/providers/hashicorp/google
- GCP Documentation: https://cloud.google.com/docs
- GKE Autopilot: https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot
- Cloud SQL: https://cloud.google.com/sql/docs

## License

This Terraform configuration is part of the VanCity Lens project.
