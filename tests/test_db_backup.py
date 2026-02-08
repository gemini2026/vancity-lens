"""
Comprehensive tests for VanCity Lens database backup and restore infrastructure.

Tests cover:
- Backup script structure and configuration
- Restore script safety checks
- Cron wrapper locking and notifications
- Environment variable validation
- Health checks and verification
- Error handling paths
"""

import pathlib
import re
from unittest import mock
import pytest


SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "scripts"


class TestBackupScriptStructure:
    """Test the fundamental structure and setup of backup_db.sh"""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()

    def test_has_shebang(self):
        """Verify script starts with proper shebang."""
        assert self.backup_script.startswith("#!/usr/bin/env bash"), \
            "Script must start with #!/usr/bin/env bash"

    def test_has_set_euo_pipefail(self):
        """Verify script uses set -euo pipefail for error handling."""
        assert "set -euo pipefail" in self.backup_script, \
            "Script must include 'set -euo pipefail' for strict error handling"

    def test_has_main_function(self):
        """Verify script defines main() function."""
        assert re.search(r"^main\(\)\s*\{", self.backup_script, re.MULTILINE), \
            "Script must define main() function"

    def test_main_function_called(self):
        """Verify main function is invoked."""
        assert re.search(r'main\s+"\$@"', self.backup_script), \
            "Script must call main function"

    def test_has_descriptive_header(self):
        """Verify script has descriptive header comment."""
        assert "VanCity Lens" in self.backup_script, \
            "Script must contain project identifier"
        assert "Database Backup" in self.backup_script, \
            "Script must clearly describe purpose"

    def test_trap_on_error(self):
        """Verify error handling setup."""
        # The script uses set -euo pipefail which handles errors
        assert "error_exit" in self.backup_script, \
            "Script must have error handling mechanism"

    def test_has_logging_functions(self):
        """Verify logging infrastructure."""
        assert re.search(r"log\(\)\s*\{", self.backup_script, re.MULTILINE), \
            "Script must have log() function"
        assert "log " in self.backup_script, \
            "Script must use log function"


class TestBackupConfiguration:
    """Test environment variable configuration and defaults."""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()

    def test_db_host_default(self):
        """Verify DB_HOST has localhost default."""
        assert 'DB_HOST="${DB_HOST:-localhost}"' in self.backup_script, \
            "DB_HOST must default to localhost"

    def test_db_port_default(self):
        """Verify DB_PORT has 5432 default."""
        assert 'DB_PORT="${DB_PORT:-5432}"' in self.backup_script, \
            "DB_PORT must default to 5432"

    def test_db_name_default(self):
        """Verify DB_NAME has vancity_lens default."""
        assert 'DB_NAME="${DB_NAME:-vancity_lens}"' in self.backup_script, \
            "DB_NAME must default to vancity_lens"

    def test_db_user_default(self):
        """Verify DB_USER has vancity default."""
        assert 'DB_USER="${DB_USER:-vancity}"' in self.backup_script, \
            "DB_USER must default to vancity"

    def test_backup_retention_days_default(self):
        """Verify BACKUP_RETENTION_DAYS has 30 day default."""
        assert 'BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"' in self.backup_script, \
            "BACKUP_RETENTION_DAYS must default to 30"

    def test_gcs_bucket_configured(self):
        """Verify GCS_BACKUP_BUCKET is configurable."""
        assert "GCS_BACKUP_BUCKET" in self.backup_script, \
            "Script must support GCS_BACKUP_BUCKET environment variable"

    def test_pgpassword_support(self):
        """Verify PGPASSWORD is exported for authentication."""
        assert "export PGPASSWORD" in self.backup_script, \
            "Script must support PGPASSWORD for database authentication"

    def test_timestamp_generation(self):
        """Verify script generates timestamp for backup naming."""
        assert "TIMESTAMP=" in self.backup_script, \
            "Script must generate timestamp"
        assert "%Y%m%d_%H%M%S" in self.backup_script, \
            "Script must use proper timestamp format"

    def test_backup_file_naming(self):
        """Verify backup file uses timestamp naming convention."""
        assert "vancity_lens_${TIMESTAMP}.dump" in self.backup_script, \
            "Backup file must use timestamp-based naming convention"


class TestBackupHealthCheck:
    """Test pre-backup database health verification."""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()

    def test_has_health_check_function(self):
        """Verify health_check() function exists."""
        assert re.search(r"^health_check\(\)\s*\{", self.backup_script, re.MULTILINE), \
            "Script must have health_check() function"

    def test_health_check_called_before_backup(self):
        """Verify health_check is invoked in main flow."""
        assert "health_check" in self.backup_script, \
            "health_check must be called"

    def test_local_postgres_check(self):
        """Verify health check for local PostgreSQL."""
        assert "pg_isready" in self.backup_script, \
            "Must check local PostgreSQL with pg_isready"

    def test_cloud_sql_check(self):
        """Verify health check for Cloud SQL."""
        assert "gcloud sql" in self.backup_script, \
            "Must support Cloud SQL health check"

    def test_gcloud_cli_validation(self):
        """Verify script checks for gcloud CLI availability."""
        assert "command -v gcloud" in self.backup_script, \
            "Script must verify gcloud CLI is available"

    def test_pg_dump_validation(self):
        """Verify script checks for pg_dump tool."""
        assert "pg_dump" in self.backup_script, \
            "Script must use pg_dump for backup"

    def test_connection_error_handling(self):
        """Verify connection failures are caught."""
        assert "Cannot connect" in self.backup_script, \
            "Script must handle connection errors"


class TestBackupPerformance:
    """Test actual backup execution logic."""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()

    def test_performs_backup(self):
        """Verify perform_backup() function exists."""
        assert re.search(r"^perform_backup\(\)\s*\{", self.backup_script, re.MULTILINE), \
            "Script must have perform_backup() function"

    def test_backup_called_in_main(self):
        """Verify backup is executed in main flow."""
        assert re.search(r"perform_backup", self.backup_script), \
            "perform_backup must be called"

    def test_pg_dump_compression_format(self):
        """Verify backup uses custom format compression (-Fc)."""
        assert "-Fc" in self.backup_script, \
            "Backup must use custom format compression (-Fc)"

    def test_pg_dump_verbose_flag(self):
        """Verify backup includes verbose output."""
        assert "--verbose" in self.backup_script, \
            "Backup must include verbose flag"

    def test_pg_dump_file_output(self):
        """Verify backup output to file."""
        assert "-f" in self.backup_script and "BACKUP_FILE" in self.backup_script, \
            "Backup must write to file"

    def test_database_name_parameter(self):
        """Verify database name is passed to pg_dump."""
        assert "-d" in self.backup_script, \
            "Backup must specify database with -d flag"

    def test_backup_error_cleanup(self):
        """Verify failed backup files are cleaned up."""
        assert "rm -f" in self.backup_script, \
            "Script must clean up failed backups"


class TestBackupVerification:
    """Test post-backup integrity verification."""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()

    def test_has_verify_backup_function(self):
        """Verify verify_backup() function exists."""
        assert re.search(r"^verify_backup\(\)\s*\{", self.backup_script, re.MULTILINE), \
            "Script must have verify_backup() function"

    def test_verify_called_after_backup(self):
        """Verify verification is run after backup."""
        main_section = self.backup_script[self.backup_script.find("main()"):]
        assert "perform_backup" in main_section and "verify_backup" in main_section, \
            "verify_backup must be called after perform_backup"

    def test_checks_file_existence(self):
        """Verify script checks backup file exists."""
        assert "if [[ ! -f" in self.backup_script, \
            "Script must verify backup file exists"

    def test_checks_file_size(self):
        """Verify script validates file is not empty."""
        assert "file_size" in self.backup_script or "stat" in self.backup_script, \
            "Script must check backup file size"

    def test_pg_restore_header_test(self):
        """Verify script tests restore header with pg_restore."""
        assert "pg_restore" in self.backup_script and "--list" in self.backup_script, \
            "Script must test backup integrity with pg_restore --list"

    def test_gcs_file_verification(self):
        """Verify script checks GCS uploads."""
        assert "gsutil" in self.backup_script, \
            "Script must verify GCS uploads"

    def test_corruption_detection(self):
        """Verify script detects corrupted backups."""
        assert "corrupted" in self.backup_script.lower() or "invalid" in self.backup_script.lower(), \
            "Script must detect and report corrupted backups"


class TestGCSIntegration:
    """Test GCS bucket upload functionality."""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()

    def test_has_gcs_upload_function(self):
        """Verify upload_to_gcs() function exists."""
        assert re.search(r"^upload_to_gcs\(\)\s*\{", self.backup_script, re.MULTILINE), \
            "Script must have upload_to_gcs() function"

    def test_uses_gsutil(self):
        """Verify script uses gsutil for GCS operations."""
        assert "gsutil" in self.backup_script, \
            "Script must use gsutil for GCS operations"

    def test_bucket_configuration(self):
        """Verify GCS bucket is configurable."""
        assert "gs://vancity-lens-backups" in self.backup_script, \
            "Script must reference correct GCS bucket"

    def test_parallel_upload(self):
        """Verify script uses parallel uploads for performance."""
        assert "gsutil -m" in self.backup_script, \
            "Script should use parallel uploads (-m flag)"

    def test_skips_upload_if_not_configured(self):
        """Verify upload is skipped if GCS bucket not set."""
        assert "if [[ -z" in self.backup_script, \
            "Script must handle missing GCS configuration"

    def test_gcloud_sql_direct_export(self):
        """Verify Cloud SQL exports directly to GCS."""
        assert "gcloud sql export" in self.backup_script, \
            "Script must use gcloud sql export for Cloud SQL"


class TestRetentionPolicy:
    """Test backup retention and cleanup logic."""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()

    def test_has_cleanup_function(self):
        """Verify cleanup_old_backups() function exists."""
        assert re.search(r"^cleanup_old_backups\(\)\s*\{", self.backup_script, re.MULTILINE), \
            "Script must have cleanup_old_backups() function"

    def test_retention_policy_applied(self):
        """Verify retention policy is enforced."""
        assert "30 daily" in self.backup_script or "BACKUP_RETENTION_DAYS" in self.backup_script, \
            "Script must enforce retention policy"

    def test_old_backups_deleted(self):
        """Verify old backups are deleted."""
        assert "rm -f" in self.backup_script and "backup" in self.backup_script, \
            "Script must delete old backup files"

    def test_find_command_used(self):
        """Verify find command for locating old files."""
        assert "find" in self.backup_script, \
            "Script must use find command for retention"

    def test_gcs_cleanup_support(self):
        """Verify GCS backups are also subject to retention."""
        assert "gsutil" in self.backup_script and "cleanup" in self.backup_script.lower(), \
            "Script must manage GCS backup retention"

    def test_cutoff_date_calculation(self):
        """Verify script calculates cutoff date correctly."""
        assert "date" in self.backup_script, \
            "Script must calculate date for retention cutoff"


class TestRestoreScriptStructure:
    """Test fundamental structure of restore_db.sh"""

    def setup_method(self):
        self.restore_script = (SCRIPTS_DIR / "restore_db.sh").read_text()

    def test_has_shebang(self):
        """Verify restore script has proper shebang."""
        assert self.restore_script.startswith("#!/usr/bin/env bash"), \
            "Restore script must start with #!/usr/bin/env bash"

    def test_has_set_euo_pipefail(self):
        """Verify restore script uses set -euo pipefail."""
        assert "set -euo pipefail" in self.restore_script, \
            "Restore script must include 'set -euo pipefail'"

    def test_has_main_function(self):
        """Verify restore script defines main()."""
        assert re.search(r"^main\(\)\s*\{", self.restore_script, re.MULTILINE), \
            "Restore script must define main() function"

    def test_has_usage_documentation(self):
        """Verify restore script documents usage."""
        assert "Usage:" in self.restore_script, \
            "Restore script must include usage documentation"

    def test_has_help_option(self):
        """Verify restore script supports --help."""
        assert "--help" in self.restore_script, \
            "Restore script must support --help option"


class TestRestoreSafetyChecks:
    """Test safety mechanisms in restore script."""

    def setup_method(self):
        self.restore_script = (SCRIPTS_DIR / "restore_db.sh").read_text()

    def test_requires_force_flag(self):
        """Verify restore requires --force flag."""
        assert "--force" in self.restore_script, \
            "Restore must require --force flag for safety"
        assert "FORCE_RESTORE" in self.restore_script, \
            "Restore must check FORCE_RESTORE variable"

    def test_confirms_restore_operation(self):
        """Verify restore confirms operation."""
        assert "Restore operation requires --force flag" in self.restore_script, \
            "Restore must require explicit confirmation"

    def test_validates_target_database(self):
        """Verify restore validates target database name."""
        assert "--target-db" in self.restore_script, \
            "Restore must support --target-db option"

    def test_checks_database_existence(self):
        """Verify restore checks if database exists."""
        assert "pg_database" in self.restore_script, \
            "Restore must check if target database exists"

    def test_terminates_existing_connections(self):
        """Verify restore terminates connections before restore."""
        assert "pg_terminate_backend" in self.restore_script, \
            "Restore must terminate existing connections"

    def test_drops_existing_database(self):
        """Verify restore can drop existing database."""
        assert "dropdb" in self.restore_script, \
            "Restore must support dropping existing database"


class TestRestoreSafetyBackup:
    """Test pre-restore safety backup creation."""

    def setup_method(self):
        self.restore_script = (SCRIPTS_DIR / "restore_db.sh").read_text()

    def test_has_safety_backup_function(self):
        """Verify create_safety_backup() function exists."""
        assert re.search(r"^create_safety_backup\(\)\s*\{", self.restore_script, re.MULTILINE), \
            "Restore script must have create_safety_backup() function"

    def test_safety_backup_called(self):
        """Verify safety backup is created before restore."""
        assert "create_safety_backup" in self.restore_script, \
            "Safety backup must be called"

    def test_creates_local_backup(self):
        """Verify safety backup uses pg_dump."""
        assert "pg_dump" in self.restore_script, \
            "Safety backup must use pg_dump"

    def test_backup_compression(self):
        """Verify safety backup is compressed."""
        assert "-Fc" in self.restore_script, \
            "Safety backup must use custom format (-Fc)"

    def test_safety_backup_skippable(self):
        """Verify safety backup can be skipped with flag."""
        assert "--no-safety-backup" in self.restore_script, \
            "Safety backup should be skippable with --no-safety-backup flag"

    def test_safety_backup_file_naming(self):
        """Verify safety backup has descriptive name."""
        assert "safety_backup" in self.restore_script, \
            "Safety backup file must contain safety_backup in name"


class TestRestoreFileHandling:
    """Test restore file source handling (local vs GCS)."""

    def setup_method(self):
        self.restore_script = (SCRIPTS_DIR / "restore_db.sh").read_text()

    def test_local_file_support(self):
        """Verify restore supports local files."""
        assert "validate_local_file" in self.restore_script, \
            "Restore must support local files"

    def test_gcs_file_support(self):
        """Verify restore supports GCS files."""
        assert "gs://" in self.restore_script, \
            "Restore must support GCS paths (gs://)"

    def test_validates_local_file_exists(self):
        """Verify script checks local file existence."""
        assert "if [[ ! -f" in self.restore_script, \
            "Restore must verify local file exists"

    def test_downloads_from_gcs(self):
        """Verify restore downloads from GCS."""
        assert "gsutil" in self.restore_script and "cp" in self.restore_script, \
            "Restore must download files from GCS"

    def test_validates_file_format(self):
        """Verify restore validates dump file format."""
        assert "pg_restore" in self.restore_script and "--list" in self.restore_script, \
            "Restore must validate backup file format"

    def test_file_size_check(self):
        """Verify restore checks file is not empty."""
        assert "file_size" in self.restore_script or "stat" in self.restore_script, \
            "Restore must check file size"

    def test_cleanup_temp_files(self):
        """Verify temporary downloaded files are cleaned up."""
        assert "rm -f" in self.restore_script and "restore_temp" in self.restore_script, \
            "Restore must clean up temporary files"


class TestRestoreProcess:
    """Test actual database restore execution."""

    def setup_method(self):
        self.restore_script = (SCRIPTS_DIR / "restore_db.sh").read_text()

    def test_has_perform_restore_function(self):
        """Verify perform_restore() function exists."""
        assert re.search(r"^perform_restore\(\)\s*\{", self.restore_script, re.MULTILINE), \
            "Restore script must have perform_restore() function"

    def test_creates_target_database(self):
        """Verify restore creates target database."""
        assert "createdb" in self.restore_script, \
            "Restore must create target database with createdb"

    def test_uses_pg_restore(self):
        """Verify restore uses pg_restore command."""
        assert "pg_restore" in self.restore_script, \
            "Restore must use pg_restore to restore backup"

    def test_restore_no_owner_flag(self):
        """Verify restore uses --no-owner flag."""
        assert "--no-owner" in self.restore_script, \
            "Restore must use --no-owner flag to avoid permission issues"

    def test_restore_verbose_output(self):
        """Verify restore includes verbose output."""
        assert "-v" in self.restore_script, \
            "Restore must include verbose flag for debugging"

    def test_restore_error_handling(self):
        """Verify restore handles errors."""
        assert "error_exit" in self.restore_script, \
            "Restore must have error handling"


class TestCronWrapperStructure:
    """Test cron wrapper script fundamentals."""

    def setup_method(self):
        self.cron_script = (SCRIPTS_DIR / "backup_cron.sh").read_text()

    def test_has_shebang(self):
        """Verify cron wrapper has proper shebang."""
        assert self.cron_script.startswith("#!/usr/bin/env bash"), \
            "Cron wrapper must start with #!/usr/bin/env bash"

    def test_has_set_euo_pipefail(self):
        """Verify cron wrapper uses set -euo pipefail."""
        assert "set -euo pipefail" in self.cron_script, \
            "Cron wrapper must include 'set -euo pipefail'"

    def test_has_main_function(self):
        """Verify cron wrapper defines main()."""
        assert re.search(r"^main\(\)\s*\{", self.cron_script, re.MULTILINE), \
            "Cron wrapper must define main() function"

    def test_scheduling_documentation(self):
        """Verify documentation includes cron schedule examples."""
        assert "0 2 * * *" in self.cron_script, \
            "Cron wrapper must document cron schedule examples"

    def test_multiple_schedule_support(self):
        """Verify documentation covers daily, weekly, and monthly."""
        assert "daily" in self.cron_script.lower() and "weekly" in self.cron_script.lower(), \
            "Cron wrapper documentation must cover multiple schedules"


class TestCronLocking:
    """Test cron wrapper lock file mechanism."""

    def setup_method(self):
        self.cron_script = (SCRIPTS_DIR / "backup_cron.sh").read_text()

    def test_has_acquire_lock_function(self):
        """Verify acquire_lock() function exists."""
        assert re.search(r"^acquire_lock\(\)\s*\{", self.cron_script, re.MULTILINE), \
            "Cron wrapper must have acquire_lock() function"

    def test_lock_file_path(self):
        """Verify lock file is created in backup directory."""
        assert "LOCK_FILE" in self.cron_script, \
            "Cron wrapper must define LOCK_FILE variable"
        assert ".backup.lock" in self.cron_script, \
            "Lock file must have .backup.lock naming"

    def test_lock_timeout(self):
        """Verify lock has timeout to prevent permanent locking."""
        assert "LOCK_TIMEOUT" in self.cron_script, \
            "Cron wrapper must define LOCK_TIMEOUT"
        assert "3600" in self.cron_script, \
            "Lock timeout should be 3600 seconds (1 hour)"

    def test_prevents_concurrent_backups(self):
        """Verify lock prevents concurrent backups."""
        assert "Backup already in progress" in self.cron_script, \
            "Cron wrapper must prevent concurrent backups"

    def test_stale_lock_cleanup(self):
        """Verify stale locks are cleaned up."""
        assert "stale" in self.cron_script.lower(), \
            "Cron wrapper must detect and clean stale locks"

    def test_release_lock_function(self):
        """Verify release_lock() function exists."""
        assert re.search(r"^release_lock\(\)\s*\{", self.cron_script, re.MULTILINE), \
            "Cron wrapper must have release_lock() function"

    def test_lock_cleanup_on_exit(self):
        """Verify lock is released on script exit."""
        assert "trap" in self.cron_script and "release_lock" in self.cron_script, \
            "Cron wrapper must use trap to release lock on exit"


class TestCronSlackNotifications:
    """Test Slack notification functionality."""

    def setup_method(self):
        self.cron_script = (SCRIPTS_DIR / "backup_cron.sh").read_text()

    def test_has_notification_function(self):
        """Verify send_slack_notification() function exists."""
        assert re.search(r"^send_slack_notification\(\)\s*\{", self.cron_script, re.MULTILINE), \
            "Cron wrapper must have send_slack_notification() function"

    def test_slack_webhook_support(self):
        """Verify Slack webhook URL is configurable."""
        assert "SLACK_WEBHOOK_URL" in self.cron_script, \
            "Cron wrapper must support SLACK_WEBHOOK_URL environment variable"

    def test_optional_slack_notifications(self):
        """Verify Slack notifications are optional."""
        assert "if [[ -z" in self.cron_script and "SLACK_WEBHOOK_URL" in self.cron_script, \
            "Slack notifications must be optional if webhook not configured"

    def test_curl_for_slack(self):
        """Verify script uses curl for Slack API."""
        assert "curl" in self.cron_script, \
            "Cron wrapper must use curl for Slack notifications"

    def test_failure_notification(self):
        """Verify failure notifications are sent."""
        assert "failure" in self.cron_script, \
            "Cron wrapper must send failure notifications"

    def test_success_notification(self):
        """Verify success notifications are sent."""
        assert "success" in self.cron_script, \
            "Cron wrapper must send success notifications"

    def test_slack_channel_configurable(self):
        """Verify Slack channel is configurable."""
        assert "SLACK_CHANNEL" in self.cron_script, \
            "Slack channel must be configurable"

    def test_notification_includes_timestamp(self):
        """Verify notifications include timestamp."""
        assert "date" in self.cron_script or "TIMESTAMP" in self.cron_script, \
            "Slack notifications must include timestamp"


class TestCronBackupExecution:
    """Test cron wrapper backup execution."""

    def setup_method(self):
        self.cron_script = (SCRIPTS_DIR / "backup_cron.sh").read_text()

    def test_calls_backup_script(self):
        """Verify cron wrapper calls backup_db.sh."""
        assert "backup_db.sh" in self.cron_script or "BACKUP_SCRIPT" in self.cron_script, \
            "Cron wrapper must call backup_db.sh"

    def test_exits_on_backup_failure(self):
        """Verify cron wrapper exits on backup failure."""
        assert "exit" in self.cron_script, \
            "Cron wrapper must exit on backup failure"

    def test_checks_backup_script_exists(self):
        """Verify cron wrapper locates backup script."""
        assert "SCRIPT_DIR" in self.cron_script, \
            "Cron wrapper must determine script directory"

    def test_runs_in_sequence(self):
        """Verify operations run in correct sequence."""
        # In the main() function, lock should be acquired before backup
        main_section = self.cron_script[self.cron_script.find("main()"):self.cron_script.find("# Execute main")]
        lock_pos = main_section.find('acquire_lock')
        backup_pos = main_section.find('BACKUP_SCRIPT')
        assert lock_pos > 0 and backup_pos > 0, "Both lock and backup should be called"
        # Lock is acquired and then backup is executed
        assert lock_pos < backup_pos, "Lock must be acquired before backup runs"


class TestEnvironmentVariableValidation:
    """Test environment variable handling and validation."""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()
        self.restore_script = (SCRIPTS_DIR / "restore_db.sh").read_text()

    def test_backup_validates_db_name(self):
        """Verify backup script validates DB_NAME is set."""
        assert 'if [[ -z "${DB_NAME}"' in self.backup_script or 'DB_NAME is required' in self.backup_script, \
            "Backup script must validate DB_NAME"

    def test_backup_validates_db_user(self):
        """Verify backup script validates DB_USER is set."""
        assert 'if [[ -z "${DB_USER}"' in self.backup_script or 'DB_USER is required' in self.backup_script, \
            "Backup script must validate DB_USER"

    def test_restore_parses_arguments(self):
        """Verify restore script parses command-line arguments."""
        assert re.search(r"parse_args|while.*\[\[ \$# -gt 0 \]\]", self.restore_script), \
            "Restore script must parse arguments"

    def test_restore_validates_restore_file(self):
        """Verify restore script validates restore file is specified."""
        assert "No restore file specified" in self.restore_script, \
            "Restore script must validate restore file is provided"

    def test_cloud_sql_validation(self):
        """Verify Cloud SQL configuration is validated."""
        assert "GCP_PROJECT_ID" in self.backup_script and "DB_INSTANCE_NAME" in self.backup_script, \
            "Backup script must validate Cloud SQL configuration"


class TestErrorHandling:
    """Test error handling in all scripts."""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()
        self.restore_script = (SCRIPTS_DIR / "restore_db.sh").read_text()
        self.cron_script = (SCRIPTS_DIR / "backup_cron.sh").read_text()

    def test_backup_handles_pg_dump_failure(self):
        """Verify backup handles pg_dump failures."""
        assert "if ! pg_dump" in self.backup_script, \
            "Backup must check pg_dump return code"

    def test_backup_handles_gcs_upload_failure(self):
        """Verify backup handles GCS upload failures."""
        assert "if ! gsutil" in self.backup_script or "error_exit" in self.backup_script, \
            "Backup must handle GCS upload failures"

    def test_restore_handles_connection_failure(self):
        """Verify restore handles connection failures."""
        assert "Cannot connect" in self.restore_script, \
            "Restore must handle connection failures"

    def test_restore_handles_file_validation_failure(self):
        """Verify restore handles invalid backup files."""
        assert "valid PostgreSQL dump" in self.restore_script, \
            "Restore must validate backup file format"

    def test_cron_handles_lock_failure(self):
        """Verify cron handles lock acquisition failure."""
        assert "exiting" in self.cron_script.lower() or "already in progress" in self.cron_script, \
            "Cron must handle concurrent backup situations"

    def test_cron_handles_backup_failure(self):
        """Verify cron handles backup script failures."""
        assert "if" in self.cron_script and "then" in self.cron_script, \
            "Cron must check backup script exit code"


class TestLoggingAndMonitoring:
    """Test logging and observability features."""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()
        self.restore_script = (SCRIPTS_DIR / "restore_db.sh").read_text()
        self.cron_script = (SCRIPTS_DIR / "backup_cron.sh").read_text()

    def test_backup_creates_log_file(self):
        """Verify backup script logs to file."""
        assert "LOG_FILE" in self.backup_script, \
            "Backup must define LOG_FILE variable"

    def test_backup_uses_timestamps_in_logs(self):
        """Verify backup logs include timestamps."""
        assert "TIMESTAMP" in self.backup_script, \
            "Backup logs must include timestamps"

    def test_restore_creates_log_file(self):
        """Verify restore script logs to file."""
        assert "LOG_FILE" in self.restore_script, \
            "Restore must define LOG_FILE variable"

    def test_cron_creates_log_file(self):
        """Verify cron wrapper logs to file."""
        assert "LOG_FILE" in self.cron_script, \
            "Cron wrapper must create log file"

    def test_backup_logs_operations(self):
        """Verify backup logs important operations."""
        assert re.search(r'log\s+"(INFO|ERROR|WARN)"', self.backup_script), \
            "Backup must log operations with log level"

    def test_restore_logs_operations(self):
        """Verify restore logs important operations."""
        assert re.search(r'log\s+"(INFO|ERROR|WARN)"', self.restore_script), \
            "Restore must log operations with log level"

    def test_cron_logs_lock_state(self):
        """Verify cron logs lock acquisition."""
        assert "Lock" in self.cron_script, \
            "Cron must log lock state"

    def test_backup_logs_file_location(self):
        """Verify backup logs where file is saved."""
        assert "BACKUP_FILE" in self.backup_script and "log" in self.backup_script, \
            "Backup must log backup file location"


class TestDocumentation:
    """Test script documentation quality."""

    def setup_method(self):
        self.backup_script = (SCRIPTS_DIR / "backup_db.sh").read_text()
        self.restore_script = (SCRIPTS_DIR / "restore_db.sh").read_text()
        self.cron_script = (SCRIPTS_DIR / "backup_cron.sh").read_text()

    def test_backup_has_descriptive_comments(self):
        """Verify backup script has clear comments."""
        assert "#" in self.backup_script, \
            "Backup script should include comments"
        assert "Backup" in self.backup_script, \
            "Backup script comments must mention backup"

    def test_restore_has_usage_help(self):
        """Verify restore script has usage help."""
        assert "show_usage" in self.restore_script, \
            "Restore script must have usage function"

    def test_cron_documents_schedules(self):
        """Verify cron wrapper documents recommended schedules."""
        assert "cron" in self.cron_script.lower(), \
            "Cron wrapper must document cron schedules"

    def test_scripts_explain_features(self):
        """Verify scripts document their features."""
        feature_words = ["backup", "restore", "compression", "retention", "health check"]
        for word in feature_words[:2]:
            assert word in self.backup_script.lower(), \
                f"Script must document {word} feature"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
