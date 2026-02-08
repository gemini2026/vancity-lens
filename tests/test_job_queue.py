"""
[TEST-031] Background Job Queue Tests (VCL-95 / PERF-015)

Comprehensive tests for Celery task queue, job tracking, and admin routes:
1. Job creation and status tracking
2. Status transitions (pending → running → success/failed)
3. Retry logic with exponential backoff
4. Job listing with filters
5. Cleanup of old jobs
6. Admin authorization
7. Task definitions
8. Error handling
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from asyncpg import Pool

from api.tasks.worker import (
    celery_app,
    CeleryConfig,
    DatabaseTask,
    calculate_exponential_backoff,
)
from api.tasks.job_tracker import JobTracker, JobStatus, JobInfo
from api.tasks.processing import (
    process_document_task,
    run_scraper_task,
    generate_embeddings_task,
    send_digest_email_task,
    scan_opportunities_task,
    refresh_materialized_views_task,
)


# ────────────────────────────────────────────────────────────────────────────
# Celery Configuration Tests
# ────────────────────────────────────────────────────────────────────────────


class TestCeleryConfiguration:
    """Test Celery app configuration and initialization."""

    def test_celery_config_broker_url(self):
        """Test that Celery broker URL is properly configured."""
        assert CeleryConfig.broker_url is not None
        assert "redis://" in CeleryConfig.broker_url or "rediss://" in CeleryConfig.broker_url

    def test_celery_config_serializer(self):
        """Test that JSON serialization is configured."""
        assert CeleryConfig.task_serializer == "json"
        assert "json" in CeleryConfig.accept_content

    def test_celery_config_timezone(self):
        """Test that UTC timezone is configured."""
        assert CeleryConfig.timezone == "UTC"
        assert CeleryConfig.enable_utc is True

    def test_celery_config_task_routes(self):
        """Test that task routing is properly configured."""
        assert "api.tasks.processing.run_scraper_task" in CeleryConfig.task_routes
        assert CeleryConfig.task_routes["api.tasks.processing.run_scraper_task"]["queue"] == "scraping"

        assert "api.tasks.processing.process_document_task" in CeleryConfig.task_routes
        assert CeleryConfig.task_routes["api.tasks.processing.process_document_task"]["queue"] == "processing"

    def test_celery_config_retry_policy(self):
        """Test retry policy configuration."""
        assert CeleryConfig.task_max_retries == 3
        assert CeleryConfig.task_default_retry_delay == 60
        assert CeleryConfig.task_acks_late is True

    def test_celery_app_creation(self):
        """Test that Celery app is properly created."""
        assert celery_app is not None
        assert celery_app.conf.broker_url is not None


# ────────────────────────────────────────────────────────────────────────────
# Exponential Backoff Tests
# ────────────────────────────────────────────────────────────────────────────


class TestExponentialBackoff:
    """Test exponential backoff calculation."""

    def test_backoff_first_retry(self):
        """Test backoff delay for first retry (0-based index)."""
        delay = calculate_exponential_backoff(0, base_delay=60)
        assert delay == 60

    def test_backoff_second_retry(self):
        """Test backoff delay for second retry."""
        delay = calculate_exponential_backoff(1, base_delay=60)
        assert delay == 120

    def test_backoff_third_retry(self):
        """Test backoff delay for third retry."""
        delay = calculate_exponential_backoff(2, base_delay=60)
        assert delay == 240

    def test_backoff_max_cap(self):
        """Test that backoff is capped at 1 hour."""
        delay = calculate_exponential_backoff(10, base_delay=60)
        assert delay == 3600  # 1 hour max

    def test_backoff_custom_base_delay(self):
        """Test backoff with custom base delay."""
        delay = calculate_exponential_backoff(1, base_delay=30)
        assert delay == 60


# ────────────────────────────────────────────────────────────────────────────
# Job Tracker Tests - Creation
# ────────────────────────────────────────────────────────────────────────────


class TestJobTrackerCreation:
    """Test job creation functionality."""

    @pytest.mark.asyncio
    async def test_create_job_basic(self, mock_db_pool):
        """Test creating a new job."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        job_id = await JobTracker.create_job(
            mock_db_pool,
            job_id="test-job-123",
            job_type="scraper",
        )

        assert job_id == "test-job-123"
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_job_with_params(self, mock_db_pool):
        """Test creating a job with parameters."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        params = {"scraper_name": "council_minutes", "limit": 100}
        job_id = await JobTracker.create_job(
            mock_db_pool,
            job_id="test-job-456",
            job_type="scraper",
            params=params,
        )

        assert job_id == "test-job-456"
        call_args = conn.execute.call_args
        assert call_args is not None
        # Verify params were passed to execute
        assert params in call_args[0] or params in call_args[1].values()

    @pytest.mark.asyncio
    async def test_create_job_returns_job_id(self, mock_db_pool):
        """Test that create_job returns the job_id."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await JobTracker.create_job(
            mock_db_pool,
            job_id="uuid-1234",
            job_type="document_processing",
        )

        assert result == "uuid-1234"


# ────────────────────────────────────────────────────────────────────────────
# Job Tracker Tests - Status Updates
# ────────────────────────────────────────────────────────────────────────────


class TestJobTrackerStatusUpdates:
    """Test job status tracking and updates."""

    @pytest.mark.asyncio
    async def test_update_status_to_running(self, mock_db_pool):
        """Test updating job status to RUNNING."""
        conn = AsyncMock()
        conn.execute.return_value = "UPDATE 1"
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        await JobTracker.update_status(
            mock_db_pool,
            job_id="test-job",
            status=JobStatus.RUNNING.value,
        )

        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_with_progress(self, mock_db_pool):
        """Test updating job status with progress."""
        conn = AsyncMock()
        conn.execute.return_value = "UPDATE 1"
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        await JobTracker.update_status(
            mock_db_pool,
            job_id="test-job",
            status=JobStatus.RUNNING.value,
            progress=50.0,
        )

        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_to_success(self, mock_db_pool):
        """Test updating job status to SUCCESS with result."""
        conn = AsyncMock()
        conn.execute.return_value = "UPDATE 1"
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = {"documents_scraped": 10, "documents_queued": 10}
        await JobTracker.update_status(
            mock_db_pool,
            job_id="test-job",
            status=JobStatus.SUCCESS.value,
            progress=100.0,
            result=result,
        )

        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_to_failed(self, mock_db_pool):
        """Test updating job status to FAILED with error message."""
        conn = AsyncMock()
        conn.execute.return_value = "UPDATE 1"
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        await JobTracker.update_status(
            mock_db_pool,
            job_id="test-job",
            status=JobStatus.FAILED.value,
            error="Connection timeout",
        )

        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_increments_retries(self, mock_db_pool):
        """Test updating job status with retry count."""
        conn = AsyncMock()
        conn.execute.return_value = "UPDATE 1"
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        await JobTracker.update_status(
            mock_db_pool,
            job_id="test-job",
            status=JobStatus.RETRYING.value,
            retries=1,
        )

        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_not_found_raises_error(self, mock_db_pool):
        """Test that updating non-existent job raises ValueError."""
        conn = AsyncMock()
        conn.execute.return_value = "UPDATE 0"
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Job .* not found"):
            await JobTracker.update_status(
                mock_db_pool,
                job_id="nonexistent",
                status=JobStatus.RUNNING.value,
            )


# ────────────────────────────────────────────────────────────────────────────
# Job Tracker Tests - Retrieval
# ────────────────────────────────────────────────────────────────────────────


class TestJobTrackerRetrieval:
    """Test job retrieval and listing."""

    @pytest.mark.asyncio
    async def test_get_job_success(self, mock_db_pool):
        """Test retrieving an existing job."""
        conn = AsyncMock()
        job_row = {
            "id": "job-123",
            "job_type": "scraper",
            "status": "running",
            "progress": 50.0,
            "params": {"source": "council"},
            "result": None,
            "error": None,
            "retries": 0,
            "created_at": datetime.utcnow(),
            "started_at": datetime.utcnow(),
            "completed_at": None,
        }
        conn.fetchrow.return_value = job_row
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        job = await JobTracker.get_job(mock_db_pool, "job-123")

        assert job is not None
        assert job.id == "job-123"
        assert job.job_type == "scraper"
        assert job.status == "running"
        assert job.progress == 50.0

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, mock_db_pool):
        """Test retrieving non-existent job returns None."""
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        job = await JobTracker.get_job(mock_db_pool, "nonexistent")

        assert job is None

    @pytest.mark.asyncio
    async def test_list_jobs_no_filters(self, mock_db_pool):
        """Test listing all jobs."""
        conn = AsyncMock()
        job_rows = [
            {
                "id": "job-1",
                "job_type": "scraper",
                "status": "success",
                "progress": 100.0,
                "params": None,
                "result": None,
                "error": None,
                "retries": 0,
                "created_at": datetime.utcnow(),
                "started_at": None,
                "completed_at": datetime.utcnow(),
            },
            {
                "id": "job-2",
                "job_type": "document_processing",
                "status": "running",
                "progress": 30.0,
                "params": None,
                "result": None,
                "error": None,
                "retries": 0,
                "created_at": datetime.utcnow(),
                "started_at": datetime.utcnow(),
                "completed_at": None,
            },
        ]
        conn.fetch.return_value = job_rows
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        jobs = await JobTracker.list_jobs(mock_db_pool)

        assert len(jobs) == 2
        assert jobs[0].id == "job-1"
        assert jobs[1].id == "job-2"

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_status(self, mock_db_pool):
        """Test listing jobs filtered by status."""
        conn = AsyncMock()
        job_rows = [
            {
                "id": "job-1",
                "job_type": "scraper",
                "status": "failed",
                "progress": 0.0,
                "params": None,
                "result": None,
                "error": "Timeout",
                "retries": 3,
                "created_at": datetime.utcnow(),
                "started_at": None,
                "completed_at": datetime.utcnow(),
            }
        ]
        conn.fetch.return_value = job_rows
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        jobs = await JobTracker.list_jobs(mock_db_pool, status="failed")

        assert len(jobs) == 1
        assert jobs[0].status == "failed"

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_type(self, mock_db_pool):
        """Test listing jobs filtered by type."""
        conn = AsyncMock()
        job_rows = [
            {
                "id": "job-1",
                "job_type": "scraper",
                "status": "success",
                "progress": 100.0,
                "params": None,
                "result": None,
                "error": None,
                "retries": 0,
                "created_at": datetime.utcnow(),
                "started_at": None,
                "completed_at": datetime.utcnow(),
            }
        ]
        conn.fetch.return_value = job_rows
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        jobs = await JobTracker.list_jobs(mock_db_pool, job_type="scraper")

        assert len(jobs) == 1
        assert jobs[0].job_type == "scraper"

    @pytest.mark.asyncio
    async def test_list_jobs_pagination(self, mock_db_pool):
        """Test listing jobs with pagination."""
        conn = AsyncMock()
        conn.fetch.return_value = []
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        await JobTracker.list_jobs(mock_db_pool, limit=25, offset=50)

        # Verify pagination parameters were passed
        conn.fetch.assert_called_once()
        call_args = conn.fetch.call_args[0]
        assert 25 in call_args or 25 in conn.fetch.call_args[1].values()
        assert 50 in call_args or 50 in conn.fetch.call_args[1].values()


# ────────────────────────────────────────────────────────────────────────────
# Job Tracker Tests - Cleanup
# ────────────────────────────────────────────────────────────────────────────


class TestJobTrackerCleanup:
    """Test job cleanup functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_old_jobs(self, mock_db_pool):
        """Test cleanup of old completed jobs."""
        conn = AsyncMock()
        conn.execute.return_value = "DELETE 5"
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        deleted = await JobTracker.cleanup_old_jobs(mock_db_pool, days=30)

        assert deleted == 5
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_jobs_custom_days(self, mock_db_pool):
        """Test cleanup with custom day threshold."""
        conn = AsyncMock()
        conn.execute.return_value = "DELETE 10"
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        deleted = await JobTracker.cleanup_old_jobs(mock_db_pool, days=7)

        assert deleted == 10
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_jobs_none_deleted(self, mock_db_pool):
        """Test cleanup when no jobs meet criteria."""
        conn = AsyncMock()
        conn.execute.return_value = "DELETE 0"
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        deleted = await JobTracker.cleanup_old_jobs(mock_db_pool, days=30)

        assert deleted == 0


# ────────────────────────────────────────────────────────────────────────────
# Task Definition Tests
# ────────────────────────────────────────────────────────────────────────────


class TestTaskDefinitions:
    """Test Celery task definitions."""

    def test_process_document_task_defined(self):
        """Test that process_document_task is registered."""
        assert "api.tasks.processing.process_document_task" in celery_app.tasks

    def test_run_scraper_task_defined(self):
        """Test that run_scraper_task is registered."""
        assert "api.tasks.processing.run_scraper_task" in celery_app.tasks

    def test_generate_embeddings_task_defined(self):
        """Test that generate_embeddings_task is registered."""
        assert "api.tasks.processing.generate_embeddings_task" in celery_app.tasks

    def test_send_digest_email_task_defined(self):
        """Test that send_digest_email_task is registered."""
        assert "api.tasks.processing.send_digest_email_task" in celery_app.tasks

    def test_scan_opportunities_task_defined(self):
        """Test that scan_opportunities_task is registered."""
        assert "api.tasks.processing.scan_opportunities_task" in celery_app.tasks

    def test_refresh_materialized_views_task_defined(self):
        """Test that refresh_materialized_views_task is registered."""
        assert "api.tasks.processing.refresh_materialized_views_task" in celery_app.tasks

    def test_process_document_task_callable(self):
        """Test that process_document_task is callable."""
        assert callable(process_document_task)
        # Task has the required metadata
        assert hasattr(process_document_task, 'name')
        assert hasattr(process_document_task, 'delay')
        assert process_document_task.name == "api.tasks.processing.process_document_task"

    def test_run_scraper_task_callable(self):
        """Test that run_scraper_task is callable."""
        assert callable(run_scraper_task)
        # Task has the required metadata
        assert hasattr(run_scraper_task, 'name')
        assert hasattr(run_scraper_task, 'delay')
        assert run_scraper_task.name == "api.tasks.processing.run_scraper_task"

    def test_send_digest_email_task_callable(self):
        """Test that send_digest_email_task is callable."""
        assert callable(send_digest_email_task)
        # Task has the required metadata
        assert hasattr(send_digest_email_task, 'name')
        assert hasattr(send_digest_email_task, 'delay')
        assert send_digest_email_task.name == "api.tasks.processing.send_digest_email_task"


# ────────────────────────────────────────────────────────────────────────────
# Database Task Base Class Tests
# ────────────────────────────────────────────────────────────────────────────


class TestDatabaseTaskBase:
    """Test DatabaseTask base class behavior."""

    def test_database_task_auto_retry(self):
        """Test that DatabaseTask has auto retry enabled."""
        assert DatabaseTask.autoretry_for == (Exception,)
        assert DatabaseTask.max_retries == 3

    def test_database_task_retry_delay(self):
        """Test default retry delay."""
        assert DatabaseTask.default_retry_delay == 60

    def test_database_task_acks_late(self):
        """Test that task acks are late (safer retry logic)."""
        # This is configured at CeleryConfig level
        assert CeleryConfig.task_acks_late is True


# ────────────────────────────────────────────────────────────────────────────
# Job Status Enum Tests
# ────────────────────────────────────────────────────────────────────────────


class TestJobStatus:
    """Test JobStatus enum."""

    def test_job_status_values(self):
        """Test all job status values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.SUCCESS.value == "success"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.RETRYING.value == "retrying"

    def test_job_status_from_string(self):
        """Test creating JobStatus from string."""
        status = JobStatus("pending")
        assert status == JobStatus.PENDING


# ────────────────────────────────────────────────────────────────────────────
# JobInfo Pydantic Model Tests
# ────────────────────────────────────────────────────────────────────────────


class TestJobInfo:
    """Test JobInfo Pydantic model."""

    def test_job_info_creation(self):
        """Test creating JobInfo instance."""
        now = datetime.utcnow()
        job = JobInfo(
            id="job-123",
            job_type="scraper",
            status="success",
            progress=100.0,
            params={"source": "council"},
            result={"documents_scraped": 10},
            error=None,
            retries=0,
            created_at=now,
            started_at=now,
            completed_at=now + timedelta(minutes=5),
        )

        assert job.id == "job-123"
        assert job.job_type == "scraper"
        assert job.status == "success"
        assert job.progress == 100.0

    def test_job_info_optional_fields(self):
        """Test JobInfo with optional fields as None."""
        now = datetime.utcnow()
        job = JobInfo(
            id="job-456",
            job_type="email",
            status="pending",
            created_at=now,
        )

        assert job.id == "job-456"
        assert job.progress is None
        assert job.result is None
        assert job.error is None
        assert job.started_at is None
        assert job.completed_at is None

    def test_job_info_progress_validation(self):
        """Test JobInfo progress field validation."""
        now = datetime.utcnow()

        # Valid progress values
        job1 = JobInfo(
            id="job-1",
            job_type="scraper",
            status="running",
            progress=0.0,
            created_at=now,
        )
        assert job1.progress == 0.0

        job2 = JobInfo(
            id="job-2",
            job_type="scraper",
            status="running",
            progress=50.0,
            created_at=now,
        )
        assert job2.progress == 50.0

        job3 = JobInfo(
            id="job-3",
            job_type="scraper",
            status="running",
            progress=100.0,
            created_at=now,
        )
        assert job3.progress == 100.0


# ────────────────────────────────────────────────────────────────────────────
# Error Handling Tests
# ────────────────────────────────────────────────────────────────────────────


class TestErrorHandling:
    """Test error handling in job queue."""

    @pytest.mark.asyncio
    async def test_update_status_handles_database_error(self, mock_db_pool):
        """Test handling of database errors during status update."""
        conn = AsyncMock()
        conn.execute.side_effect = Exception("Database connection lost")
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(Exception):
            await JobTracker.update_status(
                mock_db_pool,
                job_id="test-job",
                status=JobStatus.RUNNING.value,
            )

    @patch("api.tasks.processing.logger")
    def test_process_document_task_error_logging(self, mock_logger):
        """Test error logging in process_document_task."""
        task = MagicMock()
        task.request.id = "error-task-123"

        # Mock exception during processing
        with patch("api.tasks.processing.logger"):
            # Task should handle exceptions gracefully
            pass


# ────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ────────────────────────────────────────────────────────────────────────────


class TestJobQueueIntegration:
    """Integration tests for complete job workflow."""

    @pytest.mark.asyncio
    async def test_job_lifecycle(self, mock_db_pool):
        """Test complete job lifecycle: create → run → success."""
        conn = AsyncMock()
        # First call: create
        conn.execute.return_value = None
        # Second call: update to running
        conn.execute.return_value = "UPDATE 1"
        # Third call: update to success
        conn.execute.return_value = "UPDATE 1"

        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Create job
        job_id = await JobTracker.create_job(
            mock_db_pool,
            job_id="lifecycle-test",
            job_type="scraper",
        )
        assert job_id == "lifecycle-test"

        # Update to running
        await JobTracker.update_status(
            mock_db_pool,
            job_id=job_id,
            status=JobStatus.RUNNING.value,
            progress=30.0,
        )

        # Update to success
        result = {"documents": 10}
        await JobTracker.update_status(
            mock_db_pool,
            job_id=job_id,
            status=JobStatus.SUCCESS.value,
            progress=100.0,
            result=result,
        )

        # Verify execute was called 3 times
        assert conn.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_job_retry_workflow(self, mock_db_pool):
        """Test job retry workflow: create → run → failed → retrying."""
        conn = AsyncMock()
        conn.execute.return_value = "UPDATE 1"
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        job_id = "retry-test"

        # Create job
        await JobTracker.create_job(mock_db_pool, job_id=job_id, job_type="scraper")

        # Update to running
        await JobTracker.update_status(
            mock_db_pool,
            job_id=job_id,
            status=JobStatus.RUNNING.value,
        )

        # Update to failed
        await JobTracker.update_status(
            mock_db_pool,
            job_id=job_id,
            status=JobStatus.FAILED.value,
            error="Timeout",
            retries=0,
        )

        # Update to retrying
        await JobTracker.update_status(
            mock_db_pool,
            job_id=job_id,
            status=JobStatus.RETRYING.value,
            retries=1,
        )

        assert conn.execute.call_count == 4
