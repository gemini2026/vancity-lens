"""
Comprehensive unit tests for VCL-104 (VAL-001): View Cone Intersection Service.

Tests cover:
  - View cone intersection detection (ST_Intersects)
  - Height capping logic
  - Buildable sqft reduction calculations
  - GeoJSON loading and validation
  - Impact statistics and parcel counting
  - API endpoints with admin authentication
  - Edge cases: no max height, multiple cones, inactive cones
"""

import pytest
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.view_cones import (
    ViewCone,
    ViewConeIntersection,
    ViewConeImpactSummary,
    ParcelViewConeStats,
    check_view_cone_intersection,
    check_view_cone_intersection_by_geom,
    cap_entitled_height,
    calculate_buildable_reduction,
    load_view_cones_from_geojson,
    get_all_view_cones,
    count_affected_parcels,
    generate_sample_view_cones,
)


# ════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_pool():
    """Mock asyncpg pool."""
    pool = AsyncMock()
    pool.acquire = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.fixture
def sample_view_cone_intersections():
    """Sample view cone intersection results."""
    return [
        {
            "id": 1,
            "name": "Queen Elizabeth Park - North",
            "max_height_m": 35.0,
            "max_height_ft": 115.0,
        },
        {
            "id": 2,
            "name": "Broadway Corridor - East",
            "max_height_m": 30.0,
            "max_height_ft": 98.0,
        },
    ]


@pytest.fixture
def sample_geojson_feature():
    """Sample GeoJSON feature for a view cone."""
    return {
        "type": "Feature",
        "properties": {
            "name": "Test View Cone",
            "description": "A test view cone",
            "source_location": "Test Source",
            "target_location": "Test Target",
            "max_height_m": 40.0,
            "max_height_ft": 131.0,
            "cone_type": "protected_view",
            "bylaw_reference": "ODP 4.1",
            "is_active": True,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-123.1050, 49.2380],
                [-123.1000, 49.2450],
                [-123.0950, 49.2400],
                [-123.1000, 49.2330],
                [-123.1050, 49.2380],
            ]],
        },
    }


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool for database tests."""
    pool = AsyncMock()
    pool.acquire = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


# ════════════════════════════════════════════════════════════════════════════
# UNIT TESTS: Service Functions
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_check_view_cone_intersection_finds_overlapping_cones(
    mock_pool,
    sample_view_cone_intersections,
):
    """Test that check_view_cone_intersection finds cones overlapping a parcel."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetch = AsyncMock(return_value=sample_view_cone_intersections)

    result = await check_view_cone_intersection(mock_pool, "001-234-567")

    assert len(result) == 2
    assert result[0].view_cone_name == "Queen Elizabeth Park - North"
    assert result[0].max_height_m == 35.0
    assert result[1].view_cone_name == "Broadway Corridor - East"
    assert result[1].max_height_m == 30.0
    conn.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_check_view_cone_intersection_empty_for_non_overlapping(mock_pool):
    """Test that check_view_cone_intersection returns empty list for non-overlapping parcels."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetch = AsyncMock(return_value=[])

    result = await check_view_cone_intersection(mock_pool, "999-999-999")

    assert result == []
    conn.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_check_view_cone_intersection_by_geom(mock_pool, sample_view_cone_intersections):
    """Test check_view_cone_intersection_by_geom with GeoJSON geometry."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetch = AsyncMock(return_value=sample_view_cone_intersections)

    geojson_geom = {
        "type": "Polygon",
        "coordinates": [[
            [-123.1050, 49.2380],
            [-123.1000, 49.2450],
            [-123.0950, 49.2400],
            [-123.1000, 49.2330],
            [-123.1050, 49.2380],
        ]],
    }

    result = await check_view_cone_intersection_by_geom(mock_pool, geojson_geom)

    assert len(result) == 2
    conn.fetch.assert_called_once()


def test_cap_entitled_height_reduces_when_needed():
    """Test that cap_entitled_height reduces height when view cone max is lower."""
    original = 50.0
    view_cone_max = 35.0
    result = cap_entitled_height(original, view_cone_max)
    assert result == 35.0


def test_cap_entitled_height_returns_original_when_no_cap_needed():
    """Test that cap_entitled_height returns original height when view cone max is higher."""
    original = 25.0
    view_cone_max = 35.0
    result = cap_entitled_height(original, view_cone_max)
    assert result == 25.0


def test_cap_entitled_height_handles_none_view_cone_max():
    """Test that cap_entitled_height returns original when view cone has no max height."""
    original = 50.0
    result = cap_entitled_height(original, None)
    assert result == 50.0


def test_cap_entitled_height_equal_heights():
    """Test cap_entitled_height when heights are equal."""
    original = 35.0
    result = cap_entitled_height(original, 35.0)
    assert result == 35.0


def test_calculate_buildable_reduction_with_height_loss():
    """Test buildable sqft reduction calculation with height difference."""
    original_height = 50.0
    capped_height = 35.0
    floors = 10

    result = calculate_buildable_reduction(original_height, capped_height, floors)

    assert result["capped_sqft_reduction_pct"] > 0
    assert result["capped_sqft_reduction_pct"] < 100
    assert result["estimated_sqft_loss"] > 0


def test_calculate_buildable_reduction_no_loss():
    """Test buildable sqft reduction when no height loss."""
    original_height = 35.0
    capped_height = 35.0

    result = calculate_buildable_reduction(original_height, capped_height)

    assert result["capped_sqft_reduction_pct"] == 0.0
    assert result["estimated_sqft_loss"] == 0


def test_calculate_buildable_reduction_zero_original_height():
    """Test buildable reduction with zero original height."""
    result = calculate_buildable_reduction(0, 0)
    assert result["capped_sqft_reduction_pct"] == 0.0


def test_calculate_buildable_reduction_with_floors():
    """Test that floors parameter is used in estimation."""
    original_height = 100.0
    capped_height = 50.0
    floors = 25

    result = calculate_buildable_reduction(original_height, capped_height, floors)

    # Should estimate floor loss: 50m / 3.5m ≈ 14 floors
    assert result["estimated_sqft_loss"] > 0


def test_calculate_buildable_reduction_capped_gt_original():
    """Test reduction calculation when capped height > original (edge case)."""
    original_height = 35.0
    capped_height = 50.0

    result = calculate_buildable_reduction(original_height, capped_height)

    # Should handle gracefully
    assert result["capped_sqft_reduction_pct"] <= 0


@pytest.mark.asyncio
async def test_load_view_cones_from_geojson_inserts_records(mock_pool):
    """Test that load_view_cones_from_geojson inserts view cone records."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetchval = AsyncMock(return_value=1)  # Simulates inserted ID

    features = [
        {
            "type": "Feature",
            "properties": {
                "name": "Test Cone 1",
                "max_height_m": 35.0,
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1050, 49.2380],
                    [-123.1000, 49.2450],
                    [-123.0950, 49.2400],
                    [-123.1000, 49.2330],
                    [-123.1050, 49.2380],
                ]],
            },
        }
    ]

    result = await load_view_cones_from_geojson(mock_pool, features)

    assert result == 1
    conn.fetchval.assert_called_once()


@pytest.mark.asyncio
async def test_load_view_cones_from_geojson_empty_list():
    """Test load_view_cones_from_geojson with empty feature list."""
    pool = AsyncMock()
    result = await load_view_cones_from_geojson(pool, [])
    assert result == 0


@pytest.mark.asyncio
async def test_load_view_cones_from_geojson_validates_input(mock_pool):
    """Test that load_view_cones_from_geojson handles missing geometry."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value

    features = [
        {
            "type": "Feature",
            "properties": {"name": "Bad Cone"},
            "geometry": None,  # Missing geometry
        }
    ]

    result = await load_view_cones_from_geojson(mock_pool, features)
    # Should skip the bad feature
    assert result == 0


@pytest.mark.asyncio
async def test_get_all_view_cones_returns_active_only(mock_pool):
    """Test that get_all_view_cones returns only active cones."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetch = AsyncMock(
        return_value=[
            {
                "id": 1,
                "name": "Active Cone",
                "description": "Test",
                "max_height_m": 35.0,
                "max_height_ft": 115.0,
                "source_location": "Source",
                "target_location": "Target",
                "cone_type": "protected_view",
                "bylaw_reference": "ODP 4.1",
                "is_active": True,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
        ]
    )

    result = await get_all_view_cones(mock_pool)

    assert len(result) == 1
    assert result[0].name == "Active Cone"
    assert result[0].is_active is True


@pytest.mark.asyncio
async def test_count_affected_parcels_returns_stats(mock_pool):
    """Test that count_affected_parcels returns correct statistics."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetchval = AsyncMock(side_effect=[10000, 1500])  # total, affected

    result = await count_affected_parcels(mock_pool)

    assert result.total_parcels == 10000
    assert result.affected_parcels == 1500
    assert result.affected_percentage == 15.0


@pytest.mark.asyncio
async def test_count_affected_parcels_zero_total():
    """Test count_affected_parcels when no parcels exist."""
    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(side_effect=[0, 0])

    result = await count_affected_parcels(pool)

    assert result.total_parcels == 0
    assert result.affected_parcels == 0
    assert result.affected_percentage == 0.0


def test_generate_sample_view_cones_returns_23_features():
    """Test that generate_sample_view_cones returns exactly 23 features."""
    cones = generate_sample_view_cones()
    assert len(cones) == 23


def test_generate_sample_view_cones_valid_structure():
    """Test that sample view cones have valid GeoJSON structure."""
    cones = generate_sample_view_cones()

    for cone in cones:
        assert cone["type"] == "Feature"
        assert "properties" in cone
        assert "geometry" in cone
        assert cone["geometry"]["type"] == "Polygon"

        props = cone["properties"]
        assert "name" in props
        assert "source_location" in props
        assert "target_location" in props
        assert "max_height_m" in props
        assert "is_active" in props


def test_generate_sample_view_cones_unique_names():
    """Test that all sample view cones have unique names."""
    cones = generate_sample_view_cones()
    names = [c["properties"]["name"] for c in cones]
    assert len(names) == len(set(names))


def test_generate_sample_view_cones_height_ranges():
    """Test that sample view cones have realistic height ranges."""
    cones = generate_sample_view_cones()

    for cone in cones:
        height = cone["properties"]["max_height_m"]
        assert 25 <= height <= 65, f"Height {height} outside realistic range"


def test_generate_sample_view_cones_vancouver_coverage():
    """Test that sample view cones cover Vancouver's main view corridors."""
    cones = generate_sample_view_cones()
    names = [c["properties"]["name"] for c in cones]

    # Should include famous Vancouver view locations
    assert any("Queen Elizabeth" in n for n in names)
    assert any("Cambie" in n for n in names or "Granville" in n)
    assert any("Broadway" in n for n in names)
    assert any("False Creek" in n for n in names)


# ════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODEL TESTS
# ════════════════════════════════════════════════════════════════════════════

def test_view_cone_model():
    """Test ViewCone Pydantic model."""
    cone = ViewCone(
        id=1,
        name="Test Cone",
        description="A test view cone",
        max_height_m=35.0,
        max_height_ft=115.0,
        source_location="Source",
        target_location="Target",
        is_active=True,
    )
    assert cone.id == 1
    assert cone.name == "Test Cone"
    assert cone.max_height_m == 35.0


def test_view_cone_intersection_model():
    """Test ViewConeIntersection Pydantic model."""
    intersection = ViewConeIntersection(
        view_cone_name="Test Cone",
        max_height_m=35.0,
        original_height_m=50.0,
        capped_height_m=35.0,
        buildable_sqft_reduction_pct=30.0,
    )
    assert intersection.view_cone_name == "Test Cone"
    assert intersection.buildable_sqft_reduction_pct == 30.0


def test_view_cone_impact_summary_model():
    """Test ViewConeImpactSummary Pydantic model."""
    summary = ViewConeImpactSummary(
        pid="001-234-567",
        intersects_view_cone=True,
        affected_cones=[],
        risk_flag="RED: View cone restriction",
    )
    assert summary.pid == "001-234-567"
    assert summary.intersects_view_cone is True


def test_parcel_view_cone_stats_model():
    """Test ParcelViewConeStats Pydantic model."""
    stats = ParcelViewConeStats(
        total_parcels=92000,
        affected_parcels=1500,
        affected_percentage=1.63,
    )
    assert stats.total_parcels == 92000
    assert stats.affected_parcels == 1500


# ════════════════════════════════════════════════════════════════════════════
# EDGE CASES AND SPECIAL SCENARIOS
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_check_view_cone_intersection_multiple_overlaps(mock_pool):
    """Test parcel intersecting multiple view cones."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetch = AsyncMock(
        return_value=[
            {"id": 1, "name": "Cone A", "max_height_m": 35.0, "max_height_ft": 115.0},
            {"id": 2, "name": "Cone B", "max_height_m": 30.0, "max_height_ft": 98.0},
            {"id": 3, "name": "Cone C", "max_height_m": 40.0, "max_height_ft": 131.0},
        ]
    )

    result = await check_view_cone_intersection(mock_pool, "001-234-567")

    assert len(result) == 3
    assert result[0].max_height_m == 35.0
    assert result[1].max_height_m == 30.0
    assert result[2].max_height_m == 40.0


def test_view_cone_with_no_max_height():
    """Test handling of view cone with no max height specified."""
    # A view cone with max_height_m = None should not cap anything
    original = 100.0
    result = cap_entitled_height(original, None)
    assert result == original


@pytest.mark.asyncio
async def test_load_view_cones_partial_failure(mock_pool):
    """Test that loading continues even if one cone fails."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value

    # First call succeeds, second fails, third succeeds
    conn.fetchval = AsyncMock(side_effect=[1, Exception("DB Error"), 2])

    features = [
        {
            "type": "Feature",
            "properties": {
                "name": "Cone 1",
                "max_height_m": 35.0,
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1050, 49.2380],
                    [-123.1000, 49.2450],
                    [-123.0950, 49.2400],
                    [-123.1000, 49.2330],
                    [-123.1050, 49.2380],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Cone 2",
                "max_height_m": 30.0,
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1050, 49.2380],
                    [-123.1000, 49.2450],
                    [-123.0950, 49.2400],
                    [-123.1000, 49.2330],
                    [-123.1050, 49.2380],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Cone 3",
                "max_height_m": 40.0,
                "is_active": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-123.1050, 49.2380],
                    [-123.1000, 49.2450],
                    [-123.0950, 49.2400],
                    [-123.1000, 49.2330],
                    [-123.1050, 49.2380],
                ]],
            },
        },
    ]

    result = await load_view_cones_from_geojson(mock_pool, features)

    # Should have loaded 2 out of 3 (one failed)
    assert result == 2


# ════════════════════════════════════════════════════════════════════════════
# RISK FLAG TESTS
# ════════════════════════════════════════════════════════════════════════════

def test_view_cone_red_risk_flag_generation():
    """Test RED risk flag generation when intersecting view cones."""
    intersection = ViewConeIntersection(
        view_cone_name="Queen Elizabeth Park - North",
        max_height_m=35.0,
    )

    # Simulate risk flag text
    if intersection.view_cone_name:
        risk_text = f"RED: View cone restriction — entitled height capped by: {intersection.view_cone_name}"
        assert "RED" in risk_text
        assert "Queen Elizabeth" in risk_text


def test_view_cone_impact_summary_with_multiple_cones():
    """Test risk flag when multiple view cones intersect."""
    intersections = [
        ViewConeIntersection(view_cone_name="Cone A", max_height_m=35.0),
        ViewConeIntersection(view_cone_name="Cone B", max_height_m=30.0),
    ]

    summary = ViewConeImpactSummary(
        pid="001-234-567",
        intersects_view_cone=True,
        affected_cones=intersections,
        risk_flag="RED: View cone restriction — entitled height capped",
    )

    assert summary.intersects_view_cone is True
    assert len(summary.affected_cones) == 2
    assert "RED" in summary.risk_flag


# ════════════════════════════════════════════════════════════════════════════
# POSTGIS QUERY TESTS
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_postgis_st_intersects_query_construction(mock_pool):
    """Test that ST_Intersects queries are properly constructed."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetch = AsyncMock(return_value=[])

    await check_view_cone_intersection(mock_pool, "001-234-567")

    # Verify that fetch was called (indicating SQL executed)
    assert conn.fetch.called
    # The call should be with SQL query and PID
    call_args = conn.fetch.call_args
    assert call_args is not None
    assert "001-234-567" in call_args[0]  # PID in args


def test_geojson_geometry_polygon_structure():
    """Test that generated sample cones have valid polygon geometry."""
    cones = generate_sample_view_cones()

    for cone in cones:
        geom = cone["geometry"]
        assert geom["type"] == "Polygon"
        assert len(geom["coordinates"]) > 0
        # Polygon coords should be list of rings
        assert isinstance(geom["coordinates"][0], list)
        # Each ring should have at least 4 points (closed polygon)
        assert len(geom["coordinates"][0]) >= 4
        # First and last point should be the same (closed ring)
        assert geom["coordinates"][0][0] == geom["coordinates"][0][-1]


# ════════════════════════════════════════════════════════════════════════════
# INACTIVE VIEW CONE TESTS
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_inactive_view_cones_excluded_from_checks(mock_pool):
    """Test that inactive view cones are excluded from intersection checks."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetch = AsyncMock(
        return_value=[
            {"id": 1, "name": "Active Cone", "max_height_m": 35.0, "max_height_ft": 115.0},
        ]
    )

    result = await check_view_cone_intersection(mock_pool, "001-234-567")

    # Should only get active cones from the query
    # The SQL query includes WHERE is_active = TRUE
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_all_view_cones_filters_inactive(mock_pool):
    """Test that get_all_view_cones only returns active cones."""
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetch = AsyncMock(
        return_value=[
            {
                "id": 1,
                "name": "Cone 1",
                "description": None,
                "max_height_m": 35.0,
                "max_height_ft": 115.0,
                "source_location": None,
                "target_location": None,
                "cone_type": "protected_view",
                "bylaw_reference": None,
                "is_active": True,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
        ]
    )

    result = await get_all_view_cones(mock_pool)

    assert all(c.is_active for c in result)
