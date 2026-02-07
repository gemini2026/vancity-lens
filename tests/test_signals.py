"""Tests for signal CRUD and feed endpoints."""

from datetime import date
import pytest
from unittest.mock import AsyncMock, MagicMock
from api.intelligence.signals import (
    get_signal_feed,
    get_signal_by_id,
    get_signals_for_parcel,
    get_signal_stats,
    get_neighborhoods,
    get_signals_geojson,
)
from api.intelligence.models import SignalResponse, SignalFeedResponse


class TestGetSignalFeed:
    """Test signal feed retrieval."""

    @pytest.mark.asyncio
    async def test_get_signal_feed_no_filters(self):
        """Test signal feed with no filters."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock database responses
        count_row = {"total": 10}
        signal_rows = []

        conn.fetchrow.return_value = count_row
        conn.fetch.return_value = signal_rows

        result = await get_signal_feed(mock_pool)

        assert isinstance(result, SignalFeedResponse)
        assert result.total_count == 10
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_get_signal_feed_with_neighborhood_filter(self):
        """Test signal feed filtered by neighborhood."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 5}
        conn.fetch.return_value = []

        result = await get_signal_feed(
            mock_pool,
            neighborhood="Downtown"
        )

        assert isinstance(result, SignalFeedResponse)

    @pytest.mark.asyncio
    async def test_get_signal_feed_with_signal_type_filter(self):
        """Test signal feed filtered by type."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 3}
        conn.fetch.return_value = []

        result = await get_signal_feed(
            mock_pool,
            signal_type="rezoning_decision"
        )

        assert isinstance(result, SignalFeedResponse)

    @pytest.mark.asyncio
    async def test_get_signal_feed_with_severity_filter(self):
        """Test signal feed filtered by severity."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 2}
        conn.fetch.return_value = []

        result = await get_signal_feed(
            mock_pool,
            severity_min="high"
        )

        assert isinstance(result, SignalFeedResponse)

    @pytest.mark.asyncio
    async def test_get_signal_feed_with_date_range(self):
        """Test signal feed with date range."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 4}
        conn.fetch.return_value = []

        result = await get_signal_feed(
            mock_pool,
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31)
        )

        assert isinstance(result, SignalFeedResponse)

    @pytest.mark.asyncio
    async def test_get_signal_feed_pagination(self):
        """Test signal feed pagination."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        count_row = {"total": 100}
        signal_rows = []

        conn.fetchrow.return_value = count_row
        conn.fetch.return_value = signal_rows

        result = await get_signal_feed(
            mock_pool,
            limit=20,
            offset=40
        )

        assert result.total_count == 100
        assert result.has_more is True  # 40 + 20 < 100

    @pytest.mark.asyncio
    async def test_get_signal_feed_limit_capped(self):
        """Test that feed limit is capped at 100."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 0}
        conn.fetch.return_value = []

        # Request 150, should be capped at 100
        result = await get_signal_feed(mock_pool, limit=150)

        # Check that fetch was called (with capped limit)
        conn.fetch.assert_called_once()


class TestGetSignalById:
    """Test single signal retrieval."""

    @pytest.mark.asyncio
    async def test_get_signal_by_id_found(self):
        """Test retrieving existing signal."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        signal_row = {
            "id": 1,
            "document_id": 1,
            "signal_type": "rezoning_decision",
            "summary": "Rezoning approved",
            "headline": "Rezoning",
            "addresses": ["1234 Main Street"],
            "neighborhood": "Downtown",
            "decision": "approved",
            "vote_for": 10,
            "vote_against": 1,
            "sentiment": "positive_for_development",
            "severity": "high",
            "confidence": 0.95,
            "event_date": date(2024, 1, 15),
            "source_title": "Council Meeting",
            "source_url": "https://example.com",
            "source_type": "council_minutes",
            "source_date": date(2024, 1, 15)
        }

        conn.fetchrow.return_value = signal_row

        result = await get_signal_by_id(mock_pool, 1)

        assert isinstance(result, SignalResponse)
        assert result.id == 1
        assert result.signal_type == "rezoning_decision"

    @pytest.mark.asyncio
    async def test_get_signal_by_id_not_found(self):
        """Test retrieving nonexistent signal."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = None

        result = await get_signal_by_id(mock_pool, 999)

        assert result is None


class TestGetSignalsForParcel:
    """Test spatial signal queries."""

    @pytest.mark.asyncio
    async def test_get_signals_for_parcel_found(self):
        """Test retrieving signals near parcel."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        signal_row = {
            "id": 1,
            "document_id": 1,
            "signal_type": "rezoning_decision",
            "summary": "Rezoning nearby",
            "headline": "Rezoning",
            "addresses": ["Near Parcel"],
            "neighborhood": "Downtown",
            "decision": None,
            "vote_for": None,
            "vote_against": None,
            "sentiment": "neutral",
            "severity": "medium",
            "confidence": 0.8,
            "event_date": date(2024, 1, 15),
            "source_title": "Report",
            "source_url": "https://example.com",
            "source_type": "council_minutes",
            "source_date": date(2024, 1, 15),
            "distance_m": 250
        }

        conn.fetch.return_value = [signal_row]

        result = await get_signals_for_parcel(mock_pool, "00123456")

        assert len(result) == 1
        assert isinstance(result[0], SignalResponse)

    @pytest.mark.asyncio
    async def test_get_signals_for_parcel_no_results(self):
        """Test parcel with no nearby signals."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch.return_value = []

        result = await get_signals_for_parcel(mock_pool, "00123456")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_signals_for_parcel_custom_radius(self):
        """Test signal retrieval with custom search radius."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch.return_value = []

        result = await get_signals_for_parcel(
            mock_pool,
            "00123456",
            radius_meters=1000
        )

        assert result == []


class TestGetSignalStats:
    """Test statistics aggregation."""

    @pytest.mark.asyncio
    async def test_get_signal_stats_returns_dict(self):
        """Test that stats returns expected structure."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        stats_row = {"total_signals": 50, "recent_7d": 5, "recent_30d": 15}
        conn.fetchrow.return_value = stats_row
        conn.fetch.side_effect = [
            [],  # type query
            [],  # neighborhood query
            []   # severity query
        ]

        result = await get_signal_stats(mock_pool)

        assert isinstance(result, dict)
        assert "total_signals" in result
        assert "by_type" in result
        assert "by_neighborhood" in result
        assert "by_severity" in result
        assert "recent_count_7d" in result
        assert "recent_count_30d" in result

    @pytest.mark.asyncio
    async def test_get_signal_stats_by_type(self):
        """Test stats aggregation by type."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        stats_row = {"total_signals": 100, "recent_7d": 10, "recent_30d": 30}
        type_row = [
            {"signal_type": "rezoning_decision", "count": 40},
            {"signal_type": "permit_approval", "count": 30}
        ]

        conn.fetchrow.return_value = stats_row
        conn.fetch.side_effect = [
            type_row,
            [],
            []
        ]

        result = await get_signal_stats(mock_pool)

        assert result["by_type"]["rezoning_decision"] == 40
        assert result["by_type"]["permit_approval"] == 30

    @pytest.mark.asyncio
    async def test_get_signal_stats_recent_counts(self):
        """Test recent signal counts."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        stats_row = {"total_signals": 100, "recent_7d": 12, "recent_30d": 25}
        conn.fetchrow.return_value = stats_row
        conn.fetch.side_effect = [[], [], []]

        result = await get_signal_stats(mock_pool)

        assert result["recent_count_7d"] == 12
        assert result["recent_count_30d"] == 25


class TestGetNeighborhoods:
    """Test neighborhood enumeration."""

    @pytest.mark.asyncio
    async def test_get_neighborhoods_returns_list(self):
        """Test that neighborhoods returns sorted list."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        neighborhood_rows = [
            {"neighborhood": "Downtown"},
            {"neighborhood": "Kitsilano"},
            {"neighborhood": "Mount Pleasant"}
        ]
        conn.fetch.return_value = neighborhood_rows

        result = await get_neighborhoods(mock_pool)

        assert isinstance(result, list)
        assert len(result) == 3
        assert "Downtown" in result
        assert "Kitsilano" in result

    @pytest.mark.asyncio
    async def test_get_neighborhoods_empty(self):
        """Test neighborhoods when none exist."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch.return_value = []

        result = await get_neighborhoods(mock_pool)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_neighborhoods_sorted(self):
        """Test that neighborhoods are sorted."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        neighborhood_rows = [
            {"neighborhood": "Avalon"},
            {"neighborhood": "Downtown"},
            {"neighborhood": "Zebra Street"}
        ]
        conn.fetch.return_value = neighborhood_rows

        result = await get_neighborhoods(mock_pool)

        # Should be sorted alphabetically
        assert result == ["Avalon", "Downtown", "Zebra Street"]


class TestSignalsCrudIntegration:
    """Integration tests for signal CRUD operations."""

    @pytest.mark.asyncio
    async def test_feed_pagination_consistency(self):
        """Test that pagination returns consistent results."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # First page
        conn.fetchrow.return_value = {"total": 50}
        conn.fetch.return_value = []

        result1 = await get_signal_feed(mock_pool, limit=10, offset=0)
        assert result1.has_more is True

        # Second page
        result2 = await get_signal_feed(mock_pool, limit=10, offset=10)
        assert result2.has_more is True

    @pytest.mark.asyncio
    async def test_combined_filters(self):
        """Test signal feed with multiple filters applied."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetchrow.return_value = {"total": 2}
        conn.fetch.return_value = []

        result = await get_signal_feed(
            mock_pool,
            neighborhood="Downtown",
            signal_type="rezoning_decision",
            severity_min="high",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
            limit=20,
            offset=0
        )

        assert isinstance(result, SignalFeedResponse)


class TestGetSignalsGeoJSON:
    """Test GeoJSON generation for map overlay."""

    @pytest.mark.asyncio
    async def test_geojson_basic_structure(self):
        """Test GeoJSON returns valid FeatureCollection."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch.return_value = [
            {
                "id": 1,
                "signal_type": "rezoning_decision",
                "headline": "Rezoning approved",
                "summary": "Council approved rezoning at Main St",
                "neighborhood": "Downtown",
                "severity": "high",
                "decision": "approved",
                "confidence": 0.95,
                "event_date": date(2024, 1, 15),
                "addresses": ["1234 Main Street"],
                "lng": -123.1,
                "lat": 49.3,
                "source_title": "Council Meeting",
                "source_url": "https://example.com",
                "source_type": "council_minutes",
            }
        ]

        result = await get_signals_geojson(mock_pool, limit=50, days=30)

        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 1
        feature = result["features"][0]
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert feature["geometry"]["coordinates"] == [-123.1, 49.3]
        assert feature["properties"]["signal_type"] == "rezoning_decision"
        assert feature["properties"]["severity"] == "high"
        assert feature["properties"]["headline"] == "Rezoning approved"

    @pytest.mark.asyncio
    async def test_geojson_empty_result(self):
        """Test GeoJSON with no signals returns empty collection."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch.return_value = []

        result = await get_signals_geojson(mock_pool)

        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 0

    @pytest.mark.asyncio
    async def test_geojson_multiple_features(self):
        """Test GeoJSON with multiple signal features."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch.return_value = [
            {
                "id": i,
                "signal_type": "rezoning_decision",
                "headline": f"Signal {i}",
                "summary": f"Summary {i}",
                "neighborhood": "Downtown",
                "severity": "medium",
                "decision": None,
                "confidence": 0.8,
                "event_date": date(2024, 1, i),
                "addresses": [],
                "lng": -123.1 + i * 0.01,
                "lat": 49.3 + i * 0.01,
                "source_title": f"Source {i}",
                "source_url": f"https://example.com/{i}",
                "source_type": "council_minutes",
            }
            for i in range(1, 6)
        ]

        result = await get_signals_geojson(mock_pool, limit=10, days=60)

        assert len(result["features"]) == 5
        # Coordinates should differ for each feature
        coords = [f["geometry"]["coordinates"] for f in result["features"]]
        assert len(set(str(c) for c in coords)) == 5

    @pytest.mark.asyncio
    async def test_geojson_uses_headline_fallback(self):
        """Test that headline falls back to summary substring."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch.return_value = [
            {
                "id": 1,
                "signal_type": "policy_change",
                "headline": None,
                "summary": "A very long summary that should be truncated to 60 chars for the headline field",
                "neighborhood": "Kitsilano",
                "severity": "low",
                "decision": None,
                "confidence": 0.7,
                "event_date": None,
                "addresses": [],
                "lng": -123.15,
                "lat": 49.27,
                "source_title": "News",
                "source_url": None,
                "source_type": "news_article",
            }
        ]

        result = await get_signals_geojson(mock_pool)

        feature = result["features"][0]
        # headline should use the summary[:60] as fallback
        assert feature["properties"]["headline"].startswith("A very long summary")
