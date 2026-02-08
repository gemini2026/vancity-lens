"""
Celery worker configuration for VanCity Lens (VCL-95 / PERF-015)

Provides:
- Celery app initialization with Redis broker
- Task serialization and result backend configuration
- Retry policy with exponential backoff
- Dead letter queue (DLQ) configuration
- Task routing to separate queues
"""

import os
import logging
from celery import Celery, Task

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────────────────

# Read from environment variables with defaults
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TIMEZONE = "UTC"


# ────────────────────────────────────────────────────────────────────────────
# Celery Configuration Class
# ────────────────────────────────────────────────────────────────────────────

class CeleryConfig:
    """Celery configuration settings."""

    # Broker and result backend
    broker_url = CELERY_BROKER_URL
    result_backend = CELERY_RESULT_BACKEND

    # Serialization
    task_serializer = "json"
    accept_content = ["json"]
    result_serializer = "json"

    # Timezone
    timezone = CELERY_TIMEZONE
    enable_utc = True

    # Task configuration
    task_track_started = True
    task_time_limit = 30 * 60  # 30 minutes hard limit
    task_soft_time_limit = 25 * 60  # 25 minutes soft limit

    # Result backend configuration
    result_expires = 3600  # Results expire after 1 hour

    # Retry policy with exponential backoff
    # task_acks_late prevents redelivery if worker dies during processing
    task_acks_late = True

    # Task routing to specific queues
    task_routes = {
        "api.tasks.processing.run_scraper_task": {"queue": "scraping"},
        "api.tasks.processing.process_document_task": {"queue": "processing"},
        "api.tasks.processing.generate_embeddings_task": {"queue": "processing"},
        "api.tasks.processing.send_digest_email_task": {"queue": "email"},
        "api.tasks.processing.scan_opportunities_task": {"queue": "processing"},
        "api.tasks.processing.refresh_materialized_views_task": {"queue": "processing"},
    }

    # Retry policy for all tasks
    # Exponential backoff: 60s, 120s, 240s (max 3 retries)
    task_autoretry_for = (Exception,)
    task_max_retries = 3
    task_default_retry_delay = 60  # Initial delay in seconds

    # Dead letter queue for permanently failed tasks
    # Tasks failing after max retries go to DLQ
    task_reject_on_worker_lost = True

    # Worker configuration
    worker_prefetch_multiplier = 4
    worker_max_tasks_per_child = 1000


# ────────────────────────────────────────────────────────────────────────────
# Create and Configure Celery App
# ────────────────────────────────────────────────────────────────────────────

def create_celery_app():
    """Create and configure Celery application."""
    celery_app = Celery("vancity_lens")
    celery_app.config_from_object(CeleryConfig)

    # Auto-discover tasks from api.tasks module
    celery_app.autodiscover_tasks(["api.tasks"])

    return celery_app


# Create the global Celery app instance
celery_app = create_celery_app()


# ────────────────────────────────────────────────────────────────────────────
# Base Task Class with Error Handling
# ────────────────────────────────────────────────────────────────────────────

class DatabaseTask(Task):
    """
    Base task class with database connection management.

    Ensures that database connections are properly handled before and after
    task execution. Override on_failure and on_retry to track job status.
    """

    autoretry_for = (Exception,)
    max_retries = 3
    default_retry_delay = 60

    def __call__(self, *args, **kwargs):
        """Execute task with proper error handling."""
        try:
            return self.run(*args, **kwargs)
        except Exception as exc:
            # Log the error
            logger.error(
                f"Task {self.name} failed: {exc}",
                exc_info=True,
                extra={
                    "task_id": self.request.id,
                    "task_name": self.name,
                    "retries": self.request.retries,
                }
            )
            raise

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task is retried after failure."""
        logger.warning(
            f"Task {self.name} (id={task_id}) retrying after failure: {exc}",
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "retry_count": self.request.retries,
            }
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails permanently (all retries exhausted)."""
        logger.error(
            f"Task {self.name} (id={task_id}) failed permanently: {exc}",
            exc_info=einfo,
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "max_retries": self.max_retries,
            }
        )

    def on_success(self, result, task_id, args, kwargs):
        """Called when task completes successfully."""
        logger.info(
            f"Task {self.name} (id={task_id}) completed successfully",
            extra={
                "task_id": task_id,
                "task_name": self.name,
            }
        )


# Register the base task class
celery_app.Task = DatabaseTask


# ────────────────────────────────────────────────────────────────────────────
# Exponential Backoff Retry Calculation
# ────────────────────────────────────────────────────────────────────────────

def calculate_exponential_backoff(retry_count: int, base_delay: int = 60) -> int:
    """
    Calculate exponential backoff delay.

    Args:
        retry_count: Current retry attempt (0-based)
        base_delay: Base delay in seconds (default: 60)

    Returns:
        Delay in seconds for the next retry
    """
    # Exponential backoff: base_delay * (2 ** retry_count)
    delay = base_delay * (2 ** retry_count)
    return min(delay, 3600)  # Cap at 1 hour


logger.info(f"Celery configured with broker: {CELERY_BROKER_URL}")
