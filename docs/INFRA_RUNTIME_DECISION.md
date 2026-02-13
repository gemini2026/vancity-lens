# INFRA-001 Runtime Topology Decision

Date: 2026-02-13

## Decision

Production runtime is standardized to:

- Cloudflare edge (DNS, WAF, CDN, TLS)
- GKE for application runtime
- Cloud SQL PostgreSQL as managed primary database
- GCS for document archive + long-term retention

Cloud Run remains optional for non-production experiments only and is not part of production cutover.

## Rationale

- Existing repo already has Kubernetes manifests and cronjobs for ingestion/maintenance.
- Background processing and API runtime are easier to operate with a single GKE control plane.
- Managed Postgres requirements align with Cloud SQL and private networking model.
- Cloudflare edge gives security and caching controls without rewriting backend runtime.

## Consequences

- CI/CD pipeline will target GKE as the production deployment path.
- Terraform + Kustomize become the mandatory infra/app deployment mechanisms.
- Production readiness checks focus on GKE + Cloud SQL + Cloudflare integration.
