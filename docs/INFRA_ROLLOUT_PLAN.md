# Production Infra Rollout Plan (Cloudflare + GKE + Cloud SQL + GCS)

## Goal

Deploy `vancitylense.com` to production-grade infrastructure with:

- Cloudflare for DNS, TLS edge, WAF, CDN, and rate limiting
- GKE as the primary runtime for API, frontend, and background jobs
- Cloud SQL (PostgreSQL) as managed primary database
- Google Cloud Storage (GCS) for document archive and long-term retention
- GitHub Actions with self-hosted runners for CI/CD
- Terraform for all cloud infrastructure and platform resources (no manual console drift)
- Kustomize for Kubernetes workload composition and environment overlays

## Delivery Standards (Terraform + Kustomize)

| Area | Required Tooling | Rule |
|---|---|---|
| Cloudflare (DNS/WAF/rate rules/origin settings) | Terraform (`cloudflare` provider) | No manual Cloudflare dashboard edits in prod; all changes via PR + `terraform apply` |
| GCP infra (VPC, GKE, Cloud SQL, GCS, IAM, Secret Manager, Artifact Registry) | Terraform (`google`/`google-beta`) | No click-ops for persistent resources |
| Kubernetes app/workload config | Kustomize overlays | Environment-specific behavior in overlays; no ad-hoc `kubectl edit` |
| Runner platform (ARC install/config) | Terraform (`helm_release` + Kubernetes provider) + Kustomize where needed | Runner infra versioned and reproducible |
| Policy checks | CI gates | `terraform fmt/validate/plan` + `kustomize build` must pass before merge |

## IaC Guardrails

- All infrastructure changes require PR review and plan output artifact.
- `main` branch must remain drift-free (`terraform plan` against state returns no unexpected changes).
- Emergency console edits are allowed only under incident protocol and must be backported to Terraform within 24 hours.
- Environment overlays must be explicit (`dev`, `staging`, `prod`) and reproducible from repo state.

## Status Legend

| Status | Meaning |
|---|---|
| `TODO` | Not started |
| `IN_PROGRESS` | Implementation in progress |
| `BLOCKED` | Waiting on dependency/decision |
| `DONE` | Completed and validated |

## Target Architecture (Text Diagram)

```text
                                   +-----------------------------+
Users / Browsers ----------------->| Cloudflare                  |
                                   | - DNS (vancitylense.com)    |
                                   | - TLS, WAF, Rate Limits     |
                                   | - CDN/Cache                 |
                                   +-------------+---------------+
                                                 |
                    +----------------------------+----------------------------+
                    |                                                         |
                    v                                                         v
       app.vancitylense.com                                     api.vancitylense.com
                    |                                                         |
                    +----------------------------+----------------------------+
                                                 |
                                                 v
                                   +-----------------------------+
                                   | GKE Ingress / LB            |
                                   +-------------+---------------+
                                                 |
                  +------------------------------+------------------------------+
                  |                                                             |
                  v                                                             v
      +-------------------------+                                  +-------------------------+
      | Frontend Service        |                                  | API Service             |
      | Next.js (container)     |                                  | FastAPI (container)     |
      +-----------+-------------+                                  +-----------+-------------+
                  |                                                            |
                  |                                                            +--------------------+
                  |                                                                                 |
                  |                                                                                 v
                  |                                                     +------------------------------+
                  |                                                     | Cloud SQL PostgreSQL         |
                  |                                                     | - Private IP                 |
                  |                                                     | - HA + backups + PITR        |
                  |                                                     +------------------------------+
                  |
                  |                                                            +--------------------+
                  |                                                            |                    |
                  |                                                            v                    v
                  |                                           +--------------------------+  +--------------------------+
                  |                                           | GCS Archive Bucket       |  | GCS Long-term Bucket     |
                  |                                           | (raw/source docs)        |  | (versioned, retention)   |
                  |                                           +--------------------------+  +--------------------------+
                  |
                  +------------------------------+------------------------------+
                                                 |
                                                 v
                                   +-----------------------------+
                                   | GKE CronJobs / Workers      |
                                   | - Ingestion                 |
                                   | - K2 sync / maintenance     |
                                   +-----------------------------+

   GitHub -> Actions -> Self-hosted Runners (ARC on GKE) -> Artifact Registry -> Deploy to GKE
```

## Environment Strategy

| Environment | Purpose | Domain | Data Policy |
|---|---|---|---|
| `dev` | Engineering testing | internal/dev host | Ephemeral/test data |
| `staging` | Pre-prod validation and soak | `staging.vancitylense.com` | Production-like sanitized dataset |
| `prod` | Live traffic | `app.vancitylense.com`, `api.vancitylense.com` | Full retention, strict backups, auditable changes |

## Monitoring and Logging Architecture

```text
Cloudflare Edge
  ├─ Edge Analytics (traffic, cache, WAF events)
  └─ Security Events (blocked/challenged/rate-limited)
                |
                v
GKE Workloads (Frontend, API, CronJobs, ARC Runners)
  ├─ Metrics: Prometheus/OpenTelemetry -> Google Managed Prometheus
  ├─ Logs: stdout/stderr -> Cloud Logging
  ├─ Traces: OpenTelemetry -> Cloud Trace
  └─ Errors: uncaught exceptions -> Error Reporting/Sentry (optional dual-write)
                |
                v
Cloud Monitoring
  ├─ SLO Dashboards (availability, latency, error budget burn)
  ├─ Alert Policies (pager + Slack)
  └─ Uptime Checks (public API + frontend)
                |
                v
Incident Response
  ├─ Pager channel (P1/P2)
  ├─ Slack incident room
  └─ Runbooks + postmortems
```

## Observability Standards

| Area | Standard |
|---|---|
| Metrics | RED metrics for API (`request rate`, `error rate`, `duration`) and USE metrics for infra (`utilization`, `saturation`, `errors`) |
| Logs | Structured JSON logs only in prod; no plaintext multiline app logs |
| Tracing | End-to-end request tracing with `trace_id` and `request_id` propagation |
| Correlation | Every user-facing request carries `x-request-id` from edge to app and downstream logs |
| Error Tracking | 100% capture of uncaught backend exceptions and job failures |
| SLO ownership | Each SLO has an owner and alert policy with response playbook |

## SLO / Alert Targets (Initial)

| Service | SLI | Target | Paging Threshold |
|---|---|---|---|
| API availability | Successful requests / total requests | 99.9% monthly | Burn-rate alert at 2% budget in 1h |
| API latency | p95 latency for `GET/POST` critical routes | p95 < 1200ms | p95 > 2000ms for 15m |
| Chat/report generation | Endpoint success rate (`/api/v1/intel/chat`, report endpoints) | 99.0% monthly | 5xx > 2% for 10m |
| Cloud SQL | Connection saturation + CPU | < 75% sustained | > 85% for 10m |
| Ingestion cronjobs | Job success rate | 99% weekly | 2 consecutive failures |
| ARC runners | Job queue wait + runner availability | p95 queue wait < 2m | queue wait > 5m for 15m |

## Logging Contract (Prod)

| Field | Required | Example |
|---|---|---|
| `timestamp` | Yes | `2026-02-13T06:30:00Z` |
| `severity` | Yes | `INFO`, `ERROR` |
| `service` | Yes | `api`, `frontend`, `worker`, `runner-controller` |
| `environment` | Yes | `staging`, `prod` |
| `request_id` | Yes for HTTP | `req_abc123` |
| `trace_id` | Yes where tracing enabled | `trace_...` |
| `route` | Yes for HTTP | `/api/v1/intel/chat` |
| `status_code` | Yes for HTTP | `200`, `500` |
| `latency_ms` | Yes for HTTP/job execution | `532.4` |
| `error_code` | On failures | `k2_timeout`, `db_conn_error` |
| `tenant/user_ref` | Optional masked identifier | `usr_...` |

### Logging Guardrails

- Never log API keys, tokens, database credentials, or full PII payloads.
- Hash or truncate user identifiers before logging.
- Route security-sensitive logs to restricted sinks.
- Apply retention by class:
  - Hot operational logs: 30 days
  - Audit/security logs: 180-365 days
  - Cost-optimized archives: GCS sink for long-term storage

## Rollout Backlog

| Backlog | Ticket | Name | Description | Acceptance Criteria | Tests / Validation | Status |
|---|---|---|---|---|---|---|
| Foundation | INFRA-001 | Decide Runtime Topology | Finalize production topology: Cloudflare edge + GKE runtime + Cloud SQL + GCS. Remove ambiguity between GKE and Cloud Run for prod. | Architecture decision approved; one runtime selected for prod; diagram accepted. | Architecture review sign-off in PR/ADR. | `DONE` |
| Foundation | INFRA-002 | Domain and Subdomain Plan | Define DNS records for apex, `www`, `app`, `api`, `staging`, and ownership in Cloudflare. | DNS map documented with target records and proxy mode per host. | Dry-run DNS checklist; verify no hostname conflicts. | `DONE` |
| Foundation | INFRA-003 | Terraform Environment Split | Add `staging` and `prod` Terragrunt environments with isolated state and variables. | `terraform plan` works for both envs without manual edits. | `terraform init/validate/plan` in CI for each env. | `IN_PROGRESS` |
| Foundation | INFRA-004 | Terraform-Only Governance | Enforce Terraform as the source of truth for Cloudflare + GCP infra and document break-glass process. | Governance doc approved; all infra repos have CI guardrails; drift policy active. | Simulated change rejected without plan artifact; drift-check workflow green. | `IN_PROGRESS` |
| Foundation | INFRA-005 | Cloudflare Terraform Bootstrap | Add Cloudflare provider, zone data, and baseline resources (DNS records, SSL mode, WAF/rate rule stubs). | Cloudflare baseline managed by Terraform with remote state and import completed. | `terraform plan` shows managed Cloudflare resources and no unmanaged critical records. | `IN_PROGRESS` |
| Networking | INFRA-010 | VPC and Private Networking Hardening | Finalize private networking for GKE <-> Cloud SQL and egress controls. | GKE workloads access Cloud SQL on private path only; no public DB exposure. | Connectivity test pod; verify Cloud SQL has no public IP. | `TODO` |
| Networking | INFRA-011 | Ingress and TLS Strategy | Configure Ingress/LB and TLS with Cloudflare in front. Stage cert issuance carefully with proxy mode policy. Manage settings via Terraform + Kustomize manifests. | HTTPS works for app/api; no cert errors; secure TLS mode enforced. | SSL Labs check; curl TLS verification; browser trust check. | `TODO` |
| Networking | INFRA-012 | Cloudflare Security Baseline | Set WAF managed rules, bot controls (if needed), and endpoint-specific rate limits. | Baseline WAF/rate limits active for prod hosts. | Security smoke tests; synthetic rate-limit tests on API routes. | `TODO` |
| Database | INFRA-020 | Cloud SQL Production Sizing | Move Cloud SQL from POC class to production-grade tier and HA config. | Cloud SQL is regional HA, backups enabled, PITR enabled, alerts configured. | Failover readiness checklist; backup restore drill in staging. | `TODO` |
| Database | INFRA-021 | DB Migration Pipeline | Add automated schema migration step before deploy. | Migrations run idempotently in staging/prod deployment flow. | Apply + rollback migration test against staging clone. | `TODO` |
| Storage | INFRA-030 | GCS Buckets Provisioning | Create two buckets: document archive (hot/warm) and long-term store (cold retention). | Buckets created with lifecycle, encryption, IAM, versioning policies. | Upload/read/delete tests; verify lifecycle and retention policy simulation. | `IN_PROGRESS` |
| Storage | INFRA-031 | Archive Write Path | Update ingestion/report pipeline to persist source docs and metadata pointers in GCS. | New docs are written to archive bucket with deterministic object keys. | Integration test for ingest -> object exists -> metadata link available. | `TODO` |
| Storage | INFRA-032 | Long-term Retention Policy | Add bucket lifecycle transitions and immutable retention where required. | Retention/lifecycle policies enforced and documented for compliance. | Policy inspection + object age transition test in non-prod. | `TODO` |
| Kubernetes | INFRA-040 | Production K8s Manifests (Kustomize) | Add Kustomize overlays (replicas, resources, HPA, PodDisruptionBudget, anti-affinity) for `staging` and `prod`. | Production overlay deploys without manual patching. | `kustomize build overlays/staging` and `kustomize build overlays/prod` + `kubectl apply --dry-run=server`. | `IN_PROGRESS` |
| Kubernetes | INFRA-041 | Secrets via Secret Manager | Replace static K8s secrets in prod with Secret Manager backed access pattern. | No plaintext prod secrets in Git; runtime secret retrieval works. | Pod startup + secret access smoke; secret rotation test. | `IN_PROGRESS` |
| Kubernetes | INFRA-042 | CronJobs and Worker Reliability | Productionize ingestion/maintenance cronjobs with retries, timeouts, and alerting. | CronJobs have observability and failure alert paths. | Force-fail cronjob and confirm alert delivery. | `IN_PROGRESS` |
| CI/CD | INFRA-050 | ARC Runner Deployment | Deploy GitHub Actions Runner Controller (ARC) with ephemeral runner scale sets. | Self-hosted runner pools available for CI and deploy jobs. | Trigger test workflow using each runner group label. | `TODO` |
| CI/CD | INFRA-051 | OIDC/WIF for GCP Deploy Auth | Use GitHub OIDC + Workload Identity Federation; remove static GCP service account keys. | Deploy workflow authenticates without JSON key secret. | Run deployment workflow and verify token-exchange path only. | `TODO` |
| CI/CD | INFRA-052 | IaC Validation Workflow | Implement CI checks for Terraform + Kustomize (`fmt`, `validate`, `plan`, `kustomize build`, policy checks). | PR cannot merge if IaC checks fail. | Create failing Terraform/Kustomize change and confirm gate blocks merge. | `IN_PROGRESS` |
| CI/CD | INFRA-053 | Staging Deploy Workflow | Implement CI -> build -> push -> deploy -> smoke tests in staging. | Merge to main deploys staging with green smoke tests. | Automated post-deploy health checks + API smoke. | `IN_PROGRESS` |
| CI/CD | INFRA-054 | Production Promotion Workflow | Implement manual-approved promote flow with canary and rollback gates. | Production rollout requires approval and supports one-command rollback. | Canary test + rollback drill in controlled window. | `TODO` |
| Observability | INFRA-060 | Telemetry Stack Baseline | Provision Managed Prometheus, Cloud Monitoring dashboards, Cloud Logging sinks, and Cloud Trace integration points. | All core telemetry backends reachable and receiving data from staging. | Emit synthetic app metric/log/trace and verify ingestion in consoles. | `IN_PROGRESS` |
| Observability | INFRA-061 | App Metrics Instrumentation | Add RED metrics for API and job metrics for cron/worker pipelines. | Critical endpoints and jobs expose metrics with labels (`route`, `status`, `env`). | Unit test instrumentation + scrape verification + dashboard sanity check. | `TODO` |
| Observability | INFRA-062 | Structured Logging and Correlation IDs | Standardize JSON logging fields and propagate `request_id`/`trace_id` through edge, API, jobs, DB calls. | One request can be correlated across Cloudflare, app, and DB-adjacent logs. | Trace walkthrough with a known `request_id` in staging. | `TODO` |
| Observability | INFRA-063 | Alert Policy and Paging Matrix | Configure alert policies for 5xx rate, latency, DB saturation, cron failures, and runner queue delay. | Pager + Slack notifications fire with severity routing and dedup keys. | Alert fire-drill for each alert family and verify escalation chain. | `TODO` |
| Observability | INFRA-064 | SLO and Error Budget Dashboard | Create SLO dashboards and burn-rate alerts for API and critical report/chat paths. | SLO dashboard visible to team with daily burn-rate signal. | Simulate elevated errors in staging and confirm burn-rate alerting. | `TODO` |
| Observability | INFRA-065 | Uptime and Synthetic Monitoring | Add external uptime checks for `app` and `api` plus synthetic journey test. | Scheduled checks run from multiple regions and alert on failures. | Break a staging route intentionally and confirm synthetic alert. | `TODO` |
| Observability | INFRA-066 | Log Retention and Archive Policy | Configure log buckets/sinks for hot retention and long-term GCS archival. | Retention and sink policies match compliance/cost targets. | Validate sink delivery to GCS and retention policy enforcement. | `TODO` |
| Observability | INFRA-067 | Incident Runbooks and On-call Readiness | Create runbooks for top alert classes and define on-call rotation + severity policy. | Runbooks linked from alerts; on-call rota active before prod cutover. | Tabletop incident exercise with timer and action log. | `TODO` |
| Security | INFRA-070 | IAM Least Privilege Review | Tighten IAM for runners, GKE workloads, and service accounts. | IAM matrix reviewed; unused permissions removed. | IAM policy analyzer + privilege review checklist. | `TODO` |
| Security | INFRA-071 | Backup and DR Runbook | Document and validate RTO/RPO for DB and object storage recovery. | DR runbook approved with tested recovery steps. | Full restore simulation in staging and documented timings. | `TODO` |
| Cutover | INFRA-080 | Staging Soak | 5-7 day soak on staging with synthetic and real-like workloads. | Error/latency within thresholds for soak period. | Daily scorecard for SLO/error budget and incident notes. | `TODO` |
| Cutover | INFRA-081 | Production Cutover | Perform phased production cutover with rollback switch ready. | Prod traffic served from new infra with no critical incident. | Cutover checklist + rollback drill + post-cutover validation. | `TODO` |
| Cutover | INFRA-082 | Post-Go-Live Hardening | Address issues from first 2 weeks and lock baseline config. | P1/P2 post-go-live items resolved; baseline tagged. | Postmortem/action-item closure review. | `TODO` |

## Suggested Delivery Order

1. `INFRA-001` through `INFRA-003`
2. `INFRA-004` through `INFRA-005`
3. `INFRA-010` through `INFRA-021`
4. `INFRA-030` through `INFRA-042`
5. `INFRA-050` through `INFRA-054`
6. `INFRA-060` through `INFRA-067`
7. `INFRA-070` through `INFRA-071`
8. `INFRA-080` through `INFRA-082`

## Iteration Rule

Update only the `Status` column and add implementation notes in PRs/issues.  
Do not change acceptance criteria after execution starts unless explicitly approved.

## Execution Snapshot (2026-02-13)

| Ticket | Progress |
|---|---|
| `INFRA-001` | Runtime decision documented (`docs/INFRA_RUNTIME_DECISION.md`) |
| `INFRA-002` | Domain plan documented (`docs/DOMAIN_DNS_PLAN.md`) |
| `INFRA-003` | Staging/prod Terragrunt environment scaffolding created |
| `INFRA-004` | Governance baseline added (`docs/IAC_GOVERNANCE.md`) |
| `INFRA-005` | Cloudflare Terraform module + root wiring scaffolded (disabled by default) |
| `INFRA-030` | Added Terraform storage module for archive + long-term GCS buckets (lifecycle + retention) |
| `INFRA-040` | Added HPA + PDB + anti-affinity/topology spread in staging/prod overlays; kustomize build validated |
| `INFRA-041` | Added staging/prod ExternalSecret + SecretStore manifests; removed static secret resource from environment overlays |
| `INFRA-042` | Added CronJob reliability controls (`concurrencyPolicy`, `backoffLimit`, deadlines, TTL) |
| `INFRA-052` | IaC validation workflow added (`.github/workflows/iac-validate.yml`) |
| `INFRA-053` | Added self-hosted staging deploy workflow with deploy + smoke tests (`.github/workflows/deploy-staging.yml`) |
| `INFRA-060` | Added observability Terraform module (logging bucket + log archive sink + uptime check scaffolding) |
