"""
Redis caching layer for VanCity Lens (VCL-55 / PERF-005)

Provides:
- CacheBackend abstract base class
- RedisCache async implementation using aioredis
- InMemoryCache fallback with TTL and max-size eviction
- CacheManager singleton for automatic backend selection
- @cached decorator for function-level caching
- Cache key builders and invalidation helpers
- Proper serialization for dates, decimals, and other types
"""

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from typing import Any, Optional, Dict, Callable
from collections import OrderedDict

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
# Cache TTL Presets (seconds)
# ────────────────────────────────────────────────────────────────────────────

CACHE_TTL_SHORT = 60  # 1 minute
CACHE_TTL_MEDIUM = 300  # 5 minutes
CACHE_TTL_LONG = 3600  # 1 hour


# ────────────────────────────────────────────────────────────────────────────
# Cache Key Builders
# ────────────────────────────────────────────────────────────────────────────


def build_key(prefix: str, **kwargs) -> str:
    """
    Build a cache key from a prefix and keyword arguments.

    Args:
        prefix: Cache key prefix (e.g., "signal_feed")
        **kwargs: Additional parameters to include in key

    Returns:
        Formatted cache key (e.g., "signal_feed:limit:20:offset:0")
    """
    if not kwargs:
        return prefix

    parts = [prefix]
    for key in sorted(kwargs.keys()):
        val = kwargs[key]
        if val is None:
            continue
        # Normalize value to string
        if isinstance(val, (date, datetime)):
            val = val.isoformat()
        elif isinstance(val, (list, tuple)):
            val = ",".join(str(v) for v in val)
        parts.append(f"{key}:{val}")

    return ":".join(parts)


# ────────────────────────────────────────────────────────────────────────────
# JSON Serialization with Extended Type Support
# ────────────────────────────────────────────────────────────────────────────


class ExtendedJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles date, datetime, Decimal, and other types."""

    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        elif hasattr(obj, "__dict__"):
            return obj.__dict__
        return super().default(obj)


def _serialize(obj: Any) -> str:
    """Serialize an object to JSON string."""
    return json.dumps(obj, cls=ExtendedJSONEncoder)


def _deserialize(s: str) -> Any:
    """Deserialize a JSON string to Python object."""
    return json.loads(s)


# ────────────────────────────────────────────────────────────────────────────
# Abstract Base Class
# ────────────────────────────────────────────────────────────────────────────


class CacheBackend(ABC):
    """Abstract cache backend interface."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in cache with optional TTL."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key from cache."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all keys from cache."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if cache backend is healthy."""
        pass

    @abstractmethod
    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.

        Returns:
            Number of keys deleted
        """
        pass


# ────────────────────────────────────────────────────────────────────────────
# In-Memory Cache Implementation
# ────────────────────────────────────────────────────────────────────────────


class InMemoryCache(CacheBackend):
    """
    Simple in-memory cache with TTL and max-size eviction.

    Thread-safe via asyncio event loop (single-threaded model).
    Uses OrderedDict for LRU eviction when max_size exceeded.
    """

    def __init__(self, max_size: int = 1000):
        self._store: Dict[str, tuple[Any, Optional[float]]] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get a value, checking TTL expiration."""
        async with self._lock:
            if key not in self._store:
                return None

            value, expires_at = self._store[key]

            # Check expiration
            if expires_at is not None and time.time() >= expires_at:
                del self._store[key]
                return None

            # Move to end (for LRU)
            self._store.move_to_end(key)
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value with optional TTL."""
        async with self._lock:
            expires_at = None
            if ttl is not None:
                expires_at = time.time() + ttl

            self._store[key] = (value, expires_at)
            self._store.move_to_end(key)

            # Evict oldest if over max_size
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        """Clear all keys."""
        async with self._lock:
            self._store.clear()

    async def health_check(self) -> bool:
        """In-memory cache is always healthy."""
        return True

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate keys matching pattern (simple substring match)."""
        async with self._lock:
            keys_to_delete = [k for k in self._store if pattern in k]
            for k in keys_to_delete:
                del self._store[k]
            return len(keys_to_delete)


# ────────────────────────────────────────────────────────────────────────────
# Redis Cache Implementation
# ────────────────────────────────────────────────────────────────────────────


class RedisCache(CacheBackend):
    """
    Async Redis cache backend using redis-py with async support.

    Requires: redis[hiredis] package
    Uses: redis.asyncio.Redis for async operations
    """

    def __init__(self, redis_url: str):
        """
        Initialize Redis cache.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
        """
        self._redis_url = redis_url
        self._client = None
        self._connected = False

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            import redis.asyncio as redis_async

            self._client = await redis_async.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )

            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info(f"Redis cache connected: {self._redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            self._client = None

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            try:
                await self._client.close()
                self._connected = False
                logger.info("Redis cache disconnected")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")

    async def _ensure_connected(self) -> bool:
        """Ensure Redis is connected, attempt reconnect if needed."""
        if not self._connected or not self._client:
            try:
                await self.connect()
            except Exception as e:
                logger.error(f"Failed to reconnect to Redis: {e}")
                return False
        return self._connected

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from Redis."""
        if not await self._ensure_connected():
            return None

        try:
            value = await self._client.get(key)
            if value is None:
                return None
            return _deserialize(value)
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in Redis with optional TTL."""
        if not await self._ensure_connected():
            return

        try:
            serialized = _serialize(value)
            if ttl is not None:
                await self._client.setex(key, ttl, serialized)
            else:
                await self._client.set(key, serialized)
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {e}")

    async def delete(self, key: str) -> None:
        """Delete a key from Redis."""
        if not await self._ensure_connected():
            return

        try:
            await self._client.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error for key {key}: {e}")

    async def clear(self) -> None:
        """Clear all keys from Redis (use with caution)."""
        if not await self._ensure_connected():
            return

        try:
            await self._client.flushdb()
            logger.warning("Redis cache cleared")
        except Exception as e:
            logger.error(f"Redis clear error: {e}")

    async def health_check(self) -> bool:
        """Check Redis connection health."""
        if not await self._ensure_connected():
            return False

        try:
            response = await self._client.ping()
            return response is True or response == "PONG"
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate keys matching a pattern using Redis SCAN.

        Args:
            pattern: Redis pattern (e.g., "signal_feed:*")

        Returns:
            Number of keys deleted
        """
        if not await self._ensure_connected():
            return 0

        try:
            cursor = 0
            count = 0

            while True:
                cursor, keys = await self._client.scan(
                    cursor=cursor, match=pattern, count=100
                )

                if keys:
                    count += await self._client.delete(*keys)

                if cursor == 0:
                    break

            return count
        except Exception as e:
            logger.error(f"Redis pattern invalidation error: {e}")
            return 0


# ────────────────────────────────────────────────────────────────────────────
# Cache Manager Singleton
# ────────────────────────────────────────────────────────────────────────────


class CacheManager:
    """
    Singleton cache manager that selects backend based on environment.

    - Uses Redis if REDIS_URL env var is set
    - Falls back to InMemoryCache otherwise
    """

    _instance: Optional["CacheManager"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._backend: Optional[CacheBackend] = None
        self._initialized = True

    async def initialize(self) -> None:
        """Initialize the cache backend."""
        redis_url = os.getenv("REDIS_URL")

        if redis_url:
            logger.info("Initializing Redis cache backend")
            redis_backend = RedisCache(redis_url)
            try:
                await redis_backend.connect()
            except Exception as e:
                logger.warning(
                    f"Redis initialization failed, falling back to in-memory: {e}"
                )
            if redis_backend._connected:
                self._backend = redis_backend
            else:
                logger.warning("Redis not connected, falling back to in-memory cache")
                self._backend = InMemoryCache()
        else:
            logger.info("Initializing in-memory cache backend (REDIS_URL not set)")
            self._backend = InMemoryCache()

    async def shutdown(self) -> None:
        """Shutdown the cache backend."""
        if isinstance(self._backend, RedisCache):
            try:
                await self._backend.disconnect()
            except Exception as e:
                logger.error(f"Error shutting down Redis cache: {e}")

    def get_backend(self) -> CacheBackend:
        """Get the current cache backend."""
        if self._backend is None:
            raise RuntimeError(
                "Cache manager not initialized. Call initialize() first."
            )
        return self._backend

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        return await self.get_backend().get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in cache."""
        await self.get_backend().set(key, value, ttl)

    async def delete(self, key: str) -> None:
        """Delete a key from cache."""
        await self.get_backend().delete(key)

    async def clear(self) -> None:
        """Clear all cache."""
        await self.get_backend().clear()

    async def health_check(self) -> bool:
        """Check cache health."""
        return await self.get_backend().health_check()

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate keys matching pattern."""
        return await self.get_backend().invalidate_pattern(pattern)


# ────────────────────────────────────────────────────────────────────────────
# Decorator for Function-Level Caching
# ────────────────────────────────────────────────────────────────────────────


def cached(
    ttl: Optional[int] = None,
    key_prefix: Optional[str] = None,
):
    """
    Decorator for caching async function results.

    Args:
        ttl: Time-to-live in seconds (None = no expiration)
        key_prefix: Optional prefix for cache key (auto-generated if not provided)

    Example:
        @cached(ttl=CACHE_TTL_MEDIUM, key_prefix="signal_feed")
        async def get_signal_feed(limit: int, offset: int):
            ...
    """

    def decorator(func: Callable) -> Callable:
        prefix = key_prefix or f"{func.__module__}.{func.__name__}"

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from function args and kwargs
            cache_key = build_key(prefix, **kwargs)

            # Try to get from cache
            manager = CacheManager()
            cached_value = await manager.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value

            # Cache miss - execute function
            logger.debug(f"Cache miss: {cache_key}")
            result = await func(*args, **kwargs)

            # Store in cache
            try:
                await manager.set(cache_key, result, ttl=ttl)
            except Exception as e:
                logger.error(f"Error storing cache value for {cache_key}: {e}")

            return result

        return wrapper

    return decorator


# ────────────────────────────────────────────────────────────────────────────
# Export public API
# ────────────────────────────────────────────────────────────────────────────

__all__ = [
    "CacheBackend",
    "InMemoryCache",
    "RedisCache",
    "CacheManager",
    "cached",
    "build_key",
    "CACHE_TTL_SHORT",
    "CACHE_TTL_MEDIUM",
    "CACHE_TTL_LONG",
]
