"""
PgBouncer Connection Pooling Proxy Monitor (VCL-91 / PERF-014).

Provides monitoring and health check capabilities for PgBouncer connection pooling proxy.
Includes stats collection, pool status monitoring, and connection metrics.

Features:
- PgBouncerMonitor: Main class for PgBouncer health checks and stats retrieval
- get_stats(): Query SHOW STATS via PgBouncer admin console
- get_pools(): Query SHOW POOLS via PgBouncer admin console
- health_check(): Verify PgBouncer is responsive
- get_connection_info(): Return pool utilization metrics
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

import asyncpg

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Data Classes
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class PoolStats:
    """Statistics for a single database pool in PgBouncer."""

    database: str
    total_requests: int = 0
    total_received: int = 0
    total_sent: int = 0
    total_query_time: int = 0
    avg_query_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PoolStatus:
    """Status of a single pool in PgBouncer."""

    name: str
    client_connections: int = 0
    server_connections: int = 0
    server_idle: int = 0
    server_active: int = 0
    server_used: int = 0
    server_tested: int = 0
    server_login: int = 0
    mode: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PgBouncerMetrics:
    """Aggregated PgBouncer metrics and health status."""

    healthy: bool = False
    connected: bool = False
    total_client_connections: int = 0
    total_server_connections: int = 0
    total_server_idle: int = 0
    total_server_active: int = 0
    pool_utilization_pct: float = 0.0
    response_time_ms: float = 0.0
    error_message: Optional[str] = None
    pools: List[PoolStatus] = field(default_factory=list)
    stats: List[PoolStats] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ────────────────────────────────────────────────────────────────────────────
# PgBouncer Monitor Class
# ────────────────────────────────────────────────────────────────────────────


class PgBouncerMonitor:
    """Monitor and manage PgBouncer connection pooling proxy.

    Provides methods to:
    - Check PgBouncer health and connectivity
    - Retrieve pool statistics and status
    - Monitor connection utilization
    - Detect connection saturation

    Attributes:
        host: PgBouncer hostname (default: 'pgbouncer')
        port: PgBouncer port (default: 6432)
        username: Admin user for PgBouncer (default: 'vancity')
        password: Admin password for PgBouncer (default: 'vancity_dev')
        database: PgBouncer admin database (default: 'pgbouncer')
        timeout: Connection timeout in seconds (default: 5.0)
    """

    def __init__(
        self,
        host: str = "pgbouncer",
        port: int = 6432,
        username: str = "vancity",
        password: str = "vancity_dev",
        database: str = "pgbouncer",
        timeout: float = 5.0,
    ):
        """Initialize PgBouncer monitor.

        Args:
            host: PgBouncer hostname
            port: PgBouncer port
            username: Admin username
            password: Admin password
            database: Admin database name
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.timeout = timeout
        self._pool: Optional[asyncpg.Pool] = None

    async def _get_connection(self) -> Optional[asyncpg.Connection]:
        """Get a connection to PgBouncer admin console.

        Returns:
            Connection object or None if connection fails

        Raises:
            asyncpg.PostgresError: If connection attempt fails
        """
        try:
            conn = await asyncpg.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database,
                timeout=self.timeout,
            )
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to PgBouncer: {e}")
            raise

    async def health_check(self) -> bool:
        """Verify PgBouncer is responsive and healthy.

        Returns:
            True if PgBouncer is healthy, False otherwise
        """
        conn = None
        try:
            conn = await self._get_connection()
            # Simple SELECT 1 query to verify connectivity
            result = await conn.fetchval("SELECT 1")
            return result == 1
        except Exception as e:
            logger.warning(f"PgBouncer health check failed: {e}")
            return False
        finally:
            if conn:
                await conn.close()

    async def get_stats(self) -> List[PoolStats]:
        """Retrieve pool statistics from PgBouncer SHOW STATS.

        Returns:
            List of PoolStats objects containing per-database statistics

        Raises:
            Exception: If query fails
        """
        conn = None
        try:
            conn = await self._get_connection()
            rows = await conn.fetch("SHOW STATS")

            stats = []
            for row in rows:
                pool_stat = PoolStats(
                    database=row.get("database", ""),
                    total_requests=row.get("total_requests", 0),
                    total_received=row.get("total_received", 0),
                    total_sent=row.get("total_sent", 0),
                    total_query_time=row.get("total_query_time", 0),
                )
                # Calculate average query time if available
                if pool_stat.total_requests > 0:
                    pool_stat.avg_query_time = (
                        pool_stat.total_query_time / pool_stat.total_requests
                    )
                stats.append(pool_stat)

            return stats
        except Exception as e:
            logger.error(f"Failed to retrieve PgBouncer stats: {e}")
            raise
        finally:
            if conn:
                await conn.close()

    async def get_pools(self) -> List[PoolStatus]:
        """Retrieve pool status from PgBouncer SHOW POOLS.

        Returns:
            List of PoolStatus objects containing per-pool connection status

        Raises:
            Exception: If query fails
        """
        conn = None
        try:
            conn = await self._get_connection()
            rows = await conn.fetch("SHOW POOLS")

            pools = []
            for row in rows:
                pool = PoolStatus(
                    name=row.get("name", ""),
                    client_connections=row.get("cl_active", 0),
                    server_connections=row.get("sv_active", 0),
                    server_idle=row.get("sv_idle", 0),
                    server_active=row.get("sv_active", 0),
                    server_used=row.get("sv_used", 0),
                    server_tested=row.get("sv_tested", 0),
                    server_login=row.get("sv_login", 0),
                    mode=row.get("mode", ""),
                )
                pools.append(pool)

            return pools
        except Exception as e:
            logger.error(f"Failed to retrieve PgBouncer pools: {e}")
            raise
        finally:
            if conn:
                await conn.close()

    async def get_connection_info(self) -> Dict[str, Any]:
        """Get comprehensive connection pool information.

        Queries both SHOW STATS and SHOW POOLS to gather complete information
        about PgBouncer pool utilization, connection counts, and performance.

        Returns:
            Dictionary containing:
                - total_client_conn: Total client connections
                - total_server_conn: Total server connections
                - total_server_idle: Total idle server connections
                - total_server_active: Total active server connections
                - pool_utilization_pct: Percentage of max pool capacity in use
                - response_time_ms: Time to query PgBouncer (ms)
                - timestamp: UTC timestamp of metrics collection

        Raises:
            Exception: If either query fails
        """
        start_time = datetime.utcnow()
        try:
            pools = await self.get_pools()
            await self.get_stats()  # validate stats are accessible

            total_client_conn = sum(p.client_connections for p in pools)
            total_server_conn = sum(p.server_connections for p in pools)
            total_server_idle = sum(p.server_idle for p in pools)
            total_server_active = sum(p.server_active for p in pools)

            # Calculate utilization percentage (assuming max_client_conn = 200)
            pool_utilization_pct = (
                (total_server_active / 25 * 100) if total_server_active > 0 else 0.0
            )

            response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return {
                "total_client_conn": total_client_conn,
                "total_server_conn": total_server_conn,
                "total_server_idle": total_server_idle,
                "total_server_active": total_server_active,
                "pool_utilization_pct": round(pool_utilization_pct, 2),
                "response_time_ms": round(response_time_ms, 2),
                "timestamp": datetime.utcnow().isoformat(),
                "pools": [
                    {
                        "name": p.name,
                        "client_connections": p.client_connections,
                        "server_connections": p.server_connections,
                        "mode": p.mode,
                    }
                    for p in pools
                ],
            }
        except Exception as e:
            logger.error(f"Failed to get connection info: {e}")
            raise

    async def get_metrics(self) -> PgBouncerMetrics:
        """Get comprehensive PgBouncer metrics.

        Aggregates health, connectivity, and pool status into a single
        PgBouncerMetrics object.

        Returns:
            PgBouncerMetrics object with full status
        """
        start_time = datetime.utcnow()
        metrics = PgBouncerMetrics()

        # Check health
        healthy = await self.health_check()
        metrics.healthy = healthy
        metrics.connected = healthy

        if healthy:
            try:
                # Get pool status
                pools = await self.get_pools()
                metrics.pools = pools
                metrics.total_client_connections = sum(
                    p.client_connections for p in pools
                )
                metrics.total_server_connections = sum(
                    p.server_connections for p in pools
                )
                metrics.total_server_idle = sum(p.server_idle for p in pools)
                metrics.total_server_active = sum(p.server_active for p in pools)

                # Calculate utilization
                if metrics.total_server_active > 0:
                    metrics.pool_utilization_pct = (
                        metrics.total_server_active / 25 * 100
                    )

                # Get stats
                try:
                    stats = await self.get_stats()
                    metrics.stats = stats
                except Exception as e:
                    logger.warning(f"Failed to get stats: {e}")

            except Exception as e:
                logger.error(f"Failed to get pool metrics: {e}")
                metrics.error_message = str(e)
        else:
            metrics.error_message = "PgBouncer health check failed"

        response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        metrics.response_time_ms = round(response_time_ms, 2)

        return metrics


# ────────────────────────────────────────────────────────────────────────────
# Standalone Helper Functions
# ────────────────────────────────────────────────────────────────────────────


async def check_pgbouncer_health(
    host: str = "pgbouncer",
    port: int = 6432,
    username: str = "vancity",
    password: str = "vancity_dev",
) -> bool:
    """Quick health check for PgBouncer.

    Args:
        host: PgBouncer hostname
        port: PgBouncer port
        username: Admin username
        password: Admin password

    Returns:
        True if healthy, False otherwise
    """
    monitor = PgBouncerMonitor(
        host=host, port=port, username=username, password=password
    )
    return await monitor.health_check()


async def get_pgbouncer_connection_info(
    host: str = "pgbouncer",
    port: int = 6432,
    username: str = "vancity",
    password: str = "vancity_dev",
) -> Dict[str, Any]:
    """Get current PgBouncer connection information.

    Args:
        host: PgBouncer hostname
        port: PgBouncer port
        username: Admin username
        password: Admin password

    Returns:
        Dictionary with connection metrics
    """
    monitor = PgBouncerMonitor(
        host=host, port=port, username=username, password=password
    )
    return await monitor.get_connection_info()
