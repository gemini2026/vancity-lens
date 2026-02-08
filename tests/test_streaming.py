"""
Comprehensive tests for VCL-67 [PERF-008] Streaming GeoJSON/JSON responses.

Tests cover:
- StreamingGeoJSONResponse construction and headers
- Feature streaming order and format
- Empty collection handling
- Large result set simulation
- Proper JSON structure (parseable GeoJSON)
- Content-Type headers
- Streaming vs non-streaming comparison
- Error handling during streaming
- API endpoint contract tests
"""

import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from api.streaming import (
    StreamingGeoJSONResponse,
    StreamingJSONResponse,
    async_geojson_generator,
    async_json_generator,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_features():
    """Sample GeoJSON features for testing."""
    return [
        {
            "type": "Feature",
            "properties": {
                "station": "Central",
                "tier": 1,
                "max_storeys": 15,
                "max_fsr": 3.0,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-123.1, 49.2],
                        [-123.1, 49.3],
                        [-123.0, 49.3],
                        [-123.0, 49.2],
                        [-123.1, 49.2],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "station": "Main",
                "tier": 2,
                "max_storeys": 12,
                "max_fsr": 2.5,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-123.2, 49.2],
                        [-123.2, 49.3],
                        [-123.1, 49.3],
                        [-123.1, 49.2],
                        [-123.2, 49.2],
                    ]
                ],
            },
        },
    ]


@pytest.fixture
def sample_opportunities():
    """Sample opportunity objects for streaming."""
    return [
        {
            "pid": "001-123-456",
            "civic_address": "1234 Main St",
            "current_zoning": "RS-1",
            "asking_price": 2000000,
            "assessed_value": 1500000,
            "lot_area_sqm": 500,
            "lng": -123.1234,
            "lat": 49.2567,
            "station_name": "Central",
            "tier": 1,
            "max_storeys": 15,
            "max_fsr": 3.0,
            "storey_uplift": 10,
            "est_value": 5000000,
        },
        {
            "pid": "001-123-457",
            "civic_address": "5678 Granville St",
            "current_zoning": "RM-4",
            "asking_price": 1500000,
            "assessed_value": 1200000,
            "lot_area_sqm": 600,
            "lng": -123.1567,
            "lat": 49.2890,
            "station_name": "Main",
            "tier": 2,
            "max_storeys": 12,
            "max_fsr": 2.5,
            "storey_uplift": 8,
            "est_value": 4500000,
        },
    ]


@pytest.fixture
def mock_geojson_cursor(sample_features):
    """Mock asyncpg cursor returning GeoJSON features."""
    cursor = AsyncMock()
    cursor.__aiter__.return_value = iter(sample_features)
    return cursor


@pytest.fixture
def mock_json_cursor(sample_opportunities):
    """Mock asyncpg cursor returning JSON objects."""
    cursor = AsyncMock()
    cursor.__aiter__.return_value = iter(sample_opportunities)
    return cursor


async def mock_async_iter(items):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


# ────────────────────────────────────────────────────────────────────────────
# Tests: StreamingGeoJSONResponse
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_geojson_response_headers():
    """Test that StreamingGeoJSONResponse sets correct content-type header."""
    async def gen():
        yield {"type": "Feature", "properties": {}, "geometry": {}}

    response = StreamingGeoJSONResponse(gen())
    assert response.media_type == "application/geo+json"


@pytest.mark.asyncio
async def test_streaming_geojson_response_empty():
    """Test streaming empty feature collection."""
    async def gen():
        return
        yield  # noqa: unreachable

    response = StreamingGeoJSONResponse(gen())

    # Consume the response content
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    assert data["type"] == "FeatureCollection"
    assert data["features"] == []


@pytest.mark.asyncio
async def test_streaming_geojson_response_single_feature(sample_features):
    """Test streaming single feature."""
    features = sample_features[:1]

    async def gen():
        for f in features:
            yield f

    response = StreamingGeoJSONResponse(gen())

    # Consume the response content
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1
    assert data["features"][0]["properties"]["station"] == "Central"


@pytest.mark.asyncio
async def test_streaming_geojson_response_multiple_features(sample_features):
    """Test streaming multiple features with correct formatting."""
    async def gen():
        for f in sample_features:
            yield f

    response = StreamingGeoJSONResponse(gen())

    # Consume the response content
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")

    # Verify it's valid GeoJSON
    data = json.loads(result)
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 2

    # Verify feature order
    assert data["features"][0]["properties"]["station"] == "Central"
    assert data["features"][1]["properties"]["station"] == "Main"


@pytest.mark.asyncio
async def test_streaming_geojson_response_feature_properties(sample_features):
    """Test that feature properties are preserved correctly."""
    async def gen():
        yield sample_features[0]

    response = StreamingGeoJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    feature = data["features"][0]
    assert feature["properties"]["station"] == "Central"
    assert feature["properties"]["tier"] == 1
    assert feature["properties"]["max_storeys"] == 15
    assert feature["properties"]["max_fsr"] == 3.0


@pytest.mark.asyncio
async def test_streaming_geojson_response_geometry_preserved(sample_features):
    """Test that geometry is preserved in streaming response."""
    async def gen():
        yield sample_features[0]

    response = StreamingGeoJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    feature = data["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    assert len(feature["geometry"]["coordinates"]) == 1


@pytest.mark.asyncio
async def test_streaming_geojson_response_large_dataset():
    """Test streaming large number of features."""
    num_features = 100

    async def gen():
        for i in range(num_features):
            yield {
                "type": "Feature",
                "properties": {"id": i, "name": f"Feature {i}"},
                "geometry": {"type": "Point", "coordinates": [0, 0]},
            }

    response = StreamingGeoJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    assert len(data["features"]) == num_features
    assert data["features"][0]["properties"]["id"] == 0
    assert data["features"][-1]["properties"]["id"] == num_features - 1


@pytest.mark.asyncio
async def test_streaming_geojson_response_json_validity(sample_features):
    """Test that response produces valid, parseable GeoJSON."""
    async def gen():
        for f in sample_features:
            yield f

    response = StreamingGeoJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")

    # Must be valid JSON
    data = json.loads(result)

    # Must be valid GeoJSON FeatureCollection
    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)

    # Each feature must be valid
    for feature in data["features"]:
        assert feature["type"] == "Feature"
        assert "properties" in feature
        assert "geometry" in feature


@pytest.mark.asyncio
async def test_streaming_geojson_response_comma_separated():
    """Test that features are comma-separated in output."""
    async def gen():
        for i in range(3):
            yield {
                "type": "Feature",
                "properties": {"id": i},
                "geometry": {"type": "Point", "coordinates": [0, 0]},
            }

    response = StreamingGeoJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")

    # Count commas between features (should be 2 for 3 features)
    # Strip header and closing to count feature separators
    features_section = result[result.find("[") + 1 : result.rfind("]")]
    # Parse it directly to verify structure
    data = json.loads(result)
    assert len(data["features"]) == 3


# ────────────────────────────────────────────────────────────────────────────
# Tests: StreamingJSONResponse
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_json_response_headers():
    """Test that StreamingJSONResponse sets correct content-type header."""
    async def gen():
        yield {"id": 1}

    response = StreamingJSONResponse(gen())
    assert response.media_type == "application/json"


@pytest.mark.asyncio
async def test_streaming_json_response_empty():
    """Test streaming empty JSON array."""
    async def gen():
        return
        yield  # noqa: unreachable

    response = StreamingJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    assert data == []


@pytest.mark.asyncio
async def test_streaming_json_response_single_item():
    """Test streaming single JSON item."""
    async def gen():
        yield {"id": 1, "name": "Test"}

    response = StreamingJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["name"] == "Test"


@pytest.mark.asyncio
async def test_streaming_json_response_multiple_items(sample_opportunities):
    """Test streaming multiple JSON items."""
    async def gen():
        for item in sample_opportunities:
            yield item

    response = StreamingJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    assert len(data) == 2
    assert data[0]["pid"] == "001-123-456"
    assert data[1]["pid"] == "001-123-457"


@pytest.mark.asyncio
async def test_streaming_json_response_large_dataset():
    """Test streaming large number of JSON items."""
    num_items = 50

    async def gen():
        for i in range(num_items):
            yield {"id": i, "value": i * 100}

    response = StreamingJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    assert len(data) == num_items
    assert data[0]["id"] == 0
    assert data[-1]["id"] == num_items - 1


@pytest.mark.asyncio
async def test_streaming_json_response_json_validity(sample_opportunities):
    """Test that response produces valid, parseable JSON."""
    async def gen():
        for item in sample_opportunities:
            yield item

    response = StreamingJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")

    # Must be valid JSON
    data = json.loads(result)
    assert isinstance(data, list)


# ────────────────────────────────────────────────────────────────────────────
# Tests: async_geojson_generator
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_geojson_generator_basic():
    """Test basic async_geojson_generator functionality."""
    pool = AsyncMock(spec=asyncpg.Pool)
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock transaction as async context manager
    transaction_mock = AsyncMock()
    transaction_mock.__aenter__ = AsyncMock(return_value=None)
    transaction_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction_mock)

    test_rows = [
        {"type": "Feature", "properties": {"id": 1}, "geometry": {}},
        {"type": "Feature", "properties": {"id": 2}, "geometry": {}},
    ]
    # Mock cursor() method to return an async iterator
    conn.cursor = MagicMock(return_value=mock_async_iter(test_rows))

    result = []
    async for feature in async_geojson_generator(pool, "SELECT ..."):
        result.append(feature)

    assert len(result) == 2
    assert result[0]["properties"]["id"] == 1
    assert result[1]["properties"]["id"] == 2


@pytest.mark.asyncio
async def test_async_geojson_generator_with_params():
    """Test async_geojson_generator with parameters."""
    pool = AsyncMock(spec=asyncpg.Pool)
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock transaction as async context manager
    transaction_mock = AsyncMock()
    transaction_mock.__aenter__ = AsyncMock(return_value=None)
    transaction_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction_mock)

    test_rows = [{"type": "Feature", "properties": {}, "geometry": {}}]
    conn.cursor = MagicMock(return_value=mock_async_iter(test_rows))

    result = []
    params = ["value1", 123]
    async for feature in async_geojson_generator(pool, "SELECT ... WHERE id = $1", params):
        result.append(feature)

    assert len(result) == 1
    conn.cursor.assert_called_once()


@pytest.mark.asyncio
async def test_async_geojson_generator_empty():
    """Test async_geojson_generator with no results."""
    pool = AsyncMock(spec=asyncpg.Pool)
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock transaction as async context manager
    transaction_mock = AsyncMock()
    transaction_mock.__aenter__ = AsyncMock(return_value=None)
    transaction_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction_mock)

    conn.cursor = MagicMock(return_value=mock_async_iter([]))

    result = []
    async for feature in async_geojson_generator(pool, "SELECT ..."):
        result.append(feature)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_async_geojson_generator_adds_feature_type():
    """Test that generator ensures 'type': 'Feature' in output."""
    pool = AsyncMock(spec=asyncpg.Pool)
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock transaction as async context manager
    transaction_mock = AsyncMock()
    transaction_mock.__aenter__ = AsyncMock(return_value=None)
    transaction_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction_mock)

    test_rows = [
        {"properties": {"id": 1}, "geometry": {}},  # Missing type
    ]
    conn.cursor = MagicMock(return_value=mock_async_iter(test_rows))

    result = []
    async for feature in async_geojson_generator(pool, "SELECT ..."):
        result.append(feature)

    assert result[0]["type"] == "Feature"


# ────────────────────────────────────────────────────────────────────────────
# Tests: async_json_generator
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_json_generator_basic():
    """Test basic async_json_generator functionality."""
    pool = AsyncMock(spec=asyncpg.Pool)
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock transaction as async context manager
    transaction_mock = AsyncMock()
    transaction_mock.__aenter__ = AsyncMock(return_value=None)
    transaction_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction_mock)

    test_rows = [
        {"id": 1, "name": "Item 1"},
        {"id": 2, "name": "Item 2"},
    ]
    conn.cursor = MagicMock(return_value=mock_async_iter(test_rows))

    result = []
    async for item in async_json_generator(pool, "SELECT ..."):
        result.append(item)

    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["name"] == "Item 2"


@pytest.mark.asyncio
async def test_async_json_generator_empty():
    """Test async_json_generator with no results."""
    pool = AsyncMock(spec=asyncpg.Pool)
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock transaction as async context manager
    transaction_mock = AsyncMock()
    transaction_mock.__aenter__ = AsyncMock(return_value=None)
    transaction_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction_mock)

    conn.cursor = MagicMock(return_value=mock_async_iter([]))

    result = []
    async for item in async_json_generator(pool, "SELECT ..."):
        result.append(item)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_async_json_generator_with_params():
    """Test async_json_generator with parameters."""
    pool = AsyncMock(spec=asyncpg.Pool)
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock transaction as async context manager
    transaction_mock = AsyncMock()
    transaction_mock.__aenter__ = AsyncMock(return_value=None)
    transaction_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction_mock)

    test_rows = [{"id": 1}]
    conn.cursor = MagicMock(return_value=mock_async_iter(test_rows))

    result = []
    params = [100]
    async for item in async_json_generator(pool, "SELECT ... LIMIT $1", params):
        result.append(item)

    assert len(result) == 1
    conn.cursor.assert_called_once()


# ────────────────────────────────────────────────────────────────────────────
# Tests: Error Handling
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_geojson_response_handles_generator_error():
    """Test that StreamingGeoJSONResponse handles generator errors gracefully."""
    async def gen():
        yield {"type": "Feature", "properties": {}, "geometry": {}}
        raise ValueError("Test error")

    response = StreamingGeoJSONResponse(gen())
    chunks = []

    with pytest.raises(ValueError):
        async for chunk in response.body_iterator:
            chunks.append(chunk)

    # Should have yielded at least the opening bracket
    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_async_geojson_generator_handles_db_error():
    """Test async_geojson_generator handles database errors."""
    pool = AsyncMock(spec=asyncpg.Pool)
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock transaction as async context manager
    transaction_mock = AsyncMock()
    transaction_mock.__aenter__ = AsyncMock(return_value=None)
    transaction_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction_mock)

    conn.cursor = MagicMock(
        side_effect=asyncpg.PostgresError("Connection lost")
    )

    with pytest.raises(asyncpg.PostgresError):
        async for _ in async_geojson_generator(pool, "SELECT ..."):
            pass


# ────────────────────────────────────────────────────────────────────────────
# Tests: Streaming vs Non-Streaming Comparison
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_response_produces_same_data_as_non_streaming(
    sample_features,
):
    """Test that streaming response produces same JSON as non-streaming."""
    # Streaming version
    async def gen():
        for f in sample_features:
            yield f

    streaming_response = StreamingGeoJSONResponse(gen())
    chunks = []
    async for chunk in streaming_response.body_iterator:
        chunks.append(chunk)
    streaming_result = b"".join(chunks).decode("utf-8")
    streaming_data = json.loads(streaming_result)

    # Non-streaming version
    non_streaming_data = {
        "type": "FeatureCollection",
        "features": sample_features,
    }

    assert streaming_data == non_streaming_data


@pytest.mark.asyncio
async def test_streaming_json_produces_same_data_as_non_streaming(
    sample_opportunities,
):
    """Test that streaming JSON produces same data as non-streaming."""
    # Streaming version
    async def gen():
        for item in sample_opportunities:
            yield item

    streaming_response = StreamingJSONResponse(gen())
    chunks = []
    async for chunk in streaming_response.body_iterator:
        chunks.append(chunk)
    streaming_result = b"".join(chunks).decode("utf-8")
    streaming_data = json.loads(streaming_result)

    # Non-streaming version
    non_streaming_data = sample_opportunities

    assert streaming_data == non_streaming_data


# ────────────────────────────────────────────────────────────────────────────
# Tests: Edge Cases
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_geojson_with_special_characters():
    """Test streaming GeoJSON with special characters in properties."""
    async def gen():
        yield {
            "type": "Feature",
            "properties": {
                "name": 'Test "quoted" value',
                "description": "Line 1\nLine 2",
                "emoji": "🏢",
            },
            "geometry": {"type": "Point", "coordinates": [0, 0]},
        }

    response = StreamingGeoJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    assert data["features"][0]["properties"]["name"] == 'Test "quoted" value'
    assert "\n" in data["features"][0]["properties"]["description"]
    assert data["features"][0]["properties"]["emoji"] == "🏢"


@pytest.mark.asyncio
async def test_streaming_geojson_with_numeric_values():
    """Test streaming GeoJSON with various numeric types."""
    async def gen():
        yield {
            "type": "Feature",
            "properties": {
                "int_val": 42,
                "float_val": 3.14159,
                "negative": -100,
                "zero": 0,
            },
            "geometry": {"type": "Point", "coordinates": [0, 0]},
        }

    response = StreamingGeoJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    props = data["features"][0]["properties"]
    assert props["int_val"] == 42
    assert props["float_val"] == 3.14159
    assert props["negative"] == -100
    assert props["zero"] == 0


@pytest.mark.asyncio
async def test_streaming_response_preserves_coordinate_precision():
    """Test that streaming response preserves coordinate precision."""
    async def gen():
        yield {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Point",
                "coordinates": [-123.123456789, 49.987654321],
            },
        }

    response = StreamingGeoJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    coords = data["features"][0]["geometry"]["coordinates"]
    assert coords[0] == -123.123456789
    assert coords[1] == 49.987654321


# ────────────────────────────────────────────────────────────────────────────
# Tests: API Endpoint Contract Tests (Integration-like)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_response_content_type_for_geojson():
    """Test that GeoJSON streaming response has correct content-type."""
    async def gen():
        yield {"type": "Feature", "properties": {}, "geometry": {}}

    response = StreamingGeoJSONResponse(gen())
    assert "application/geo+json" in response.media_type


@pytest.mark.asyncio
async def test_streaming_response_content_type_for_json():
    """Test that JSON streaming response has correct content-type."""
    async def gen():
        yield {"id": 1}

    response = StreamingJSONResponse(gen())
    assert "application/json" in response.media_type


@pytest.mark.asyncio
async def test_streaming_geojson_response_status_code():
    """Test that streaming response has correct status code."""
    async def gen():
        yield {"type": "Feature", "properties": {}, "geometry": {}}

    response = StreamingGeoJSONResponse(gen())
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_streaming_json_response_status_code():
    """Test that streaming JSON response has correct status code."""
    async def gen():
        yield {"id": 1}

    response = StreamingJSONResponse(gen())
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_streaming_geojson_maintains_feature_collection_contract():
    """Test that streaming response maintains GeoJSON FeatureCollection contract."""
    async def gen():
        for i in range(10):
            yield {
                "type": "Feature",
                "properties": {"id": i},
                "geometry": {"type": "Point", "coordinates": [0, 0]},
            }

    response = StreamingGeoJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    # Must follow GeoJSON spec
    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)
    assert all(f["type"] == "Feature" for f in data["features"])
    assert all("properties" in f and "geometry" in f for f in data["features"])


@pytest.mark.asyncio
async def test_streaming_json_maintains_array_contract():
    """Test that streaming JSON response maintains array contract."""
    async def gen():
        for i in range(5):
            yield {"id": i, "value": i * 10}

    response = StreamingJSONResponse(gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    assert isinstance(data, list)
    assert len(data) == 5
    assert all(isinstance(item, dict) for item in data)


# ────────────────────────────────────────────────────────────────────────────
# Tests: Performance Characteristics (Conceptual)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_response_yields_immediately():
    """Test that streaming response yields data immediately without buffering."""
    yielded_items = []

    async def gen():
        for i in range(3):
            yielded_items.append(i)
            yield {
                "type": "Feature",
                "properties": {"id": i},
                "geometry": {},
            }

    response = StreamingGeoJSONResponse(gen())

    # Start consuming but don't consume everything
    iterator = response.body_iterator
    first_chunk = await iterator.__anext__()

    # First chunk should be the opening bracket
    assert first_chunk == b'{"type":"FeatureCollection","features":['

    # Consume more
    chunks = [first_chunk]
    async for chunk in iterator:
        chunks.append(chunk)
        if len(chunks) > 10:  # Safety break
            break

    # Should have yielded items as they were generated
    assert len(yielded_items) > 0


@pytest.mark.asyncio
async def test_streaming_response_handles_slow_generator():
    """Test streaming response handles slow-producing generator."""
    async def slow_gen():
        for i in range(3):
            await asyncio.sleep(0.01)
            yield {"type": "Feature", "properties": {"id": i}, "geometry": {}}

    response = StreamingGeoJSONResponse(slow_gen())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    result = b"".join(chunks).decode("utf-8")
    data = json.loads(result)

    assert len(data["features"]) == 3
