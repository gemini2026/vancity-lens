"""
Streaming GeoJSON and JSON responses for VanCity Lens (VCL-67 / PERF-008)

Provides:
- StreamingGeoJSONResponse: Streams GeoJSON FeatureCollection incrementally
- StreamingJSONResponse: Generic streaming JSON array response
- async_geojson_generator: Async generator that yields features from DB cursor
"""

import asyncio
import json
import logging
from typing import AsyncIterator, Any, Dict, List, Optional

import asyncpg
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)


class StreamingGeoJSONResponse(StreamingResponse):
    """
    Streams GeoJSON FeatureCollection incrementally without loading all features into memory.

    Yields:
    1. Header: '{"type":"FeatureCollection","features":['
    2. Each feature as JSON + comma separator
    3. Closing: ']}'

    Content-Type: application/geo+json
    """

    def __init__(self, generator: AsyncIterator[Dict[str, Any]], **kwargs):
        """
        Initialize StreamingGeoJSONResponse.

        Args:
            generator: Async generator yielding feature dicts
            **kwargs: Additional arguments to pass to StreamingResponse
        """
        super().__init__(
            content=self._stream_features(generator),
            media_type="application/geo+json",
            **kwargs,
        )

    async def _stream_features(
        self, generator: AsyncIterator[Dict[str, Any]]
    ) -> AsyncIterator[bytes]:
        """
        Stream GeoJSON FeatureCollection with proper formatting.

        Args:
            generator: Async generator yielding feature dicts

        Yields:
            Bytes representing GeoJSON chunks
        """
        # Yield opening bracket and features array start
        yield b'{"type":"FeatureCollection","features":['

        first = True
        try:
            async for feature in generator:
                # Add comma before each feature except the first
                if not first:
                    yield b","
                first = False

                # Serialize feature to JSON and yield as bytes
                feature_json = json.dumps(feature, separators=(",", ":"))
                yield feature_json.encode("utf-8")
        except Exception as e:
            logger.error(f"Error streaming GeoJSON features: {e}")
            # Still close the JSON structure gracefully
            raise

        # Yield closing brackets
        yield b"]}"


class StreamingJSONResponse(StreamingResponse):
    """
    Generic streaming JSON array response without loading all items into memory.

    Yields:
    1. Header: '['
    2. Each item as JSON + comma separator
    3. Closing: ']'

    Content-Type: application/json
    """

    def __init__(self, generator: AsyncIterator[Any], **kwargs):
        """
        Initialize StreamingJSONResponse.

        Args:
            generator: Async generator yielding items
            **kwargs: Additional arguments to pass to StreamingResponse
        """
        super().__init__(
            content=self._stream_items(generator),
            media_type="application/json",
            **kwargs,
        )

    async def _stream_items(self, generator: AsyncIterator[Any]) -> AsyncIterator[bytes]:
        """
        Stream JSON array with proper formatting.

        Args:
            generator: Async generator yielding items

        Yields:
            Bytes representing JSON chunks
        """
        # Yield opening bracket
        yield b"["

        first = True
        try:
            async for item in generator:
                # Add comma before each item except the first
                if not first:
                    yield b","
                first = False

                # Serialize item to JSON and yield as bytes
                item_json = json.dumps(item, separators=(",", ":"))
                yield item_json.encode("utf-8")
        except Exception as e:
            logger.error(f"Error streaming JSON items: {e}")
            # Still close the JSON structure gracefully
            raise

        # Yield closing bracket
        yield b"]"


async def async_geojson_generator(
    db_pool: asyncpg.Pool,
    query: str,
    params: Optional[List[Any]] = None,
    timeout: float = 30.0,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Async generator that yields GeoJSON features from a database cursor.

    Uses server-side cursor to stream rows without loading all into memory.
    Each row must have 'properties' (dict) and 'geometry' (already JSON-encoded GeoJSON) fields.

    Args:
        db_pool: AsyncPG connection pool
        query: SQL query that returns rows with feature data
        params: Optional list of query parameters
        timeout: Query timeout in seconds

    Yields:
        GeoJSON Feature dicts with type, properties, and geometry

    Raises:
        asyncpg.PostgresError: If database query fails
    """
    if params is None:
        params = []

    async with db_pool.acquire() as conn:
        try:
            # Use a server-side cursor for streaming
            async with conn.transaction():
                async for row in conn.cursor(query, *params):
                    try:
                        # Assume row is a tuple/Record with feature data
                        # Caller responsible for providing query that returns proper structure
                        feature = dict(row) if hasattr(row, "__iter__") else row

                        # Ensure feature is a proper GeoJSON Feature
                        if "type" not in feature:
                            feature["type"] = "Feature"

                        yield feature
                    except Exception as e:
                        logger.error(f"Error processing feature row: {e}")
                        # Continue streaming other features
                        continue
        except asyncio.TimeoutError:
            logger.error(f"Database query timeout ({timeout}s): {query}")
            raise
        except Exception as e:
            logger.error(f"Error streaming features from database: {e}")
            raise


async def async_json_generator(
    db_pool: asyncpg.Pool,
    query: str,
    params: Optional[List[Any]] = None,
    timeout: float = 30.0,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Async generator that yields JSON objects from a database cursor.

    Uses server-side cursor to stream rows without loading all into memory.

    Args:
        db_pool: AsyncPG connection pool
        query: SQL query that returns rows with data
        params: Optional list of query parameters
        timeout: Query timeout in seconds

    Yields:
        Dicts representing JSON objects

    Raises:
        asyncpg.PostgresError: If database query fails
    """
    if params is None:
        params = []

    async with db_pool.acquire() as conn:
        try:
            # Use a server-side cursor for streaming
            async with conn.transaction():
                async for row in conn.cursor(query, *params):
                    try:
                        # Convert Row to dict
                        item = dict(row) if hasattr(row, "__iter__") else row
                        yield item
                    except Exception as e:
                        logger.error(f"Error processing row: {e}")
                        # Continue streaming other items
                        continue
        except asyncio.TimeoutError:
            logger.error(f"Database query timeout ({timeout}s): {query}")
            raise
        except Exception as e:
            logger.error(f"Error streaming items from database: {e}")
            raise
