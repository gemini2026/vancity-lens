# VanCity Lens Database Backup and Restore Guide

This guide covers the production database backup and restore infrastructure for VanCity Lens (VCL-65: INFRA-011).

## Overview

The backup and restore system provides:

- **Full database backups** using pg_dump with compression (custom format -Fc)
- **Multi-destination support**: Local storage and GCP Cloud Storage (GCS)
- **Safety features**: Pre-backup health checks, post-backup verification, pre-restore safety backups
- **Retention policies**: Automatic cleanup of old backups (30-day default)
- **Scheduled automation**: Cron wrapper with concurrent operation locking
- **Notifications**: Slack integration for backup status alerts
- **Flexibility**: Support for both local PostgreSQL and GCP Cloud SQL

## Files

### Core Scripts

1. **backup_db.sh** (287 lines)
   - Full database backup with compression
   - Health checks and verification
   - GCS bucket upload support
   - Retention policy enforcement
   - Comprehensive logging

2. **restore_db.sh** (335 lines)
   - Restore from local or GCS backups
   - Safety checks and confirmations
   - Pre-restore safety backups
   - Target database override capability
   - Connection and file validation

3. **backup_cron.sh** (168 lines)
   - Cron scheduling wrapper
   - Concurrent operation locking (1-hour timeout)
   - Slack notifications
   - Error handling and logging

### Tests

- **test_db_backup.py** (126 tests)
  - Comprehensive test coverage for all scripts
  - Tests organized by functionality
  - All tests use mocked external calls

## Quick Start

### Backup

#### Local PostgreSQL

```bash
# Basic backup
./scripts/backup_db.sh

# Custom database
DB_NAME=my_custom_db ./scripts/backup_db.sh

# With remote password
PGPASSWORD="secure_password" ./scripts/backup_db.sh
```

#### GCP Cloud SQL

```bash
# Enable Cloud SQL backup
USE_CLOUD_SQL=true \
GCP_PROJECT_ID=my-project \
DB_INSTANCE_NAME=my-db-instance \
./scripts/backup_db.sh
```

#### With GCS Upload

```bash
# Backup and upload to GCS bucket
GCS_BACKUP_BUCKET=gs://my-backups \
./scripts/backup_db.sh
```

### Restore

#### From Local File

```bash
# Restore with safety backup and confirmation
./scripts/restore_db.sh \
  --file /tmp/db_backups/vancity_lens_20240101_120000.dump \
  --force

# Restore to different database
./scripts/restore_db.sh \
  --file /tmp/db_backups/vancity_lens_20240101_120000.dump \
  --target-db staging_db \
  --force
```

#### From GCS

```bash
# Restore from GCS bucket
./scripts/restore_db.sh \
  --file gs://my-backups/vancity_lens_20240101_120000.sql.gz \
  --force
```

#### Without Safety Backup

```bash
# Restore without pre-restore safety backup
./scripts/restore_db.sh \
  --file backup.dump \
  --no-safety-backup \
  --force
```

### Scheduled Backups

Add to crontab with notifications:

```bash
# Daily at 2 AM UTC
0 2 * * * SLACK_WEBHOOK_URL=https://hooks.slack.com/... /path/to/backup_cron.sh

# Weekly Sundays at 3 AM UTC
0 3 * * 0 SLACK_WEBHOOK_URL=https://hooks.slack.com/... /path/to/backup_cron.sh

# Monthly on 1st at 4 AM UTC
0 4 1 * * SLACK_WEBHOOK_URL=https://hooks.slack.com/... /path/to/backup_cron.sh
```

## Configuration

### Environment Variables

#### backup_db.sh

| Variable | Default | Description |
|----------|---------|-------------|
| DB_HOST | localhost | PostgreSQL host |
| DB_PORT | 5432 | PostgreSQL port |
| DB_NAME | vancity_lens | Database name |
| DB_USER | vancity | Database user |
| PGPASSWORD | (none) | Database password |
| GCS_BACKUP_BUCKET | gs://vancity-lens-backups | GCS bucket for backups |
| BACKUP_RETENTION_DAYS | 30 | Days to keep daily backups |
| BACKUP_DIR | /tmp/db_backups | Local backup directory |
| LOG_FILE | BACKUP_DIR/backup.log | Log file path |
| USE_CLOUD_SQL | false | Use GCP Cloud SQL |
| GCP_PROJECT_ID | (none) | GCP project ID |
| DB_INSTANCE_NAME | (none) | Cloud SQL instance name |

#### restore_db.sh

| Variable | Default | Description |
|----------|---------|-------------|
| DB_HOST | localhost | PostgreSQL host |
| DB_PORT | 5432 | PostgreSQL port |
| DB_NAME | vancity_lens | Default database name |
| DB_USER | vancity | Database user |
| PGPASSWORD | (none) | Database password |
| BACKUP_DIR | /tmp/db_backups | Backup directory |
| LOG_FILE | BACKUP_DIR/restore.log | Log file path |

#### backup_cron.sh

| Variable | Default | Description |
|----------|---------|-------------|
| BACKUP_DIR | /tmp/db_backups | Backup directory |
| SLACK_WEBHOOK_URL | (none) | Slack webhook for notifications |
| SLACK_CHANNEL | #operations | Slack channel |
| SLACK_USERNAME | Database Backup Bot | Slack username |

## Features

### Pre-backup Health Check

The backup script verifies database accessibility before attempting backup:

- For local PostgreSQL: Uses `pg_isready` for connection check
- For Cloud SQL: Validates instance exists and database is accessible
- Exits with error if database is unreachable
- Logs all health check operations

### Post-backup Verification

Backups are verified for integrity:

- Checks file exists and is not empty
- Tests restore header with `pg_restore --list`
- Verifies GCS uploads with `gsutil stat`
- Detects corrupted backups and cleans them up

### Retention Policy

Automatic cleanup maintains storage efficiency:

- Keeps last 30 daily backups (configurable)
- Supports ~48 total backups per system
- Uses `find` for age-based deletion (local backups)
- Uses `gsutil ls` for GCS cleanup
- Respects BACKUP_RETENTION_DAYS environment variable

### Safety Features

#### Pre-restore Safety Backup

Before restoring over a database:

1. Creates backup of target database (custom format)
2. Names backup as `safety_backup_[dbname]_[timestamp].dump`
3. Stores in BACKUP_DIR with other backups
4. Skippable with `--no-safety-backup` flag
5. Allows recovery if restore fails

#### Restore Confirmations

Restore operation requires explicit confirmation:

1. Must specify `--file` with backup location
2. Must use `--force` flag to confirm operation
3. Must specify target database (defaults to DB_NAME)
4. Terminates existing connections before restore
5. Logs all operations for audit trail

### GCS Integration

Upload and restore from Google Cloud Storage:

- Uses `gsutil` for GCS operations
- Supports parallel uploads with `-m` flag
- Cloud SQL exports directly to GCS
- Automatic retention applies to GCS backups
- Downloads to temporary file for restore

### Slack Notifications

Backup status notifications:

- Sends to configured Slack webhook
- Includes timestamp and hostname
- Color-coded: green (success), red (failure), yellow (warning)
- Optional - skipped if SLACK_WEBHOOK_URL not set
- Includes backup exit code on failures

### Concurrent Operation Locking

Prevents simultaneous backups:

- Lock file: `BACKUP_DIR/.backup.lock`
- Lock timeout: 1 hour (stale lock cleanup)
- Exits gracefully if backup already running
- Uses `trap` to release lock on exit
- Prevents resource contention on production database

## Monitoring and Logging

### Log Files

Location varies by script:

- **backup_db.sh**: `BACKUP_DIR/backup.log` (default: `/tmp/db_backups/backup.log`)
- **restore_db.sh**: `BACKUP_DIR/restore.log` (default: `/tmp/db_backups/restore.log`)
- **backup_cron.sh**: `BACKUP_DIR/cron.log` (default: `/tmp/db_backups/cron.log`)

### Log Format

Each log entry includes:

```
[YYYY-MM-DD HH:MM:SS] [LEVEL] message
```

Log levels:
- INFO: Normal operations
- WARN: Non-fatal issues
- ERROR: Fatal errors

### Monitoring Examples

```bash
# Watch backup in real-time
tail -f /tmp/db_backups/backup.log

# Check backup status
grep "Backup completed" /tmp/db_backups/backup.log | tail -1

# List all backups
ls -lh /tmp/db_backups/vancity_lens_*.dump

# Check GCS backups
gsutil ls -h gs://vancity-lens-backups/

# Find failed backups
grep ERROR /tmp/db_backups/backup.log
```

## Error Handling

### Common Issues

#### Cannot connect to database

**Error**: "Cannot connect to PostgreSQL at [host]:[port]"

**Solution**:
- Verify host and port are correct
- Check database is running
- Verify firewall rules allow connection
- Check PGPASSWORD is correct

#### Backup file is corrupted

**Error**: "Backup file is corrupted or not a valid pg_dump file"

**Solution**:
- Backup file exists but is invalid
- Check disk space during backup
- Verify pg_dump completed successfully
- Check backup.log for more details

#### GCS upload failed

**Error**: "Failed to upload backup to GCS"

**Solution**:
- Verify gsutil is installed and configured
- Check GCP credentials are valid
- Verify GCS_BACKUP_BUCKET exists and is accessible
- Check network connectivity to GCS

#### Restore requires --force flag

**Error**: "Restore operation requires --force flag for safety"

**Solution**:
- This is intentional safety measure
- Add `--force` flag to restore command
- Ensures administrator consciously confirms restore

#### Lock already exists

**Error**: "Backup already in progress (lock age: XXs). Exiting."

**Solution**:
- Another backup is running
- Wait for previous backup to complete
- If backup is hung, manually delete lock file:
  ```bash
  rm /tmp/db_backups/.backup.lock
  ```
- Lock expires after 1 hour automatically

## Testing

### Running Tests

```bash
# Run all database backup tests
python -m pytest tests/test_db_backup.py -v

# Run specific test class
python -m pytest tests/test_db_backup.py::TestBackupScriptStructure -v

# Run with coverage
python -m pytest tests/test_db_backup.py --cov=scripts --cov-report=html
```

### Test Coverage

126 tests organized by functionality:

- Script structure and setup (7 tests)
- Configuration and defaults (10 tests)
- Health checks and verification (7 tests)
- Backup execution (7 tests)
- Backup verification (7 tests)
- GCS integration (6 tests)
- Retention policy (6 tests)
- Restore safety (6 tests)
- Pre-restore backups (6 tests)
- Restore file handling (7 tests)
- Restore execution (6 tests)
- Cron wrapper structure (5 tests)
- Cron locking (7 tests)
- Cron Slack notifications (8 tests)
- Cron backup execution (4 tests)
- Environment variables (5 tests)
- Error handling (6 tests)
- Logging and monitoring (8 tests)
- Documentation (4 tests)

## Production Setup

### Step 1: Create Backup Directory

```bash
sudo mkdir -p /var/lib/database_backups
sudo chown postgres:postgres /var/lib/database_backups
sudo chmod 700 /var/lib/database_backups
```

### Step 2: Configure Cron Job

```bash
# Add to /etc/cron.d/database-backups

# Daily at 2 AM UTC
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
0 2 * * * root BACKUP_DIR=/var/lib/database_backups /opt/scripts/backup_cron.sh

# Weekly on Sundays at 3 AM UTC
0 3 * * 0 root BACKUP_DIR=/var/lib/database_backups /opt/scripts/backup_cron.sh

# Monthly on 1st at 4 AM UTC
0 4 1 * * root BACKUP_DIR=/var/lib/database_backups /opt/scripts/backup_cron.sh
```

### Step 3: Test Backup

```bash
# Run manual backup
BACKUP_DIR=/var/lib/database_backups ./scripts/backup_db.sh

# Verify backup was created
ls -lh /var/lib/database_backups/vancity_lens_*.dump
```

### Step 4: Test Restore

```bash
# Create test database for restore testing
createdb test_restore

# Test restore
./scripts/restore_db.sh \
  --file /var/lib/database_backups/vancity_lens_latest.dump \
  --target-db test_restore \
  --force

# Verify restore
psql test_restore -c "SELECT COUNT(*) FROM information_schema.tables;"

# Cleanup
dropdb test_restore
```

### Step 5: Enable Slack Notifications

1. Create Slack webhook in your workspace
2. Add to cron environment:
   ```bash
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```
3. Verify notifications by running backup_cron.sh manually

## Cloud SQL Specific Setup

### Enable Cloud SQL Backups

```bash
# Use gcloud sql export for Cloud SQL (recommended)
USE_CLOUD_SQL=true \
GCP_PROJECT_ID=your-project \
DB_INSTANCE_NAME=vancity-lens-db \
./scripts/backup_db.sh
```

### Automated Cloud SQL Backups

```bash
# Configure in cron with Cloud SQL settings
GCP_PROJECT_ID=your-project \
DB_INSTANCE_NAME=vancity-lens-db \
USE_CLOUD_SQL=true \
0 2 * * * root /opt/scripts/backup_cron.sh
```

### Restore from Cloud SQL Backup

```bash
# Download from GCS and restore
./scripts/restore_db.sh \
  --file gs://your-project-cloudsql/backup.sql.gz \
  --target-db production_restore \
  --force
```

## Troubleshooting

### Check Script Syntax

```bash
# Check backup_db.sh
bash -n scripts/backup_db.sh

# Check restore_db.sh
bash -n scripts/restore_db.sh

# Check backup_cron.sh
bash -n scripts/backup_cron.sh
```

### Enable Debug Mode

```bash
# Run with debug output
bash -x ./scripts/backup_db.sh 2>&1 | head -100
```

### Verify Executable Permissions

```bash
# Check permissions
ls -la scripts/backup_db.sh scripts/restore_db.sh scripts/backup_cron.sh

# Fix if needed
chmod +x scripts/backup_db.sh
chmod +x scripts/restore_db.sh
chmod +x scripts/backup_cron.sh
```

### Check Dependencies

```bash
# Verify pg_dump is installed
which pg_dump

# Verify pg_restore is installed
which pg_restore

# Verify pg_isready is installed
which pg_isready

# For Cloud SQL: verify gcloud is installed
which gcloud

# For GCS: verify gsutil is installed
which gsutil
```

## Support

For issues or questions:

1. Check logs in `BACKUP_DIR/*.log`
2. Review error messages for details
3. Verify environment variables are set
4. Run tests to verify script integrity
5. Check dependencies are installed

## License

VanCity Lens Database Backup Infrastructure (VCL-65 / INFRA-011)
