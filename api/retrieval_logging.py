"""Retrieval audit logging (DI-005) and data freshness monitoring (DI-006).

Also provides record_ingestion_success() for scrapers/jobs to stamp
their last-successful-retrieval time in data_source_freshness.
"""

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger(__name__)

_last_error_log_time: float = 0.0
_ERROR_LOG_INTERVAL_S = 300  # Log at ERROR level at most once per 5 minutes


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
            global _last_error_log_time
            now = time.monotonic()
            if now - _last_error_log_time >= _ERROR_LOG_INTERVAL_S:
                logger.error(
                    "Failed to log retrieval for %s: %s",
                    source_id, log_err, exc_info=True,
                )
                _last_error_log_time = now
            else:
                logger.warning(
                    "Failed to log retrieval for %s: %s",
                    source_id, log_err,
                )


# ── Standalone freshness helpers (F02-001, F04-001) ─────────────────


# Map scraper names (as registered in the scheduler) to data_source_freshness IDs
SCRAPER_TO_SOURCE_ID = {
    "council": "DS-006",
    "dpb": "DS-015",
    "rezoning": "DS-016",
    "news": "DS-013",
    "opendata": "DS-001",
    "bclaws": "DS-005",
    "gazette": "DS-014",
    "contaminated": "DS-007",
    "statscan": "DS-008",
    "cmhc": "DS-009",
    "political_risk": "DS-017",
}


async def record_ingestion_success(db_pool, source_id: str) -> None:
    """Record a successful ingestion for a data source.

    Updates the ``last_successful_retrieval`` timestamp in the
    ``data_source_freshness`` table so the SLA monitor can detect
    stale sources.

    Args:
        db_pool: asyncpg connection pool.
        source_id: The ``source_id`` value in ``data_source_freshness``
            (e.g. ``"DS-001"``).  Alternatively, pass a scheduler scraper
            name (e.g. ``"council"``) and it will be mapped automatically.
    """
    # Allow callers to pass a scheduler scraper name for convenience
    resolved_id = SCRAPER_TO_SOURCE_ID.get(source_id, source_id)

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE data_source_freshness
                SET last_successful_retrieval = NOW(),
                    updated_at = NOW()
                WHERE source_id = $1
                """,
                resolved_id,
            )
    except Exception as exc:
        logger.warning(
            "record_ingestion_success failed for %s: %s", resolved_id, exc
        )
