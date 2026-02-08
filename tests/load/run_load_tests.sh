#!/bin/bash

##############################################################################
# VCL-36: k6 Load Test Runner Script
#
# Executes k6 load testing scenarios and saves results to tests/load/results/
#
# Usage:
#   ./run_load_tests.sh [scenario_name] [base_url] [api_key] [cohere_key]
#
# Examples:
#   ./run_load_tests.sh all
#   ./run_load_tests.sh ramp http://localhost:8000 my-api-key my-cohere-key
#   ./run_load_tests.sh burst
#   ./run_load_tests.sh chat
##############################################################################

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TESTS_DIR="${SCRIPT_DIR}"
K6_SCENARIOS="${TESTS_DIR}/k6_scenarios.js"
RESULTS_DIR="${TESTS_DIR}/results"

# Get environment variables or use defaults
BASE_URL="${2:-http://localhost:8000}"
API_KEY="${3:-test-key-123}"
COHERE_KEY="${4:-test-cohere-key}"
SCENARIO="${1:-all}"

# Timestamp for unique result files
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ─────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────

if [[ ! -f "${K6_SCENARIOS}" ]]; then
    echo "ERROR: k6_scenarios.js not found at ${K6_SCENARIOS}"
    exit 1
fi

if ! command -v k6 &> /dev/null; then
    echo "ERROR: k6 is not installed. Please install k6 from https://k6.io/"
    exit 1
fi

# Ensure results directory exists
mkdir -p "${RESULTS_DIR}"

# ─────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────

log_info() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $*"
}

log_error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

run_scenario() {
    local scenario_name="$1"
    local scenario_key="$2"
    local results_file="${RESULTS_DIR}/${scenario_name}_${TIMESTAMP}.json"
    local summary_file="${RESULTS_DIR}/${scenario_name}_${TIMESTAMP}_summary.txt"

    log_info "Running scenario: ${scenario_name}"
    log_info "Results will be saved to: ${results_file}"

    # Run k6 with the specified scenario
    if k6 run \
        --scenario "${scenario_key}" \
        --out json="${results_file}" \
        --env BASE_URL="${BASE_URL}" \
        --env API_KEY="${API_KEY}" \
        --env COHERE_KEY="${COHERE_KEY}" \
        "${K6_SCENARIOS}" 2>&1 | tee "${summary_file}"; then

        log_info "✓ Scenario '${scenario_name}' completed successfully"
        return 0
    else
        log_error "✗ Scenario '${scenario_name}' failed or had threshold violations"
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────
# Main Execution
# ─────────────────────────────────────────────────────────────────────────

log_info "VanCity Lens k6 Load Testing"
log_info "========================================="
log_info "Project Root: ${PROJECT_ROOT}"
log_info "Results Directory: ${RESULTS_DIR}"
log_info "Base URL: ${BASE_URL}"
log_info "Scenario: ${SCENARIO}"
log_info "Timestamp: ${TIMESTAMP}"
log_info "========================================="

# Initialize test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Run the requested scenario(s)
case "${SCENARIO}" in
    ramp)
        run_scenario "ramp" "ramppScenario" && ((PASSED_TESTS++)) || ((FAILED_TESTS++))
        ((TOTAL_TESTS++))
        ;;

    burst)
        run_scenario "burst" "burstScenario" && ((PASSED_TESTS++)) || ((FAILED_TESTS++))
        ((TOTAL_TESTS++))
        ;;

    chat)
        run_scenario "chat" "chatStressScenario" && ((PASSED_TESTS++)) || ((FAILED_TESTS++))
        ((TOTAL_TESTS++))
        ;;

    all)
        log_info "Running all scenarios..."
        run_scenario "ramp" "ramppScenario" && ((PASSED_TESTS++)) || ((FAILED_TESTS++))
        ((TOTAL_TESTS++))

        run_scenario "burst" "burstScenario" && ((PASSED_TESTS++)) || ((FAILED_TESTS++))
        ((TOTAL_TESTS++))

        run_scenario "chat" "chatStressScenario" && ((PASSED_TESTS++)) || ((FAILED_TESTS++))
        ((TOTAL_TESTS++))
        ;;

    *)
        log_error "Unknown scenario: ${SCENARIO}"
        echo "Valid scenarios: ramp, burst, chat, all"
        exit 1
        ;;
esac

# ─────────────────────────────────────────────────────────────────────────
# Summary Report
# ─────────────────────────────────────────────────────────────────────────

log_info "========================================="
log_info "Test Summary"
log_info "========================================="
log_info "Total scenarios: ${TOTAL_TESTS}"
log_info "Passed: ${PASSED_TESTS}"
log_info "Failed: ${FAILED_TESTS}"
log_info "========================================="

# List generated results
log_info "Generated result files:"
ls -lh "${RESULTS_DIR}" | grep "${TIMESTAMP}" | tail -n +2 | while read -r line; do
    log_info "  ${line}"
done

# Determine exit code
if [[ ${FAILED_TESTS} -eq 0 ]]; then
    log_info "✓ All scenarios completed successfully!"
    exit 0
else
    log_error "✗ Some scenarios failed or had threshold violations"
    exit 1
fi
