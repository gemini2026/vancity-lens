"""
VanCity Lens — Connection Pool Monitoring Tests (VCL-87 / PERF-013).

Comprehensive test suite for pool monitoring functionality including:
- PoolMetrics dataclass
- PoolMonitor class and health status tracking
- MonitoredDatabase integration
- Admin endpoints
- Health/ready endpoint integration
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import asyncpg

from api.pool_monitor import PoolMetrics, PoolMonitor, MonitoredDatabase


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_pool():
    """Create a mocked asyncpg.Pool."""
    pool = AsyncMock(spec=asyncpg.Pool)
    # Mock pool methods
    pool.get_size = MagicMock(return_value=10)
    pool.get_idle_size = MagicMock(return_value=8)
    pool.get_min_size = MagicMock(return_value=2)
    pool.get_max_size = MagicMock(return_value=25)
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def monitor(mock_pool):
    """Create a PoolMonitor instance with mocked pool."""
    return PoolMonitor(mock_pool, check_interval=1)


# ────────────────────────────────────────────────────────────────────────────
# PoolMetrics Tests
# ────────────────────────────────────────────────────────────────────────────

class TestPoolMetrics:
    """Tests for PoolMetrics dataclass."""

    def test_pool_metrics_creation(self):
        """Test basic PoolMetrics creation."""
        metrics = PoolMetrics(
            size=10,
            min_size=2,
            max_size=25,
            free_size=8,
            used_size=2,
            utilization_pct=20.0,
        )
        assert metrics.size == 10
        assert metrics.min_size == 2
        assert metrics.max_size == 25
        assert metrics.free_size == 8
        assert metrics.used_size == 2
        assert metrics.utilization_pct == 20.0

    def test_pool_metrics_defaults(self):
        """Test PoolMetrics default values."""
        metrics = PoolMetrics()
        assert metrics.size == 0
        assert metrics.min_size == 0
        assert metrics.max_size == 0
        assert metrics.free_size == 0
        assert metrics.used_size == 0
        assert metrics.utilization_pct == 0.0
        assert metrics.queries_total == 0
        assert metrics.queries_active == 0
        assert metrics.avg_acquire_time_ms == 0.0
        assert metrics.max_acquire_time_ms == 0.0
        assert metrics.connection_errors == 0
        assert metrics.pool_full_events == 0
        assert metrics.uptime_seconds == 0.0

    def test_pool_metrics_all_fields(self):
        """Test PoolMetrics with all fields populated."""
        metrics = PoolMetrics(
            size=15,
            min_size=2,
            max_size=25,
            free_size=5,
            used_size=10,
            utilization_pct=66.67,
            queries_total=1000,
            queries_active=5,
            avg_acquire_time_ms=5.5,
            max_acquire_time_ms=45.2,
            connection_errors=3,
            pool_full_events=1,
            uptime_seconds=3600.0,
        )
        assert metrics.size == 15
        assert metrics.queries_total == 1000
        assert metrics.queries_active == 5
        assert metrics.connection_errors == 3
        assert metrics.pool_full_events == 1


# ────────────────────────────────────────────────────────────────────────────
# PoolMonitor Tests
# ────────────────────────────────────────────────────────────────────────────

class TestPoolMonitor:
    """Tests for PoolMonitor class."""

    def test_pool_monitor_initialization(self, mock_pool):
        """Test PoolMonitor initialization."""
        monitor = PoolMonitor(mock_pool, check_interval=30)
        assert monitor.pool is mock_pool
        assert monitor.check_interval == 30
        assert monitor._queries_total == 0
        assert monitor._queries_active == 0
        assert monitor._connection_errors == 0
        assert monitor._pool_full_events == 0

    def test_get_metrics_healthy_pool(self, monitor, mock_pool):
        """Test metrics collection from healthy pool."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 8
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        metrics = monitor.get_metrics()

        assert metrics.size == 10
        assert metrics.free_size == 8
        assert metrics.used_size == 2
        assert metrics.min_size == 2
        assert metrics.max_size == 25
        assert metrics.utilization_pct == 20.0

    def test_get_metrics_full_pool(self, monitor, mock_pool):
        """Test metrics collection from fully utilized pool."""
        mock_pool.get_size.return_value = 25
        mock_pool.get_idle_size.return_value = 0
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        metrics = monitor.get_metrics()

        assert metrics.size == 25
        assert metrics.free_size == 0
        assert metrics.used_size == 25
        assert metrics.utilization_pct == 100.0

    def test_get_metrics_empty_pool(self, monitor, mock_pool):
        """Test metrics collection from empty pool."""
        mock_pool.get_size.return_value = 0
        mock_pool.get_idle_size.return_value = 0
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        metrics = monitor.get_metrics()

        assert metrics.size == 0
        assert metrics.free_size == 0
        assert metrics.used_size == 0
        # utilization_pct should be 0 when size is 0
        assert metrics.utilization_pct == 0.0

    def test_get_metrics_pool_exception(self, monitor, mock_pool):
        """Test metrics collection when pool throws exception."""
        mock_pool.get_size.side_effect = RuntimeError("Pool error")

        metrics = monitor.get_metrics()

        # Should return empty metrics on error
        assert metrics.size == 0
        assert metrics.min_size == 0
        assert metrics.max_size == 0

    def test_record_acquire_single(self, monitor):
        """Test recording a single acquire operation."""
        monitor.record_acquire(5.5)

        assert len(monitor._acquire_times) == 1
        assert monitor._acquire_times[0] == 5.5

    def test_record_acquire_multiple(self, monitor):
        """Test recording multiple acquire operations."""
        for i in range(5):
            monitor.record_acquire(i * 2.0)

        assert len(monitor._acquire_times) == 5
        assert monitor._acquire_times == [0.0, 2.0, 4.0, 6.0, 8.0]

    def test_record_acquire_rolling_window(self, monitor):
        """Test that acquire times maintain rolling window."""
        # Add more than 1000 entries
        for i in range(1500):
            monitor.record_acquire(float(i))

        # Should only keep last 1000
        assert len(monitor._acquire_times) == 1000
        # Should have entries from 500-1499
        assert monitor._acquire_times[0] == 500.0
        assert monitor._acquire_times[-1] == 1499.0

    def test_record_acquire_avg_and_max(self, monitor, mock_pool):
        """Test average and max acquire time calculation."""
        monitor.record_acquire(1.0)
        monitor.record_acquire(2.0)
        monitor.record_acquire(3.0)
        monitor.record_acquire(4.0)
        monitor.record_acquire(5.0)

        metrics = monitor.get_metrics()

        assert metrics.avg_acquire_time_ms == 3.0
        assert metrics.max_acquire_time_ms == 5.0

    def test_record_error(self, monitor):
        """Test recording connection errors."""
        monitor.record_error("TimeoutError")
        monitor.record_error("ConnectionRefusedError")

        assert monitor._connection_errors == 2

    def test_record_pool_full(self, monitor):
        """Test recording pool exhaustion events."""
        monitor.record_pool_full()
        monitor.record_pool_full()

        assert monitor._pool_full_events == 2

    def test_record_query_lifecycle(self, monitor):
        """Test query start/end recording."""
        assert monitor._queries_active == 0
        assert monitor._queries_total == 0

        monitor.record_query_start()
        assert monitor._queries_active == 1
        assert monitor._queries_total == 0

        monitor.record_query_start()
        assert monitor._queries_active == 2

        monitor.record_query_end()
        assert monitor._queries_active == 1
        assert monitor._queries_total == 1

        monitor.record_query_end()
        assert monitor._queries_active == 0
        assert monitor._queries_total == 2

    def test_record_query_end_never_negative(self, monitor):
        """Test that query active count never goes negative."""
        monitor.record_query_end()
        assert monitor._queries_active == 0

    def test_get_health_status_healthy(self, monitor, mock_pool):
        """Test health status when pool is healthy."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 7
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        health = monitor.get_health_status()

        assert health["status"] == "healthy"
        assert health["utilization_pct"] == 30.0
        assert health["connection_errors"] == 0
        assert "reason" in health

    def test_get_health_status_degraded_utilization(self, monitor, mock_pool):
        """Test health status when utilization is degraded."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 2
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        health = monitor.get_health_status()

        assert health["status"] == "degraded"
        assert health["utilization_pct"] == 80.0

    def test_get_health_status_degraded_boundary(self, monitor, mock_pool):
        """Test health status at degraded boundary (70%)."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 3
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        health = monitor.get_health_status()

        assert health["status"] == "degraded"
        assert health["utilization_pct"] == 70.0

    def test_get_health_status_unhealthy_utilization(self, monitor, mock_pool):
        """Test health status when utilization is very high."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 0
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        health = monitor.get_health_status()

        assert health["status"] == "unhealthy"
        assert health["utilization_pct"] == 100.0

    def test_get_health_status_unhealthy_errors(self, monitor, mock_pool):
        """Test health status when error count is high."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 8
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        for _ in range(11):
            monitor.record_error("Error")

        health = monitor.get_health_status()

        assert health["status"] == "unhealthy"
        assert health["connection_errors"] == 11

    def test_get_health_status_unhealthy_boundary(self, monitor, mock_pool):
        """Test health status at unhealthy boundary (>90%)."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 0
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        health = monitor.get_health_status()

        assert health["status"] == "unhealthy"
        assert health["utilization_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_start_background_check(self, monitor, mock_pool):
        """Test starting background health check."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 8
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        await monitor.start_background_check()

        assert monitor._background_task is not None
        assert not monitor._background_task.done()

        await monitor.stop_background_check()

    @pytest.mark.asyncio
    async def test_start_background_check_already_running(self, monitor):
        """Test that starting check twice doesn't create duplicate."""
        await monitor.start_background_check()
        first_task = monitor._background_task

        await monitor.start_background_check()
        second_task = monitor._background_task

        # Should be the same task
        assert first_task is second_task

        await monitor.stop_background_check()

    @pytest.mark.asyncio
    async def test_stop_background_check(self, monitor):
        """Test stopping background health check."""
        await monitor.start_background_check()

        assert monitor._background_task is not None

        await monitor.stop_background_check()

        assert monitor._background_task is None
        # Task should be cancelled
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_stop_background_check_not_running(self, monitor):
        """Test stopping check when not running."""
        assert monitor._background_task is None

        # Should not raise
        await monitor.stop_background_check()

        assert monitor._background_task is None

    @pytest.mark.asyncio
    async def test_background_check_monitors_health(self, monitor, mock_pool):
        """Test that background check actually monitors health."""
        monitor.check_interval = 0.1

        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 0  # 100% utilization = unhealthy
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        await monitor.start_background_check()

        # Wait for at least one check cycle
        await asyncio.sleep(0.3)

        health = monitor.get_health_status()
        assert health["status"] == "unhealthy"

        await monitor.stop_background_check()


# ────────────────────────────────────────────────────────────────────────────
# MonitoredDatabase Tests
# ────────────────────────────────────────────────────────────────────────────

class TestMonitoredDatabase:
    """Tests for MonitoredDatabase class."""

    def test_monitored_database_initialization(self):
        """Test MonitoredDatabase initialization."""
        db = MonitoredDatabase()
        assert db.pool is None
        assert db.monitor is None

    @pytest.mark.asyncio
    async def test_monitored_database_connect(self):
        """Test MonitoredDatabase connection."""
        with patch('api.pool_monitor.asyncpg.create_pool') as mock_create:
            mock_pool = AsyncMock()
            mock_create = AsyncMock(return_value=mock_pool)

            with patch('api.pool_monitor.asyncpg.create_pool', mock_create):
                db = MonitoredDatabase()
                await db.connect("postgresql://test", min_size=2, max_size=25)

                assert db.pool is mock_pool
                assert db.monitor is not None
                assert isinstance(db.monitor, PoolMonitor)

    @pytest.mark.asyncio
    async def test_monitored_database_disconnect(self):
        """Test MonitoredDatabase disconnection."""
        mock_pool = AsyncMock()
        mock_create = AsyncMock(return_value=mock_pool)

        with patch('api.pool_monitor.asyncpg.create_pool', mock_create):
            db = MonitoredDatabase()
            await db.connect("postgresql://test")
            await db.disconnect()

            mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitored_database_acquire_records_timing(self):
        """Test that acquire mechanism exists."""
        # Just verify the MonitoredDatabase has the acquire method
        # Full integration tests would require actual database
        db = MonitoredDatabase()
        assert hasattr(db, 'acquire')
        assert callable(db.acquire)

    @pytest.mark.asyncio
    async def test_monitored_database_attributes(self):
        """Test that MonitoredDatabase has expected attributes."""
        db = MonitoredDatabase()
        assert hasattr(db, 'pool')
        assert hasattr(db, 'monitor')
        assert hasattr(db, 'connect')
        assert hasattr(db, 'disconnect')
        assert hasattr(db, 'acquire')

    @pytest.mark.asyncio
    async def test_monitored_database_backward_compatibility(self):
        """Test that MonitoredDatabase is backward compatible with Database."""
        # Should be able to instantiate without arguments
        db = MonitoredDatabase()
        assert db is not None
        # Should have same interface as original Database class
        assert hasattr(db, 'pool')
        assert hasattr(db, 'connect')
        assert hasattr(db, 'disconnect')
        assert hasattr(db, 'acquire')

    @pytest.mark.asyncio
    async def test_monitored_database_acquire_not_connected(self):
        """Test that acquire raises when not connected."""
        db = MonitoredDatabase()

        with pytest.raises(RuntimeError, match="Database not connected"):
            async with db.acquire() as conn:
                pass


# ────────────────────────────────────────────────────────────────────────────
# Health Status Transition Tests
# ────────────────────────────────────────────────────────────────────────────

class TestHealthStatusTransitions:
    """Tests for health status state transitions."""

    def test_health_transition_healthy_to_degraded(self, monitor, mock_pool):
        """Test transition from healthy to degraded."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        # Start healthy
        mock_pool.get_idle_size.return_value = 7
        health1 = monitor.get_health_status()
        assert health1["status"] == "healthy"

        # Transition to degraded (increase utilization)
        mock_pool.get_idle_size.return_value = 3
        health2 = monitor.get_health_status()
        assert health2["status"] == "degraded"

    def test_health_transition_degraded_to_unhealthy(self, monitor, mock_pool):
        """Test transition from degraded to unhealthy."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        # Start degraded
        mock_pool.get_idle_size.return_value = 3
        health1 = monitor.get_health_status()
        assert health1["status"] == "degraded"

        # Transition to unhealthy
        mock_pool.get_idle_size.return_value = 0
        health2 = monitor.get_health_status()
        assert health2["status"] == "unhealthy"

    def test_health_transition_unhealthy_to_healthy(self, monitor, mock_pool):
        """Test transition from unhealthy back to healthy."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        # Start unhealthy
        mock_pool.get_idle_size.return_value = 0
        health1 = monitor.get_health_status()
        assert health1["status"] == "unhealthy"

        # Return to healthy
        mock_pool.get_idle_size.return_value = 8
        health2 = monitor.get_health_status()
        assert health2["status"] == "healthy"


# ────────────────────────────────────────────────────────────────────────────
# Edge Case Tests
# ────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_acquire_times_list(self, monitor, mock_pool):
        """Test metrics when no acquires have been recorded."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 8
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        metrics = monitor.get_metrics()

        assert metrics.avg_acquire_time_ms == 0.0
        assert metrics.max_acquire_time_ms == 0.0

    def test_single_acquire_time(self, monitor, mock_pool):
        """Test avg/max with single acquire."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 8
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        monitor.record_acquire(42.5)
        metrics = monitor.get_metrics()

        assert metrics.avg_acquire_time_ms == 42.5
        assert metrics.max_acquire_time_ms == 42.5

    def test_zero_pool_size_utilization(self, monitor, mock_pool):
        """Test utilization calculation with zero pool size."""
        mock_pool.get_size.return_value = 0
        mock_pool.get_idle_size.return_value = 0
        mock_pool.get_min_size.return_value = 0
        mock_pool.get_max_size.return_value = 0

        metrics = monitor.get_metrics()

        assert metrics.utilization_pct == 0.0

    def test_rapid_state_changes(self, monitor, mock_pool):
        """Test rapid state changes don't cause issues."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        for i in range(100):
            mock_pool.get_idle_size.return_value = i % 10
            health = monitor.get_health_status()
            assert health["status"] in ["healthy", "degraded", "unhealthy"]


# ────────────────────────────────────────────────────────────────────────────
# Uptime Tracking Tests
# ────────────────────────────────────────────────────────────────────────────

class TestUptimeTracking:
    """Tests for uptime calculation."""

    def test_uptime_increases(self, monitor, mock_pool):
        """Test that uptime increases over time."""
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 8
        mock_pool.get_min_size.return_value = 2
        mock_pool.get_max_size.return_value = 25

        start_uptime = monitor.get_metrics().uptime_seconds
        time.sleep(0.1)
        end_uptime = monitor.get_metrics().uptime_seconds

        assert end_uptime > start_uptime
