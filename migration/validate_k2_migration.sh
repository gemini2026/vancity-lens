#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8080}"
BACKEND="local"
SKIP_E2E=0
SKIP_PYTEST=0
RESTART_API=0

usage() {
  cat <<'EOF'
Usage: migration/validate_k2_migration.sh [--backend local|k2|both] [--api-url URL] [--skip-e2e]

Options:
  --backend   Which RAG backend mode to validate. Default: local
  --api-url   Base API URL. Default: http://localhost:8080
  --skip-e2e  Skip Playwright E2E checks (faster)
  --skip-pytest Skip local pytest suite (useful for validating a remote/staging API)
  --restart-api  Restart Docker Compose `api` service for each backend mode (recommended for local validation)

Environment:
  API_URL              Override API base URL
  K2_API_HOST          Required when backend includes k2
  K2_API_KEY           Required when backend includes k2
  K2_CORPUS_ID         Required when backend includes k2
EOF
}

log() {
  printf '[k2-migration-validate] %s\n' "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend)
      BACKEND="${2:-}"
      shift 2
      ;;
    --api-url)
      API_URL="${2:-}"
      shift 2
      ;;
    --skip-e2e)
      SKIP_E2E=1
      shift
      ;;
    --skip-pytest)
      SKIP_PYTEST=1
      shift
      ;;
    --restart-api)
      RESTART_API=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$BACKEND" != "local" && "$BACKEND" != "k2" && "$BACKEND" != "both" ]]; then
  echo "--backend must be one of: local, k2, both" >&2
  exit 1
fi

require_cmd curl
require_cmd python3

restart_api_service() {
  local backend_mode="$1"
  if [[ "$RESTART_API" -ne 1 ]]; then
    return 0
  fi
  require_cmd docker
  log "Restarting docker compose api service (RAG_BACKEND=${backend_mode})"
  # Use env var substitution in docker-compose.yml.
  export RAG_BACKEND="$backend_mode"
  docker compose up -d --build --force-recreate --no-deps api >/dev/null

  log "Waiting for API health to become ok..."
  local attempts=60
  for ((i=1; i<=attempts; i++)); do
    if curl -sSf "${API_URL}/health" >/dev/null 2>&1; then
      # Ensure status is ok, not just reachable.
      if curl -sSf "${API_URL}/health" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("status")=="ok" else 1)' >/dev/null 2>&1; then
        log "API healthy."
        return 0
      fi
    fi
    sleep 2
  done
  echo "API did not become healthy at ${API_URL}/health after ${attempts} attempts" >&2
  exit 1
}

health_check() {
  log "Health check: ${API_URL}/health"
  local response
  response="$(curl -sSf "${API_URL}/health")"
  printf '%s' "$response" | python3 -c '
import json, sys
data = json.load(sys.stdin)
if data.get("status") != "ok":
    raise SystemExit(f"health status not ok: {data}")
print("health_ok")
'
}

chat_contract_check() {
  local backend_mode="$1"
  log "Chat contract validation (backend=${backend_mode})"

  local response
  response="$(curl -sSf -X POST "${API_URL}/api/v1/intel/chat" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"What Vancouver TOD due diligence risks should I watch this month?\"}")"

  printf '%s' "$response" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
required = ["answer", "citations", "related_signals", "session_id", "mode"]
missing = [k for k in required if k not in payload]
if missing:
    raise SystemExit(f"missing keys: {missing}")
if not isinstance(payload["answer"], str) or not payload["answer"].strip():
    raise SystemExit("answer is empty")
if not isinstance(payload["citations"], list):
    raise SystemExit("citations is not a list")
if not isinstance(payload["related_signals"], list):
    raise SystemExit("related_signals is not a list")
if not isinstance(payload["session_id"], str) or not payload["session_id"].strip():
    raise SystemExit("session_id is empty")
if payload["mode"] not in {"full", "partial", "demo"}:
    raise SystemExit(f"unexpected mode: {payload['mode']}")
for idx, citation in enumerate(payload["citations"][:5], start=1):
    for key in ["document_title", "document_url", "source_type", "relevance_score", "excerpt"]:
        if key not in citation:
            raise SystemExit(f"citation[{idx}] missing key: {key}")
print("chat_contract_ok")
'
}

run_pytest_suite() {
  local backend_mode="$1"
  if [[ "$SKIP_PYTEST" -eq 1 ]]; then
    log "Skipping pytest suite (--skip-pytest)"
    return 0
  fi
  log "Pytest migration parity suite (backend=${backend_mode})"
  RAG_BACKEND="$backend_mode" \
  python3 -m pytest \
    tests/test_api_contracts.py \
    tests/test_routes.py \
    tests/test_chat.py \
    tests/test_external_failures.py \
    tests/test_k2_backend.py \
    tests/test_signals.py \
    tests/test_report_generator.py \
    tests/test_due_diligence.py \
    -q
}

run_e2e_suite() {
  local backend_mode="$1"
  if [[ "$SKIP_E2E" -eq 1 ]]; then
    log "Skipping E2E suite (--skip-e2e)"
    return 0
  fi
  log "Playwright E2E (backend=${backend_mode})"
  (
    cd frontend
    RAG_BACKEND="$backend_mode" API_BASE_URL="$API_URL" npx playwright test e2e/intelligence.spec.ts e2e/e2e-full.spec.ts
  )
}

validate_backend_mode() {
  local backend_mode="$1"
  log "=== Validate backend mode: ${backend_mode} ==="
  export RAG_BACKEND="$backend_mode"
  restart_api_service "$backend_mode"
  health_check
  run_pytest_suite "$backend_mode"
  chat_contract_check "$backend_mode"
  run_e2e_suite "$backend_mode"
  log "=== Validation complete: ${backend_mode} ==="
}

validate_k2_prereqs() {
  local missing=0
  for var in K2_API_HOST K2_API_KEY K2_CORPUS_ID; do
    if [[ -z "${!var:-}" ]]; then
      echo "Missing required env var for k2 validation: $var" >&2
      missing=1
    fi
  done
  if [[ "$missing" -ne 0 ]]; then
    exit 1
  fi
}

if [[ "$BACKEND" == "local" ]]; then
  validate_backend_mode "local"
elif [[ "$BACKEND" == "k2" ]]; then
  validate_k2_prereqs
  validate_backend_mode "k2"
else
  validate_backend_mode "local"
  validate_k2_prereqs
  validate_backend_mode "k2"
fi

log "All requested validation stages passed."
