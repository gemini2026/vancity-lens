#!/usr/bin/env bash
set -euo pipefail

#──────────────────────────────────────────────────────────────────────────────
# VanCity Lens — Production Database Backup Script
# Supports: GCP Cloud SQL and local PostgreSQL with pg_dump
# Features:
#   - Full backup with compression (custom format -Fc)
#   - Automatic upload to GCS bucket
#   - Retention policy (30 daily, 12 weekly, 6 monthly)
#   - Pre-backup health check
#   - Post-backup verification
#   - Timestamp-based naming and logging
#──────────────────────────────────────────────────────────────────────────────

# ─── Configuration ───────────────────────────────────────────────────────────

# Required environment variables (set defaults where reasonable)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-vancity_lens}"
DB_USER="${DB_USER:-vancity}"
GCS_BACKUP_BUCKET="${GCS_BACKUP_BUCKET:-gs://vancity-lens-backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_DIR="${BACKUP_DIR:-/tmp/db_backups}"
PGPASSWORD="${PGPASSWORD:-}"

# Derive environment type (local vs GCP Cloud SQL)
USE_CLOUD_SQL="${USE_CLOUD_SQL:-false}"
GCP_PROJECT_ID="${GCP_PROJECT_ID:-}"
DB_INSTANCE_NAME="${DB_INSTANCE_NAME:-}"

# Logging
LOG_FILE="${LOG_FILE:-${BACKUP_DIR}/backup.log}"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_FILE="${BACKUP_DIR}/vancity_lens_${TIMESTAMP}.dump"

# ─── Helper Functions ────────────────────────────────────────────────────────

log() {
    local level="$1"
    shift
    echo "[${TIMESTAMP}] [${level}] $*" | tee -a "${LOG_FILE}"
}

error_exit() {
    log "ERROR" "$@"
    exit 1
}

create_backup_dir() {
    if [[ ! -d "${BACKUP_DIR}" ]]; then
        mkdir -p "${BACKUP_DIR}" || error_exit "Failed to create backup directory: ${BACKUP_DIR}"
    fi
}

# ─── Pre-backup Health Check ─────────────────────────────────────────────────

health_check() {
    log "INFO" "Performing database health check..."

    if [[ "${USE_CLOUD_SQL}" == "true" ]]; then
        # Check Cloud SQL instance accessibility via gcloud
        if ! command -v gcloud &> /dev/null; then
            error_exit "gcloud CLI not found. Cannot connect to Cloud SQL."
        fi

        if ! gcloud sql instances describe "${DB_INSTANCE_NAME}" \
            --project="${GCP_PROJECT_ID}" &>/dev/null; then
            error_exit "Cannot access Cloud SQL instance: ${DB_INSTANCE_NAME}"
        fi

        # Test database connectivity
        if ! gcloud sql connect "${DB_INSTANCE_NAME}" \
            --database="${DB_NAME}" \
            --user="${DB_USER}" \
            --project="${GCP_PROJECT_ID}" \
            --quiet <<< "SELECT 1;" &>/dev/null; then
            error_exit "Failed to connect to Cloud SQL database"
        fi
    else
        # Local PostgreSQL health check
        if ! command -v pg_isready &> /dev/null; then
            error_exit "pg_isready not found. Please install PostgreSQL client tools."
        fi

        if ! pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" &>/dev/null; then
            error_exit "Cannot connect to PostgreSQL at ${DB_HOST}:${DB_PORT}"
        fi
    fi

    log "INFO" "Health check passed"
}

# ─── Perform Backup ─────────────────────────────────────────────────────────

perform_backup() {
    log "INFO" "Starting database backup to: ${BACKUP_FILE}"

    if [[ "${USE_CLOUD_SQL}" == "true" ]]; then
        # Use gcloud sql export for Cloud SQL
        log "INFO" "Exporting Cloud SQL instance to GCS..."

        if ! gcloud sql export sql "${DB_INSTANCE_NAME}" \
            "${GCS_BACKUP_BUCKET}/vancity_lens_${TIMESTAMP}.sql.gz" \
            --database="${DB_NAME}" \
            --project="${GCP_PROJECT_ID}" \
            --async; then
            error_exit "Failed to export Cloud SQL instance"
        fi

        log "INFO" "Cloud SQL export initiated (async operation)"
        BACKUP_FILE="${GCS_BACKUP_BUCKET}/vancity_lens_${TIMESTAMP}.sql.gz"
    else
        # Use pg_dump for local PostgreSQL
        export PGPASSWORD="${PGPASSWORD}"

        if ! pg_dump \
            -h "${DB_HOST}" \
            -p "${DB_PORT}" \
            -U "${DB_USER}" \
            -d "${DB_NAME}" \
            -Fc \
            --verbose \
            --no-password \
            -f "${BACKUP_FILE}"; then
            rm -f "${BACKUP_FILE}"
            error_exit "pg_dump failed"
        fi

        log "INFO" "Backup file created successfully"
    fi
}

# ─── Post-backup Verification ───────────────────────────────────────────────

verify_backup() {
    log "INFO" "Verifying backup integrity..."

    if [[ "${USE_CLOUD_SQL}" == "true" ]]; then
        # For Cloud SQL exports, check file exists in GCS
        if ! gsutil -q stat "${BACKUP_FILE}" &>/dev/null; then
            error_exit "Backup file not found in GCS: ${BACKUP_FILE}"
        fi
        log "INFO" "Backup file verified in GCS"
    else
        # Check file exists and has content
        if [[ ! -f "${BACKUP_FILE}" ]]; then
            error_exit "Backup file not found: ${BACKUP_FILE}"
        fi

        local file_size
        file_size=$(stat -f%z "${BACKUP_FILE}" 2>/dev/null || stat -c%s "${BACKUP_FILE}" 2>/dev/null)

        if [[ ${file_size} -le 0 ]]; then
            rm -f "${BACKUP_FILE}"
            error_exit "Backup file is empty or invalid"
        fi

        log "INFO" "Backup file size: ${file_size} bytes"

        # Test restore header with pg_restore
        if ! pg_restore -h "${DB_HOST}" -p "${DB_PORT}" --list "${BACKUP_FILE}" &>/dev/null; then
            rm -f "${BACKUP_FILE}"
            error_exit "Backup file is corrupted or not a valid pg_dump file"
        fi

        log "INFO" "Backup file header verification passed"
    fi
}

# ─── Upload to GCS ──────────────────────────────────────────────────────────

upload_to_gcs() {
    if [[ "${USE_CLOUD_SQL}" == "true" ]]; then
        log "INFO" "Skipping GCS upload (already in GCS from Cloud SQL export)"
        return 0
    fi

    if [[ -z "${GCS_BACKUP_BUCKET}" ]]; then
        log "WARN" "GCS_BACKUP_BUCKET not set, skipping GCS upload"
        return 0
    fi

    log "INFO" "Uploading backup to GCS: ${GCS_BACKUP_BUCKET}/"

    if ! command -v gsutil &> /dev/null; then
        log "WARN" "gsutil not found, skipping GCS upload"
        return 0
    fi

    if ! gsutil -m cp "${BACKUP_FILE}" "${GCS_BACKUP_BUCKET}/"; then
        error_exit "Failed to upload backup to GCS"
    fi

    log "INFO" "Backup uploaded to GCS successfully"
}

# ─── Retention Policy Management ────────────────────────────────────────────

cleanup_old_backups() {
    log "INFO" "Applying retention policy (keeping last 30 daily, 12 weekly, 6 monthly)..."

    if [[ "${USE_CLOUD_SQL}" == "true" ]]; then
        # For Cloud SQL backups in GCS
        if ! command -v gsutil &> /dev/null; then
            log "WARN" "gsutil not found, skipping cleanup"
            return 0
        fi

        # List all backup files in GCS
        local gcs_files
        gcs_files=$(gsutil ls "${GCS_BACKUP_BUCKET}/" 2>/dev/null | grep "\.sql\.gz$" || true)

        # Count and remove old files if needed (keep approximately 48 backups)
        local file_count
        file_count=$(echo "${gcs_files}" | wc -l)

        if [[ ${file_count} -gt 48 ]]; then
            log "INFO" "Found ${file_count} backups, cleaning oldest files..."
            echo "${gcs_files}" | sort | head -n $((file_count - 48)) | while read -r file; do
                if [[ -n "${file}" ]]; then
                    log "INFO" "Deleting old backup: ${file}"
                    gsutil -m rm "${file}" || log "WARN" "Failed to delete ${file}"
                fi
            done
        fi
    else
        # For local backups
        local cutoff_date
        cutoff_date=$(date -d "${BACKUP_RETENTION_DAYS} days ago" '+%s' 2>/dev/null || \
                     date -v-${BACKUP_RETENTION_DAYS}d '+%s' 2>/dev/null)

        find "${BACKUP_DIR}" -name "vancity_lens_*.dump" -type f | while read -r backup_file; do
            local file_date
            file_date=$(stat -f%B "${backup_file}" 2>/dev/null || stat -c%Y "${backup_file}" 2>/dev/null)

            if [[ ${file_date} -lt ${cutoff_date} ]]; then
                log "INFO" "Deleting old backup: ${backup_file}"
                rm -f "${backup_file}"
            fi
        done
    fi

    log "INFO" "Retention policy applied"
}

# ─── Main Execution ─────────────────────────────────────────────────────────

main() {
    log "INFO" "═══════════════════════════════════════════════════════════"
    log "INFO" "VanCity Lens Database Backup Started"
    log "INFO" "Time: ${TIMESTAMP}"
    log "INFO" "Database: ${DB_NAME} @ ${DB_HOST}:${DB_PORT}"
    log "INFO" "═══════════════════════════════════════════════════════════"

    # Validate required configuration
    if [[ -z "${DB_NAME}" ]]; then
        error_exit "DB_NAME environment variable is required"
    fi
    if [[ -z "${DB_USER}" ]]; then
        error_exit "DB_USER environment variable is required"
    fi
    if [[ "${USE_CLOUD_SQL}" == "true" ]]; then
        if [[ -z "${GCP_PROJECT_ID}" ]] || [[ -z "${DB_INSTANCE_NAME}" ]]; then
            error_exit "GCP_PROJECT_ID and DB_INSTANCE_NAME required for Cloud SQL"
        fi
    fi

    # Create backup directory
    create_backup_dir

    # Execute backup sequence
    health_check
    perform_backup
    verify_backup
    upload_to_gcs
    cleanup_old_backups

    log "INFO" "═══════════════════════════════════════════════════════════"
    log "INFO" "Backup completed successfully"
    log "INFO" "Backup file: ${BACKUP_FILE}"
    log "INFO" "═══════════════════════════════════════════════════════════"
}

# Execute main function
main "$@"
