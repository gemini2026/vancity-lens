"""
VanCity Lens — Database connection pool (asyncpg).
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

from .pool_monitor import MonitoredDatabase

logger = logging.getLogger(__name__)

# In production, DATABASE_URL MUST be set as an environment variable.
# The dev default is only used when VANCITY_ENV != "production".
_DEFAULT_DEV_URL = "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens"


def _get_database_url() -> str:
    """Resolve DATABASE_URL, failing loudly in production if not set."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    env = os.getenv("VANCITY_ENV", "development")
    if env == "production":
        raise RuntimeError(
            "DATABASE_URL environment variable is REQUIRED in production. "
            "Refusing to start with default credentials."
        )

    logger.warning(
        "DATABASE_URL not set — using development default. "
        "Set DATABASE_URL for production deployments."
    )
    return _DEFAULT_DEV_URL


DATABASE_URL = _get_database_url()

# Pool sizing: configurable via env vars
_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "25"))


class Database:
    """Thin wrapper around an asyncpg connection pool."""

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=_POOL_MIN,
            max_size=_POOL_MAX,
            command_timeout=30,
        )
        logger.info(f"Database pool created (min={_POOL_MIN}, max={_POOL_MAX})")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection, None]:
        if self.pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        async with self.pool.acquire() as conn:
            yield conn


# Use MonitoredDatabase as the default instance (backward compatible)
db = MonitoredDatabase()
# Wrapper to maintain backward compatibility with existing code
_original_connect = db.connect


async def _connect_wrapper():
    """Wrapper to connect without explicit parameters."""
    await _original_connect(DATABASE_URL, _POOL_MIN, _POOL_MAX)


# Replace the connect method for transparent operation
db.connect = _connect_wrapper
