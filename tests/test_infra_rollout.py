"""Validation tests for active infrastructure rollout tickets.

Covers:
- INFRA-041: Secret Manager-backed K8s secret delivery via External Secrets
- INFRA-042: CronJob reliability controls
- INFRA-053: Staging deployment workflow
"""

from pathlib import Path

import yaml


ROOT = Path(__file__).parent.parent
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
K8S_DIR = ROOT / "k8s"


def _load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_staging_deploy_workflow_exists():
    workflow_path = WORKFLOWS_DIR / "deploy-staging.yml"
    assert workflow_path.exists(), f"Missing workflow: {workflow_path}"


def test_staging_deploy_workflow_uses_self_hosted_runner():
    workflow = _load_yaml(WORKFLOWS_DIR / "deploy-staging.yml")
    jobs = workflow.get("jobs", {})
    deploy_job = jobs.get("deploy-staging")
    assert deploy_job is not None, "deploy-staging job is missing"

    runs_on = deploy_job.get("runs-on")
    assert isinstance(runs_on, list), "runs-on should be a list"
    assert "self-hosted" in runs_on, "staging deploy must use self-hosted runner"


def test_staging_deploy_workflow_applies_staging_overlay_and_smokes():
    workflow = _load_yaml(WORKFLOWS_DIR / "deploy-staging.yml")
    steps = workflow["jobs"]["deploy-staging"]["steps"]

    deploy_steps = [s for s in steps if s.get("name") == "Deploy Staging Overlay"]
    assert deploy_steps, "Missing Deploy Staging Overlay step"
    deploy_run = deploy_steps[0].get("run", "")
    assert (
        "kubectl apply -k k8s/overlays/staging" in deploy_run
        or "kubectl kustomize --load-restrictor=LoadRestrictionsNone k8s/overlays/staging | kubectl apply -f -" in deploy_run
    )

    smoke_steps = [s for s in steps if s.get("name") == "API Smoke Tests"]
    assert smoke_steps, "Missing API Smoke Tests step"
    smoke_run = smoke_steps[0].get("run", "")
    assert "/health" in smoke_run
    assert "/ready" in smoke_run


def test_staging_overlay_uses_external_secret_pattern():
    kustomization = _load_yaml(K8S_DIR / "overlays" / "staging" / "kustomization.yaml")
    resources = set(kustomization.get("resources", []))

    assert "../../secret.yaml" not in resources
    assert "secretstore.yaml" in resources
    assert "externalsecret.yaml" in resources


def test_prod_overlay_uses_external_secret_pattern():
    kustomization = _load_yaml(K8S_DIR / "overlays" / "prod" / "kustomization.yaml")
    resources = set(kustomization.get("resources", []))

    assert "../../secret.yaml" not in resources
    assert "secretstore.yaml" in resources
    assert "externalsecret.yaml" in resources


def test_external_secret_maps_required_keys_for_runtime():
    ext_secret = _load_yaml(K8S_DIR / "overlays" / "prod" / "externalsecret.yaml")
    entries = ext_secret.get("spec", {}).get("data", [])
    keys = {item.get("secretKey") for item in entries}

    expected_keys = {
        "database-url",
        "anthropic-api-key",
        "cohere-api-key",
        "k2-api-key",
        "brave-search-api-key",
        "admin-api-key",
    }
    assert keys >= expected_keys


def test_daily_scrape_cronjob_has_reliability_controls():
    cronjob = _load_yaml(K8S_DIR / "cronjob.yaml")
    spec = cronjob.get("spec", {})
    job_spec = spec.get("jobTemplate", {}).get("spec", {})

    assert spec.get("concurrencyPolicy") == "Forbid"
    assert isinstance(spec.get("startingDeadlineSeconds"), int)
    assert isinstance(job_spec.get("backoffLimit"), int)
    assert isinstance(job_spec.get("activeDeadlineSeconds"), int)
    assert isinstance(job_spec.get("ttlSecondsAfterFinished"), int)


def test_k2_ingest_cronjob_has_reliability_controls():
    cronjob = _load_yaml(K8S_DIR / "cronjob-k2-ingest.yaml")
    spec = cronjob.get("spec", {})
    job_spec = spec.get("jobTemplate", {}).get("spec", {})

    assert spec.get("concurrencyPolicy") == "Forbid"
    assert isinstance(spec.get("startingDeadlineSeconds"), int)
    assert isinstance(job_spec.get("backoffLimit"), int)
    assert isinstance(job_spec.get("activeDeadlineSeconds"), int)
    assert isinstance(job_spec.get("ttlSecondsAfterFinished"), int)
