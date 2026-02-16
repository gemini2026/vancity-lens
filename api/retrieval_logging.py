"""Retrieval audit logging (DI-005) and data freshness monitoring (DI-006)."""

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RetrievalTracker:
    """Tracks a single external data retrieval for audit logging."""

    def __init__(self, source_id: str, query_params: Optional[dict] = None):
        self.source_id = source_id
        self.query_params = query_params or {}
        self.http_status: Optional[int] = None
        self.record_count: Optional[int] = None
        self.error_message: Optional[str] = None
        self._start = time.perf_counter()

    def set_status(self, status: int) -> None:
        self.http_status = status

    def set_record_count(self, count: int) -> None:
        self.record_count = count

    def set_error(self, message: str) -> None:
        self.error_message = message

    @property
    def duration_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)


@asynccontextmanager
async def log_retrieval(db_pool, source_id: str, query_params: Optional[dict] = None):
    """Context manager that logs a retrieval to the audit table.

    Usage:
        async with log_retrieval(pool, "DS-001", {"q": "permits"}) as tracker:
            resp = await client.get(url)
            tracker.set_status(resp.status_code)
            tracker.set_record_count(10)
    """
    tracker = RetrievalTracker(source_id, query_params)
    try:
        yield tracker
    except Exception as exc:
        tracker.set_error(str(exc))
        raise
    finally:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO retrieval_log
                        (source_id, query_params, http_status,
                         record_count, duration_ms, error_message)
                    VALUES ($1, $2::jsonb, $3, $4, $5, $6)
                    """,
                    tracker.source_id,
                    json.dumps(tracker.query_params),
                    tracker.http_status,
                    tracker.record_count,
                    tracker.duration_ms,
                    tracker.error_message,
                )
                if tracker.http_status and 200 <= tracker.http_status < 300:
                    await conn.execute(
                        """
                        UPDATE data_source_freshness
                        SET last_successful_retrieval = NOW(),
                            updated_at = NOW()
                        WHERE source_id = $1
                        """,
                        tracker.source_id,
                    )
        except Exception as log_err:
            logger.warning(
                "Failed to log retrieval for %s: %s",
                source_id, log_err,
            )
