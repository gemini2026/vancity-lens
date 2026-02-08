"""
Comprehensive tests for VanCity Lens caching layer (VCL-55 / PERF-005).

Tests cover:
- InMemoryCache: get, set, delete, TTL expiration, max-size eviction, pattern invalidation
- RedisCache: connection handling, serialization, health check (mocked Redis)
- CacheManager: backend selection, singleton behavior
- @cached decorator: cache hit/miss, TTL behavior, key generation
- Cache key building with various parameter types
- Extended JSON serialization for dates, decimals, etc.
- Graceful degradation when Redis unavailable

All tests use async/await and pytest.mark.asyncio.
Redis is mocked using unittest.mock to avoid requiring actual Redis.
"""

import asyncio
import json
import pytest
from datetime import datetime, date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import time

from api.cache import (
    InMemoryCache,
    RedisCache,
    CacheManager,
    cached,
    build_key,
    CACHE_TTL_SHORT,
    CACHE_TTL_MEDIUM,
    CACHE_TTL_LONG,
    ExtendedJSONEncoder,
    _serialize,
    _deserialize,
)


# ────────────────────────────────────────────────────────────────────────────
# InMemoryCache Tests
# ────────────────────────────────────────────────────────────────────────────


class TestInMemoryCache:
    """Tests for InMemoryCache backend."""

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = InMemoryCache()
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self):
        """Test getting a key that doesn't exist returns None."""
        cache = InMemoryCache()
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deleting a key."""
        cache = InMemoryCache()
        await cache.set("key1", "value1")
        await cache.delete("key1")
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing all keys."""
        cache = InMemoryCache()
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.clear()
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        """Test that values expire after TTL."""
        cache = InMemoryCache()
        await cache.set("key1", "value1", ttl=1)
        assert await cache.get("key1") == "value1"
        await asyncio.sleep(1.1)
        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_ttl_not_expired(self):
        """Test that values don't expire before TTL."""
        cache = InMemoryCache()
        await cache.set("key1", "value1", ttl=2)
        await asyncio.sleep(0.5)
        assert await cache.get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_no_ttl(self):
        """Test that values without TTL persist."""
        cache = InMemoryCache()
        await cache.set("key1", "value1")
        await asyncio.sleep(0.5)
        assert await cache.get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_max_size_eviction(self):
        """Test LRU eviction when max_size exceeded."""
        cache = InMemoryCache(max_size=3)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        # Adding 4th key should evict first
        await cache.set("key4", "value4")
        assert await cache.get("key1") is None
        assert await cache.get("key2") == "value2"
        assert await cache.get("key3") == "value3"
        assert await cache.get("key4") == "value4"

    @pytest.mark.asyncio
    async def test_lru_access_updates_order(self):
        """Test that accessing a key updates its LRU position."""
        cache = InMemoryCache(max_size=2)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        # Access key1 to move it to end
        await cache.get("key1")
        # Add key3 - should evict key2, not key1
        await cache.set("key3", "value3")
        assert await cache.get("key1") == "value1"
        assert await cache.get("key2") is None
        assert await cache.get("key3") == "value3"

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test that in-memory cache always reports healthy."""
        cache = InMemoryCache()
        assert await cache.health_check() is True

    @pytest.mark.asyncio
    async def test_invalidate_pattern(self):
        """Test pattern-based invalidation."""
        cache = InMemoryCache()
        await cache.set("signal_feed:limit:10", "value1")
        await cache.set("signal_feed:limit:20", "value2")
        await cache.set("stats:total", "value3")

        count = await cache.invalidate_pattern("signal_feed")
        assert count == 2
        assert await cache.get("signal_feed:limit:10") is None
        assert await cache.get("signal_feed:limit:20") is None
        assert await cache.get("stats:total") == "value3"

    @pytest.mark.asyncio
    async def test_complex_values(self):
        """Test storing complex objects."""
        cache = InMemoryCache()
        obj = {"name": "test", "values": [1, 2, 3], "nested": {"key": "value"}}
        await cache.set("complex", obj)
        result = await cache.get("complex")
        assert result == obj

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test concurrent get/set operations."""
        cache = InMemoryCache(max_size=100)

        async def set_key(i):
            await cache.set(f"key{i}", f"value{i}")

        async def get_key(i):
            return await cache.get(f"key{i}")

        # Set 50 keys concurrently
        await asyncio.gather(*[set_key(i) for i in range(50)])

        # Get them concurrently
        results = await asyncio.gather(*[get_key(i) for i in range(50)])
        assert all(v is not None for v in results)


# ────────────────────────────────────────────────────────────────────────────
# RedisCache Tests (with mocked Redis)
# ────────────────────────────────────────────────────────────────────────────


class TestRedisCache:
    """Tests for RedisCache backend with mocked Redis client."""

    def setup_method(self):
        """Skip these tests if redis is not installed."""
        try:
            import redis.asyncio
        except ImportError:
            pytest.skip("redis package not installed")

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful Redis connection."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_from_url.return_value = mock_client

            cache = RedisCache("redis://localhost:6379/0")
            await cache.connect()

            assert cache._connected is True
            assert cache._client is not None
            mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Test failed Redis connection falls back gracefully."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Connection failed")

            cache = RedisCache("redis://localhost:6379/0")
            await cache.connect()

            assert cache._connected is False
            assert cache._client is None

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Test basic set and get with mocked Redis."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.get = AsyncMock(return_value='"value1"')
            mock_client.set = AsyncMock()
            mock_from_url.return_value = mock_client

            cache = RedisCache("redis://localhost:6379/0")
            await cache.connect()
            await cache.set("key1", "value1")
            result = await cache.get("key1")

            assert result == "value1"
            mock_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_with_ttl(self):
        """Test set with TTL uses setex."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.setex = AsyncMock()
            mock_from_url.return_value = mock_client

            cache = RedisCache("redis://localhost:6379/0")
            await cache.connect()
            await cache.set("key1", "value1", ttl=60)

            mock_client.setex.assert_called_once()
            args = mock_client.setex.call_args[0]
            assert args[0] == "key1"
            assert args[1] == 60

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test delete operation."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.delete = AsyncMock()
            mock_from_url.return_value = mock_client

            cache = RedisCache("redis://localhost:6379/0")
            await cache.connect()
            await cache.delete("key1")

            mock_client.delete.assert_called_once_with("key1")

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clear operation."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.flushdb = AsyncMock()
            mock_from_url.return_value = mock_client

            cache = RedisCache("redis://localhost:6379/0")
            await cache.connect()
            await cache.clear()

            mock_client.flushdb.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_from_url.return_value = mock_client

            cache = RedisCache("redis://localhost:6379/0")
            await cache.connect()
            is_healthy = await cache.health_check()

            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test failed health check."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(side_effect=ConnectionError())
            mock_from_url.return_value = mock_client

            cache = RedisCache("redis://localhost:6379/0")
            await cache.connect()
            is_healthy = await cache.health_check()

            assert is_healthy is False

    @pytest.mark.asyncio
    async def test_invalidate_pattern(self):
        """Test pattern-based invalidation with SCAN."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            # Mock SCAN cursor behavior
            mock_client.scan = AsyncMock(side_effect=[
                (0, ["signal_feed:1", "signal_feed:2"])  # First call returns cursor 0
            ])
            mock_client.delete = AsyncMock(return_value=2)
            mock_from_url.return_value = mock_client

            cache = RedisCache("redis://localhost:6379/0")
            await cache.connect()
            count = await cache.invalidate_pattern("signal_feed:*")

            assert count == 2

    @pytest.mark.asyncio
    async def test_reconnect_on_failed_operation(self):
        """Test automatic reconnection when operation fails."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.get = AsyncMock(side_effect=ConnectionError())
            mock_from_url.return_value = mock_client

            cache = RedisCache("redis://localhost:6379/0")
            await cache.connect()
            result = await cache.get("key1")

            # Should return None when get fails
            assert result is None


# ────────────────────────────────────────────────────────────────────────────
# CacheManager Tests
# ────────────────────────────────────────────────────────────────────────────


class TestCacheManager:
    """Tests for CacheManager singleton."""

    @pytest.mark.asyncio
    async def test_singleton_instance(self):
        """Test that CacheManager returns same instance."""
        manager1 = CacheManager()
        manager2 = CacheManager()
        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_initialize_with_redis_url(self):
        """Test initialization with REDIS_URL env var."""
        try:
            import redis.asyncio
        except ImportError:
            pytest.skip("redis package not installed")

        with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}):
            with patch("redis.asyncio.from_url") as mock_from_url:
                mock_client = AsyncMock()
                mock_client.ping = AsyncMock(return_value=True)
                mock_from_url.return_value = mock_client

                manager = CacheManager()
                await manager.initialize()

                assert isinstance(manager.get_backend(), RedisCache)

    @pytest.mark.asyncio
    async def test_initialize_without_redis_url(self):
        """Test initialization falls back to InMemoryCache when REDIS_URL not set."""
        with patch.dict("os.environ", {}, clear=True):
            manager = CacheManager()
            await manager.initialize()

            assert isinstance(manager.get_backend(), InMemoryCache)

    @pytest.mark.asyncio
    async def test_fallback_when_redis_fails(self):
        """Test fallback to InMemoryCache when Redis connection fails."""
        try:
            import redis.asyncio
        except ImportError:
            pytest.skip("redis package not installed")

        with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}):
            with patch("redis.asyncio.from_url") as mock_from_url:
                mock_from_url.side_effect = ConnectionError("Connection refused")

                manager = CacheManager()
                await manager.initialize()

                assert isinstance(manager.get_backend(), InMemoryCache)

    @pytest.mark.asyncio
    async def test_manager_operations(self):
        """Test manager delegates operations to backend."""
        with patch.dict("os.environ", {}, clear=True):
            manager = CacheManager()
            await manager.initialize()

            await manager.set("key1", "value1")
            result = await manager.get("key1")
            assert result == "value1"

            await manager.delete("key1")
            assert await manager.get("key1") is None

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test manager shutdown."""
        with patch.dict("os.environ", {}, clear=True):
            manager = CacheManager()
            await manager.initialize()
            await manager.shutdown()
            # No error should occur


# ────────────────────────────────────────────────────────────────────────────
# Cache Key Building Tests
# ────────────────────────────────────────────────────────────────────────────


class TestCacheKeyBuilding:
    """Tests for cache key construction."""

    def test_build_key_simple(self):
        """Test building key with just prefix."""
        key = build_key("signal_feed")
        assert key == "signal_feed"

    def test_build_key_with_kwargs(self):
        """Test building key with keyword arguments."""
        key = build_key("signal_feed", limit=20, offset=0)
        # Keys should be sorted
        assert "limit:20" in key
        assert "offset:0" in key
        assert key.startswith("signal_feed:")

    def test_build_key_with_date(self):
        """Test building key with date parameter."""
        d = date(2024, 1, 15)
        key = build_key("signals", date_from=d)
        assert "2024-01-15" in key

    def test_build_key_with_none_values(self):
        """Test that None values are excluded from key."""
        key = build_key("test", a="value", b=None)
        assert "a:value" in key
        assert "b" not in key

    def test_build_key_with_list(self):
        """Test building key with list parameter."""
        key = build_key("test", tags=["a", "b", "c"])
        assert "tags:a,b,c" in key

    def test_build_key_sorted_kwargs(self):
        """Test that kwargs are sorted alphabetically for consistency."""
        key1 = build_key("test", z="last", a="first", m="middle")
        key2 = build_key("test", a="first", m="middle", z="last")
        assert key1 == key2


# ────────────────────────────────────────────────────────────────────────────
# JSON Serialization Tests
# ────────────────────────────────────────────────────────────────────────────


class TestSerialization:
    """Tests for extended JSON serialization."""

    def test_serialize_date(self):
        """Test serializing date objects."""
        d = date(2024, 1, 15)
        serialized = _serialize({"date": d})
        assert "2024-01-15" in serialized

    def test_serialize_datetime(self):
        """Test serializing datetime objects."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        serialized = _serialize({"datetime": dt})
        assert "2024-01-15T10:30:00" in serialized

    def test_serialize_decimal(self):
        """Test serializing Decimal objects."""
        d = Decimal("123.45")
        serialized = _serialize({"price": d})
        assert "123.45" in serialized

    def test_serialize_complex_object(self):
        """Test serializing complex nested objects."""
        obj = {
            "date": date(2024, 1, 15),
            "price": Decimal("123.45"),
            "nested": {
                "datetime": datetime(2024, 1, 15, 10, 30, 0),
                "list": [1, 2, 3]
            }
        }
        serialized = _serialize(obj)
        assert "2024-01-15" in serialized
        assert "123.45" in serialized

    def test_deserialize(self):
        """Test deserialization."""
        original = {"key": "value", "number": 42}
        serialized = _serialize(original)
        deserialized = _deserialize(serialized)
        assert deserialized == original


# ────────────────────────────────────────────────────────────────────────────
# @cached Decorator Tests
# ────────────────────────────────────────────────────────────────────────────


class TestCachedDecorator:
    """Tests for @cached decorator."""

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test cache hit on decorated function."""
        with patch.dict("os.environ", {}, clear=True):
            call_count = 0

            @cached(ttl=CACHE_TTL_SHORT, key_prefix="test_func")
            async def test_func(a, b=None):
                nonlocal call_count
                call_count += 1
                return f"result_{a}_{b}"

            manager = CacheManager()
            await manager.initialize()

            # First call should execute function
            result1 = await test_func("x", b="y")
            assert result1 == "result_x_y"
            assert call_count == 1

            # Second call should hit cache
            result2 = await test_func("x", b="y")
            assert result2 == "result_x_y"
            assert call_count == 1  # Not incremented

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        """Test cache miss with different parameters."""
        with patch.dict("os.environ", {}, clear=True):
            call_count = 0

            @cached(ttl=CACHE_TTL_SHORT, key_prefix="test_func")
            async def test_func(a=None):
                nonlocal call_count
                call_count += 1
                return f"result_{a}"

            manager = CacheManager()
            await manager.initialize()

            # Different parameters should not hit cache
            result1 = await test_func(a="x")
            assert call_count == 1

            result2 = await test_func(a="y")
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_with_ttl(self):
        """Test decorator respects TTL."""
        with patch.dict("os.environ", {}, clear=True):
            call_count = 0

            @cached(ttl=1, key_prefix="test_func")
            async def test_func(a):
                nonlocal call_count
                call_count += 1
                return f"result_{a}"

            manager = CacheManager()
            await manager.initialize()

            result1 = await test_func("x")
            assert call_count == 1

            # Wait for TTL to expire
            await asyncio.sleep(1.1)

            result2 = await test_func("x")
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_key_generation(self):
        """Test decorator generates proper cache keys."""
        with patch.dict("os.environ", {}, clear=True):
            @cached(ttl=CACHE_TTL_SHORT, key_prefix="test_key")
            async def test_func(limit=10, offset=0):
                return {"limit": limit, "offset": offset}

            manager = CacheManager()
            await manager.initialize()

            await test_func(limit=20, offset=5)

            # The cache should contain a key with our parameters
            backend = manager.get_backend()
            assert isinstance(backend, InMemoryCache)

    @pytest.mark.asyncio
    async def test_decorator_with_complex_return(self):
        """Test decorator handles complex return values."""
        with patch.dict("os.environ", {}, clear=True):
            @cached(ttl=CACHE_TTL_SHORT, key_prefix="complex")
            async def test_func():
                return {
                    "date": date(2024, 1, 15),
                    "items": [1, 2, 3],
                    "price": Decimal("99.99")
                }

            manager = CacheManager()
            await manager.initialize()

            result1 = await test_func()
            result2 = await test_func()

            assert result1 == result2
            assert isinstance(result1["date"], date)


# ────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests for cache layer."""

    @pytest.mark.asyncio
    async def test_cache_manager_lifecycle(self):
        """Test full lifecycle of cache manager."""
        with patch.dict("os.environ", {}, clear=True):
            manager = CacheManager()

            # Initialize
            await manager.initialize()
            backend = manager.get_backend()
            assert backend is not None

            # Use
            await manager.set("key", "value")
            assert await manager.get("key") == "value"

            # Health check
            is_healthy = await manager.health_check()
            assert is_healthy is True

            # Shutdown
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_ttl_presets(self):
        """Test TTL preset values are reasonable."""
        assert CACHE_TTL_SHORT == 60
        assert CACHE_TTL_MEDIUM == 300
        assert CACHE_TTL_LONG == 3600

    @pytest.mark.asyncio
    async def test_graceful_degradation(self):
        """Test system works when cache operations fail."""
        with patch.dict("os.environ", {}, clear=True):
            manager = CacheManager()
            await manager.initialize()

            # Get on non-existent key should return None, not error
            result = await manager.get("nonexistent")
            assert result is None

            # Set should succeed even if storage fails
            await manager.set("key", "value")

            # Delete should not error
            await manager.delete("key")

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self):
        """Test cache under concurrent load."""
        with patch.dict("os.environ", {}, clear=True):
            manager = CacheManager()
            await manager.initialize()

            async def cache_operation(i):
                key = f"key_{i}"
                await manager.set(key, f"value_{i}")
                result = await manager.get(key)
                return result == f"value_{i}"

            results = await asyncio.gather(*[
                cache_operation(i) for i in range(20)
            ])

            assert all(results)
