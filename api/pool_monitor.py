"""
VanCity Lens — Database Connection Pool Monitoring (VCL-87 / PERF-013).

Provides real-time metrics collection and health monitoring for asyncpg connection pool.
Tracks utilization, timing, errors, and pool exhaustion events.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional
from contextlib import asynccontextmanager

import asyncpg

logger = logging.getLogger(__name__)


# ── Data Classes ──────────────────────────────────────────────────


@dataclass
class PoolMetrics:
    """Real-time metrics snapshot of the connection pool."""

    size: int = 0
    min_size: int = 0
    max_size: int = 0
    free_size: int = 0
    used_size: int = 0
    utilization_pct: float = 0.0
    queries_total: int = 0
    queries_active: int = 0
    avg_acquire_time_ms: float = 0.0
    max_acquire_time_ms: float = 0.0
    connection_errors: int = 0
    pool_full_events: int = 0
    uptime_seconds: float = 0.0


# ── Pool Monitor ──────────────────────────────────────────────────


class PoolMonitor:
    """Wraps asyncpg.Pool to collect and expose metrics."""

    def __init__(self, pool: asyncpg.Pool, check_interval: int = 30):
        """
        Initialize the pool monitor.

        Args:
            pool: An asyncpg.Pool instance to monitor.
            check_interval: Seconds between background health checks.
        """
        self.pool = pool
        self.check_interval = check_interval
        self.start_time = time.time()

        # Metrics tracking
        self._acquire_times: list[float] = []
        self._queries_total = 0
        self._queries_active = 0
        self._connection_errors = 0
        self._pool_full_events = 0
        self._background_task: Optional[asyncio.Task] = None

    def get_metrics(self) -> PoolMetrics:
        """
        Collect current pool metrics.

        Returns:
            PoolMetrics snapshot with current pool statistics.
        """
        try:
            # Get pool state from asyncpg.Pool internals
            size = self.pool.get_size()
            idle_size = self.pool.get_idle_size()
            min_size = self.pool.get_min_size()
            max_size = self.pool.get_max_size()
        except Exception as e:
            logger.warning(f"Failed to read pool state: {e}")
            # Return empty metrics on error
            return PoolMetrics(
                uptime_seconds=time.time() - self.start_time,
                connection_errors=self._connection_errors,
                pool_full_events=self._pool_full_events,
                queries_total=self._queries_total,
                queries_active=self._queries_active,
            )

        used_size = size - idle_size
        utilization_pct = 0.0
        if size > 0:
            utilization_pct = (used_size / size) * 100.0

        # Calculate acquire time statistics
        avg_acquire_ms = 0.0
        max_acquire_ms = 0.0
        if self._acquire_times:
            avg_acquire_ms = sum(self._acquire_times) / len(self._acquire_times)
            max_acquire_ms = max(self._acquire_times)

        return PoolMetrics(
            size=size,
            min_size=min_size,
            max_size=max_size,
            free_size=idle_size,
            used_size=used_size,
            utilization_pct=utilization_pct,
            queries_total=self._queries_total,
            queries_active=self._queries_active,
            avg_acquire_time_ms=avg_acquire_ms,
            max_acquire_time_ms=max_acquire_ms,
            connection_errors=self._connection_errors,
            pool_full_events=self._pool_full_events,
            uptime_seconds=time.time() - self.start_time,
        )

    def record_acquire(self, duration_ms: float) -> None:
        """
        Record a connection acquire operation.

        Args:
            duration_ms: Time taken to acquire in milliseconds.
        """
        self._acquire_times.append(duration_ms)
        # Keep rolling window of last 1000 acquire times
        if len(self._acquire_times) > 1000:
            self._acquire_times = self._acquire_times[-1000:]

    def record_error(self, error_type: str) -> None:
        """
        Record a connection error.

        Args:
            error_type: Type/description of the error.
        """
        self._connection_errors += 1
        logger.warning(f"Connection error recorded: {error_type}")

    def record_pool_full(self) -> None:
        """Record a pool exhaustion event."""
        self._pool_full_events += 1
        logger.warning("Pool exhaustion event recorded")

    def record_query_start(self) -> None:
        """Record a query start (increment active count)."""
        self._queries_active += 1

    def record_query_end(self) -> None:
        """Record a query end (decrement active count, increment total)."""
        self._queries_active = max(0, self._queries_active - 1)
        self._queries_total += 1

    def get_health_status(self) -> dict:
        """
        Determine pool health status based on metrics.

        Returns:
            dict with keys:
            - status: "healthy", "degraded", or "unhealthy"
            - utilization_pct: Current pool utilization
            - reason: Explanation of status
        """
        metrics = self.get_metrics()

        # Unhealthy thresholds
        if metrics.utilization_pct > 90 or metrics.connection_errors > 10:
            return {
                "status": "unhealthy",
                "utilization_pct": metrics.utilization_pct,
                "connection_errors": metrics.connection_errors,
                "pool_full_events": metrics.pool_full_events,
                "reason": (
                    f"High utilization ({metrics.utilization_pct:.1f}%) "
                    f"or connection errors ({metrics.connection_errors})"
                ),
            }

        # Degraded thresholds
        if metrics.utilization_pct >= 70:
            return {
                "status": "degraded",
                "utilization_pct": metrics.utilization_pct,
                "connection_errors": metrics.connection_errors,
                "pool_full_events": metrics.pool_full_events,
                "reason": f"Elevated utilization ({metrics.utilization_pct:.1f}%)",
            }

        # Healthy
        return {
            "status": "healthy",
            "utilization_pct": metrics.utilization_pct,
            "connection_errors": metrics.connection_errors,
            "pool_full_events": metrics.pool_full_events,
            "reason": "Pool operating normally",
        }

    async def start_background_check(self) -> None:
        """Start periodic background health check task."""
        if self._background_task is not None:
            logger.warning("Background check already running")
            return

        async def check_loop():
            while True:
                try:
                    await asyncio.sleep(self.check_interval)
                    metrics = self.get_metrics()
                    health = self.get_health_status()

                    if health["status"] == "degraded":
                        logger.warning(
                            f"Pool health degraded: "
                            f"utilization={metrics.utilization_pct:.1f}%, "
                            f"used={metrics.used_size}/{metrics.size}, "
                            f"errors={metrics.connection_errors}"
                        )
                    elif health["status"] == "unhealthy":
                        logger.error(
                            f"Pool health unhealthy: "
                            f"utilization={metrics.utilization_pct:.1f}%, "
                            f"used={metrics.used_size}/{metrics.size}, "
                            f"errors={metrics.connection_errors}"
                        )
                except asyncio.CancelledError:
                    logger.debug("Pool monitor background check cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in pool health check: {e}")

        self._background_task = asyncio.create_task(check_loop())
        logger.info(
            f"Pool monitor background check started (interval={self.check_interval}s)"
        )

    async def stop_background_check(self) -> None:
        """Stop the background health check task."""
        if self._background_task is None:
            return

        self._background_task.cancel()
        try:
            await self._background_task
        except asyncio.CancelledError:
            pass
        self._background_task = None
        logger.info("Pool monitor background check stopped")


# ── Monitored Database Class ──────────────────────────────────────


class MonitoredDatabase:
    """Extended Database class with pool monitoring (backward compatible)."""

    def __init__(self):
        self.pool: asyncpg.Pool | None = None
        self.monitor: PoolMonitor | None = None

    async def connect(self, db_url: str, min_size: int = 2, max_size: int = 25):
        """
        Connect to database and initialize pool monitor.

        Args:
            db_url: PostgreSQL connection URL.
            min_size: Minimum pool size.
            max_size: Maximum pool size.
        """
        self.pool = await asyncpg.create_pool(
            db_url,
            min_size=min_size,
            max_size=max_size,
            command_timeout=30,
        )
        self.monitor = PoolMonitor(self.pool)
        logger.info(
            f"Database pool created (min={min_size}, max={max_size}) with monitoring"
        )

    async def disconnect(self):
        """Close the pool and stop monitoring."""
        if self.monitor:
            await self.monitor.stop_background_check()
        if self.pool:
            await self.pool.close()
        logger.info("Database pool closed")

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection with timing and error tracking.

        Yields:
            asyncpg.Connection
        """
        if self.pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")

        start_time = time.time()
        try:
            async with self.pool.acquire() as conn:
                duration_ms = (time.time() - start_time) * 1000
                if self.monitor:
                    self.monitor.record_acquire(duration_ms)
                yield conn
        except asyncpg.TooManyConnectionsError:
            if self.monitor:
                self.monitor.record_pool_full()
            raise
        except Exception as e:
            if self.monitor:
                self.monitor.record_error(type(e).__name__)
            raise
