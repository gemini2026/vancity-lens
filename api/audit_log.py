"""
VanCity Lens — External Retrieval Audit Log (DI-005)

Tracks every external data source retrieval for compliance,
debugging, and data currency reporting.
"""

import logging
import time
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


async def log_retrieval(
    db_pool: asyncpg.Pool,
    *,
    source_name: str,
    operation: str,
    endpoint_url: Optional[str] = None,
    request_params: Optional[dict] = None,
    response_status: Optional[int] = None,
    records_returned: int = 0,
    records_stored: int = 0,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
    triggered_by: str = "scheduler",
    user_id: Optional[int] = None,
    pid: Optional[str] = None,
) -> Optional[int]:
    """
    Log an external data retrieval event.

    Returns the log entry ID, or None if logging failed.
    """
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO external_retrieval_log (
                    source_name, operation, endpoint_url, request_params,
                    response_status, records_returned, records_stored,
                    error_message, duration_ms, triggered_by, user_id, pid
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING id
            """,
                source_name,
                operation,
                endpoint_url,
                request_params if request_params else None,
                response_status,
                records_returned,
                records_stored,
                error_message[:500] if error_message else None,
                duration_ms,
                triggered_by,
                user_id,
                pid,
            )
            return row["id"] if row else None
    except Exception as e:
        logger.warning("Failed to log retrieval for %s: %s", source_name, str(e)[:200])
        return None


class RetrievalTimer:
    """Context manager for timing external retrievals and auto-logging."""

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        source_name: str,
        operation: str,
        endpoint_url: Optional[str] = None,
        triggered_by: str = "scheduler",
        user_id: Optional[int] = None,
        pid: Optional[str] = None,
    ):
        self.db_pool = db_pool
        self.source_name = source_name
        self.operation = operation
        self.endpoint_url = endpoint_url
        self.triggered_by = triggered_by
        self.user_id = user_id
        self.pid = pid
        self._start: float = 0
        self.response_status: Optional[int] = None
        self.records_returned: int = 0
        self.records_stored: int = 0
        self.error_message: Optional[str] = None
        self.request_params: Optional[dict] = None

    async def __aenter__(self):
        self._start = time.monotonic()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.monotonic() - self._start) * 1000)
        if exc_val and not self.error_message:
            self.error_message = str(exc_val)[:500]
        if exc_val and self.response_status is None:
            self.response_status = 500

        await log_retrieval(
            self.db_pool,
            source_name=self.source_name,
            operation=self.operation,
            endpoint_url=self.endpoint_url,
            request_params=self.request_params,
            response_status=self.response_status,
            records_returned=self.records_returned,
            records_stored=self.records_stored,
            error_message=self.error_message,
            duration_ms=duration_ms,
            triggered_by=self.triggered_by,
            user_id=self.user_id,
            pid=self.pid,
        )
        return False  # Don't suppress exceptions


async def get_retrieval_summary(
    db_pool: asyncpg.Pool,
    days_back: int = 7,
) -> list[dict]:
    """
    Get a summary of recent external retrievals grouped by source.

    Returns list of dicts with source_name, total_calls, success_count,
    error_count, avg_duration_ms, last_retrieval.
    """
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT "
                "source_name, "
                "COUNT(*) AS total_calls, "
                "COUNT(*) FILTER (WHERE response_status BETWEEN 200 AND 299) AS success_count, "
                "COUNT(*) FILTER (WHERE error_message IS NOT NULL) AS error_count, "
                "AVG(duration_ms)::INTEGER AS avg_duration_ms, "
                "MAX(created_at) AS last_retrieval, "
                "SUM(records_stored) AS total_records_stored "
                "FROM external_retrieval_log "
                "WHERE created_at >= NOW() - make_interval(days => $1) "
                "GROUP BY source_name "
                "ORDER BY last_retrieval DESC",
                days_back,
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("Failed to get retrieval summary: %s", str(e)[:200])
        return []
