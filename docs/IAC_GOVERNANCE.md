# Terraform and Kustomize Governance

## Scope

This governance applies to:

- `terraform/**` for Cloudflare and GCP infrastructure
- `k8s/**` for Kubernetes manifests and overlays
- `.github/workflows/iac-validate.yml` for IaC policy checks

## Source of Truth

- Terraform is the source of truth for persistent cloud resources.
- Kustomize is the source of truth for Kubernetes runtime configuration by environment.
- Manual console changes are prohibited except break-glass incidents.

## Change Process

1. Create PR with IaC changes.
2. Attach `terraform plan` output artifact (where backend/auth is configured).
3. Ensure `iac-validate` workflow is green.
4. Get required reviewer approval.
5. Apply via CI/CD pipeline or approved operator procedure.

## Break-Glass Process

- Allowed only for production incident mitigation.
- Must open incident ticket and capture exact manual change.
- Must backport the change to Terraform/Kustomize within 24 hours.
- Must run post-incident drift check and close with evidence.

## Drift Management

- Weekly drift detection job should run against production state.
- Any unexpected drift creates a P2 infra issue.
- Drift must be resolved via code, not by repeated console edits.

## Required CI Checks

- `terraform fmt -check`
- `terraform validate`
- `kustomize build` for base/staging/prod overlays
- Optional `terraform plan` (enabled when backend/auth variables are set)
