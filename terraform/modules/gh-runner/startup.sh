#!/usr/bin/env bash
# GitHub Actions self-hosted runner — idempotent startup script.
# Phase 1 runs once (first boot); Phase 2 runs every boot.
#
# NOTE: This file is processed by Terraform templatefile(). Shell variables
# using double-dollar syntax are escaped so they pass through at runtime.
set -euo pipefail

MARKER="/opt/runner/.provisioned"
RUNNER_HOME="/opt/runner"
RUNNER_USER="runner"

log() { echo "[gh-runner] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

# ── Phase 1: First-boot provisioning ────────────────────────────────────────
if [ ! -f "$MARKER" ]; then
  log "Phase 1 — first-boot provisioning"

  # ── Docker CE ──────────────────────────────────────────────────────────────
  if ! command -v docker &>/dev/null; then
    log "Installing Docker CE"
    apt-get update -y
    apt-get install -y ca-certificates curl gnupg lsb-release jq
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
  fi

  # ── Google Cloud SDK apt repo (needed for kubectl & gke-gcloud-auth-plugin)
  # GCE images have gcloud via snap but not the apt repo, so always add it.
  if [ ! -f /etc/apt/sources.list.d/google-cloud-sdk.list ]; then
    log "Adding Google Cloud SDK apt repo"
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] \
      https://packages.cloud.google.com/apt cloud-sdk main" \
      > /etc/apt/sources.list.d/google-cloud-sdk.list
    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
      | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
    apt-get update -y
  fi

  # ── gcloud CLI ─────────────────────────────────────────────────────────────
  if ! command -v gcloud &>/dev/null; then
    log "Installing gcloud CLI"
    apt-get install -y google-cloud-cli
  fi

  # ── kubectl ────────────────────────────────────────────────────────────────
  if ! command -v kubectl &>/dev/null; then
    log "Installing kubectl"
    apt-get install -y kubectl
  fi

  # ── gke-gcloud-auth-plugin ────────────────────────────────────────────────
  if ! command -v gke-gcloud-auth-plugin &>/dev/null; then
    log "Installing gke-gcloud-auth-plugin"
    apt-get install -y google-cloud-cli-gke-gcloud-auth-plugin
  fi

  # ── Runner user ────────────────────────────────────────────────────────────
  if ! id "$RUNNER_USER" &>/dev/null; then
    log "Creating runner user"
    useradd -m -s /bin/bash "$RUNNER_USER"
    usermod -aG docker "$RUNNER_USER"
  fi

  # ── GitHub Actions runner ─────────────────────────────────────────────────
  mkdir -p "$RUNNER_HOME"
  cd "$RUNNER_HOME"

  RUNNER_VERSION=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
    | jq -r '.tag_name' | sed 's/^v//')
  RUNNER_ARCHIVE="actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz"

  if [ ! -f "$RUNNER_HOME/.runner" ]; then
    log "Downloading runner v$${RUNNER_VERSION}"
    curl -fsSL -o "$RUNNER_ARCHIVE" \
      "https://github.com/actions/runner/releases/download/v$${RUNNER_VERSION}/$${RUNNER_ARCHIVE}"
    tar xzf "$RUNNER_ARCHIVE"
    rm -f "$RUNNER_ARCHIVE"

    # Read PAT from Secret Manager
    GITHUB_PAT=$(gcloud secrets versions access latest \
      --secret="${GITHUB_RUNNER_TOKEN_SECRET}" \
      --project="${GCP_PROJECT_ID}")

    # Exchange PAT for a short-lived registration token
    REG_TOKEN=$(curl -fsSL \
      -X POST \
      -H "Authorization: token $${GITHUB_PAT}" \
      -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/${GITHUB_REPO}/actions/runners/registration-token" \
      | jq -r '.token')

    LABELS="self-hosted,linux,x64"
    if [ -n "${RUNNER_LABELS}" ]; then
      LABELS="$${LABELS},${RUNNER_LABELS}"
    fi

    log "Registering runner '${RUNNER_NAME}' for ${GITHUB_REPO}"
    chown -R "$RUNNER_USER":"$RUNNER_USER" "$RUNNER_HOME"
    sudo -u "$RUNNER_USER" ./config.sh \
      --unattended \
      --replace \
      --url "https://github.com/${GITHUB_REPO}" \
      --token "$REG_TOKEN" \
      --name "${RUNNER_NAME}" \
      --labels "$LABELS" \
      --work "_work"
  fi

  # Install as systemd service
  log "Installing systemd service"
  cd "$RUNNER_HOME"
  ./svc.sh install "$RUNNER_USER"

  touch "$MARKER"
  log "Phase 1 complete"
fi

# ── Phase 2: Every boot ────────────────────────────────────────────────────
log "Phase 2 — boot-time setup"

# Refresh Docker auth for Artifact Registry
log "Configuring Docker credential helper for Artifact Registry"
sudo -u "$RUNNER_USER" gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet 2>/dev/null || true

# Start the runner service
log "Starting actions.runner service"
cd "$RUNNER_HOME"
./svc.sh start || true

log "Startup complete"
