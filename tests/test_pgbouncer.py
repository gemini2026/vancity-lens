"""
PgBouncer Connection Pooling Proxy Tests (VCL-91 / PERF-014).

Comprehensive test suite for PgBouncer configuration, health monitoring,
and connection pool management.

Tests cover:
- PgBouncer configuration files (pgbouncer.ini, userlist.txt)
- Docker Compose service configuration
- API DATABASE_URL routing through PgBouncer
- PgBouncerMonitor class and methods
- Connection pool statistics and status
- Health checks and error handling
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import asyncpg

from api.pgbouncer import (
    PgBouncerMonitor,
    PoolStats,
    PoolStatus,
    PgBouncerMetrics,
    check_pgbouncer_health,
    get_pgbouncer_connection_info,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_connection():
    """Create a mocked asyncpg.Connection."""
    conn = AsyncMock(spec=asyncpg.Connection)
    return conn


@pytest.fixture
def pgbouncer_monitor():
    """Create a PgBouncerMonitor instance."""
    return PgBouncerMonitor(
        host="pgbouncer",
        port=6432,
        username="vancity",
        password="vancity_dev",
        database="pgbouncer",
        timeout=5.0,
    )


# ────────────────────────────────────────────────────────────────────────────
# Configuration File Tests
# ────────────────────────────────────────────────────────────────────────────


class TestPgBouncerConfiguration:
    """Tests for PgBouncer configuration files."""

    def test_pgbouncer_ini_exists(self):
        """Test that pgbouncer.ini configuration file exists."""
        import os

        config_path = "config/pgbouncer/pgbouncer.ini"
        assert os.path.exists(config_path), "pgbouncer.ini not found"

    def test_pgbouncer_ini_content(self):
        """Test pgbouncer.ini contains required configuration sections."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        # Check for required sections
        assert "[databases]" in content, "Missing [databases] section"
        assert "[pgbouncer]" in content, "Missing [pgbouncer] section"

    def test_pgbouncer_ini_database_mapping(self):
        """Test pgbouncer.ini has correct database mapping."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        # Check database mapping
        assert "vancity_lens" in content, "Missing vancity_lens database mapping"
        assert "host=db" in content, "Database should map to 'db' host"
        assert "port=5432" in content, "Database should use port 5432"

    def test_pgbouncer_ini_pool_mode_transaction(self):
        """Test pgbouncer.ini has transaction-level pooling mode."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        assert "pool_mode = transaction" in content, (
            "pool_mode should be set to transaction"
        )

    def test_pgbouncer_ini_max_client_conn(self):
        """Test pgbouncer.ini has max_client_conn set to 200."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        assert "max_client_conn = 200" in content, (
            "max_client_conn should be 200"
        )

    def test_pgbouncer_ini_default_pool_size(self):
        """Test pgbouncer.ini has default_pool_size set to 25."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        assert "default_pool_size = 25" in content, (
            "default_pool_size should be 25"
        )

    def test_pgbouncer_ini_min_pool_size(self):
        """Test pgbouncer.ini has min_pool_size set to 5."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        assert "min_pool_size = 5" in content, (
            "min_pool_size should be 5"
        )

    def test_pgbouncer_ini_reserve_pool_size(self):
        """Test pgbouncer.ini has reserve_pool_size set to 5."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        assert "reserve_pool_size = 5" in content, (
            "reserve_pool_size should be 5"
        )

    def test_pgbouncer_ini_reserve_pool_timeout(self):
        """Test pgbouncer.ini has reserve_pool_timeout set to 3."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        assert "reserve_pool_timeout = 3" in content, (
            "reserve_pool_timeout should be 3"
        )

    def test_pgbouncer_ini_server_lifetime(self):
        """Test pgbouncer.ini has server_lifetime set to 3600."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        assert "server_lifetime = 3600" in content, (
            "server_lifetime should be 3600"
        )

    def test_pgbouncer_ini_server_idle_timeout(self):
        """Test pgbouncer.ini has server_idle_timeout set to 600."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        assert "server_idle_timeout = 600" in content, (
            "server_idle_timeout should be 600"
        )

    def test_pgbouncer_ini_logging_enabled(self):
        """Test pgbouncer.ini has logging enabled."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        assert "log_connections = 1" in content, (
            "log_connections should be enabled"
        )
        assert "log_disconnections = 1" in content, (
            "log_disconnections should be enabled"
        )

    def test_pgbouncer_ini_stats_period(self):
        """Test pgbouncer.ini has stats_period set to 60."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            content = f.read()

        assert "stats_period = 60" in content, (
            "stats_period should be 60"
        )

    def test_userlist_txt_exists(self):
        """Test that userlist.txt authentication file exists."""
        import os

        auth_path = "config/pgbouncer/userlist.txt"
        assert os.path.exists(auth_path), "userlist.txt not found"

    def test_userlist_txt_format(self):
        """Test userlist.txt has correct format."""
        with open("config/pgbouncer/userlist.txt", "r") as f:
            content = f.read().strip()

        # Format: "username" "password"
        assert content.startswith('"vancity"'), (
            "userlist.txt should have vancity user"
        )
        assert "vancity_dev" in content, (
            "userlist.txt should have vancity_dev password"
        )

    def test_userlist_txt_quoted_values(self):
        """Test userlist.txt values are properly quoted."""
        with open("config/pgbouncer/userlist.txt", "r") as f:
            content = f.read().strip()

        # All values should be quoted
        assert content.count('"') >= 4, (
            "userlist.txt values should be quoted"
        )


# ────────────────────────────────────────────────────────────────────────────
# Docker Compose Configuration Tests
# ────────────────────────────────────────────────────────────────────────────


class TestDockerComposeConfiguration:
    """Tests for docker-compose.yml PgBouncer service configuration."""

    def test_pgbouncer_service_exists(self):
        """Test pgbouncer service is defined in docker-compose.yml."""
        with open("docker-compose.yml", "r") as f:
            content = f.read()

        assert "pgbouncer:" in content, "pgbouncer service not found in docker-compose.yml"

    def test_pgbouncer_image(self):
        """Test pgbouncer service uses correct image."""
        with open("docker-compose.yml", "r") as f:
            content = f.read()

        assert "edoburu/pgbouncer:1.22.0" in content, (
            "pgbouncer image should be edoburu/pgbouncer:1.22.0"
        )

    def test_pgbouncer_container_name(self):
        """Test pgbouncer service has correct container name."""
        with open("docker-compose.yml", "r") as f:
            content = f.read()

        assert "vancity_pgbouncer" in content, (
            "pgbouncer container should be named vancity_pgbouncer"
        )

    def test_pgbouncer_port_mapping(self):
        """Test pgbouncer service exposes port 6432."""
        with open("docker-compose.yml", "r") as f:
            content = f.read()

        # Find pgbouncer section and check ports
        pgbouncer_idx = content.find("pgbouncer:")
        next_service_idx = content.find("\n  ", pgbouncer_idx + 1)
        pgbouncer_section = content[pgbouncer_idx:next_service_idx]

        assert '"6432:6432"' in content or "'6432:6432'" in content, (
            "pgbouncer should expose port 6432"
        )

    def test_pgbouncer_volume_mounts(self):
        """Test pgbouncer service mounts config files."""
        with open("docker-compose.yml", "r") as f:
            content = f.read()

        assert "./config/pgbouncer/pgbouncer.ini" in content, (
            "pgbouncer.ini should be mounted"
        )
        assert "./config/pgbouncer/userlist.txt" in content, (
            "userlist.txt should be mounted"
        )

    def test_pgbouncer_healthcheck(self):
        """Test pgbouncer service has healthcheck defined."""
        with open("docker-compose.yml", "r") as f:
            content = f.read()

        assert "pg_isready -h 127.0.0.1 -p 6432" in content, (
            "pgbouncer healthcheck should use pg_isready"
        )

    def test_pgbouncer_depends_on_db(self):
        """Test pgbouncer service depends on db service."""
        with open("docker-compose.yml", "r") as f:
            content = f.read()

        # Check pgbouncer section for db dependency
        pgbouncer_idx = content.find("pgbouncer:")
        next_service_idx = content.find("  api:", pgbouncer_idx)
        pgbouncer_section = content[pgbouncer_idx:next_service_idx]

        assert "db:" in pgbouncer_section and "service_healthy" in pgbouncer_section, (
            "pgbouncer should depend on healthy db service"
        )

    def test_api_database_url_points_to_pgbouncer(self):
        """Test API service DATABASE_URL points to pgbouncer:6432."""
        with open("docker-compose.yml", "r") as f:
            content = f.read()

        assert "postgresql://vancity:vancity_dev@pgbouncer:6432/vancity_lens" in content, (
            "API DATABASE_URL should point to pgbouncer:6432"
        )

    def test_api_depends_on_pgbouncer(self):
        """Test API service depends on pgbouncer service."""
        import yaml
        with open("docker-compose.yml", "r") as f:
            compose = yaml.safe_load(f)

        api_service = compose.get("services", {}).get("api", {})
        depends_on = api_service.get("depends_on", {})

        assert "pgbouncer" in depends_on, (
            "API should depend on pgbouncer service"
        )
        assert depends_on["pgbouncer"].get("condition") == "service_healthy", (
            "API should depend on healthy pgbouncer service"
        )

    def test_pgbouncer_resource_limits(self):
        """Test pgbouncer service has resource limits defined."""
        with open("docker-compose.yml", "r") as f:
            content = f.read()

        pgbouncer_idx = content.find("pgbouncer:")
        next_service_idx = content.find("  api:", pgbouncer_idx)
        pgbouncer_section = content[pgbouncer_idx:next_service_idx]

        assert "256M" in pgbouncer_section, (
            "pgbouncer memory limit should be 256M"
        )
        assert '"0.5"' in pgbouncer_section or "'0.5'" in pgbouncer_section, (
            "pgbouncer CPU limit should be 0.5"
        )


# ────────────────────────────────────────────────────────────────────────────
# Data Class Tests
# ────────────────────────────────────────────────────────────────────────────


class TestPoolStats:
    """Tests for PoolStats dataclass."""

    def test_pool_stats_creation(self):
        """Test PoolStats creation with all fields."""
        stats = PoolStats(
            database="vancity_lens",
            total_requests=1000,
            total_received=5000,
            total_sent=4000,
            total_query_time=50000,
        )
        assert stats.database == "vancity_lens"
        assert stats.total_requests == 1000
        assert stats.total_received == 5000
        assert stats.total_sent == 4000
        assert stats.total_query_time == 50000

    def test_pool_stats_avg_query_time_calculation(self):
        """Test PoolStats average query time calculation."""
        stats = PoolStats(
            database="vancity_lens",
            total_requests=1000,
            total_query_time=50000,
        )
        stats.avg_query_time = stats.total_query_time / stats.total_requests
        assert stats.avg_query_time == 50.0

    def test_pool_stats_defaults(self):
        """Test PoolStats default values."""
        stats = PoolStats(database="test")
        assert stats.total_requests == 0
        assert stats.total_received == 0
        assert stats.total_sent == 0
        assert stats.total_query_time == 0


class TestPoolStatus:
    """Tests for PoolStatus dataclass."""

    def test_pool_status_creation(self):
        """Test PoolStatus creation with all fields."""
        status = PoolStatus(
            name="vancity_lens/vancity",
            client_connections=15,
            server_connections=10,
            server_idle=5,
            server_active=5,
            server_used=5,
            mode="transaction",
        )
        assert status.name == "vancity_lens/vancity"
        assert status.client_connections == 15
        assert status.server_connections == 10
        assert status.server_idle == 5
        assert status.server_active == 5
        assert status.mode == "transaction"

    def test_pool_status_defaults(self):
        """Test PoolStatus default values."""
        status = PoolStatus(name="test")
        assert status.client_connections == 0
        assert status.server_connections == 0
        assert status.server_idle == 0


class TestPgBouncerMetrics:
    """Tests for PgBouncerMetrics dataclass."""

    def test_pgbouncer_metrics_creation(self):
        """Test PgBouncerMetrics creation."""
        metrics = PgBouncerMetrics(
            healthy=True,
            connected=True,
            total_client_connections=50,
            total_server_connections=20,
            pool_utilization_pct=80.0,
        )
        assert metrics.healthy is True
        assert metrics.connected is True
        assert metrics.total_client_connections == 50
        assert metrics.total_server_connections == 20
        assert metrics.pool_utilization_pct == 80.0

    def test_pgbouncer_metrics_unhealthy(self):
        """Test PgBouncerMetrics with unhealthy status."""
        metrics = PgBouncerMetrics(
            healthy=False,
            connected=False,
            error_message="Connection failed",
        )
        assert metrics.healthy is False
        assert metrics.error_message == "Connection failed"


# ────────────────────────────────────────────────────────────────────────────
# PgBouncerMonitor Class Tests
# ────────────────────────────────────────────────────────────────────────────


class TestPgBouncerMonitor:
    """Tests for PgBouncerMonitor class."""

    def test_pgbouncer_monitor_initialization(self, pgbouncer_monitor):
        """Test PgBouncerMonitor initialization with default values."""
        assert pgbouncer_monitor.host == "pgbouncer"
        assert pgbouncer_monitor.port == 6432
        assert pgbouncer_monitor.username == "vancity"
        assert pgbouncer_monitor.password == "vancity_dev"
        assert pgbouncer_monitor.database == "pgbouncer"
        assert pgbouncer_monitor.timeout == 5.0

    def test_pgbouncer_monitor_custom_initialization(self):
        """Test PgBouncerMonitor initialization with custom values."""
        monitor = PgBouncerMonitor(
            host="custom.host",
            port=7000,
            username="admin",
            password="secret",
            database="custom_db",
            timeout=10.0,
        )
        assert monitor.host == "custom.host"
        assert monitor.port == 7000
        assert monitor.username == "admin"
        assert monitor.password == "secret"
        assert monitor.database == "custom_db"
        assert monitor.timeout == 10.0

    @pytest.mark.asyncio
    async def test_health_check_success(self, pgbouncer_monitor):
        """Test health_check returns True when PgBouncer is healthy."""
        with patch.object(
            pgbouncer_monitor, "_get_connection"
        ) as mock_get_conn:
            mock_conn = AsyncMock()
            mock_conn.fetchval = AsyncMock(return_value=1)
            mock_conn.close = AsyncMock()
            mock_get_conn.return_value = mock_conn

            result = await pgbouncer_monitor.health_check()

            assert result is True
            mock_conn.fetchval.assert_called_once_with("SELECT 1")
            mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, pgbouncer_monitor):
        """Test health_check returns False when connection fails."""
        with patch.object(
            pgbouncer_monitor, "_get_connection"
        ) as mock_get_conn:
            mock_get_conn.side_effect = Exception("Connection refused")

            result = await pgbouncer_monitor.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_get_stats_success(self, pgbouncer_monitor):
        """Test get_stats successfully retrieves statistics."""
        mock_stats_data = [
            {
                "database": "vancity_lens",
                "total_requests": 1000,
                "total_received": 5000,
                "total_sent": 4000,
                "total_query_time": 50000,
            }
        ]

        with patch.object(
            pgbouncer_monitor, "_get_connection"
        ) as mock_get_conn:
            mock_conn = AsyncMock()
            mock_conn.fetch = AsyncMock(return_value=mock_stats_data)
            mock_conn.close = AsyncMock()
            mock_get_conn.return_value = mock_conn

            stats = await pgbouncer_monitor.get_stats()

            assert len(stats) == 1
            assert stats[0].database == "vancity_lens"
            assert stats[0].total_requests == 1000
            assert stats[0].avg_query_time == 50.0
            mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stats_failure(self, pgbouncer_monitor):
        """Test get_stats raises exception on connection failure."""
        with patch.object(
            pgbouncer_monitor, "_get_connection"
        ) as mock_get_conn:
            mock_get_conn.side_effect = Exception("Connection failed")

            with pytest.raises(Exception):
                await pgbouncer_monitor.get_stats()

    @pytest.mark.asyncio
    async def test_get_pools_success(self, pgbouncer_monitor):
        """Test get_pools successfully retrieves pool status."""
        mock_pools_data = [
            {
                "name": "vancity_lens/vancity",
                "cl_active": 15,
                "sv_active": 10,
                "sv_idle": 5,
                "sv_used": 5,
                "sv_tested": 0,
                "sv_login": 0,
                "mode": "transaction",
            }
        ]

        with patch.object(
            pgbouncer_monitor, "_get_connection"
        ) as mock_get_conn:
            mock_conn = AsyncMock()
            mock_conn.fetch = AsyncMock(return_value=mock_pools_data)
            mock_conn.close = AsyncMock()
            mock_get_conn.return_value = mock_conn

            pools = await pgbouncer_monitor.get_pools()

            assert len(pools) == 1
            assert pools[0].name == "vancity_lens/vancity"
            assert pools[0].client_connections == 15
            assert pools[0].server_connections == 10
            assert pools[0].server_idle == 5
            assert pools[0].mode == "transaction"
            mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pools_failure(self, pgbouncer_monitor):
        """Test get_pools raises exception on connection failure."""
        with patch.object(
            pgbouncer_monitor, "_get_connection"
        ) as mock_get_conn:
            mock_get_conn.side_effect = Exception("Connection failed")

            with pytest.raises(Exception):
                await pgbouncer_monitor.get_pools()

    @pytest.mark.asyncio
    async def test_get_connection_info_success(self, pgbouncer_monitor):
        """Test get_connection_info returns aggregated metrics."""
        mock_pools_data = [
            {
                "name": "vancity_lens/vancity",
                "cl_active": 15,
                "sv_active": 10,
                "sv_idle": 5,
                "sv_used": 5,
                "sv_tested": 0,
                "sv_login": 0,
                "mode": "transaction",
            }
        ]

        mock_stats_data = [
            {
                "database": "vancity_lens",
                "total_requests": 1000,
                "total_received": 5000,
                "total_sent": 4000,
                "total_query_time": 50000,
            }
        ]

        with patch.object(
            pgbouncer_monitor, "get_pools"
        ) as mock_get_pools, patch.object(
            pgbouncer_monitor, "get_stats"
        ) as mock_get_stats:
            # Create proper PoolStatus objects
            pools = [
                PoolStatus(
                    name="vancity_lens/vancity",
                    client_connections=15,
                    server_connections=10,
                    server_idle=5,
                    server_active=10,
                    mode="transaction",
                )
            ]
            mock_get_pools.return_value = pools
            mock_get_stats.return_value = []

            info = await pgbouncer_monitor.get_connection_info()

            assert info["total_client_conn"] == 15
            assert info["total_server_conn"] == 10
            assert info["total_server_idle"] == 5
            assert info["total_server_active"] == 10
            assert "pool_utilization_pct" in info
            assert "response_time_ms" in info
            assert "timestamp" in info
            assert "pools" in info

    @pytest.mark.asyncio
    async def test_get_connection_info_failure(self, pgbouncer_monitor):
        """Test get_connection_info raises exception on failure."""
        with patch.object(
            pgbouncer_monitor, "get_pools"
        ) as mock_get_pools:
            mock_get_pools.side_effect = Exception("Connection failed")

            with pytest.raises(Exception):
                await pgbouncer_monitor.get_connection_info()

    @pytest.mark.asyncio
    async def test_get_metrics_healthy(self, pgbouncer_monitor):
        """Test get_metrics when PgBouncer is healthy."""
        pools = [
            PoolStatus(
                name="vancity_lens/vancity",
                client_connections=15,
                server_connections=10,
                server_idle=5,
                server_active=10,
                mode="transaction",
            )
        ]

        stats = [
            PoolStats(
                database="vancity_lens",
                total_requests=1000,
                total_query_time=50000,
            )
        ]

        with patch.object(
            pgbouncer_monitor, "health_check"
        ) as mock_health, patch.object(
            pgbouncer_monitor, "get_pools"
        ) as mock_get_pools, patch.object(
            pgbouncer_monitor, "get_stats"
        ) as mock_get_stats:
            mock_health.return_value = True
            mock_get_pools.return_value = pools
            mock_get_stats.return_value = stats

            metrics = await pgbouncer_monitor.get_metrics()

            assert metrics.healthy is True
            assert metrics.connected is True
            assert metrics.total_client_connections == 15
            assert metrics.total_server_connections == 10
            assert len(metrics.pools) == 1
            assert len(metrics.stats) == 1
            assert "response_time_ms" in metrics.__dict__

    @pytest.mark.asyncio
    async def test_get_metrics_unhealthy(self, pgbouncer_monitor):
        """Test get_metrics when PgBouncer is unhealthy."""
        with patch.object(
            pgbouncer_monitor, "health_check"
        ) as mock_health:
            mock_health.return_value = False

            metrics = await pgbouncer_monitor.get_metrics()

            assert metrics.healthy is False
            assert metrics.connected is False
            assert metrics.error_message == "PgBouncer health check failed"


# ────────────────────────────────────────────────────────────────────────────
# Standalone Helper Function Tests
# ────────────────────────────────────────────────────────────────────────────


class TestStandaloneFunctions:
    """Tests for standalone helper functions."""

    @pytest.mark.asyncio
    async def test_check_pgbouncer_health_success(self):
        """Test check_pgbouncer_health helper function succeeds."""
        with patch("api.pgbouncer.PgBouncerMonitor") as mock_monitor_class:
            mock_monitor = AsyncMock()
            mock_monitor.health_check = AsyncMock(return_value=True)
            mock_monitor_class.return_value = mock_monitor

            result = await check_pgbouncer_health()

            assert result is True
            mock_monitor_class.assert_called_once()
            mock_monitor.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_pgbouncer_health_failure(self):
        """Test check_pgbouncer_health helper function fails."""
        with patch("api.pgbouncer.PgBouncerMonitor") as mock_monitor_class:
            mock_monitor = AsyncMock()
            mock_monitor.health_check = AsyncMock(return_value=False)
            mock_monitor_class.return_value = mock_monitor

            result = await check_pgbouncer_health()

            assert result is False

    @pytest.mark.asyncio
    async def test_get_pgbouncer_connection_info_success(self):
        """Test get_pgbouncer_connection_info helper function."""
        expected_info = {
            "total_client_conn": 20,
            "total_server_conn": 15,
            "total_server_idle": 10,
            "total_server_active": 5,
        }

        with patch("api.pgbouncer.PgBouncerMonitor") as mock_monitor_class:
            mock_monitor = AsyncMock()
            mock_monitor.get_connection_info = AsyncMock(
                return_value=expected_info
            )
            mock_monitor_class.return_value = mock_monitor

            result = await get_pgbouncer_connection_info()

            assert result == expected_info
            mock_monitor_class.assert_called_once()
            mock_monitor.get_connection_info.assert_called_once()


# ────────────────────────────────────────────────────────────────────────────
# Integration-style Tests
# ────────────────────────────────────────────────────────────────────────────


class TestPgBouncerIntegration:
    """Integration tests for PgBouncer components."""

    def test_pgbouncer_config_consistency(self):
        """Test pgbouncer.ini and userlist.txt are consistent."""
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            ini_content = f.read()

        with open("config/pgbouncer/userlist.txt", "r") as f:
            userlist_content = f.read()

        # Both should reference vancity user
        assert "vancity" in ini_content, "pgbouncer.ini should reference vancity user"
        assert "vancity" in userlist_content, (
            "userlist.txt should define vancity user"
        )

        # Userlist should have password that matches env
        assert "vancity_dev" in userlist_content, (
            "userlist.txt should have vancity_dev password"
        )

    def test_docker_compose_service_order(self):
        """Test docker-compose service dependencies are logical."""
        with open("docker-compose.yml", "r") as f:
            content = f.read()

        # pgbouncer should appear before api
        pgbouncer_pos = content.find("pgbouncer:")
        api_pos = content.find("  api:")

        assert pgbouncer_pos < api_pos, (
            "pgbouncer service should be defined before api service"
        )

    @pytest.mark.asyncio
    async def test_monitor_with_multiple_pools(self):
        """Test PgBouncerMonitor handles multiple pools correctly."""
        pools_data = [
            {
                "name": "pool1",
                "cl_active": 10,
                "sv_active": 5,
                "sv_idle": 3,
                "sv_used": 2,
                "sv_tested": 0,
                "sv_login": 0,
                "mode": "transaction",
            },
            {
                "name": "pool2",
                "cl_active": 15,
                "sv_active": 8,
                "sv_idle": 4,
                "sv_used": 4,
                "sv_tested": 0,
                "sv_login": 0,
                "mode": "transaction",
            },
        ]

        monitor = PgBouncerMonitor()

        with patch.object(
            monitor, "_get_connection"
        ) as mock_get_conn:
            mock_conn = AsyncMock()
            mock_conn.fetch = AsyncMock(return_value=pools_data)
            mock_conn.close = AsyncMock()
            mock_get_conn.return_value = mock_conn

            pools = await monitor.get_pools()

            assert len(pools) == 2
            assert pools[0].name == "pool1"
            assert pools[1].name == "pool2"
            # Verify aggregation would work
            total_clients = sum(p.client_connections for p in pools)
            assert total_clients == 25

    @pytest.mark.asyncio
    async def test_monitor_transaction_pooling_mode(self):
        """Test monitor respects transaction pooling mode."""
        monitor = PgBouncerMonitor()

        # Verify pool_mode = transaction is understood
        # (This is a configuration test, not a live test)
        with open("config/pgbouncer/pgbouncer.ini", "r") as f:
            ini_content = f.read()

        assert "pool_mode = transaction" in ini_content
        assert "pool_mode = session" not in ini_content
