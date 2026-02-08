#!/usr/bin/env bash
set -euo pipefail

#──────────────────────────────────────────────────────────────────────────────
# VanCity Lens — Backup Cron Wrapper
# Scheduled backup automation with locking and Slack notifications
#
# Recommended cron schedules:
#   0 2 * * *   /path/to/backup_cron.sh  (daily at 2 AM UTC)
#   0 3 * * 0   /path/to/backup_cron.sh  (weekly Sundays at 3 AM UTC)
#   0 4 1 * *   /path/to/backup_cron.sh  (monthly 1st at 4 AM UTC)
#──────────────────────────────────────────────────────────────────────────────

# ─── Configuration ───────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup_db.sh"
BACKUP_DIR="${BACKUP_DIR:-/tmp/db_backups}"
LOCK_FILE="${BACKUP_DIR}/.backup.lock"
LOCK_TIMEOUT=3600  # 1 hour timeout

# Slack notification
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
SLACK_CHANNEL="${SLACK_CHANNEL:-#operations}"
SLACK_USERNAME="${SLACK_USERNAME:-Database Backup Bot}"

# Timestamp and logging
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="${BACKUP_DIR}/cron.log"

# ─── Helper Functions ────────────────────────────────────────────────────────

log() {
    local level="$1"
    shift
    echo "[${TIMESTAMP}] [${level}] $*" >> "${LOG_FILE}"
}

acquire_lock() {
    log "INFO" "Attempting to acquire lock..."

    # Check if lock exists and is stale
    if [[ -f "${LOCK_FILE}" ]]; then
        local lock_age
        lock_age=$(($(date +%s) - $(stat -f%m "${LOCK_FILE}" 2>/dev/null || stat -c%Y "${LOCK_FILE}" 2>/dev/null)))

        if [[ ${lock_age} -lt ${LOCK_TIMEOUT} ]]; then
            log "WARN" "Backup already in progress (lock age: ${lock_age}s). Exiting."
            return 1
        fi

        log "INFO" "Lock is stale (age: ${lock_age}s), removing"
        rm -f "${LOCK_FILE}"
    fi

    # Create new lock
    mkdir -p "${BACKUP_DIR}"
    echo "$$ $(date '+%Y-%m-%d %H:%M:%S')" > "${LOCK_FILE}"
    log "INFO" "Lock acquired (PID: $$)"
    return 0
}

release_lock() {
    rm -f "${LOCK_FILE}"
    log "INFO" "Lock released"
}

send_slack_notification() {
    local status="$1"
    local message="$2"

    if [[ -z "${SLACK_WEBHOOK_URL}" ]]; then
        log "INFO" "Slack notifications not configured"
        return 0
    fi

    if ! command -v curl &> /dev/null; then
        log "WARN" "curl not found, cannot send Slack notification"
        return 1
    fi

    local color="good"
    [[ "${status}" == "failure" ]] && color="danger"
    [[ "${status}" == "warning" ]] && color="warning"

    local payload
    payload=$(cat <<EOF
{
    "channel": "${SLACK_CHANNEL}",
    "username": "${SLACK_USERNAME}",
    "attachments": [
        {
            "color": "${color}",
            "title": "Database Backup ${status^^}",
            "text": "${message}",
            "fields": [
                {
                    "title": "Timestamp",
                    "value": "$(date '+%Y-%m-%d %H:%M:%S')",
                    "short": true
                },
                {
                    "title": "Host",
                    "value": "$(hostname)",
                    "short": true
                }
            ]
        }
    ]
}
EOF
)

    if ! curl -X POST \
        -H 'Content-type: application/json' \
        --data "${payload}" \
        "${SLACK_WEBHOOK_URL}" &>/dev/null; then
        log "WARN" "Failed to send Slack notification"
        return 1
    fi

    log "INFO" "Slack notification sent (${status})"
    return 0
}

# ─── Main Execution ─────────────────────────────────────────────────────────

main() {
    log "INFO" "═══════════════════════════════════════════════════════════"
    log "INFO" "Backup Cron Wrapper Started"
    log "INFO" "Time: ${TIMESTAMP}"
    log "INFO" "═══════════════════════════════════════════════════════════"

    # Ensure backup directory exists
    mkdir -p "${BACKUP_DIR}" || {
        log "ERROR" "Failed to create backup directory: ${BACKUP_DIR}"
        exit 1
    }

    # Attempt to acquire lock
    if ! acquire_lock; then
        log "INFO" "Backup already in progress, exiting"
        exit 0
    fi

    # Cleanup on exit
    trap release_lock EXIT

    # Run backup script
    log "INFO" "Executing backup script..."

    if "${BACKUP_SCRIPT}"; then
        log "INFO" "Backup completed successfully"
        send_slack_notification "success" "Database backup completed successfully"
    else
        local exit_code=$?
        log "ERROR" "Backup failed with exit code: ${exit_code}"
        send_slack_notification "failure" "Database backup failed with exit code: ${exit_code}"
        exit "${exit_code}"
    fi

    log "INFO" "═══════════════════════════════════════════════════════════"
    log "INFO" "Backup Cron Wrapper Completed"
    log "INFO" "═══════════════════════════════════════════════════════════"
}

# Execute main function
main "$@"
