#!/usr/bin/env bash
set -euo pipefail

#──────────────────────────────────────────────────────────────────────────────
# VanCity Lens — Database Restore Script
# Features:
#   - Restore from pg_dump custom format
#   - Support for GCS bucket or local file restore
#   - Safety checks and production database protection
#   - Pre-restore safety backup
#   - Target database override capability
#   - Comprehensive logging
#──────────────────────────────────────────────────────────────────────────────

# ─── Configuration ───────────────────────────────────────────────────────────

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-vancity_lens}"
DB_USER="${DB_USER:-vancity}"
PGPASSWORD="${PGPASSWORD:-}"

# Restore-specific variables
RESTORE_FILE=""
TARGET_DB="${DB_NAME}"
FORCE_RESTORE="${FORCE_RESTORE:-false}"
CREATE_SAFETY_BACKUP="${CREATE_SAFETY_BACKUP:-true}"
BACKUP_DIR="${BACKUP_DIR:-/tmp/db_backups}"

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="${LOG_FILE:-${BACKUP_DIR}/restore.log}"

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

show_usage() {
    cat << EOF
Usage: restore_db.sh [OPTIONS]

Restore a PostgreSQL database from a backup file.

OPTIONS:
  --file FILE              Path to restore file (local or gs://... for GCS)
  --target-db NAME         Target database name (default: ${DB_NAME})
  --force                  Confirm dangerous restore operations (REQUIRED for production)
  --no-safety-backup       Skip creating safety backup before restore
  --help                   Show this help message

EXAMPLES:
  # Restore from local file
  restore_db.sh --file /tmp/db_backups/vancity_lens_20240101_120000.dump --force

  # Restore from GCS
  restore_db.sh --file gs://vancity-lens-backups/vancity_lens_20240101_120000.dump --force

  # Restore to different database
  restore_db.sh --file backup.dump --target-db staging_db --force

ENVIRONMENT VARIABLES:
  DB_HOST              Database host (default: localhost)
  DB_PORT              Database port (default: 5432)
  DB_NAME              Default database name (default: vancity_lens)
  DB_USER              Database user (default: vancity)
  PGPASSWORD           Database password (for non-local connections)
  BACKUP_DIR           Directory for backups (default: /tmp/db_backups)
  LOG_FILE             Log file path (default: BACKUP_DIR/restore.log)

EOF
    exit 0
}

# ─── Parse Arguments ────────────────────────────────────────────────────────

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --file)
                RESTORE_FILE="$2"
                shift 2
                ;;
            --target-db)
                TARGET_DB="$2"
                shift 2
                ;;
            --force)
                FORCE_RESTORE="true"
                shift
                ;;
            --no-safety-backup)
                CREATE_SAFETY_BACKUP="false"
                shift
                ;;
            --help)
                show_usage
                ;;
            *)
                error_exit "Unknown option: $1"
                ;;
        esac
    done
}

# ─── Pre-restore Validation ─────────────────────────────────────────────────

validate_inputs() {
    log "INFO" "Validating restore inputs..."

    if [[ -z "${RESTORE_FILE}" ]]; then
        error_exit "No restore file specified. Use --file option."
    fi

    if [[ -z "${TARGET_DB}" ]]; then
        error_exit "No target database specified"
    fi

    if [[ "${FORCE_RESTORE}" != "true" ]]; then
        error_exit "Restore operation requires --force flag for safety"
    fi

    # Check if file is local or GCS
    if [[ "${RESTORE_FILE}" == gs://* ]]; then
        validate_gcs_file
    else
        validate_local_file
    fi

    log "INFO" "Input validation passed"
}

validate_local_file() {
    if [[ ! -f "${RESTORE_FILE}" ]]; then
        error_exit "Restore file not found: ${RESTORE_FILE}"
    fi

    local file_size
    file_size=$(stat -f%z "${RESTORE_FILE}" 2>/dev/null || stat -c%s "${RESTORE_FILE}" 2>/dev/null)

    if [[ ${file_size} -le 0 ]]; then
        error_exit "Restore file is empty or invalid"
    fi

    # Verify it is a valid pg_dump file
    if ! pg_restore --list "${RESTORE_FILE}" &>/dev/null; then
        error_exit "File is not a valid PostgreSQL dump: ${RESTORE_FILE}"
    fi

    log "INFO" "Local file validation passed (size: ${file_size} bytes)"
}

validate_gcs_file() {
    if ! command -v gsutil &> /dev/null; then
        error_exit "gsutil not found. Cannot restore from GCS."
    fi

    if ! gsutil -q stat "${RESTORE_FILE}" &>/dev/null; then
        error_exit "GCS file not found: ${RESTORE_FILE}"
    fi

    log "INFO" "GCS file validation passed"
}

# ─── Database Connection Check ──────────────────────────────────────────────

check_database_connection() {
    log "INFO" "Checking database connection..."

    export PGPASSWORD="${PGPASSWORD}"

    if ! pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" &>/dev/null; then
        error_exit "Cannot connect to PostgreSQL at ${DB_HOST}:${DB_PORT}"
    fi

    log "INFO" "Database connection verified"
}

# ─── Create Safety Backup ───────────────────────────────────────────────────

create_safety_backup() {
    if [[ "${CREATE_SAFETY_BACKUP}" != "true" ]]; then
        log "INFO" "Skipping safety backup (--no-safety-backup set)"
        return 0
    fi

    log "INFO" "Creating safety backup of target database: ${TARGET_DB}"

    mkdir -p "${BACKUP_DIR}" || error_exit "Failed to create backup directory"

    local safety_backup="${BACKUP_DIR}/safety_backup_${TARGET_DB}_${TIMESTAMP}.dump"

    export PGPASSWORD="${PGPASSWORD}"

    if ! pg_dump \
        -h "${DB_HOST}" \
        -p "${DB_PORT}" \
        -U "${DB_USER}" \
        -d "${TARGET_DB}" \
        -Fc \
        --no-password \
        -f "${safety_backup}"; then
        log "WARN" "Failed to create safety backup"
        return 1
    fi

    log "INFO" "Safety backup created: ${safety_backup}"
}

# ─── Download File from GCS if Needed ───────────────────────────────────────

prepare_restore_file() {
    if [[ "${RESTORE_FILE}" == gs://* ]]; then
        log "INFO" "Downloading backup from GCS..."

        mkdir -p "${BACKUP_DIR}" || error_exit "Failed to create backup directory"

        local local_file="${BACKUP_DIR}/restore_temp_${TIMESTAMP}.dump"

        if ! gsutil -m cp "${RESTORE_FILE}" "${local_file}"; then
            error_exit "Failed to download backup from GCS"
        fi

        RESTORE_FILE="${local_file}"
        log "INFO" "Backup downloaded to: ${RESTORE_FILE}"
    fi
}

# ─── Drop Target Database (if exists) ───────────────────────────────────────

drop_target_database() {
    log "INFO" "Checking if target database exists: ${TARGET_DB}"

    export PGPASSWORD="${PGPASSWORD}"

    # Check if database exists
    local db_exists
    db_exists=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
        -t -c "SELECT 1 FROM pg_database WHERE datname = '${TARGET_DB}';" 2>/dev/null || echo "0")

    if [[ "${db_exists}" == "1" ]]; then
        log "INFO" "Target database exists, dropping connections and dropping database..."

        # Terminate all connections to target database
        psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres \
            --no-password \
            -c "SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '${TARGET_DB}'
                AND pid <> pg_backend_pid();" &>/dev/null || true

        # Drop the database
        if ! dropdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
            --no-password "${TARGET_DB}" 2>/dev/null; then
            log "WARN" "Failed to drop existing database, attempting restore anyway..."
        fi
    else
        log "INFO" "Target database does not exist, will be created"
    fi
}

# ─── Perform Restore ────────────────────────────────────────────────────────

perform_restore() {
    log "INFO" "Starting database restore from: ${RESTORE_FILE}"

    export PGPASSWORD="${PGPASSWORD}"

    # Create database first
    log "INFO" "Creating target database: ${TARGET_DB}"

    createdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
        --no-password "${TARGET_DB}" 2>/dev/null || log "INFO" "Database already exists"

    # Restore using pg_restore
    log "INFO" "Restoring database contents..."

    if ! pg_restore \
        -h "${DB_HOST}" \
        -p "${DB_PORT}" \
        -U "${DB_USER}" \
        -d "${TARGET_DB}" \
        -v \
        --no-password \
        --no-owner \
        "${RESTORE_FILE}"; then
        error_exit "Database restore failed"
    fi

    log "INFO" "Database restore completed successfully"
}

# ─── Cleanup Temporary Files ────────────────────────────────────────────────

cleanup_temp_files() {
    # Only cleanup if file was downloaded from GCS
    if [[ "${RESTORE_FILE}" == /tmp/db_backups/restore_temp_* ]]; then
        log "INFO" "Cleaning up temporary restore file"
        rm -f "${RESTORE_FILE}"
    fi
}

# ─── Main Execution ─────────────────────────────────────────────────────────

main() {
    log "INFO" "═══════════════════════════════════════════════════════════"
    log "INFO" "VanCity Lens Database Restore Started"
    log "INFO" "Time: ${TIMESTAMP}"
    log "INFO" "Target Database: ${TARGET_DB}"
    log "INFO" "═══════════════════════════════════════════════════════════"

    parse_args "$@"
    validate_inputs
    check_database_connection
    prepare_restore_file
    create_safety_backup
    drop_target_database
    perform_restore
    cleanup_temp_files

    log "INFO" "═══════════════════════════════════════════════════════════"
    log "INFO" "Restore completed successfully"
    log "INFO" "Target Database: ${TARGET_DB}"
    log "INFO" "═══════════════════════════════════════════════════════════"
}

# Execute main function
main "$@"
