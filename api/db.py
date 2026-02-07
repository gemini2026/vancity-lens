"""
VanCity Lens — Database connection pool (asyncpg).
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens"
)


class Database:
    """Thin wrapper around an asyncpg connection pool."""

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection, None]:
        if self.pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        async with self.pool.acquire() as conn:
            yield conn


db = Database()
